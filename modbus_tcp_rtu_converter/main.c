#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <modbus.h>
#include <time.h>

#include <sys/types.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <netinet/in.h>
#include <net/if.h>
#include <arpa/inet.h>

#include <signal.h>

#include "modbus_converter_config.h"
#include "logger.h"

#include "camera_api.h"

/* Prototypes */
static void _hello_print(const char *software_name);
static void _obtain_and_copy_my_ip_to_dev_struct(void);
static void _free_all_ctx(void);
static void _free_tcp_ctx(void);
static void _free_serial_ctx(void);
static void _setup_serial_connection(void);
static void _setup_tcp_connection(void);

/* Global device struct describing all states */
typedef struct {
    modbus_converter_config_t *config;
    modbus_t *uart_ctx;
    modbus_t *tcp_ctx;
    int modbus_socket;
    int listen_socket;
    char my_ip[INET_ADDRSTRLEN];
    char host_ip[INET_ADDRSTRLEN];
    int is_my_ip_obtained;
} modbus_converter_dev_t;

static modbus_converter_dev_t modbus_converter_dev = { 0 };

int main(int argc, char *argv[])
{
    /* Log starting time */
    _hello_print(argv[0]);

    modbus_converter_dev.listen_socket = -1;
    modbus_converter_dev.modbus_socket = -1;

    /* Obtain converter configuration */
    modbus_converter_dev.config = modbus_converter_read_config();
    if (modbus_converter_dev.config == NULL) {
        logger_err_print("Unable to read modbus converter configuration. Check existance and content of file <%s>\r\n", MODBUS_CONV_CONFIG_JSON_FILE_PATH);

        #if (MODBUS_USE_DEFAULT_CONFIG_IN_CASE_OF_JSON_ERROR == 1)
            logger_info_print("Apply default configuration\r\n");
            modbus_converter_dev.config = modbus_converter_apply_default_configuration();
        #else
            exit(EXIT_FAILURE);
        #endif
    }

    _obtain_and_copy_my_ip_to_dev_struct();

    logger_info_print("uart device               - %s\r\n", modbus_converter_dev.config->uart_device_name);
    logger_info_print("uart baud                 - %d\r\n", modbus_converter_dev.config->baud);
    logger_info_print("uart parity               - %c\r\n", modbus_converter_dev.config->parity);
    logger_info_print("uart data bit             - %d\r\n", modbus_converter_dev.config->data_bit);
    logger_info_print("uart stop bit             - %d\r\n", modbus_converter_dev.config->stop_bit);
    logger_info_print("modbus port               - %d\r\n", modbus_converter_dev.config->modbus_port);
    logger_info_print("modbus TCP nc             - %d\r\n", modbus_converter_dev.config->modbus_number_of_tcp_connections);
    logger_info_print("modbus mcu slave addr     - %d\r\n", modbus_converter_dev.config->modbus_micro_slave_addr);
    logger_info_print("modbus camera slave addr  - %d\r\n", modbus_converter_dev.config->modbus_camera_slave_addr);
    logger_info_print("modbus loss connection ms - %d\r\n", modbus_converter_dev.config->modbus_loss_connection_timeout_ms);
    logger_info_print("RPI IPv4 addr             - %s\r\n", modbus_converter_dev.my_ip);

    #if (MODBUS_SUPPORT_MORE_THAN_1_TCP_CONNECTION == 0)
        if (modbus_converter_dev.config->modbus_number_of_tcp_connections > 1) {
            logger_info_print("For now only 1 tcp connection supported\r\n");
            modbus_converter_dev.config->modbus_number_of_tcp_connections = 1;
        }
    #endif

    _setup_serial_connection();
    _setup_tcp_connection();

#if (MODBUS_CONVERTER_DEBUG == 1)
    modbus_set_debug(modbus_converter_dev.uart_ctx, 1);
    modbus_set_debug(modbus_converter_dev.tcp_ctx, 1);
#endif

    int rc = 0;
    uint8_t tcp_query[MODBUS_TCP_MAX_ADU_LENGTH];
    uint8_t uart_rsp[MODBUS_RTU_MAX_ADU_LENGTH];

    uint8_t rtu_slave_addr = 0;
    uint8_t rtu_start_pos = 0;
    uint16_t rtu_length = 0;
    int mbar_header_len = 0;

    /* Main loop */
    for (;;) {
        rc = modbus_receive(modbus_converter_dev.tcp_ctx, tcp_query);
        if (rc > 0) {
            /* Parse input TCP modbus message */
            mbar_header_len = modbus_get_header_length(modbus_converter_dev.tcp_ctx);
            if (mbar_header_len < 7) { /* MBAP always = 7 bytes for TCP Modbus */
                logger_err_print("Unable to get MBAR tcp header len\r\n");
                continue;
            }

            rtu_slave_addr = tcp_query[mbar_header_len - 1];
            rtu_start_pos = mbar_header_len - 1;
            rtu_length = (((uint16_t)(tcp_query[mbar_header_len - 3] << 8)) | (tcp_query[mbar_header_len - 2]));

            logger_dbg_print("Rx common len=%d\r\n", rc);
            logger_dbg_print("RTU slave addr=%d\r\n", rtu_slave_addr);
            logger_dbg_print("RTU start pos=%d\r\n", rtu_start_pos);
            logger_dbg_print("RTU length=%d\r\n", rtu_length);

            if (rtu_slave_addr == modbus_converter_dev.config->modbus_camera_slave_addr) {
                /* Parse and execute camera comands */
                rc = camera_api_parse_and_execute_cmd(&tcp_query[rtu_start_pos]);
                if (rc < 0) {
                    unsigned int exception_code = 0;

                    switch (rc) {
                    case CAMERA_API_ERROR_ILLEGAL_FUNCTION:
                        exception_code = MODBUS_EXCEPTION_ILLEGAL_FUNCTION;
                        break;
                    case CAMERA_API_ERROR_ILLEGAL_DATA_ADDRESS:
                        exception_code = MODBUS_EXCEPTION_ILLEGAL_DATA_ADDRESS;
                        break;
                    case CAMERA_API_ERROR_ILLEGAL_DATA_VALUE:
                        exception_code = MODBUS_EXCEPTION_ILLEGAL_DATA_VALUE;
                        break;
                    default:
                        exception_code = MODBUS_EXCEPTION_NOT_DEFINED;
                        break;
                    }

                    rc = modbus_reply_exception(modbus_converter_dev.tcp_ctx, tcp_query, exception_code);
                    if (rc < 0) {
                        logger_err_print("Unably to reply TCP modbus exeption\r\n");
                    }
                } else {
                    rc = modbus_send_raw_request(modbus_converter_dev.tcp_ctx,
                                                &tcp_query[rtu_start_pos],
                                                rtu_length,
                                                (int)(((uint16_t)(tcp_query[0]) << 8) | tcp_query[1]));
                    if (rc < 0) {
                        logger_err_print("Unable to send raw request to TCP connection: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                    }
                    rc = modbus_flush(modbus_converter_dev.tcp_ctx);
                    if (rc < 0) {
                        logger_err_print("Unable to flush TCP socket: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                    }
                    #if (MODBUS_CONVERTER_DEBUG == 1)
                        fflush(stdout); /* to make available libmodbus log in journalctl */
                    #endif
                }
            } else {
                /* Send data to serial device */
                rc = modbus_send_raw_request(modbus_converter_dev.uart_ctx, &tcp_query[rtu_start_pos], rtu_length, 0);
                #if (MODBUS_CONVERTER_DEBUG == 1)
                    fflush(stdout); /* to make available libmodbus log in journalctl */
                #endif
                if (rc < 0) {
                    logger_err_print("Unable to send raw request to uart device: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                    continue;
                }

                rc = modbus_flush(modbus_converter_dev.uart_ctx);
                #if (MODBUS_CONVERTER_DEBUG == 1)
                    fflush(stdout); /* to make available libmodbus log in journalctl */
                #endif
                if (rc < 0) {
                    logger_err_print("Unable to flush to uart device: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                }

                rc = modbus_receive_confirmation(modbus_converter_dev.uart_ctx, uart_rsp);
                #if (MODBUS_CONVERTER_DEBUG == 1)
                    fflush(stdout); /* to make available libmodbus log in journalctl */
                #endif
                if (rc > 0) {
                    logger_dbg_print("Uart slave responce len = %d\r\n", rc);

                    /* Send the responce to TCP client */
                    rc = modbus_send_raw_request(modbus_converter_dev.tcp_ctx, uart_rsp, rc - 2, (int)(((uint16_t)(tcp_query[0]) << 8) | tcp_query[1]));
                    if (rc < 0) {
                        logger_err_print("Unable to send raw request to TCP connection: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                    }

                    rc = modbus_flush(modbus_converter_dev.tcp_ctx);
                    if (rc < 0) {
                        logger_err_print("Unable to flush TCP socket: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                    }

                    #if (MODBUS_CONVERTER_DEBUG == 1)
                        fflush(stdout); /* to make available libmodbus log in journalctl */
                    #endif
                } else {
                    logger_err_print("Unable to receive confirmation from uart device: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                    continue;
                }
            }
        } else {
            if (errno == ECONNRESET) { /* Host has closed tcp connection */
                logger_err_print("TCP connection closed by the client or error: errno=%d --> %s. Try again...\r\n", errno, modbus_strerror(errno));
                _free_tcp_ctx();
                _setup_tcp_connection();
            } else { /* Error has occured during tcp receiving */
                logger_err_print("Error has occured during TCP receiving: errno=%d --> %s\r\n", errno, modbus_strerror(errno));
                continue;
            }
        }
    }
}

static void _hello_print(const char *software_name)
{
    time_t ltime = 0;

    time(&ltime);
    logger_info_print("%s service started: %s", software_name, ctime(&ltime));
}

static void _obtain_and_copy_my_ip_to_dev_struct(void)
{
    int fd = 0;
    int ret = 0;
    struct ifreq ifr = { 0 };
    char *ip = NULL;

    memcmp(modbus_converter_dev.my_ip, "00.00.00.00", 12);
    modbus_converter_dev.is_my_ip_obtained = 0;

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        logger_err_print("Unable to open socket to get my IP\r\n");
        return;
    }

    ifr.ifr_addr.sa_family = AF_INET;
    (void)strncpy(ifr.ifr_name, "wlan0", IFNAMSIZ-1);
    ret = ioctl(fd, SIOCGIFADDR, &ifr);
    if (ret < 0) {
        logger_err_print("Failed to fill ifreq struct with ioctl; errno=%d --> %s\r\n", errno, strerror(errno));
        close(fd);
        return;
    }

    close(fd);

    ip = inet_ntoa(((struct sockaddr_in *)&ifr.ifr_addr)->sin_addr);
    if (ip == NULL) {
        logger_err_print("Failed to convert rpi ip to sctring\r\n");
        return;
    }

    (void)strncpy(modbus_converter_dev.my_ip, ip, sizeof(modbus_converter_dev.my_ip));
    logger_dbg_print("RPI IPv4 addr=%s\r\n", modbus_converter_dev.my_ip);
    modbus_converter_dev.is_my_ip_obtained = 1;
}

static void _free_all_ctx(void)
{
    _free_tcp_ctx();
    _free_serial_ctx();
}

static void _free_tcp_ctx(void)
{
    if (modbus_converter_dev.listen_socket != -1) {
        close(modbus_converter_dev.listen_socket);
    }

    if (modbus_converter_dev.modbus_socket != -1) {
        close(modbus_converter_dev.modbus_socket);
    }

    modbus_close(modbus_converter_dev.tcp_ctx);
    modbus_free(modbus_converter_dev.tcp_ctx);
}

static void _free_serial_ctx(void)
{
    modbus_close(modbus_converter_dev.uart_ctx);
    modbus_free(modbus_converter_dev.uart_ctx);
}

static void _setup_serial_connection(void)
{
    int rc = 0;
    uint32_t timeout_s = 0;
    uint32_t timeout_us = 0;

    logger_dbg_print("Start setup serial connection...\r\n");

    if (modbus_converter_dev.config->modbus_loss_connection_timeout_ms >= 1000) {
        timeout_s = modbus_converter_dev.config->modbus_loss_connection_timeout_ms / 1000;
        timeout_us = (modbus_converter_dev.config->modbus_loss_connection_timeout_ms % 1000) * 1000;
    } else {
        timeout_s = 0;
        timeout_us = modbus_converter_dev.config->modbus_loss_connection_timeout_ms * 1000;
    }

    /*
     * CREATE and SETUP context for SERIAL device.
     *
     * Slave address must be set:
     * Client is called master in Modbus terminology, the program will send requests to servers to read or write data
     * from them. Before issuing the requests, we should define the slave ID of the remote device with modbus_set_slave.
     * 
     * So the remotely connected mcu (serial microcontroller) is a server(slave). We are a client(master).
     */
    modbus_converter_dev.uart_ctx = modbus_new_rtu(modbus_converter_dev.config->uart_device_name,
                                                   modbus_converter_dev.config->baud,
                                                   modbus_converter_dev.config->parity,
                                                   modbus_converter_dev.config->data_bit,
                                                   modbus_converter_dev.config->stop_bit);
    if (modbus_converter_dev.uart_ctx == NULL) {
        logger_err_print("Unable to create the libmodbus context for uard device %d. %s\r\n", modbus_converter_dev.config->uart_device_name, modbus_strerror(errno));
        exit(EXIT_FAILURE);
    }

    rc = modbus_set_response_timeout(modbus_converter_dev.uart_ctx, timeout_s, timeout_us);
    if (rc < 0) {
        logger_err_print("Unable to setup response timeout for serial device: %s\r\n", modbus_strerror(errno));
        _free_serial_ctx();
        exit(EXIT_FAILURE);
    }

    rc = modbus_set_slave(modbus_converter_dev.uart_ctx,
                          modbus_converter_dev.config->modbus_micro_slave_addr);
    if (rc < 0) {
        logger_err_print("Invalid slave ID (%d) for serial device. %s\r\n", modbus_converter_dev.config->modbus_micro_slave_addr, modbus_strerror(errno));
        _free_serial_ctx();
        exit(EXIT_FAILURE);
    }

    rc = modbus_connect(modbus_converter_dev.uart_ctx);
//    if (rc < 0) {
//        logger_err_print("Connection to serial device %s failed: %s\r\n", modbus_converter_dev.config->uart_device_name, modbus_strerror(errno));
//        _free_serial_ctx();
//        exit(EXIT_FAILURE);
//    }

    logger_info_print("Serial connection has been established successfully\r\n");
}

static void _setup_tcp_connection(void)
{
    int rc = 0;
    char *ip = NULL;

    logger_dbg_print("Wait for host TCP connection request...\r\n");

    /*
     * CREATE and SETUP context for TCP server device(slave).
     * In case of TCP we are a slave device.
     * Modbus poll will connect to us and send queries.
     */
    modbus_converter_dev.tcp_ctx = modbus_new_tcp((modbus_converter_dev.is_my_ip_obtained) ? modbus_converter_dev.my_ip : NULL,
                                                  modbus_converter_dev.config->modbus_port);
    if (modbus_converter_dev.tcp_ctx == NULL) {
        logger_err_print("Unable to create the libmodbus context for TCP connection %s:%d. %s\r\n", modbus_converter_dev.my_ip, modbus_converter_dev.config->modbus_port, modbus_strerror(errno));
        _free_serial_ctx();
        exit(EXIT_FAILURE);
    }

    modbus_set_indication_timeout(modbus_converter_dev.tcp_ctx, 0, 0); /* wait for connection or indication forever */

    rc = modbus_set_slave(modbus_converter_dev.tcp_ctx, MODBUS_TCP_SLAVE);
    if (rc < 0) {
        logger_err_print("Unable to set TCP slave. %s\r\n", modbus_strerror(errno));
        _free_all_ctx();
        exit(EXIT_FAILURE);
    }

    rc = modbus_tcp_listen(modbus_converter_dev.tcp_ctx,
                           modbus_converter_dev.config->modbus_number_of_tcp_connections);
    if (rc < 0) {
        logger_err_print("Unable to create TCP socket on %s:%d. %s\r\n", modbus_converter_dev.my_ip, modbus_converter_dev.config->modbus_port, modbus_strerror(errno));
        _free_all_ctx();
        exit(EXIT_FAILURE);
    }

    modbus_converter_dev.listen_socket = rc;
    logger_dbg_print("TCP listen socket=%d\r\n", modbus_converter_dev.listen_socket);

    rc = modbus_tcp_accept(modbus_converter_dev.tcp_ctx, &modbus_converter_dev.listen_socket);
    if (rc < 0) {
        logger_err_print("Unable to accept TCP connection: %s\r\n",  modbus_strerror(errno));
        _free_all_ctx();
        exit(EXIT_FAILURE);
    }

    struct sockaddr_in addr = { 0 };
    socklen_t addr_size = sizeof(struct sockaddr_in);

    modbus_converter_dev.modbus_socket = rc;
    logger_dbg_print("TCP modbus socket=%d\r\n", modbus_converter_dev.modbus_socket);

    rc = getpeername(modbus_converter_dev.modbus_socket, (struct sockaddr *)&addr, &addr_size);
    if (rc < 0) {
        logger_err_print("Failed to get connected peer name; errno=%d --> %s\r\n", errno, strerror(errno));
    } else {
        ip = inet_ntoa(addr.sin_addr);
        if (ip == NULL) {
            logger_err_print("Failed to convert host ip to sctring\r\n");
        } else {
            (void)strncpy(modbus_converter_dev.host_ip, ip, sizeof(modbus_converter_dev.host_ip));

            #if (MODBUS_CONVERTER_UPDATE_HOST_IP_CONFIG == 1)
                camera_api_setup_host_ip_config(modbus_converter_dev.host_ip);
            #endif
        }
    }

    logger_info_print("TCP connection has been established successfully; Host IPv4 addr=%s\r\n", modbus_converter_dev.host_ip);
}

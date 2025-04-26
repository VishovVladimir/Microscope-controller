import pymodbus.client as ModbusClient
from pymodbus import (
    ExceptionResponse,
    Framer,
    ModbusException,
    pymodbus_apply_logging_config,
)
from pymodbus.framer.socket_framer import ModbusSocketFramer

from time import sleep
import helpers as helper
import config_reader as conf_reader
import logging

class ModbusMicroscope:
    def __init__(self):
        self.cur_pwm_duty = 0
        self.last_bat_level = 0
        self.debug = False

        self.ip = helper.get_my_ip()
        self.port = conf_reader.get_modbus_tcp_rtu_converter_port()
        self.timeout = conf_reader.get_modbus_slave_timeout()
        self.slave_addr = conf_reader.get_modbus_slave_id()
        logging.info('Modbus TCP/RTU converter is running on {}:{}, stm32 slave addr={}, timeout={}s'.format(self.ip, self.port, self.slave_addr, self.timeout))

        # connect to Modbus TCP/RTU converter
        self.clinet = ModbusClient.ModbusTcpClient(
                            host=self.ip,
                            port=self.port,
                            framer=ModbusSocketFramer,
                            timeout=self.timeout)
        self.clinet.connect()
        assert self.clinet.connected
        if self.clinet.connected == True:
            logging.info('Connected to Modbus TCP/RTU client OK')
        else:
            logging.error('Connected to Modbus TCP/RTU client FAILED')

    def get_bat_level(self):
        logging.debug("Obtained request to retrieve battery level")
        try:
            response = self.clinet.read_holding_registers(17, 1, slave=self.slave_addr)
        except ModbusException as exc:
            logging.error(f"(Read battery level) --> Received ModbusException({exc}) from library")
            return self.last_bat_level

        if response.isError():
            logging.error(f"(Read battery level) --> Received Modbus library error({response})")
            return self.last_bat_level
        elif isinstance(response, ExceptionResponse): # THIS IS NOT A PYTHON EXCEPTION, but a valid modbus message
            logging.error(f"(Read battery level) --> Received Modbus library exception ({response})")
            return self.last_bat_level
        else:
            self.last_bat_level = int(response.registers[0])

        logging.debug('BAT level = {}%'.format(self.last_bat_level))
        return self.last_bat_level

    def focus_motor_control(self, level, retention):
        logging.debug("Obtained request to focus " + level)

        step_size_positive = 0
        step_size_negative = 0

        if retention == "no":
            step_size_positive = 1
            step_size_negative = (-1) & 0xffff
        elif retention == "released":
            step_size_positive = 0
            step_size_negative = 0
            logging.debug("0 STEPS! 0 STEPS! 0 STEPS!")
        elif retention == "yes":
            step_size_positive = abs(conf_reader.get_step_size_for_focus_stepper())
            step_size_negative = (step_size_positive * (-1)) & 0xffff

        logging.debug("step_size_positive = {}".format(step_size_positive))
        logging.debug("step_size_negative = {}".format(step_size_negative))

        if level == "upper":
            self.clinet.write_register(12, step_size_positive, slave=self.slave_addr)
        elif level == "lower":
            self.clinet.write_register(12, step_size_negative, slave=self.slave_addr)
        else:
            logging.error("wrong cmd")
        sleep(0.001)

        # Send 0 steps to disable engine after click
        if retention == "no":
            # self.clinet.write_register(12, 0, slave=self.slave_addr)
            sleep(0.02)


    def light_control(self, level):
        logging.debug("Obtained request to make light " + level)
        MAX_PWM_DUTY = conf_reader.get_led_pwm_max_power()

        if level == "upper":
            self.cur_pwm_duty += 1
            if self.cur_pwm_duty > MAX_PWM_DUTY:
                self.cur_pwm_duty = MAX_PWM_DUTY
            self.clinet.write_register(14, self.cur_pwm_duty, slave=self.slave_addr)
        elif level == "lower":
            if self.cur_pwm_duty > 0:
                self.cur_pwm_duty -= 1
            self.clinet.write_register(14, self.cur_pwm_duty, slave=self.slave_addr)
        else:
            logging.error("wrong cmd")

        logging.debug("Light PWM=%d%% %s\n" % (self.cur_pwm_duty, "(MAX)" if self.cur_pwm_duty >= MAX_PWM_DUTY else ""))

    def main_motors_control(self, position, retention):
        logging.debug("Obtained request to move motors to " + position)
        # Swap up and left AND right and down?
        swap = conf_reader.get_swap()

        # 2  - up\down addr
        # 4  - left\right
        # 12 - focus

        # Swap INdependent functions
        if position == "STOP":
            self.clinet.write_register(33, 1, slave=self.slave_addr)
        else:
            step_size_positive = 0
            step_size_negative = 0

            if retention == "no":
                step_size_positive = 1
                step_size_negative = (-1) & 0xffff
            elif retention == "released":
                step_size_positive = 0
                step_size_negative = 0
                logging.debug("0 STEPS! 0 STEPS! 0 STEPS!")
            elif retention == "yes":
                if position == "up" or position == "down":
                    step_size_positive = abs(conf_reader.get_step_size_for_updown_stepper())
                    step_size_negative = (step_size_positive * (-1)) & 0xffff
                elif position == "right" or position == "left":
                    step_size_positive = abs(conf_reader.get_step_size_for_leftright_stepper())
                    step_size_negative = (step_size_positive * (-1)) & 0xffff

            logging.debug("step_size_positive = {}".format(step_size_positive))
            logging.debug("step_size_negative = {}".format(step_size_negative))

            # Swap dependent functions
            if swap == "no":
                if position == "up":
                    self.clinet.write_register(2, step_size_positive, slave=self.slave_addr)
                elif position == "down":
                    self.clinet.write_register(2, step_size_negative, slave=self.slave_addr)
                elif position == "right":
                    self.clinet.write_register(4, step_size_positive, slave=self.slave_addr)
                elif position == "left":
                    self.clinet.write_register(4, step_size_negative, slave=self.slave_addr)
                elif position == "HOME" or position == "WORK":
                    if position == "WORK":
                        updown_steps = conf_reader.get_work_btn_updown_stepper_default_steps()
                        leftright_steps = conf_reader.get_work_btn_leftright_stepper_default_steps()
                        focus_steps = conf_reader.get_work_btn_focus_stepper_default_steps()
                    elif position == "HOME":
                        updown_steps = conf_reader.get_home_btn_updown_stepper_default_steps()
                        leftright_steps = conf_reader.get_home_btn_leftright_stepper_default_steps()
                        focus_steps = conf_reader.get_home_btn_focus_stepper_default_steps()

                    if updown_steps != 0:
                        if updown_steps < 0:
                            updown_steps &= 0xffff
                        self.clinet.write_register(2, updown_steps, slave=self.slave_addr)
                        sleep(0.02)

                    if leftright_steps != 0:
                        if leftright_steps < 0:
                            leftright_steps &= 0xffff
                        self.clinet.write_register(4, leftright_steps, slave=self.slave_addr)
                        sleep(0.02)

                    if focus_steps != 0:
                        if focus_steps < 0:
                            focus_steps &= 0xffff
                        self.clinet.write_register(12, focus_steps, slave=self.slave_addr)
                else:
                    logging.error("Unknown command for motors")
            elif swap == "yes":
                if position == "up":
                    self.clinet.write_register(4, step_size_negative, slave=self.slave_addr)
                elif position == "down":
                    self.clinet.write_register(4, step_size_positive, slave=self.slave_addr)
                elif position == "right":
                    self.clinet.write_register(2, step_size_negative, slave=self.slave_addr)
                elif position == "left":
                    self.clinet.write_register(2, step_size_positive, slave=self.slave_addr)
                elif position == "HOME" or position == "WORK":
                    if position == "WORK":
                        updown_steps = conf_reader.get_work_btn_updown_stepper_default_steps()
                        leftright_steps = conf_reader.get_work_btn_leftright_stepper_default_steps()
                        focus_steps = conf_reader.get_work_btn_focus_stepper_default_steps()
                    elif position == "HOME":
                        updown_steps = conf_reader.get_home_btn_updown_stepper_default_steps()
                        leftright_steps = conf_reader.get_home_btn_leftright_stepper_default_steps()
                        focus_steps = conf_reader.get_home_btn_focus_stepper_default_steps()

                    if updown_steps != 0:
                        if updown_steps < 0:
                            updown_steps &= 0xffff
                        self.clinet.write_register(4, updown_steps, slave=self.slave_addr)
                        sleep(0.02)

                    if leftright_steps != 0:
                        if leftright_steps < 0:
                            leftright_steps &= 0xffff
                        self.clinet.write_register(2, leftright_steps, slave=self.slave_addr)
                        sleep(0.02)

                    if focus_steps != 0:
                        if focus_steps < 0:
                            focus_steps &= 0xffff
                        self.clinet.write_register(12, focus_steps, slave=self.slave_addr)
                else:
                    logging.error("Unknown command for motors")
            else:
                logging.error("Unknown swap value in config file")

        sleep(0.02)

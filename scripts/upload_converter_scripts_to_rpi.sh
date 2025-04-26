#!/bin/sh
microscope_contoller_scr_dir=Microscope-controller
scripts_dir=$microscope_contoller_scr_dir/scripts

rpi_user=pi
rpi_ip=192.168.1.55

# Create environment on RPI before copying
cd ..
ssh $rpi_user@$rpi_ip "cd ~;mkdir -p $scripts_dir;" 

# Send scripts for make install/uninstall targets
scp -r $scripts_dir/*.sh $rpi_user@$rpi_ip:/home/pi/$scripts_dir
scp $scripts_dir/../update.sh $rpi_user@$rpi_ip:/home/pi/$scripts_dir/../

ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/rpi_get_throttling_state.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/stop_service_if_running.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/update_host_ip_for_video_streaming.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/rpi_launch_udp_4k_soft_h264.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/rpi_launch_udp_1080p_mjpg.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/rpi_stop_video_stream.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/rpi_record_video_clips.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/check_config_exists.sh"
ssh $rpi_user@$rpi_ip "chmod +x $scripts_dir/../update.sh"

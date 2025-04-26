import re
import subprocess
import logging
from time import sleep
import threading
import os


class VideoStreamer:
    # Stop gstreamer and v4l2 if running
    STOP_STREAM_SCRIPT_FILE_PATH="/home/pi/.microscope/scripts/rpi_stop_video_stream.sh"

    # Set resolution
    SET_RES_1920X1080_SCRIPT_FILE_PATH="/home/pi/.microscope/web_server/stream_scripts/camera_set_resolution_1920x1080.sh"
    SET_RES_4k_SCRIPT_FILE_PATH="/home/pi/.microscope/web_server/stream_scripts/camera_set_resolution_4k.sh"

    # Get exactly one frame
    GET_JPEG_IMG_FRAME_SCRIPT_FILE_PATH="/home/pi/.microscope/web_server/stream_scripts/camera_capture_one_image_frame.sh"

    # Get frames in continuously mode (for threading)
    START_JPEG_IMG_FRAME_CONTINUOUSLY_SCRIPT_FILE_PATH="/home/pi/.microscope/web_server/stream_scripts/camera_capture_frames_continuously.sh"

    # Record video clips
    RECORD_VIDEO_CLIPS_SCRIPT_FILE_PATH="/home/pi/.microscope/scripts/rpi_record_video_clips.sh"

    is_stream_started_flag = False
    is_stop_pending_flag = False
    is_stop_done_flag = False
    is_recording_active = False

    last_captured_frame = b''

    current_width = "1920"
    current_height = "1080"
    current_framerate = "30"

    # Lock to access self.last_captured_frame
    mutex = threading.Lock()

    # Recording process
    recording_process = None


    def __init__(self):
        subprocess.call(self.STOP_STREAM_SCRIPT_FILE_PATH)
        #subprocess.call(self.SET_RES_1920X1080_SCRIPT_FILE_PATH)
        self.cam_device_connected()

    def cam_device_connected(self):
        device_re = re.compile(b"Bus\s+(?P<bus>\d+)\s+Device\s+(?P<device>\d+).+ID\s(?P<id>\w+:\w+)\s(?P<tag>.+)$", re.I)
        df = subprocess.check_output("lsusb")
        devices = []
        for i in df.split(b'\n'):
            if i:
                info = device_re.match(i)
                if info:
                    dinfo = info.groupdict()
                    dinfo['device'] = '/dev/bus/usb/%s/%s' % (dinfo.pop('bus'), dinfo.pop('device'))
                    devices.append(dinfo)

        if str(devices).find("16MP Camera Mamufacture 16MP USB Camera") == -1:
            logging.info("USB Camera not found")
        else:
            logging.info("USB CAMERA CONNECTED")

            self.pipe = subprocess.Popen([self.START_JPEG_IMG_FRAME_CONTINUOUSLY_SCRIPT_FILE_PATH, self.current_width, self.current_height, self.current_framerate], stdout=subprocess.PIPE, bufsize=-1)
            logging.info("Start read stdout from Gstreamer")

            self.thread = threading.Thread(target=self.mjpg_frames_fetcher, args=())
            self.thread.start()
            self.is_stream_started_flag = True
            self.is_stop_done_flag = False
            self.is_stop_pending_flag = False
            logging.info("Create new mjpg fetcher thread")


    def cam_device_disconnected(self):
        device_re = re.compile(b"Bus\s+(?P<bus>\d+)\s+Device\s+(?P<device>\d+).+ID\s(?P<id>\w+:\w+)\s(?P<tag>.+)$", re.I)
        df = subprocess.check_output("lsusb")
        devices = []
        for i in df.split(b'\n'):
            if i:
                info = device_re.match(i)
                if info:
                    dinfo = info.groupdict()
                    dinfo['device'] = '/dev/bus/usb/%s/%s' % (dinfo.pop('bus'), dinfo.pop('device'))
                    devices.append(dinfo)

        if str(devices).find("16MP Camera Mamufacture 16MP USB Camera") == -1:
            # Stop recording if active
            if self.is_recording_active:
                self.stop_recording()

            subprocess.call(self.STOP_STREAM_SCRIPT_FILE_PATH)
            self.request_to_stop_mjpg_fetcher()
            self.wait_stopping()
            logging.info("USB CAMERA HAS BEEN DISCONNECTED")
        else:
            logging.info("USB camera is still connected")


    def mjpg_frames_fetcher(self):
        bytes = b''
        while True:
            part = self.pipe.stdout.read(10000)
            bytes += part
            a = bytes.find(b'\xff\xd8')
            b = bytes.find(b'\xff\xd9')
            if a != -1 and b != -1:
                self.mutex.acquire()
                self.last_captured_frame = bytes[a:b+2]
                self.mutex.release()
                bytes = bytes[b+2:]

            if self.is_stop_pending_flag:
                self.is_stop_done_flag = True
                self.is_stream_started_flag = False
                self.is_stop_pending_flag = False
                logging.info("Video fetcher has been stopped")
                break


    def request_to_stop_mjpg_fetcher(self):
        self.is_stop_pending_flag = True
        self.is_stop_done_flag = False
        logging.debug("Video streaming request to stop mjpg fetcher thread..")


    def wait_stopping(self):
        stop_iter = 0
        logging.debug("Video streaming waiting stop.....")
        if self.is_stream_started_flag:
            while self.is_stop_done_flag == False:
                sleep(0.1)
                stop_iter += 1
                if stop_iter >= 40: # 4sec
                    break
            sleep(0.5)
        logging.debug("Video streaming waiting stop done")


    def set_resolution(self, resolution):
        if resolution == "1080p" and self.current_width == "1920" or resolution == "4k" and self.current_width == "4656":
            logging.info("Requested resolution {} had already been set previously".format(resolution))
            return
        else:
            logging.info("Video streamer obtained request to change stream resolution to " + resolution)

        # Remember if recording was active
        was_recording = self.is_recording_active

        # Stop recording if active
        if was_recording:
            self.stop_recording()

        subprocess.call(self.STOP_STREAM_SCRIPT_FILE_PATH)
        self.request_to_stop_mjpg_fetcher()
        self.wait_stopping()

        if resolution == "1080p":
            subprocess.call(self.SET_RES_1920X1080_SCRIPT_FILE_PATH)
            self.current_width = "1920"
            self.current_height = "1080"
            self.current_framerate = "30"
        elif resolution == "4k":
            subprocess.call(self.SET_RES_4k_SCRIPT_FILE_PATH)
            self.current_width = "4656"
            self.current_height = "3496"
            self.current_framerate = "10"
        else:
            logging.error("Video streamer wrong command to set resolution")
            return

        # Create pipe and thread again
        self.pipe = subprocess.Popen([self.START_JPEG_IMG_FRAME_CONTINUOUSLY_SCRIPT_FILE_PATH, self.current_width, self.current_height, self.current_framerate], stdout=subprocess.PIPE, bufsize=10**8)
        self.thread = threading.Thread(target=self.mjpg_frames_fetcher, args=())
        self.thread.start()
        logging.info("Start video fetching and streaming")
        self.is_stream_started_flag = True
        self.is_stop_done_flag = False
        self.is_stop_pending_flag = False

        # Restart recording if it was active
        if was_recording:
            self.start_recording()

    def capture_frame(self):
        self.mutex.acquire()
        frame = self.last_captured_frame
        self.mutex.release()

        return frame

    def start_recording(self):
        """Start recording 1-minute video clips if not already recording"""
        if not self.is_recording_active:
            # Create the saved-video directory if it doesn't exist
            os.makedirs(os.path.expanduser("~/saved-video"), exist_ok=True)

            # Start a new thread to handle recording without interfering with streaming
            self.recording_thread = threading.Thread(target=self._record_from_stream, args=())
            self.recording_thread.daemon = True
            self.recording_thread.start()

            self.is_recording_active = True
            logging.info("Started recording 1-minute video clips to ~/saved-video/")
        else:
            logging.info("Recording is already active")

    def _record_from_stream(self):
        """Record video clips using frames from the streaming process"""
        import cv2
        import numpy as np
        from datetime import datetime

        # Initialize variables for recording
        frame_count = 0
        frames_per_clip = int(self.current_framerate) * 60  # 1 minute of frames

        while self.is_recording_active:
            try:
                # Get the latest frame from the streaming process
                jpeg_frame = self.capture_frame()

                if not jpeg_frame:
                    sleep(0.01)  # Short sleep if no frame is available
                    continue

                # If this is the first frame of a new clip, initialize the video writer
                if frame_count == 0:
                    # Generate filename with current date and time
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = os.path.expanduser(f"~/saved-video/video_{timestamp}.mp4")

                    # Decode JPEG frame to get dimensions
                    nparr = np.frombuffer(jpeg_frame, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    height, width = img.shape[:2]

                    # Initialize video writer
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    out = cv2.VideoWriter(filename, fourcc, float(self.current_framerate), (width, height))
                    logging.info(f"Started recording clip: {filename}")

                # Decode and write the frame
                nparr = np.frombuffer(jpeg_frame, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                out.write(img)

                frame_count += 1

                # If we've recorded enough frames for a clip, finalize it and start a new one
                if frame_count >= frames_per_clip:
                    out.release()
                    logging.info(f"Completed recording clip: {filename}")
                    frame_count = 0  # Reset for next clip

                sleep(1.0 / float(self.current_framerate))  # Sleep to match framerate

            except Exception as e:
                logging.error(f"Error in recording thread: {str(e)}")
                sleep(1)  # Sleep longer on error

        # Ensure the video writer is released when recording stops
        if frame_count > 0 and 'out' in locals():
            out.release()
            logging.info(f"Completed final recording clip: {filename}")

    def stop_recording(self):
        """Stop recording if currently recording"""
        if self.is_recording_active:
            # Set the flag to stop the recording thread
            self.is_recording_active = False

            # Wait for the recording thread to finish (with timeout)
            if hasattr(self, 'recording_thread') and self.recording_thread.is_alive():
                self.recording_thread.join(timeout=3.0)

            logging.info("Stopped recording video clips")
        else:
            logging.info("No active recording to stop")

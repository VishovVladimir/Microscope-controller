#!/bin/sh

# This script records 1-minute video clips from the camera and saves them to ~/saved-video/
# It uses the current date and time to create unique filenames for each clip
# This version uses a tee element to allow simultaneous streaming and recording

# Create the saved-video directory if it doesn't exist
mkdir -p ~/saved-video

# Get the first video device
video=$(ls /sys/class/video4linux -1 | head -n1)

# Set the video format to MJPG with the specified resolution and framerate
# $1 - width (default: 1920)
# $2 - height (default: 1080)
# $3 - framerate (default: 30)
width=${1:-1920}
height=${2:-1080}
framerate=${3:-30}

# Start recording 1-minute clips in a loop
while true; do
    # Generate filename with current date and time
    filename=~/saved-video/video_$(date +%Y%m%d_%H%M%S).mp4

    # Record a 1-minute clip using a tee element to split the stream
    # This allows the camera to be shared between streaming and recording
    gst-launch-1.0 -v --eos-on-shutdown v4l2src device=/dev/$video io-mode=4 ! \
        image/jpeg,width=$width,height=$height,type=video,framerate=$framerate/1 ! \
        tee name=t ! queue ! \
        jpegdec ! videoconvert ! x264enc ! mp4mux ! \
        filesink location=$filename \
        t. ! queue ! fakesink sync=false > /dev/null

    # Log the recording
    echo "Recorded video clip: $filename"
done

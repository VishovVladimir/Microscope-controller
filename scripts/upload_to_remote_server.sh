#!/bin/bash

SAVE_DIR="/home/pi/saved-video"
LOG_FILE="$SAVE_DIR/video_log.txt"
REMOTE_USER="isaiya"
REMOTE_HOST="164.90.187.105"
REMOTE_DIR="/home/isaiya/recorded_video"

# Check if log file exists
if [ ! -f "$LOG_FILE" ]; then
    echo "No video_log.txt found, exiting."
    exit 0
fi

# Read filenames line-by-line
while IFS= read -r filename; do
    # Full local path
    LOCAL_FILE="$SAVE_DIR/$filename"

    # Check if file actually exists
    if [ -f "$LOCAL_FILE" ]; then
        echo "Uploading $filename..."
        scp "$LOCAL_FILE" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"

        if [ $? -eq 0 ]; then
            echo "Upload successful, deleting $filename"
            rm "$LOCAL_FILE"
        else
            echo "Upload failed for $filename, skipping delete."
        fi
    else
        echo "File $filename not found, skipping."
    fi
done < "$LOG_FILE"

# After uploading all, clear the log file
> "$LOG_FILE"

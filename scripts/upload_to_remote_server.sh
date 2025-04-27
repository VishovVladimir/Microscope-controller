#!/bin/bash

SAVE_DIR="/home/pi/saved-video"
LOG_FILE="$SAVE_DIR/video_log.txt"
REMOTE_USER="isaiya"
REMOTE_HOST="164.90.187.105"
REMOTE_DIR="/home/isaiya/recorded_video"

# Make sure video_log.txt exists
if [ ! -f "$LOG_FILE" ]; then
    echo "No video_log.txt found, exiting."
    exit 0
fi

# Build a list of completed filenames
declare -A completed_files
while IFS= read -r line || [ -n "$line" ]; do
    completed_files["$line"]=1
done < "$LOG_FILE"

# Go through all files in saved-video
for filepath in "$SAVE_DIR"/*; do
    filename=$(basename "$filepath")

    # Check if filename is in completed list
    if [[ -n "${completed_files[$filename]}" && -f "$filepath" ]]; then
        echo "Uploading $filename via rsync..."

        rsync -avz --remove-source-files "$filepath" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"

        if [ $? -eq 0 ]; then
            echo "Upload and delete success: $filename"
        else
            echo "Upload failed: $filename"
        fi
    else
        echo "Skipping $filename, not in completed list."
    fi
done

echo "Upload finished."

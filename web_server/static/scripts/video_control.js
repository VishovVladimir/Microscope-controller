function video_switch_resolution(new_res) {
    var request = new XMLHttpRequest()

    request.onload = function() {
        if (request.response == "OK") {
            if (new_res == "1080p") {
                console.log("Stream resolution has been changed to 1080p");
                document.querySelector(".video-stream-mode-text").innerHTML = "Video: <span style=\"color:DodgerBlue\">1080p</span>";
            } else if (new_res == "4k") {
                console.log("Stream resolution has been changed to 4k");
                document.querySelector(".video-stream-mode-text").innerHTML = "Video: <span style=\"color:DodgerBlue\">4k</span>";
            }
        } else {
            console.log("[ERR] stream resolution changing HTTP response != OK");
            document.querySelector(".video-stream-mode-text").innerHTML = "Video: <span style=\"color:Tomato\">unavailable</span>";
        }
    }

    // Send a request
    request.responseType = 'json';
    request.open("GET", "/video_control?new_res=" + new_res, true);
    request.send();
}

function video_recording_control(action) {
    var request = new XMLHttpRequest()

    request.onload = function() {
        if (request.response == "OK") {
            if (action == "start") {
                console.log("Video recording started");
                document.getElementById("start-recording-btn").classList.remove("btn-outline-danger");
                document.getElementById("start-recording-btn").classList.add("btn-danger");
                document.getElementById("stop-recording-btn").classList.remove("btn-outline-secondary");
                document.getElementById("stop-recording-btn").classList.add("btn-outline-secondary");
            } else if (action == "stop") {
                console.log("Video recording stopped");
                document.getElementById("start-recording-btn").classList.remove("btn-danger");
                document.getElementById("start-recording-btn").classList.add("btn-outline-danger");
                document.getElementById("stop-recording-btn").classList.remove("btn-outline-secondary");
                document.getElementById("stop-recording-btn").classList.add("btn-secondary");
                setTimeout(function() {
                    document.getElementById("stop-recording-btn").classList.remove("btn-secondary");
                    document.getElementById("stop-recording-btn").classList.add("btn-outline-secondary");
                }, 1000);
            }
        } else {
            console.log("[ERR] video recording control HTTP response != OK");
        }
    }

    // Send a request
    request.responseType = 'json';
    request.open("GET", "/video_recording?action=" + action, true);
    request.send();
}

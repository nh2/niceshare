# NiceShare

GUI for gstreamer-based screen sharing.


## Running

Install wxPython, e.g. via `sudo apt install python3-wxgtk4.0`.

### GUI

```sh
python3 -m venv python3-venv
source python3-venv/bin/activate

pip install Gooey

./niceshare.py --gui
```

### CLI

When the screensharer opens the port in their firewall:

```sh
# Host a screenshare:
./niceshare.py  --screenshare-screen-0 --listen-port 5000 --fps 30 --bitrate 2048 --latency 1000

# Connect to it:
./niceshare.py --view --call localhost:5000
```

When the viewer opens the port in their firewall:

```sh
# Listen for incoming stream:
./niceshare.py --view --listen-port 5000

# Send a stream:
./niceshare.py  --screenshare-screen-0 --call localhost:5000 --fps 30 --bitrate 2048 --latency 1000
```

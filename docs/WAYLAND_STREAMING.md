# How We Made Wayland Screen Streaming Work

Hello everyone! While working on the PSP Linux Controller app, I ran into a fascinating challenge: **streaming the screen from Wayland to a phone**. Here's the journey and what I learned.

## The Problem

On X11 (the old Linux display system), screen capture was easy - any app could just grab pixels from the screen. But Wayland is different. It's designed for security, so apps **cannot** directly access screen contents. This is why tools like `scrot`, `grim`, and even `mss` (Python library) fail on GNOME Wayland with errors like:

```
XGetImage() failed
compositor doesn't support wlr-screencopy-unstable-v1
```

## What I Tried (And Why It Failed)

### 1. MSS Library (Python)
```python
import mss
sct = mss.mss()
sct.grab(sct.monitors[1])  # Fails on Wayland
```
MSS uses X11 APIs internally - doesn't work on Wayland.

### 2. grim (Wayland Screenshot Tool)
```bash
grim screenshot.png  # "compositor doesn't support wlr-screencopy"
```
`grim` uses `wlr-screencopy-unstable-v1` protocol, which only wlroots-based compositors (Sway, Hyprland) support. GNOME doesn't implement this.

### 3. wf-recorder
```bash
wf-recorder  # Same issue - needs wlr-screencopy
```

### 4. gnome-screenshot
Works on GNOME, but it's slow (1-2 seconds per capture) and not suitable for streaming.

## The Solution: XDG Desktop Portal + PipeWire

I studied **OBS Studio's source code** to understand how it captures screens on Wayland. OBS uses the same infrastructure as screen sharing in browsers and video calls.

### The Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Your Application                        │
└─────────────────────────┬───────────────────────────────────┘
                          │ D-Bus
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              XDG Desktop Portal Daemon                      │
│         (org.freedesktop.portal.ScreenCast)                 │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Desktop Environment Portal                      │
│    (xdg-desktop-portal-gnome / kde / hyprland)              │
│         Shows system permission dialog                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ User grants permission
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      PipeWire                                │
│           (Provides video stream to your app)                │
└─────────────────────────────────────────────────────────────┘
```

### The Flow (From OBS Source Code)

Looking at `plugins/linux-pipewire/screencast-portal.c`, I found the exact sequence:

1. **CreateSession** - Create a D-Bus session with the portal
2. **SelectSources** - Opens system dialog for user to pick screen/window
3. **Start** - User confirms, portal returns PipeWire node ID
4. **OpenPipeWireRemote** - Get file descriptor to read PipeWire stream
5. **GStreamer Pipeline** - Read frames from PipeWire and encode

### Python Implementation

Here's the core of what I implemented:

```python
import gi
gi.require_version('Gio', '2.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gio, GLib, Gst

# 1. Connect to D-Bus session bus
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

# 2. Call CreateSession on ScreenCast portal
connection.call(
    'org.freedesktop.portal.Desktop',
    '/org/freedesktop/portal/desktop',
    'org.freedesktop.portal.ScreenCast',
    'CreateSession',
    params,  # GLib.Variant with tokens
    ...
)

# 3. Call SelectSources - this triggers the permission dialog!
# 4. Call Start - get PipeWire node ID
# 5. Call OpenPipeWireRemote - get file descriptor

# 6. Create GStreamer pipeline to read from PipeWire
pipeline = Gst.parse_launch(
    f"pipewiresrc fd={fd} path={node_id} ! "
    f"videoconvert ! jpegenc ! appsink"
)
```

### Key Insight: User Permission is REQUIRED

On Wayland, you **cannot** silently capture the screen. The user must:
1. See a system dialog
2. Select which screen/window to share
3. Click "Share"

This is a **security feature**, not a limitation. The same reason Discord and Chrome ask for screen share permission.

## Dependencies

For this to work, you need:

```bash
# GStreamer with PipeWire support
sudo apt install python3-gi gir1.2-gst-1.0 gstreamer1.0-pipewire

# Portal backends (usually pre-installed)
# GNOME: xdg-desktop-portal-gnome
# KDE: xdg-desktop-portal-kde
```

## The Result

Now when you enable Game Stream:
1. A system dialog appears (just like OBS or Discord)
2. You select your screen
3. Frames flow via PipeWire → GStreamer → MJPEG → Phone

It's secure, performant, and works with any Wayland compositor!

## Lessons Learned

1. **Wayland security is intentional** - Apps can't spy on your screen
2. **Portals are the answer** - D-Bus portals are the standardized way to request permissions
3. **Study existing implementations** - OBS source code was invaluable
4. **GStreamer + PipeWire** - The modern Linux multimedia stack is powerful

## References

- [OBS Studio linux-pipewire plugin](https://github.com/obsproject/obs-studio/tree/master/plugins/linux-pipewire)
- [XDG Desktop Portal ScreenCast API](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
- [PipeWire Documentation](https://docs.pipewire.org/)

---

*Written while building the PSP Linux Controller project. The streaming feature lets you see your game while using your phone as a controller!*

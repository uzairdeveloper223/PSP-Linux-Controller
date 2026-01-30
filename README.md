# PSP Linux Controller

Use your Android phone as a wireless PSP controller for PPSSPP emulator on Linux.

![Android App](images/android.jpg)
![Desktop Layout Editor](images/layout_editor_linux.png)

## What It Does

This app lets you control PPSSPP running on your Linux PC using your phone as a gamepad. It connects over WiFi with very low latency (typically 1-5ms on a local network).

The controller has all the PSP buttons - D-pad, analog stick, action buttons (Triangle, Circle, Square, Cross), shoulders (L/R), and Start/Select.

There's also a desktop layout editor that lets you drag buttons around and see the changes live on your phone. Much easier than fiddling with the phone screen.

## Getting Started

### Step 1: Download

Grab the latest release from the [Releases page](../../releases):

- **PSPLinuxController-x.x.x.apk** - Install this on your Android phone
- **PSPLinuxController-Server-x.x.x.tar.gz** - Extract this on your Linux PC

### Step 2: Set Up the Server

Extract the server tarball somewhere convenient:

```bash
tar -xzf PSPLinuxController-Server-*.tar.gz
cd PSPLinuxController-Server
```

Install xdotool if you don't have it (the server uses this to simulate keyboard input):

```bash
sudo apt install xdotool
```

Start the server:

```bash
./start_server.sh
```

You'll see something like this:

```
==================================================
  PSP Controller Server
  Made by Uzair
==================================================
  Local IP:  192.168.1.100
  Port:      5555
==================================================
```

Note down that IP address - you'll need it for the phone app.

### Step 3: Install the App

Transfer the APK to your phone and install it. You might need to allow installing from unknown sources in your phone's settings.

### Step 4: Connect and Play

1. Open the app on your phone
2. Tap the Connect button and enter your PC's IP address
3. Launch PPSSPP on your PC and load a game
4. Use your phone as the controller!

## Customizing the Layout

If you want to move buttons around, use the desktop layout editor:

```bash
pip install PyQt5  # Only needed once
python3 layout_editor_gui.py
```

Drag controls to reposition them. Changes show up on your phone in real-time. Hit Save when you're happy with the layout.

The editor supports undo/redo with Ctrl+Z and Ctrl+Y.

## Default Key Bindings

These are the keyboard keys that get pressed when you tap each button:

| Button | Key |
|--------|-----|
| D-pad | Arrow Keys |
| Cross | Z |
| Circle | X |
| Square | A |
| Triangle | S |
| Start | Space |
| Select | V |
| L / R | Q / W |
| Analog | I/J/K/L |

You can change these in PPSSPP's control settings if needed.

## Troubleshooting

**Can't connect?**

Make sure your phone and PC are on the same WiFi network. You might also need to allow port 5555 through your firewall:

```bash
sudo ufw allow 5555
```

**Button presses not working?**

Make sure PPSSPP has focus (click on it). You can test if xdotool is working by running:

```bash
xdotool key z
```

## Building From Source

If you want to build the app yourself instead of using the releases:

```bash
# Build the APK
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk

# Run the server (no build needed, it's Python)
cd server
python3 psp_controller_server.py
```

## License

Apache License 2.0

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

---

Made by Uzair

# PSP Linux Controller

A wireless controller app for PPSSPP emulator on Linux. Use your Android phone as a PSP controller over WiFi.

## Features

- **Full PSP Controller Layout**: D-pad, action buttons (△, ○, □, ✕), Start/Select, L/R triggers, and analog stick
- **Low Latency**: TCP socket connection (~1-5ms on local network)
- **Connection Status**: Real-time connection indicator
- **Auto-reconnect**: Automatically saves server IP for quick reconnection
- **Fullscreen Mode**: Landscape layout with immersive controller experience

## Quick Start

### 1. Start the Server

**On Linux:**
```bash
# Install xdotool if not already installed
sudo apt install xdotool

cd server
./start_server.sh
```

**On Windows:**
```powershell
# Just run the batch file (Python required)
cd server
start_server.bat
```

The server will display your local IP address. Note this for the Android app.

### 3. Install the Android App

Build and install the APK on your Android phone:

```bash
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

### 4. Connect

1. Open the app on your phone
2. Tap "Connect"
3. Enter the IP address shown by the server
4. Tap "Connect"

### 5. Play!

1. Launch PPSSPP on your Linux machine
2. Start a game
3. Use your phone as the controller!

## Key Mapping

| PSP Button | Keyboard Key |
|------------|--------------|
| D-pad | Arrow Keys |
| ✕ | Z |
| ○ | X |
| □ | A |
| △ | S |
| Start | Space |
| Select | V |
| L Trigger | Q |
| R Trigger | W |
| Analog | I/J/K/L |

## Server Options

```bash
python3 server/psp_controller_server.py --help

Options:
  -p, --port PORT   Port to listen on (default: 5555)
  --host HOST       Host to bind to (default: 0.0.0.0)
```

## Troubleshooting

### "Connection failed" on Android

- Make sure your phone and Linux PC are on the same WiFi network
- Check that the server is running
- Verify the IP address is correct
- Check firewall settings: `sudo ufw allow 5555`

### Keys not working in PPSSPP

- Make sure PPSSPP window is focused
- Verify xdotool is installed: `which xdotool`
- Test xdotool manually: `xdotool key z`

### High latency

- Use 5GHz WiFi if available
- Reduce distance from router
- Close bandwidth-heavy apps

## Project Structure

```
PSPLinuxController/
├── server/
│   ├── psp_controller_server.py  # Python TCP server
│   ├── requirements.txt           # Dependencies
│   └── start_server.sh           # Startup script
├── app/
│   └── src/main/
│       ├── java/.../
│       │   ├── MainActivity.java     # Controller UI
│       │   ├── TcpClient.java        # TCP connection
│       │   └── ConnectionManager.java # Connection logic
│       └── res/layout/
│           └── activity_main.xml     # Controller layout
└── README.md
```

## License

Apache License 2.0

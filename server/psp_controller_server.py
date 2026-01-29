#!/usr/bin/env python3
"""
PSP Controller Server for Linux and Windows
Receives button commands from Android app and simulates keyboard input for PPSSPP.
"""

import socket
import subprocess
import json
import threading
import time
import argparse
import signal
import sys
import platform
from datetime import datetime

# Detect platform
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX = platform.system() == 'Linux'

# PPSSPP Default Key Mappings
KEY_MAP = {
    # D-pad
    "dpad_up": "Up",
    "dpad_down": "Down",
    "dpad_left": "Left",
    "dpad_right": "Right",
    
    # Action buttons
    "x": "z",
    "circle": "x",
    "square": "a",
    "triangle": "s",
    
    # System buttons
    "start": "space",
    "select": "v",
    
    # Shoulder buttons
    "l": "q",
    "r": "w",
    
    # Analog stick
    "analog_up": "i",
    "analog_down": "k",
    "analog_left": "j",
    "analog_right": "l",
}

# Windows virtual key codes mapping
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    
    # Windows Virtual Key Codes
    VK_CODES = {
        'Up': 0x26,
        'Down': 0x28,
        'Left': 0x25,
        'Right': 0x27,
        'z': 0x5A,
        'x': 0x58,
        'a': 0x41,
        's': 0x53,
        'space': 0x20,
        'v': 0x56,
        'q': 0x51,
        'w': 0x57,
        'i': 0x49,
        'j': 0x4A,
        'k': 0x4B,
        'l': 0x4C,
    }
    
    # Windows API constants
    KEYEVENTF_KEYDOWN = 0x0000
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_EXTENDEDKEY = 0x0001
    
    # Extended keys (arrow keys need this flag)
    EXTENDED_KEYS = {'Up', 'Down', 'Left', 'Right'}
    
    # Load user32.dll
    user32 = ctypes.windll.user32


class PSPControllerServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = []
        self.clients_lock = threading.Lock()
        self.ppsspp_window = None
        self.last_window_check = 0
        
    def check_dependencies(self):
        """Check if required dependencies are installed."""
        if IS_LINUX:
            return self._check_xdotool()
        elif IS_WINDOWS:
            return self._check_windows()
        else:
            print(f"ERROR: Unsupported platform: {platform.system()}")
            print("This server only supports Linux and Windows.")
            return False
    
    def _check_xdotool(self):
        """Check if xdotool is installed (Linux)."""
        try:
            result = subprocess.run(['which', 'xdotool'], 
                                    capture_output=True, text=True)
            if result.returncode != 0:
                print("ERROR: xdotool not found!")
                print("Install it with: sudo apt install xdotool")
                return False
            print(f"✓ xdotool found: {result.stdout.strip()}")
            return True
        except Exception as e:
            print(f"ERROR checking xdotool: {e}")
            return False
    
    def _check_windows(self):
        """Check Windows dependencies."""
        print("✓ Running on Windows - using native Win32 API")
        return True
    
    def find_ppsspp_window(self):
        """Find PPSSPP window. Caches result for 5 seconds."""
        now = time.time()
        if self.ppsspp_window and (now - self.last_window_check) < 5:
            return self.ppsspp_window
        
        if IS_LINUX:
            return self._find_ppsspp_linux()
        elif IS_WINDOWS:
            return self._find_ppsspp_windows()
        
        return None
    
    def _find_ppsspp_linux(self):
        """Find PPSSPP window on Linux using xdotool."""
        try:
            result = subprocess.run(
                ['xdotool', 'search', '--name', 'PPSSPP'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0 and result.stdout.strip():
                windows = result.stdout.strip().split('\n')
                self.ppsspp_window = windows[0]
                self.last_window_check = time.time()
                return self.ppsspp_window
        except:
            pass
        
        self.ppsspp_window = None
        return None
    
    def _find_ppsspp_windows(self):
        """Find PPSSPP window on Windows."""
        try:
            # Use ctypes to find window
            hwnd = user32.FindWindowW(None, None)
            
            # Enumerate windows to find PPSSPP
            def enum_callback(hwnd, results):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    if 'PPSSPP' in buff.value:
                        results.append(hwnd)
                return True
            
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            results = []
            user32.EnumWindows(WNDENUMPROC(lambda h, l: enum_callback(h, results)), 0)
            
            if results:
                self.ppsspp_window = results[0]
                self.last_window_check = time.time()
                return self.ppsspp_window
        except:
            pass
        
        self.ppsspp_window = None
        return None
    
    def simulate_key(self, key, action):
        """Simulate key press or release."""
        if IS_LINUX:
            return self._simulate_key_linux(key, action)
        elif IS_WINDOWS:
            return self._simulate_key_windows(key, action)
        return False
    
    def _simulate_key_linux(self, key, action):
        """Simulate key using xdotool on Linux."""
        try:
            window = self.find_ppsspp_window()
            
            if action == "press":
                if window:
                    subprocess.Popen(['xdotool', 'keydown', '--window', window, key], 
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(['xdotool', 'keydown', key], 
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.DEVNULL)
            elif action == "release":
                if window:
                    subprocess.Popen(['xdotool', 'keyup', '--window', window, key],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(['xdotool', 'keyup', key],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"Error simulating key {key}: {e}")
            return False
    
    def _simulate_key_windows(self, key, action):
        """Simulate key using Win32 API on Windows."""
        try:
            if key not in VK_CODES:
                print(f"Unknown key: {key}")
                return False
            
            vk_code = VK_CODES[key]
            
            # Set flags
            flags = KEYEVENTF_KEYDOWN if action == "press" else KEYEVENTF_KEYUP
            if key in EXTENDED_KEYS:
                flags |= KEYEVENTF_EXTENDEDKEY
            
            # Send the key event
            user32.keybd_event(vk_code, 0, flags, 0)
            return True
        except Exception as e:
            print(f"Error simulating key {key}: {e}")
            return False
    
    def handle_command(self, data, client_addr):
        """Process a command from the client."""
        try:
            command = json.loads(data)
            cmd_type = command.get('type')
            
            if cmd_type == 'ping':
                return json.dumps({'type': 'pong', 'timestamp': time.time()})
            
            elif cmd_type == 'button':
                button = command.get('button')
                action = command.get('action')  # 'press' or 'release'
                
                if button in KEY_MAP:
                    key = KEY_MAP[button]
                    success = self.simulate_key(key, action)
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    print(f"[{timestamp}] {client_addr[0]}: {button} -> {key} ({action})")
                    return json.dumps({'type': 'ack', 'success': success})
                else:
                    print(f"Unknown button: {button}")
                    return json.dumps({'type': 'error', 'message': f'Unknown button: {button}'})
            
            elif cmd_type == 'analog':
                x = command.get('x', 0)
                y = command.get('y', 0)
                
                # Release all analog keys first
                for key in ['i', 'k', 'j', 'l']:
                    self.simulate_key(key, 'release')
                
                # Press appropriate keys based on analog position
                threshold = 0.3
                if y < -threshold:
                    self.simulate_key('i', 'press')  # Up
                elif y > threshold:
                    self.simulate_key('k', 'press')  # Down
                    
                if x < -threshold:
                    self.simulate_key('j', 'press')  # Left
                elif x > threshold:
                    self.simulate_key('l', 'press')  # Right
                
                return json.dumps({'type': 'ack', 'success': True})
            
            else:
                return json.dumps({'type': 'error', 'message': f'Unknown command type: {cmd_type}'})
                
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return json.dumps({'type': 'error', 'message': 'Invalid JSON'})
        except Exception as e:
            print(f"Error handling command: {e}")
            return json.dumps({'type': 'error', 'message': str(e)})
    
    def handle_client(self, client_socket, client_addr):
        """Handle a connected client."""
        print(f"✓ Client connected: {client_addr[0]}:{client_addr[1]}")
        
        with self.clients_lock:
            self.clients.append(client_socket)
        
        buffer = ""
        try:
            while self.running:
                try:
                    data = client_socket.recv(1024).decode('utf-8')
                    if not data:
                        break
                    
                    buffer += data
                    
                    # Process complete messages (newline-delimited JSON)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            response = self.handle_command(line.strip(), client_addr)
                            client_socket.send((response + '\n').encode('utf-8'))
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error receiving data: {e}")
                    break
                    
        except Exception as e:
            print(f"Client handler error: {e}")
        finally:
            print(f"✗ Client disconnected: {client_addr[0]}:{client_addr[1]}")
            with self.clients_lock:
                if client_socket in self.clients:
                    self.clients.remove(client_socket)
            try:
                client_socket.close()
            except:
                pass
    
    def get_local_ip(self):
        """Get local IP address for display."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def start(self):
        """Start the server."""
        if not self.check_dependencies():
            return False
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            self.running = True
            
            local_ip = self.get_local_ip()
            os_name = "Windows" if IS_WINDOWS else "Linux"
            print("\n" + "="*50)
            print(f"  PSP Controller Server Started! ({os_name})")
            print("="*50)
            print(f"  Local IP:  {local_ip}")
            print(f"  Port:      {self.port}")
            print("="*50)
            print("  Enter this IP in your Android app to connect")
            print("="*50 + "\n")
            print("Waiting for connections... (Ctrl+C to stop)\n")
            
            while self.running:
                try:
                    client_socket, client_addr = self.server_socket.accept()
                    
                    # Reject localhost connections (likely other processes, not mobile)
                    if client_addr[0] == '127.0.0.1':
                        client_socket.close()
                        continue
                    
                    client_socket.settimeout(5.0)
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_addr),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Accept error: {e}")
                        
        except Exception as e:
            print(f"Server error: {e}")
            return False
        
        return True
    
    def stop(self):
        """Stop the server."""
        print("\nShutting down server...")
        self.running = False
        
        # Close all client connections
        with self.clients_lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients.clear()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Release all keys
        print("Releasing all keys...")
        for key in KEY_MAP.values():
            try:
                self.simulate_key(key, 'release')
            except:
                pass
        
        print("Server stopped.")


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global server
    if server:
        server.stop()
    sys.exit(0)


server = None

def main():
    global server
    
    parser = argparse.ArgumentParser(description='PSP Controller Server for PPSSPP')
    parser.add_argument('-p', '--port', type=int, default=5555,
                        help='Port to listen on (default: 5555)')
    parser.add_argument('--host', default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    args = parser.parse_args()
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server = PSPControllerServer(host=args.host, port=args.port)
    server.start()


if __name__ == '__main__':
    main()

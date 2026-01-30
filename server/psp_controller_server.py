#!/usr/bin/env python3
"""
PSP Controller Server for Linux
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
from datetime import datetime

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


class PSPControllerServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = []
        self.clients_lock = threading.Lock()
        
    def check_dependencies(self):
        """Check if xdotool is installed."""
        try:
            result = subprocess.run(['which', 'xdotool'], 
                                    capture_output=True, text=True)
            if result.returncode != 0:
                print("ERROR: xdotool not found!")
                print("Install it with: sudo apt install xdotool")
                return False
            print(f"[OK] xdotool found: {result.stdout.strip()}")
            return True
        except Exception as e:
            print(f"ERROR checking xdotool: {e}")
            return False
    
    def simulate_key(self, key, action):
        """Simulate key press or release using xdotool.
        
        Keys are sent globally so they work when PPSSPP is focused,
        including in dialogs like the control mapper.
        """
        try:
            if action == "press":
                subprocess.Popen(['xdotool', 'keydown', key], 
                                stdout=subprocess.DEVNULL, 
                                stderr=subprocess.DEVNULL)
            elif action == "release":
                subprocess.Popen(['xdotool', 'keyup', key],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"Error simulating key {key}: {e}")
            return False
    
    def handle_command(self, data, client_addr, client_socket=None):
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
            
            # Layout Editor Commands
            elif cmd_type == 'device_info':
                # Store device info from Android client
                with self.clients_lock:
                    self.device_info = {
                        'width': command.get('width', 1920),
                        'height': command.get('height', 1080),
                        'density': command.get('density', 2.75)
                    }
                    # Mark this as android client
                    if client_socket:
                        self.android_client = client_socket
                print(f"[DEVICE] Device info received: {self.device_info}")
                return json.dumps({'type': 'ack', 'success': True})
            
            elif cmd_type == 'get_device_info':
                # Desktop editor requesting device info
                if hasattr(self, 'device_info'):
                    return json.dumps({'type': 'device_info', **self.device_info})
                else:
                    return json.dumps({'type': 'device_info', 'width': 1920, 'height': 1080, 'density': 2.75})
            
            elif cmd_type == 'get_layout':
                # Desktop editor requesting current layout
                if hasattr(self, 'current_layout'):
                    return json.dumps({'type': 'layout', 'controls': self.current_layout})
                else:
                    return json.dumps({'type': 'layout', 'controls': {}})
            
            elif cmd_type == 'current_layout':
                # Android phone sent its current layout on connect
                self.current_layout = command.get('controls', {})
                print(f"[LAYOUT] Layout received from phone: {len(self.current_layout)} controls")
                return json.dumps({'type': 'ack', 'success': True})
            
            elif cmd_type == 'layout_update':
                # Android sent layout update
                self.current_layout = command.get('layout', {})
                return json.dumps({'type': 'ack', 'success': True})
            
            elif cmd_type == 'layout_preview':
                # Desktop editor sending live preview - forward to Android
                if hasattr(self, 'android_client') and self.android_client:
                    try:
                        forward_cmd = json.dumps(command) + '\n'
                        self.android_client.send(forward_cmd.encode('utf-8'))
                    except:
                        pass
                return json.dumps({'type': 'ack', 'success': True})
            
            elif cmd_type == 'set_layout':
                # Desktop editor saving layout - forward to Android
                layout = command.get('layout', {})
                self.current_layout = layout
                if hasattr(self, 'android_client') and self.android_client:
                    try:
                        forward_cmd = json.dumps({'type': 'set_layout', 'layout': layout}) + '\n'
                        self.android_client.send(forward_cmd.encode('utf-8'))
                    except:
                        pass
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
        print(f"[OK] Client connected: {client_addr[0]}:{client_addr[1]}")
        
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
                            response = self.handle_command(line.strip(), client_addr, client_socket)
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
            print("\n" + "="*50)
            print("  PSP Controller Server")
            print("  Made by Uzair")
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

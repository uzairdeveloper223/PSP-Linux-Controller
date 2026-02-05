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
import os
import select
from datetime import datetime

# For keyboard input
try:
    import termios
    import tty
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False  # Windows compatibility

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

# Import QR code library (optional)
try:
    import qrcode
    from PIL import Image
    QR_CODE_AVAILABLE = True
except ImportError:
    QR_CODE_AVAILABLE = False
    print("WARNING: qrcode and/or PIL not installed. QR code functionality disabled.")
    print("Install with: pip install qrcode[pil]")

# Import screen streamer (optional)
try:
    from screen_streamer import ScreenStreamer, STREAMING_AVAILABLE
except ImportError:
    STREAMING_AVAILABLE = False
    ScreenStreamer = None
    print("WARNING: screen_streamer module not found. Screen streaming disabled.")


class PSPControllerServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = []
        self.clients_lock = threading.Lock()
        self.qr_code_visible = False
        self.qr_process = None
        
        # Screen streaming
        self.pending_stream_client = None  # Client waiting for stream to be ready
        self.pending_stream_params = None  # Parameters for pending stream
        if STREAMING_AVAILABLE and ScreenStreamer:
            self.screen_streamer = ScreenStreamer(port=port + 1, on_ready_callback=self._on_stream_ready)
        else:
            self.screen_streamer = None
    
    def _on_stream_ready(self):
        """Called when screen stream is ready (portal permission granted)."""
        if self.pending_stream_client and self.pending_stream_params:
            local_ip = self.get_local_ip()
            stream_port = self.port + 1
            response = json.dumps({
                'type': 'stream_start',
                'url': f'http://{local_ip}:{stream_port}',
                'port': stream_port,
                'width': self.pending_stream_params['width'],
                'height': self.pending_stream_params['height']
            })
            try:
                self.pending_stream_client.sendall((response + '\n').encode('utf-8'))
                print("[STREAM] Sent stream_start to client")
            except Exception as e:
                print(f"[STREAM] Failed to notify client: {e}")
            self.pending_stream_client = None
            self.pending_stream_params = None
        
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

    def generate_qr_code(self, ip, port):
        """Generate QR code containing connection info."""
        if not QR_CODE_AVAILABLE:
            print("Cannot generate QR code: qrcode library not available")
            return None

        # Create connection string in format: ip:port
        connection_string = f"{ip}:{port}"

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(connection_string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        return img

    def show_qr_code(self):
        """Display QR code in a window."""
        if not QR_CODE_AVAILABLE:
            return False

        local_ip = self.get_local_ip()
        qr_img = self.generate_qr_code(local_ip, self.port)

        if qr_img:
            # Save temporarily and open in default image viewer
            temp_filename = "/tmp/psp_controller_qr.png"
            qr_img.save(temp_filename)

            # Try to open with default image viewer
            try:
                # Try different image viewers (prefer ones we can control)
                viewers = [
                    ['feh', '--title', 'PSP Controller QR Code', temp_filename],  # Lightweight, controllable
                    ['eog', temp_filename],  # Eye of GNOME
                    ['gpicview', temp_filename],  # GPicView
                    ['display', temp_filename],  # ImageMagick
                    ['gthumb', temp_filename],  # gThumb
                    ['xdg-open', temp_filename],  # Fallback
                ]

                opened = False
                for viewer_cmd in viewers:
                    try:
                        self.qr_process = subprocess.Popen(
                            viewer_cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        self.qr_viewer_name = viewer_cmd[0]
                        opened = True
                        break
                    except FileNotFoundError:
                        continue

                if not opened:
                    print("Could not find an image viewer to display QR code")
                    print("Please install one of: feh, eog, gpicview, display, gthumb")
                    return False

                print(f"\nQR Code displayed! (IP: {local_ip}, Port: {self.port})")
                print("Scan this QR code with the Android app to connect automatically.")
                print("Press 'F' again to hide the QR code.\n")
                return True
            except Exception as e:
                print(f"Error displaying QR code: {e}")
                return False
        return False

    def hide_qr_code(self):
        """Close the QR code window if open."""
        try:
            # First try to terminate the process if we have it
            if self.qr_process and self.qr_process.poll() is None:
                self.qr_process.terminate()
                try:
                    self.qr_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.qr_process.kill()
                    self.qr_process.wait()
            
            # Also try to kill by process name (for viewers that fork)
            if hasattr(self, 'qr_viewer_name'):
                try:
                    subprocess.run(['pkill', '-f', self.qr_viewer_name], 
                                 stdout=subprocess.DEVNULL, 
                                 stderr=subprocess.DEVNULL,
                                 timeout=1)
                except:
                    pass
            
            # Remove the temp file
            try:
                import os
                os.remove('/tmp/psp_controller_qr.png')
            except:
                pass
                
        except Exception as e:
            print(f"Error closing QR code: {e}")
        finally:
            self.qr_process = None

    def toggle_qr_code(self):
        """Toggle QR code display."""
        if not QR_CODE_AVAILABLE:
            print("QR code functionality not available. Install with: pip install qrcode[pil]")
            return

        if self.qr_code_visible:
            self.hide_qr_code()
            self.qr_code_visible = False
            print("QR code hidden.")
        else:
            if self.show_qr_code():
                self.qr_code_visible = True
            else:
                print("Failed to display QR code.")

    def keyboard_input_thread(self):
        """Thread to handle keyboard input."""
        if not HAS_TERMIOS:
            print("Keyboard input not available on this platform (requires termios)")
            return

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setcbreak(sys.stdin.fileno())  # Use cbreak instead of raw mode
            while self.running:
                import select
                # Use select to check if input is available (non-blocking)
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    ch = sys.stdin.read(1).lower()
                    if ch == 'f':
                        self.toggle_qr_code()
        except Exception as e:
            print(f"Keyboard input error: {e}")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
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
            
            # Screen Streaming Commands
            elif cmd_type == 'request_stream':
                # Android requesting to start stream
                if not self.screen_streamer:
                    return json.dumps({'type': 'stream_error', 'message': 'Streaming not available'})
                
                width = command.get('width', 720)
                height = command.get('height', 1280)
                fps = command.get('fps', 30)
                quality = command.get('quality', 60)
                
                # Store client and params for callback (response sent when portal ready)
                self.pending_stream_client = client_socket
                self.pending_stream_params = {'width': width, 'height': height}
                
                success = self.screen_streamer.start(width, height, fps, quality)
                if success:
                    # For portal capture, response will be sent via callback
                    # For other methods, callback fires immediately
                    return None  # Don't send response yet, callback will handle it
                else:
                    self.pending_stream_client = None
                    self.pending_stream_params = None
                    return json.dumps({'type': 'stream_error', 'message': 'Failed to start stream'})
            
            elif cmd_type == 'stop_stream':
                # Android requesting to stop stream
                if self.screen_streamer:
                    self.screen_streamer.stop()
                return json.dumps({'type': 'stream_stop', 'success': True})
            
            elif cmd_type == 'refresh_stream':
                # Refresh PPSSPP window position
                if self.screen_streamer:
                    self.screen_streamer.refresh_window()
                return json.dumps({'type': 'ack', 'success': True})
            
            elif cmd_type == 'stream_status':
                # Get streaming status
                if self.screen_streamer:
                    status = self.screen_streamer.get_status()
                    return json.dumps({'type': 'stream_status', **status})
                else:
                    return json.dumps({'type': 'stream_status', 'streaming': False, 'available': False})
            
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
                            # Only send if there's a response (None means callback will send later)
                            if response is not None:
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
            
            # Stop stream if this client was the one that requested it
            if self.pending_stream_client == client_socket or self.screen_streamer and self.screen_streamer.streaming:
                if self.screen_streamer:
                    self.screen_streamer.stop()
                    print("[STREAM] Stopped (client disconnected)")
                self.pending_stream_client = None
                self.pending_stream_params = None
            
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

            # Start keyboard input thread
            if HAS_TERMIOS:
                keyboard_thread = threading.Thread(target=self.keyboard_input_thread, daemon=True)
                keyboard_thread.start()
                print("Press 'F' to toggle QR code display\n")

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

        # Hide QR code if visible
        if self.qr_code_visible:
            self.hide_qr_code()
            self.qr_code_visible = False

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

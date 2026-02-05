#!/usr/bin/env python3
"""
Screen Streamer for PSP Controller
Uses XDG Desktop Portal + PipeWire for GNOME Wayland screen capture.
This implements the same approach OBS uses.

Requirements:
- pip install PyGObject
- sudo apt install python3-gi gir1.2-gst-1.0 gstreamer1.0-pipewire
"""

import socket
import threading
import time
import io
import os
import sys
import random

# Try to import required libraries
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[STREAM] WARNING: Pillow not available. pip install Pillow")

try:
    import gi
    gi.require_version('Gio', '2.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import Gio, GLib
    GIO_AVAILABLE = True
except (ImportError, ValueError) as e:
    GIO_AVAILABLE = False
    print(f"[STREAM] WARNING: GIO not available: {e}")
    print("[STREAM] Install: sudo apt install python3-gi")

try:
    gi.require_version('Gst', '1.0')
    gi.require_version('GstApp', '1.0')
    from gi.repository import Gst, GstApp
    Gst.init(None)
    GST_AVAILABLE = True
except (ImportError, ValueError, NameError) as e:
    GST_AVAILABLE = False
    print(f"[STREAM] WARNING: GStreamer not available: {e}")
    print("[STREAM] Install: sudo apt install gir1.2-gst-1.0 gstreamer1.0-pipewire")

PORTAL_AVAILABLE = GIO_AVAILABLE and GST_AVAILABLE
STREAMING_AVAILABLE = PIL_AVAILABLE


def detect_display_server():
    """Detect display server type."""
    session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
    if session_type == 'wayland':
        return 'wayland'
    elif session_type == 'x11':
        return 'x11'
    if os.environ.get('WAYLAND_DISPLAY'):
        return 'wayland'
    if os.environ.get('DISPLAY'):
        return 'x11'
    return 'unknown'


class PortalScreenCapture:
    """
    Screen capture using XDG Desktop Portal.
    This shows a system dialog for user to select which screen/window to share.
    """
    
    PORTAL_BUS_NAME = 'org.freedesktop.portal.Desktop'
    PORTAL_OBJECT_PATH = '/org/freedesktop/portal/desktop'
    SCREENCAST_INTERFACE = 'org.freedesktop.portal.ScreenCast'
    REQUEST_INTERFACE = 'org.freedesktop.portal.Request'
    
    def __init__(self, on_ready_callback=None):
        self.session_handle = None
        self.pipewire_fd = None
        self.pipewire_node_id = None
        self.pipeline = None
        self.frame_buffer = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.loop = None
        self.loop_thread = None
        self.width = 720
        self.height = 1280
        self.quality = 60
        self.portal_ready = False
        self.connection = None
        self.request_counter = 0
        self.on_ready_callback = on_ready_callback  # Called when portal is ready
        # Source window bounds (for cropping if needed)
        self.source_x = 0
        self.source_y = 0
        self.source_width = None
        self.source_height = None
        
    def _generate_token(self):
        """Generate unique token for portal requests."""
        self.request_counter += 1
        return f"psp_{os.getpid()}_{self.request_counter}"
    
    def _generate_request_path(self, token):
        """Generate D-Bus request path."""
        sender = self.connection.get_unique_name().replace('.', '_').replace(':', '')
        return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    
    def _on_create_session_response(self, connection, sender_name, object_path, interface_name, signal_name, parameters):
        """Handle CreateSession response."""
        response, results = parameters.unpack()
        
        if response != 0:
            print(f"[PORTAL] CreateSession failed with response {response}")
            return
        
        self.session_handle = results.get('session_handle', '')
        print(f"[PORTAL] Session created: {self.session_handle[:50]}...")
        
        # Now call SelectSources - this will show the system dialog
        self._select_sources()
    
    def _on_select_sources_response(self, connection, sender_name, object_path, interface_name, signal_name, parameters):
        """Handle SelectSources response."""
        response, results = parameters.unpack()
        
        if response != 0:
            print(f"[PORTAL] SelectSources failed - user cancelled or denied")
            return
        
        print("[PORTAL] Source selected, starting capture...")
        self._start_capture()
    
    def _on_start_response(self, connection, sender_name, object_path, interface_name, signal_name, parameters):
        """Handle Start response."""
        response, results = parameters.unpack()
        
        if response != 0:
            print(f"[PORTAL] Start failed - user cancelled")
            return
        
        streams = results.get('streams', [])
        if not streams:
            print("[PORTAL] No streams returned")
            return
        
        # Get the PipeWire node ID and stream properties from the first stream
        node_id, stream_props = streams[0]
        self.pipewire_node_id = node_id
        print(f"[PORTAL] Got PipeWire node: {node_id}")
        
        # Extract source info for cropping (position and size on screen)
        self.source_x = 0
        self.source_y = 0
        self.source_width = None
        self.source_height = None
        
        if stream_props:
            # Try to get source position and size
            if 'position' in stream_props:
                pos = stream_props['position']
                self.source_x = pos[0] if len(pos) > 0 else 0
                self.source_y = pos[1] if len(pos) > 1 else 0
            if 'size' in stream_props:
                size = stream_props['size']
                self.source_width = size[0] if len(size) > 0 else None
                self.source_height = size[1] if len(size) > 1 else None
            if self.source_width:
                print(f"[PORTAL] Source: pos=({self.source_x},{self.source_y}), size={self.source_width}x{self.source_height}")
        
        # Open the PipeWire remote
        self._open_pipewire_remote()
    
    def _create_session(self):
        """Create a screencast session."""
        token = self._generate_token()
        request_path = self._generate_request_path(token)
        
        # Subscribe to the response signal
        self.connection.signal_subscribe(
            None,  # sender
            self.REQUEST_INTERFACE,
            'Response',
            request_path,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            self._on_create_session_response
        )
        
        # Build the options dict for D-Bus
        options_builder = GLib.VariantBuilder.new(GLib.VariantType.new('a{sv}'))
        options_builder.add_value(GLib.Variant.new_dict_entry(
            GLib.Variant.new_string('handle_token'),
            GLib.Variant.new_variant(GLib.Variant.new_string(token))
        ))
        options_builder.add_value(GLib.Variant.new_dict_entry(
            GLib.Variant.new_string('session_handle_token'),
            GLib.Variant.new_variant(GLib.Variant.new_string(f"session_{token}"))
        ))
        options = options_builder.end()
        
        self.connection.call(
            self.PORTAL_BUS_NAME,
            self.PORTAL_OBJECT_PATH,
            self.SCREENCAST_INTERFACE,
            'CreateSession',
            GLib.Variant.new_tuple(options),
            GLib.VariantType.new('(o)'),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_call_finished
        )
        
        print("[PORTAL] CreateSession called")
    
    def _build_variant_dict(self, entries):
        """Build a GLib.Variant dict from a list of (key, value) tuples."""
        builder = GLib.VariantBuilder.new(GLib.VariantType.new('a{sv}'))
        for key, value in entries:
            builder.add_value(GLib.Variant.new_dict_entry(
                GLib.Variant.new_string(key),
                GLib.Variant.new_variant(value)
            ))
        return builder.end()
    
    def _select_sources(self):
        """Select sources - shows system permission dialog."""
        token = self._generate_token()
        request_path = self._generate_request_path(token)
        
        self.connection.signal_subscribe(
            None,
            self.REQUEST_INTERFACE,
            'Response',
            request_path,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            self._on_select_sources_response
        )
        
        # Build options
        # types: 1 = Monitor, 2 = Window, 3 = Both
        options = self._build_variant_dict([
            ('handle_token', GLib.Variant.new_string(token)),
            ('types', GLib.Variant.new_uint32(2)),  # Window only (for PPSSPP)
            ('multiple', GLib.Variant.new_boolean(False)),
            ('cursor_mode', GLib.Variant.new_uint32(2)),  # Embedded cursor
        ])
        
        # Build (oa{sv}) tuple
        params = GLib.Variant.new_tuple(
            GLib.Variant.new_object_path(self.session_handle),
            options
        )
        
        self.connection.call(
            self.PORTAL_BUS_NAME,
            self.PORTAL_OBJECT_PATH,
            self.SCREENCAST_INTERFACE,
            'SelectSources',
            params,
            GLib.VariantType.new('(o)'),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_call_finished
        )
        
        print("[PORTAL] SelectSources called - waiting for user to select screen...")
    
    def _start_capture(self):
        """Start the capture after user selects source."""
        token = self._generate_token()
        request_path = self._generate_request_path(token)
        
        self.connection.signal_subscribe(
            None,
            self.REQUEST_INTERFACE,
            'Response',
            request_path,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            self._on_start_response
        )
        
        options = self._build_variant_dict([
            ('handle_token', GLib.Variant.new_string(token)),
        ])
        
        # Build (osa{sv}) tuple
        params = GLib.Variant.new_tuple(
            GLib.Variant.new_object_path(self.session_handle),
            GLib.Variant.new_string(''),
            options
        )
        
        self.connection.call(
            self.PORTAL_BUS_NAME,
            self.PORTAL_OBJECT_PATH,
            self.SCREENCAST_INTERFACE,
            'Start',
            params,
            GLib.VariantType.new('(o)'),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_call_finished
        )
        
        print("[PORTAL] Start called")
    
    def _open_pipewire_remote(self):
        """Open the PipeWire file descriptor."""
        try:
            # Use sync call with FD list support
            result, fd_list = self.connection.call_with_unix_fd_list_sync(
                self.PORTAL_BUS_NAME,
                self.PORTAL_OBJECT_PATH,
                self.SCREENCAST_INTERFACE,
                'OpenPipeWireRemote',
                GLib.Variant('(oa{sv})', (self.session_handle, {})),
                GLib.VariantType.new('(h)'),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None
            )
            
            fd_index = result.unpack()[0]
            self.pipewire_fd = fd_list.get(fd_index)
            print(f"[PORTAL] Got PipeWire FD: {self.pipewire_fd}")
            
            # Start GStreamer pipeline
            self._start_gstreamer_pipeline()
            
        except Exception as e:
            print(f"[PORTAL] Error opening PipeWire remote: {e}")
    
    def _start_gstreamer_pipeline(self):
        """Start GStreamer pipeline to read from PipeWire."""
        if not GST_AVAILABLE:
            print("[PORTAL] GStreamer not available")
            return
        
        # Create pipeline: pipewiresrc → videoconvert → jpegenc → appsink
        pipeline_str = (
            f"pipewiresrc fd={self.pipewire_fd} path={self.pipewire_node_id} ! "
            f"videoconvert ! "
            f"videoscale ! "
            f"video/x-raw,width={self.width},height={self.height} ! "
            f"jpegenc quality={self.quality} ! "
            f"appsink name=sink emit-signals=true max-buffers=1 drop=true"
        )
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
            
            # Get appsink and connect signal
            appsink = self.pipeline.get_by_name('sink')
            appsink.connect('new-sample', self._on_new_sample)
            
            self.pipeline.set_state(Gst.State.PLAYING)
            self.portal_ready = True
            print("[PORTAL] GStreamer pipeline started")
            
            # Notify that portal is ready
            if self.on_ready_callback:
                self.on_ready_callback()
            
        except Exception as e:
            print(f"[PORTAL] GStreamer error: {e}")
    
    def _on_new_sample(self, appsink):
        """Handle new frame from GStreamer."""
        sample = appsink.emit('pull-sample')
        if sample:
            buf = sample.get_buffer()
            success, map_info = buf.map(Gst.MapFlags.READ)
            if success:
                with self.frame_lock:
                    self.frame_buffer = bytes(map_info.data)
                buf.unmap(map_info)
        return Gst.FlowReturn.OK
    
    def _on_call_finished(self, source, result):
        """Callback for async D-Bus calls."""
        try:
            source.call_finish(result)
        except Exception as e:
            print(f"[PORTAL] D-Bus call error: {e}")
    
    def _run_loop(self):
        """Run GLib main loop."""
        try:
            self.loop.run()
        except:
            pass
    
    def start(self, width, height, quality):
        """Start portal capture."""
        if not PORTAL_AVAILABLE:
            print("[PORTAL] Portal not available - missing dependencies")
            return False
        
        self.width = width
        self.height = height
        self.quality = quality
        self.running = True
        
        try:
            # Get D-Bus connection
            self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            
            # Start GLib main loop
            self.loop = GLib.MainLoop()
            self.loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self.loop_thread.start()
            
            # Create session - this will chain through the portal flow
            GLib.idle_add(self._create_session)
            
            return True
            
        except Exception as e:
            print(f"[PORTAL] Error starting: {e}")
            return False
    
    def stop(self):
        """Stop capture."""
        self.running = False
        self.portal_ready = False
        
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        
        if self.loop:
            self.loop.quit()
    
    def get_frame(self):
        """Get latest frame."""
        with self.frame_lock:
            return self.frame_buffer
    
    def is_ready(self):
        """Check if portal capture is ready."""
        return self.portal_ready


class ScreenStreamer:
    """MJPEG screen streamer with portal support."""
    
    def __init__(self, port=5556, on_ready_callback=None):
        self.port = port
        self.streaming = False
        self.server_socket = None
        self.clients = []
        self.clients_lock = threading.Lock()
        self.target_width = 720
        self.target_height = 1280
        self.fps = 30
        self.quality = 60
        self.display_server = detect_display_server()
        self.frame_buffer = None
        self.frame_lock = threading.Lock()
        self.new_frame_event = threading.Event()
        self.capture_method = 'portal' if PORTAL_AVAILABLE and self.display_server == 'wayland' else 'mss'
        self.portal_capture = None
        self.on_ready_callback = on_ready_callback  # Called when stream is ready
        
        print(f"[STREAM] Display: {self.display_server}, Method: {self.capture_method}")
        
    def capture_loop(self):
        """Main capture loop."""
        frame_time = 1.0 / self.fps
        
        while self.streaming:
            start = time.time()
            frame_data = None
            
            try:
                if self.capture_method == 'portal' and self.portal_capture:
                    if self.portal_capture.is_ready():
                        frame_data = self.portal_capture.get_frame()
                else:
                    frame_data = self._capture_mss()
                
                if frame_data:
                    with self.frame_lock:
                        self.frame_buffer = frame_data
                    self.new_frame_event.set()
                    
            except Exception as e:
                print(f"[STREAM] Capture error: {e}")
            
            elapsed = time.time() - start
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
    
    def _capture_mss(self):
        """Capture using mss library."""
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                img = sct.grab(monitor)
                pil_img = Image.frombytes('RGB', img.size, img.bgra, 'raw', 'BGRX')
                pil_img = pil_img.resize(
                    (self.target_width, self.target_height),
                    Image.Resampling.LANCZOS
                )
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
                buffer = io.BytesIO()
                pil_img.save(buffer, format='JPEG', quality=self.quality)
                return buffer.getvalue()
        except Exception as e:
            return None
    
    def stream_to_client(self, client_socket, client_addr):
        """Stream MJPEG to client."""
        print(f"[STREAM] Client connected: {client_addr[0]}:{client_addr[1]}")
        
        try:
            headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
                "Cache-Control: no-cache\r\n"
                "Connection: keep-alive\r\n"
                "\r\n"
            )
            client_socket.send(headers.encode('utf-8'))
            
            while self.streaming:
                self.new_frame_event.wait(timeout=1.0)
                self.new_frame_event.clear()
                
                with self.frame_lock:
                    frame_data = self.frame_buffer
                
                if frame_data:
                    try:
                        frame_header = (
                            "--frame\r\n"
                            "Content-Type: image/jpeg\r\n"
                            f"Content-Length: {len(frame_data)}\r\n"
                            "\r\n"
                        )
                        client_socket.send(frame_header.encode('utf-8'))
                        client_socket.send(frame_data)
                        client_socket.send(b"\r\n")
                    except (BrokenPipeError, ConnectionResetError):
                        break
                        
        except Exception as e:
            pass
        finally:
            try:
                client_socket.close()
            except:
                pass
            with self.clients_lock:
                if client_socket in self.clients:
                    self.clients.remove(client_socket)
            print(f"[STREAM] Client disconnected: {client_addr[0]}")
    
    def accept_clients(self):
        """Accept client connections."""
        while self.streaming:
            try:
                self.server_socket.settimeout(1.0)
                client_socket, client_addr = self.server_socket.accept()
                
                with self.clients_lock:
                    self.clients.append(client_socket)
                
                thread = threading.Thread(
                    target=self.stream_to_client,
                    args=(client_socket, client_addr),
                    daemon=True
                )
                thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.streaming:
                    print(f"[STREAM] Accept error: {e}")
    
    def start(self, width=720, height=1280, fps=30, quality=60):
        """Start streaming server."""
        if not STREAMING_AVAILABLE:
            print("[STREAM] Missing Pillow")
            return False
        
        if self.streaming:
            return True
        
        self.target_width = width
        self.target_height = height
        self.fps = fps
        self.quality = quality
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            
            self.streaming = True
            
            # Start portal capture for Wayland
            if self.capture_method == 'portal':
                self.portal_capture = PortalScreenCapture(on_ready_callback=self.on_ready_callback)
                if not self.portal_capture.start(width, height, quality):
                    print("[STREAM] Portal failed, falling back to mss")
                    self.capture_method = 'mss'
                    # For mss fallback, call ready immediately
                    if self.on_ready_callback:
                        self.on_ready_callback()
            else:
                # For non-portal methods, we're ready immediately
                if self.on_ready_callback:
                    self.on_ready_callback()
            
            # Start capture thread
            self.capture_thread = threading.Thread(
                target=self.capture_loop,
                daemon=True
            )
            self.capture_thread.start()
            
            # Start accept thread
            self.accept_thread = threading.Thread(
                target=self.accept_clients,
                daemon=True
            )
            self.accept_thread.start()
            
            print(f"[STREAM] Started on port {self.port} ({self.capture_method})")
            if self.capture_method == 'portal':
                print("[STREAM] A system dialog will appear to select the screen to share")
            return True
            
        except Exception as e:
            print(f"[STREAM] Failed: {e}")
            return False
    
    def stop(self):
        """Stop streaming."""
        if not self.streaming:
            return
        
        self.streaming = False
        self.new_frame_event.set()
        
        if self.portal_capture:
            self.portal_capture.stop()
        
        with self.clients_lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients.clear()
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        print("[STREAM] Stopped")
    
    def refresh_window(self):
        return None
    
    def is_streaming(self):
        return self.streaming
    
    def get_status(self):
        with self.clients_lock:
            client_count = len(self.clients)
        return {
            'streaming': self.streaming,
            'port': self.port,
            'clients': client_count,
            'fps': self.fps,
            'capture_method': self.capture_method,
            'display_server': self.display_server,
            'portal_ready': self.portal_capture.is_ready() if self.portal_capture else False
        }


if __name__ == '__main__':
    print("=" * 50)
    print("PSP Controller Screen Streamer")
    print("Using XDG Desktop Portal")
    print("=" * 50)
    print()
    
    if not PORTAL_AVAILABLE:
        print("WARNING: Portal capture not available!")
        print("Install dependencies:")
        print("  sudo apt install python3-gi gir1.2-gst-1.0 gstreamer1.0-pipewire")
        print()
    
    streamer = ScreenStreamer(port=5556)
    
    print("Starting stream...")
    print("Open http://localhost:5556 in browser")
    print()
    
    if streamer.start(width=720, height=1280, fps=30, quality=60):
        print("Press Ctrl+C to stop")
        print()
        
        try:
            while True:
                time.sleep(1)
                status = streamer.get_status()
                if status['capture_method'] == 'portal':
                    print(f"\rPortal ready: {status['portal_ready']}, Clients: {status['clients']}", end='', flush=True)
        except KeyboardInterrupt:
            print("\nStopping...")
        
        streamer.stop()
    else:
        print("Failed to start")

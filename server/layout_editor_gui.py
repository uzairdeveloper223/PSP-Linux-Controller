#!/usr/bin/env python3
"""
Desktop Layout Editor for PSP Controller
A PyQt5-based GUI for customizing controller button positions with live sync to Android app.
"""

import sys
import json
import socket
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QFrame, QGroupBox, QComboBox,
    QStatusBar, QAction, QToolBar, QMessageBox, QSplitter
)
from PyQt5.QtCore import Qt, QPoint, QRectF, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath


# Control identifiers matching Android LayoutSettingsManager
CONTROL_DPAD = "dpad"
CONTROL_ANALOG = "analog"
CONTROL_ACTION_BUTTONS = "action_buttons"
CONTROL_L_BUTTON = "l_button"
CONTROL_R_BUTTON = "r_button"
CONTROL_START = "start"
CONTROL_SELECT = "select"

# Default positions (percentage of screen)
DEFAULT_LAYOUT = {
    CONTROL_DPAD: {"x": 0.05, "y": 0.35, "scale": 1.0, "opacity": 1.0, "visible": True},
    CONTROL_ANALOG: {"x": 0.18, "y": 0.70, "scale": 1.0, "opacity": 1.0, "visible": True},
    CONTROL_ACTION_BUTTONS: {"x": 0.75, "y": 0.35, "scale": 1.0, "opacity": 1.0, "visible": True},
    CONTROL_L_BUTTON: {"x": 0.05, "y": 0.08, "scale": 1.0, "opacity": 1.0, "visible": True},
    CONTROL_R_BUTTON: {"x": 0.75, "y": 0.08, "scale": 1.0, "opacity": 1.0, "visible": True},
    CONTROL_START: {"x": 0.60, "y": 0.85, "scale": 1.0, "opacity": 1.0, "visible": True},
    CONTROL_SELECT: {"x": 0.30, "y": 0.85, "scale": 1.0, "opacity": 1.0, "visible": True},
}

COMPACT_LAYOUT = {
    CONTROL_DPAD: {"x": 0.02, "y": 0.40, "scale": 0.8, "opacity": 1.0, "visible": True},
    CONTROL_ANALOG: {"x": 0.12, "y": 0.75, "scale": 0.8, "opacity": 1.0, "visible": True},
    CONTROL_ACTION_BUTTONS: {"x": 0.80, "y": 0.40, "scale": 0.8, "opacity": 1.0, "visible": True},
    CONTROL_L_BUTTON: {"x": 0.02, "y": 0.05, "scale": 0.8, "opacity": 1.0, "visible": True},
    CONTROL_R_BUTTON: {"x": 0.80, "y": 0.05, "scale": 0.8, "opacity": 1.0, "visible": True},
    CONTROL_START: {"x": 0.65, "y": 0.90, "scale": 0.8, "opacity": 1.0, "visible": True},
    CONTROL_SELECT: {"x": 0.25, "y": 0.90, "scale": 0.8, "opacity": 1.0, "visible": True},
}

WIDE_LAYOUT = {
    CONTROL_DPAD: {"x": 0.08, "y": 0.30, "scale": 1.2, "opacity": 1.0, "visible": True},
    CONTROL_ANALOG: {"x": 0.20, "y": 0.65, "scale": 1.2, "opacity": 1.0, "visible": True},
    CONTROL_ACTION_BUTTONS: {"x": 0.70, "y": 0.30, "scale": 1.2, "opacity": 1.0, "visible": True},
    CONTROL_L_BUTTON: {"x": 0.08, "y": 0.05, "scale": 1.2, "opacity": 1.0, "visible": True},
    CONTROL_R_BUTTON: {"x": 0.70, "y": 0.05, "scale": 1.2, "opacity": 1.0, "visible": True},
    CONTROL_START: {"x": 0.58, "y": 0.85, "scale": 1.2, "opacity": 1.0, "visible": True},
    CONTROL_SELECT: {"x": 0.32, "y": 0.85, "scale": 1.2, "opacity": 1.0, "visible": True},
}

# Control sizes in dp (matching activity_main.xml)
CONTROL_SIZES_DP = {
    CONTROL_DPAD: (180, 180),
    CONTROL_ANALOG: (80, 80),
    CONTROL_ACTION_BUTTONS: (180, 180),
    CONTROL_L_BUTTON: (160, 48),
    CONTROL_R_BUTTON: (160, 48),
    CONTROL_START: (100, 40),
    CONTROL_SELECT: (100, 40),
}


class LayoutSignals(QObject):
    """Signals for thread-safe communication."""
    device_connected = pyqtSignal(dict)
    layout_received = pyqtSignal(dict)
    connection_lost = pyqtSignal()


@dataclass
class HistoryAction:
    """Represents a single undoable action."""
    control_id: str
    old_state: dict
    new_state: dict


class LayoutEditorCanvas(QWidget):
    """Canvas widget displaying controller layout."""
    
    control_selected = pyqtSignal(str)
    layout_changed = pyqtSignal(str, dict)  # control_id, new_settings
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)
        
        # Device dimensions (default, updated on connection)
        self.device_width = 1920
        self.device_height = 1080
        self.device_density = 2.75
        
        # Layout data
        self.layout_data = self._deep_copy_layout(DEFAULT_LAYOUT)
        self.selected_control = None
        
        # Dragging state
        self.dragging = False
        self.drag_start = QPoint()
        self.drag_control_start = (0, 0)
        
        # Colors
        self.bg_color = QColor(0x1a, 0x1a, 0x2e)
        self.control_color = QColor(0x2a, 0x2a, 0x4e)
        self.selection_color = QColor(0x00, 0xaa, 0xff)
        
    def _deep_copy_layout(self, layout: dict) -> dict:
        """Create a deep copy of layout data."""
        return {k: dict(v) for k, v in layout.items()}
    
    def set_device_info(self, width: int, height: int, density: float):
        """Set device dimensions."""
        self.device_width = width
        self.device_height = height
        self.device_density = density
        self.update()
    
    def set_layout(self, layout: dict):
        """Set the entire layout."""
        self.layout_data = self._deep_copy_layout(layout)
        self.update()
    
    def get_layout(self) -> dict:
        """Get the current layout."""
        return self._deep_copy_layout(self.layout_data)
    
    def update_control(self, control_id: str, settings: dict):
        """Update a single control's settings."""
        if control_id in self.layout_data:
            self.layout_data[control_id].update(settings)
            self.update()
    
    def _get_canvas_rect(self) -> QRectF:
        """Get the canvas rectangle maintaining device aspect ratio."""
        widget_w = self.width()
        widget_h = self.height()
        
        device_aspect = self.device_width / self.device_height
        widget_aspect = widget_w / widget_h
        
        if widget_aspect > device_aspect:
            # Widget is wider, fit to height
            canvas_h = widget_h - 20
            canvas_w = canvas_h * device_aspect
        else:
            # Widget is taller, fit to width
            canvas_w = widget_w - 20
            canvas_h = canvas_w / device_aspect
        
        x = (widget_w - canvas_w) / 2
        y = (widget_h - canvas_h) / 2
        
        return QRectF(x, y, canvas_w, canvas_h)
    
    def _dp_to_canvas_px(self, dp: int, canvas_rect: QRectF) -> float:
        """Convert dp to canvas pixels."""
        # Scale factor: how many canvas pixels per device pixel
        scale = canvas_rect.width() / self.device_width
        # dp to device pixels, then to canvas pixels
        return dp * self.device_density * scale
    
    def _get_control_rect(self, control_id: str, canvas_rect: QRectF) -> QRectF:
        """Get the rectangle for a control on the canvas."""
        settings = self.layout_data.get(control_id, {})
        size_dp = CONTROL_SIZES_DP.get(control_id, (100, 100))
        
        # Convert dp to canvas pixels
        base_w = self._dp_to_canvas_px(size_dp[0], canvas_rect)
        base_h = self._dp_to_canvas_px(size_dp[1], canvas_rect)
        
        # Apply scale
        scale = settings.get("scale", 1.0)
        w = base_w * scale
        h = base_h * scale
        
        # Position (percentage of canvas)
        x = canvas_rect.x() + settings.get("x", 0) * canvas_rect.width()
        y = canvas_rect.y() + settings.get("y", 0) * canvas_rect.height()
        
        return QRectF(x, y, w, h)
    
    def _control_at_pos(self, pos: QPoint) -> Optional[str]:
        """Find control at given position."""
        canvas_rect = self._get_canvas_rect()
        
        # Check in reverse order (top-most first)
        for control_id in reversed(list(self.layout_data.keys())):
            if not self.layout_data[control_id].get("visible", True):
                continue
            rect = self._get_control_rect(control_id, canvas_rect)
            if rect.contains(pos.x(), pos.y()):
                return control_id
        return None
    
    def paintEvent(self, event):
        """Paint the canvas."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(0x10, 0x10, 0x20))
        
        # Canvas area (device screen)
        canvas_rect = self._get_canvas_rect()
        painter.fillRect(canvas_rect, self.bg_color)
        
        # Draw border around canvas
        painter.setPen(QPen(QColor(0x40, 0x40, 0x60), 2))
        painter.drawRect(canvas_rect)
        
        # Draw controls
        for control_id, settings in self.layout_data.items():
            self._draw_control(painter, control_id, settings, canvas_rect)
        
        # Device info label
        painter.setPen(QColor(0x80, 0x80, 0x80))
        painter.setFont(QFont("Monospace", 9))
        painter.drawText(
            int(canvas_rect.x()), 
            int(canvas_rect.y() + canvas_rect.height() + 15),
            f"Device: {self.device_width}x{self.device_height} @ {self.device_density}x"
        )
    
    def _draw_control(self, painter: QPainter, control_id: str, settings: dict, canvas_rect: QRectF):
        """Draw a single control."""
        if not settings.get("visible", True):
            return
        
        rect = self._get_control_rect(control_id, canvas_rect)
        opacity = settings.get("opacity", 1.0)
        is_selected = control_id == self.selected_control
        
        # Set opacity
        painter.setOpacity(opacity)
        
        # Draw based on control type
        if control_id in [CONTROL_DPAD, CONTROL_ACTION_BUTTONS, CONTROL_ANALOG]:
            # Circular controls
            center = rect.center()
            radius = min(rect.width(), rect.height()) / 2
            
            # Background
            painter.setBrush(QBrush(self.control_color))
            painter.setPen(QPen(QColor(0x4a, 0x4a, 0x6e), 2))
            painter.drawEllipse(center, radius, radius)
            
            # Label
            painter.setOpacity(opacity * 0.8)
            painter.setPen(QColor(0xff, 0xff, 0xff))
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            label = {"dpad": "D-PAD", "analog": "ANALOG", "action_buttons": "△○□✕"}
            painter.drawText(rect, Qt.AlignCenter, label.get(control_id, control_id.upper()))
        else:
            # Rectangular controls (buttons)
            painter.setBrush(QBrush(self.control_color))
            painter.setPen(QPen(QColor(0x4a, 0x4a, 0x6e), 2))
            painter.drawRoundedRect(rect, 10, 10)
            
            # Label
            painter.setOpacity(opacity * 0.8)
            painter.setPen(QColor(0xff, 0xff, 0xff))
            painter.setFont(QFont("Arial", 10, QFont.Bold))
            label = {"l_button": "L", "r_button": "R", "start": "START", "select": "SELECT"}
            painter.drawText(rect, Qt.AlignCenter, label.get(control_id, control_id.upper()))
        
        # Selection border
        if is_selected:
            painter.setOpacity(1.0)
            painter.setPen(QPen(self.selection_color, 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            if control_id in [CONTROL_DPAD, CONTROL_ACTION_BUTTONS, CONTROL_ANALOG]:
                center = rect.center()
                radius = min(rect.width(), rect.height()) / 2 + 5
                painter.drawEllipse(center, radius, radius)
            else:
                painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 12, 12)
        
        painter.setOpacity(1.0)
    
    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.LeftButton:
            control = self._control_at_pos(event.pos())
            self.selected_control = control
            
            if control:
                self.control_selected.emit(control)
                self.dragging = True
                self.drag_start = event.pos()
                settings = self.layout_data[control]
                self.drag_control_start = (settings["x"], settings["y"])
            
            self.update()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move."""
        if self.dragging and self.selected_control:
            canvas_rect = self._get_canvas_rect()
            
            # Calculate new position
            dx = (event.pos().x() - self.drag_start.x()) / canvas_rect.width()
            dy = (event.pos().y() - self.drag_start.y()) / canvas_rect.height()
            
            new_x = max(0, min(1, self.drag_control_start[0] + dx))
            new_y = max(0, min(1, self.drag_control_start[1] + dy))
            
            self.layout_data[self.selected_control]["x"] = new_x
            self.layout_data[self.selected_control]["y"] = new_y
            
            # Emit live update
            self.layout_changed.emit(
                self.selected_control, 
                {"x": new_x, "y": new_y}
            )
            
            self.update()
        else:
            # Update cursor
            control = self._control_at_pos(event.pos())
            if control and self.layout_data[control].get("visible", True):
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)


class ControlPanel(QWidget):
    """Side panel for control properties."""
    
    settings_changed = pyqtSignal(str, dict)  # control_id, new_settings
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_control = None
        self.updating_ui = False
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Control name label
        self.control_label = QLabel("No control selected")
        self.control_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.control_label.setStyleSheet("color: #00aaff;")
        layout.addWidget(self.control_label)
        
        layout.addSpacing(10)
        
        # Scale slider
        scale_group = QGroupBox("Scale")
        scale_layout = QVBoxLayout(scale_group)
        
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(50, 200)
        self.scale_slider.setValue(100)
        self.scale_slider.valueChanged.connect(self._on_scale_changed)
        scale_layout.addWidget(self.scale_slider)
        
        self.scale_label = QLabel("100%")
        self.scale_label.setAlignment(Qt.AlignCenter)
        scale_layout.addWidget(self.scale_label)
        
        layout.addWidget(scale_group)
        
        # Opacity slider
        opacity_group = QGroupBox("Opacity")
        opacity_layout = QVBoxLayout(opacity_group)
        
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)
        
        self.opacity_label = QLabel("100%")
        self.opacity_label.setAlignment(Qt.AlignCenter)
        opacity_layout.addWidget(self.opacity_label)
        
        layout.addWidget(opacity_group)
        
        # Visibility toggle
        self.visibility_btn = QPushButton("VISIBLE")
        self.visibility_btn.setCheckable(True)
        self.visibility_btn.setChecked(True)
        self.visibility_btn.clicked.connect(self._on_visibility_changed)
        self.visibility_btn.setStyleSheet("""
            QPushButton { background: #4CAF50; color: white; padding: 10px; border-radius: 5px; }
            QPushButton:checked { background: #4CAF50; }
            QPushButton:!checked { background: #f44336; }
        """)
        layout.addWidget(self.visibility_btn)
        
        layout.addStretch()
        
        # Position info
        self.position_label = QLabel("X: 0.00  Y: 0.00")
        self.position_label.setStyleSheet("color: #888;")
        layout.addWidget(self.position_label)
    
    def set_control(self, control_id: str, settings: dict):
        """Update panel for selected control."""
        self.current_control = control_id
        self.updating_ui = True
        
        # Display name
        names = {
            CONTROL_DPAD: "D-Pad",
            CONTROL_ANALOG: "Analog Stick",
            CONTROL_ACTION_BUTTONS: "Action Buttons",
            CONTROL_L_BUTTON: "L Button",
            CONTROL_R_BUTTON: "R Button",
            CONTROL_START: "Start",
            CONTROL_SELECT: "Select",
        }
        self.control_label.setText(names.get(control_id, control_id))
        
        # Update sliders
        self.scale_slider.setValue(int(settings.get("scale", 1.0) * 100))
        self.opacity_slider.setValue(int(settings.get("opacity", 1.0) * 100))
        
        # Update visibility button
        visible = settings.get("visible", True)
        self.visibility_btn.setChecked(visible)
        self.visibility_btn.setText("VISIBLE" if visible else "HIDDEN")
        
        # Position
        self.position_label.setText(f"X: {settings.get('x', 0):.2f}  Y: {settings.get('y', 0):.2f}")
        
        self.updating_ui = False
    
    def update_position(self, x: float, y: float):
        """Update position display."""
        self.position_label.setText(f"X: {x:.2f}  Y: {y:.2f}")
    
    def _on_scale_changed(self, value):
        if self.updating_ui or not self.current_control:
            return
        self.scale_label.setText(f"{value}%")
        self.settings_changed.emit(self.current_control, {"scale": value / 100.0})
    
    def _on_opacity_changed(self, value):
        if self.updating_ui or not self.current_control:
            return
        self.opacity_label.setText(f"{value}%")
        self.settings_changed.emit(self.current_control, {"opacity": value / 100.0})
    
    def _on_visibility_changed(self, checked):
        if self.updating_ui or not self.current_control:
            return
        self.visibility_btn.setText("VISIBLE" if checked else "HIDDEN")
        self.settings_changed.emit(self.current_control, {"visible": checked})


class LayoutEditorWindow(QMainWindow):
    """Main layout editor window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PSP Controller - Layout Editor | Made by Uzair")
        self.setMinimumSize(900, 600)
        
        # Signals for thread-safe updates
        self.signals = LayoutSignals()
        self.signals.device_connected.connect(self._on_device_connected)
        self.signals.layout_received.connect(self._on_layout_received)
        self.signals.connection_lost.connect(self._on_connection_lost)
        
        # Undo/redo history
        self.history: List[HistoryAction] = []
        self.history_index = -1
        self.max_history = 50
        
        # TCP connection
        self.socket = None
        self.connected = False
        self.device_address = None
        
        self.setup_ui()
        self.setup_toolbar()
        self.setup_statusbar()
        self.apply_dark_theme()
    
    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        
        # Canvas
        self.canvas = LayoutEditorCanvas()
        self.canvas.control_selected.connect(self._on_control_selected)
        self.canvas.layout_changed.connect(self._on_layout_changed)
        splitter.addWidget(self.canvas)
        
        # Control panel
        self.control_panel = ControlPanel()
        self.control_panel.settings_changed.connect(self._on_settings_changed)
        self.control_panel.setMaximumWidth(250)
        splitter.addWidget(self.control_panel)
        
        splitter.setSizes([700, 200])
        layout.addWidget(splitter)
    
    def setup_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        toolbar.addWidget(self.connect_btn)
        
        toolbar.addSeparator()
        
        # Preset selector
        toolbar.addWidget(QLabel("Preset: "))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Default", "Compact", "Wide"])
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        toolbar.addWidget(self.preset_combo)
        
        toolbar.addSeparator()
        
        # Undo/Redo
        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.undo)
        toolbar.addAction(undo_action)
        
        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self.redo)
        toolbar.addAction(redo_action)
        
        toolbar.addSeparator()
        
        # Reset
        reset_action = QAction("Reset", self)
        reset_action.triggered.connect(self._reset_layout)
        toolbar.addAction(reset_action)
        
        # Save
        save_action = QAction("Save to Device", self)
        save_action.triggered.connect(self._save_to_device)
        toolbar.addAction(save_action)
    
    def _toggle_connection(self):
        """Toggle server connection."""
        if self.connected:
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            self.socket = None
            self.connect_btn.setText("Connect")
            self.statusbar.showMessage("Disconnected")
        else:
            # Connect to localhost:5555
            if self.connect_to_server(("127.0.0.1", 5555)):
                self.connect_btn.setText("Disconnect")
    
    def setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Not connected to device")
    
    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }
            QToolBar { background: #181825; border: none; padding: 5px; }
            QToolBar QToolButton { padding: 5px 10px; }
            QPushButton { background: #45475a; color: #cdd6f4; border: none; padding: 8px 16px; border-radius: 4px; }
            QPushButton:hover { background: #585b70; }
            QGroupBox { border: 1px solid #45475a; border-radius: 5px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QSlider::groove:horizontal { background: #45475a; height: 6px; border-radius: 3px; }
            QSlider::handle:horizontal { background: #89b4fa; width: 16px; margin: -5px 0; border-radius: 8px; }
            QComboBox { background: #45475a; border: none; padding: 5px; border-radius: 3px; }
            QStatusBar { background: #181825; }
        """)
    
    def connect_to_server(self, address: Tuple[str, int]):
        """Connect to the PSP Controller server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(address)
            self.socket.settimeout(0.5)
            self.connected = True
            self.device_address = address
            
            # Request device info and layout
            self._send_command({"type": "get_device_info"})
            self._send_command({"type": "get_layout"})
            
            # Start receive thread
            threading.Thread(target=self._receive_loop, daemon=True).start()
            
            self.statusbar.showMessage(f"Connected to {address[0]}:{address[1]}")
            return True
        except Exception as e:
            self.statusbar.showMessage(f"Connection failed: {e}")
            return False
    
    def _send_command(self, command: dict):
        """Send a command to the server."""
        if self.connected and self.socket:
            try:
                data = json.dumps(command) + "\n"
                self.socket.send(data.encode("utf-8"))
            except Exception as e:
                print(f"Send error: {e}")
                self.signals.connection_lost.emit()
    
    def _receive_loop(self):
        """Background thread for receiving server messages."""
        buffer = ""
        while self.connected:
            try:
                data = self.socket.recv(1024).decode("utf-8")
                if not data:
                    break
                
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self._handle_response(json.loads(line))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Receive error: {e}")
                break
        
        self.signals.connection_lost.emit()
    
    def _handle_response(self, response: dict):
        """Handle server response."""
        resp_type = response.get("type")
        
        if resp_type == "device_info":
            self.signals.device_connected.emit(response)
        elif resp_type == "layout":
            self.signals.layout_received.emit(response.get("controls", {}))
    
    def _on_device_connected(self, info: dict):
        """Handle device connection."""
        self.canvas.set_device_info(
            info.get("width", 1920),
            info.get("height", 1080),
            info.get("density", 2.75)
        )
    
    def _on_layout_received(self, layout: dict):
        """Handle received layout data."""
        if layout:
            self.canvas.set_layout(layout)
    
    def _on_connection_lost(self):
        """Handle connection loss."""
        self.connected = False
        self.socket = None
        self.statusbar.showMessage("Disconnected from device")
    
    def _on_control_selected(self, control_id: str):
        """Handle control selection."""
        settings = self.canvas.layout_data.get(control_id, {})
        self.control_panel.set_control(control_id, settings)
    
    def _on_layout_changed(self, control_id: str, new_settings: dict):
        """Handle layout change from canvas (drag)."""
        # Update control panel position display
        self.control_panel.update_position(
            new_settings.get("x", 0),
            new_settings.get("y", 0)
        )
        
        # Send live preview to device
        self._send_command({
            "type": "layout_preview",
            "control": control_id,
            **new_settings
        })
    
    def _on_settings_changed(self, control_id: str, settings: dict):
        """Handle settings change from control panel."""
        # Save for undo
        old_settings = dict(self.canvas.layout_data.get(control_id, {}))
        
        # Apply change
        self.canvas.update_control(control_id, settings)
        new_settings = dict(self.canvas.layout_data.get(control_id, {}))
        
        # Add to history
        self._add_to_history(HistoryAction(control_id, old_settings, new_settings))
        
        # Send live preview
        self._send_command({
            "type": "layout_preview",
            "control": control_id,
            **settings
        })
    
    def _add_to_history(self, action: HistoryAction):
        """Add action to undo history."""
        # Remove any redo history
        self.history = self.history[:self.history_index + 1]
        
        # Add new action
        self.history.append(action)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        self.history_index = len(self.history) - 1
    
    def undo(self):
        """Undo last action."""
        if self.history_index >= 0:
            action = self.history[self.history_index]
            self.canvas.update_control(action.control_id, action.old_state)
            self.history_index -= 1
            
            # Update device
            self._send_command({
                "type": "layout_preview",
                "control": action.control_id,
                **action.old_state
            })
    
    def redo(self):
        """Redo last undone action."""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            action = self.history[self.history_index]
            self.canvas.update_control(action.control_id, action.new_state)
            
            # Update device
            self._send_command({
                "type": "layout_preview",
                "control": action.control_id,
                **action.new_state
            })
    
    def _apply_preset(self, preset_name: str):
        """Apply a preset layout."""
        presets = {
            "Default": DEFAULT_LAYOUT,
            "Compact": COMPACT_LAYOUT,
            "Wide": WIDE_LAYOUT,
        }
        
        if preset_name in presets:
            self.canvas.set_layout(presets[preset_name])
            self._send_command({
                "type": "set_layout",
                "layout": self.canvas.get_layout()
            })
    
    def _reset_layout(self):
        """Reset to default layout."""
        reply = QMessageBox.question(
            self, "Reset Layout",
            "Reset all controls to default positions?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.canvas.set_layout(DEFAULT_LAYOUT)
            self.preset_combo.setCurrentText("Default")
            self._send_command({
                "type": "set_layout",
                "layout": self.canvas.get_layout()
            })
    
    def _save_to_device(self):
        """Save current layout to device."""
        self._send_command({
            "type": "set_layout",
            "layout": self.canvas.get_layout()
        })
        self.statusbar.showMessage("Layout saved to device", 3000)
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.connected:
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = LayoutEditorWindow()
    window.show()
    
    # Auto-connect to server on startup
    QTimer.singleShot(100, lambda: window._toggle_connection())
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

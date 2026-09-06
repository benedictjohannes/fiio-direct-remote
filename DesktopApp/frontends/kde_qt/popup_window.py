"""
PyQt6 Control Window / Card for FiiO K17.
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QComboBox,
    QPushButton,
    QStyle,
    QStyleOptionSlider,
)

from core.constants import INPUT_MODES_ORDERED, InputMode
from core.controller import K17DeviceController, K17State


class ClickableSlider(QSlider):
    """
    QSlider subclass that immediately jumps directly to the clicked location
    rather than stepping incrementally (PageStep) by 10.
    """
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            sr = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                opt,
                QStyle.SubControl.SC_SliderHandle,
                self
            )
            # If clicked outside the handle, jump directly to click position
            if not sr.contains(event.position().toPoint()):
                new_val = QStyle.sliderValueFromPosition(
                    self.minimum(),
                    self.maximum(),
                    int(event.position().x()),
                    self.width()
                )
                self.setValue(new_val)
        super().mousePressEvent(event)


class K17PopupWindow(QWidget):
    def __init__(self, controller: K17DeviceController, tray_app):
        super().__init__()
        self.controller = controller
        self.tray_app = tray_app
        self.is_updating_ui = False

        # Standard desktop window with title bar
        self.setObjectName("K17Window")
        self.setWindowTitle("FiiO K17 Controller")
        self.setFixedSize(340, 260)
        self.setWindowFlags(Qt.WindowType.Window)

        # Volume Debounce Timer (500ms)
        self.vol_timer = QTimer(self)
        self.vol_timer.setSingleShot(True)
        self.vol_timer.setInterval(500)
        self.vol_timer.timeout.connect(self._dispatch_volume_change)

        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget#K17Window {
                background-color: #1e1e2e;
            }
            QLabel {
                color: #cdd6f4;
                font-family: 'Segoe UI', sans-serif;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #313244;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #89b4fa;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #b4befe;
                border: none;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #cba6f7;
            }
            QComboBox {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e;
                color: #cdd6f4;
                selection-background-color: #313244;
                border: 1px solid #45475a;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header Row
        header_layout = QHBoxLayout()
        title_label = QLabel("FiiO K17", self)
        font = title_label.font()
        font.setPointSize(12)
        font.setBold(True)
        title_label.setFont(font)

        self.status_badge = QLabel("OFFLINE", self)
        self.status_badge.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 10px;")

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_badge)
        main_layout.addLayout(header_layout)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: #313244; max-height: 1px; border: none;")
        main_layout.addWidget(sep)

        # Volume Controls
        vol_header = QHBoxLayout()
        vol_title = QLabel("Volume", self)
        self.vol_val_label = QLabel("--", self)
        self.vol_val_label.setStyleSheet("color: #89b4fa; font-weight: bold;")
        vol_header.addWidget(vol_title)
        vol_header.addStretch()
        vol_header.addWidget(self.vol_val_label)
        main_layout.addLayout(vol_header)

        self.vol_slider = ClickableSlider(Qt.Orientation.Horizontal, self)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(0)
        self.vol_slider.valueChanged.connect(self._on_slider_value_changed)
        main_layout.addWidget(self.vol_slider)

        # Input Mode Selection
        mode_header = QHBoxLayout()
        mode_title = QLabel("Input Source", self)
        mode_header.addWidget(mode_title)
        mode_header.addStretch()
        main_layout.addLayout(mode_header)

        self.mode_combo = QComboBox(self)
        self.mode_combo.setPlaceholderText("-- Select Input --")
        for label, code in INPUT_MODES_ORDERED:
            self.mode_combo.addItem(label, code)
        self.mode_combo.setCurrentIndex(-1)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_selected)
        main_layout.addWidget(self.mode_combo)

        # Retry / Refresh Button for Offline state
        self.retry_btn = QPushButton("Retry Connection", self)
        self.retry_btn.clicked.connect(lambda: self.tray_app.refresh_status(force_resolve=True))
        main_layout.addWidget(self.retry_btn)

    def set_connecting_state(self):
        self.status_badge.setText("CONNECTING...")
        self.status_badge.setStyleSheet("color: #f9e2af; font-weight: bold; font-size: 10px;")

    def _on_slider_value_changed(self, value: int):
        self.vol_val_label.setText(f"{value}")
        if not self.is_updating_ui:
            self.vol_timer.start()

    def update_volume_display(self, val: int):
        self.is_updating_ui = True
        try:
            self.vol_slider.setValue(val)
            self.vol_val_label.setText(str(val))
        finally:
            self.is_updating_ui = False

    def _dispatch_volume_change(self):
        val = self.vol_slider.value()
        self.tray_app.set_volume(val)

    def _on_mode_selected(self, index: int):
        if self.is_updating_ui or index < 0:
            return
        code = self.mode_combo.itemData(index)
        if code:
            self.tray_app.set_input_mode(code)

    def update_state(self, state: K17State):
        self.is_updating_ui = True
        try:
            if state.is_online:
                self.status_badge.setText("ONLINE")
                self.status_badge.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 10px;")
                self.vol_slider.setEnabled(True)
                self.mode_combo.setEnabled(True)
                self.retry_btn.setVisible(False)

                if state.volume is not None:
                    self.vol_slider.setValue(state.volume)
                    self.vol_val_label.setText(str(state.volume))

                if state.input_mode is not None:
                    target_code = state.input_mode.value.upper()
                    for idx in range(self.mode_combo.count()):
                        if self.mode_combo.itemData(idx).upper() == target_code:
                            self.mode_combo.setCurrentIndex(idx)
                            break
            else:
                self.status_badge.setText("OFFLINE")
                self.status_badge.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 10px;")
                self.vol_slider.setEnabled(False)
                self.mode_combo.setEnabled(False)
                self.vol_val_label.setText("--")
                self.retry_btn.setVisible(True)
        finally:
            self.is_updating_ui = False

    def closeEvent(self, event):
        # Intercept close button to hide to system tray instead of exiting app
        event.ignore()
        self.hide()

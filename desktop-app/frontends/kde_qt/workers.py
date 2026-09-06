"""
PyQt6 Worker Threads for non-blocking K17 controller operations.
"""
from PyQt6.QtCore import QThread, pyqtSignal
from core.controller import K17DeviceController, K17State
from core.constants import InputMode


class StatusWorker(QThread):
    finished = pyqtSignal(bool, object)

    def __init__(self, controller: K17DeviceController, force_resolve: bool = False):
        super().__init__()
        self.controller = controller
        self.force_resolve = force_resolve

    def run(self):
        success, state = self.controller.fetch_status(force_resolve=self.force_resolve)
        self.finished.emit(success, state)


class ModeWorker(QThread):
    finished = pyqtSignal(bool)

    def __init__(self, controller: K17DeviceController, mode: InputMode | str):
        super().__init__()
        self.controller = controller
        self.mode = mode

    def run(self):
        success = self.controller.set_input_mode(self.mode)
        self.finished.emit(success)


class VolumeWorker(QThread):
    finished = pyqtSignal(bool)

    def __init__(self, controller: K17DeviceController, val: int):
        super().__init__()
        self.controller = controller
        self.val = val

    def run(self):
        success = self.controller.set_volume(self.val)
        self.finished.emit(success)

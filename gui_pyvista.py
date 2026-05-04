import sys
import threading
from queue import Queue

import numpy as np
import pandas as pd

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import pyvista as pv
from pyvistaqt import QtInteractor

from data_source import SimulatedDataSource
from point_processing import statistical_outlier_removal


class DataThread(QObject):
    """Worker thread that continuously reads data points from the source."""

    point_ready = Signal(tuple)
    connected = Signal(bool)

    def __init__(self, data_source):
        super().__init__()
        self.data_source = data_source
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self.data_source.connect()
        self.connected.emit(True)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self.data_source.disconnect()
        self.connected.emit(False)
        if self._thread:
            self._thread.join(timeout=2)

    def _read_loop(self):
        while self._running:
            point = self.data_source.read_point()
            if point:
                self.point_ready.emit(point)
            else:
                threading.Event().wait(0.01)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('极简三维测量 — PyVista/Open3D 实时测量系统')
        self.resize(1500, 950)

        self.collected_points = []
        self.current_actor = None
        self.camera_initialized = False
        self.last_rendered_count = 0

        self.apply_dark_theme()

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        control_row = QHBoxLayout()
        control_row.setSpacing(8)

        self.btn_import = QPushButton('导入本地 CSV 文件')
        self.btn_import.clicked.connect(self.on_import)
        control_row.addWidget(self.btn_import)

        self.btn_start = QPushButton('开始测量')
        self.btn_start.setObjectName('startButton')
        self.btn_start.clicked.connect(self.on_start_measurement)
        control_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton('停止测量')
        self.btn_stop.setObjectName('stopButton')
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop_measurement)
        control_row.addWidget(self.btn_stop)

        self.btn_refresh_fit = QPushButton('刷新拟合')
        self.btn_refresh_fit.clicked.connect(self.on_refresh_fit)
        control_row.addWidget(self.btn_refresh_fit)

        self.chk_enable_sor = QCheckBox('启用 SOR 滤波')
        self.chk_enable_sor.setChecked(True)
        control_row.addWidget(self.chk_enable_sor)

        sor_group = QGroupBox('SOR 参数')
        sor_layout = QFormLayout(sor_group)
        sor_layout.setContentsMargins(10, 8, 10, 8)
        sor_layout.setSpacing(6)

        self.spin_nb_neighbors = QSpinBox()
        self.spin_nb_neighbors.setRange(5, 500)
        self.spin_nb_neighbors.setValue(30)
        self.spin_nb_neighbors.setSingleStep(5)
        sor_layout.addRow('邻居点数量', self.spin_nb_neighbors)

        self.spin_std_ratio = QDoubleSpinBox()
        self.spin_std_ratio.setRange(0.1, 10.0)
        self.spin_std_ratio.setDecimals(2)
        self.spin_std_ratio.setSingleStep(0.1)
        self.spin_std_ratio.setValue(1.5)
        sor_layout.addRow('标准差比率', self.spin_std_ratio)

        control_row.addWidget(sor_group)

        self.combo_preview_mode = QComboBox()
        self.combo_preview_mode.addItems(['实时点云', 'SOR 过滤后'])
        control_row.addWidget(self.combo_preview_mode)

        self.btn_export = QPushButton('导出图片')
        self.btn_export.clicked.connect(self.on_export)
        control_row.addWidget(self.btn_export)

        control_row.addStretch(1)
        root_layout.addLayout(control_row)

        self.label_info = QLabel('未加载数据 | 点云点数: 0')
        self.label_info.setObjectName('infoLabel')
        root_layout.addWidget(self.label_info)

        self.viewer = QtInteractor(central)
        self.viewer.set_background('#1a1a1a')
        self.viewer.add_axes()
        self.viewer.enable_trackball_style()
        root_layout.addWidget(self.viewer, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet('QStatusBar { background-color: #232323; color: #0FF; }')
        self.update_status('Ready')

        self.data_queue = Queue()
        self.data_source = SimulatedDataSource(self.data_queue, total_points=2000)
        self.data_thread = DataThread(self.data_source)
        self.data_thread.point_ready.connect(self.on_point_ready)
        self.data_thread.connected.connect(self.on_connected)

        self.init_viewer()

    def init_viewer(self):
        self.viewer.clear()
        self.viewer.set_background('#1a1a1a')
        self.viewer.add_axes()
        self.viewer.show_bounds(grid='front', color='#444444', location='outer')
        self.viewer.camera_position = 'iso'
        self.camera_initialized = False
        self.current_actor = None
        self.viewer.render()

    def on_connected(self, status):
        self.btn_start.setEnabled(not status)
        self.btn_stop.setEnabled(status)

    def on_start_measurement(self):
        self.collected_points = []
        self.last_rendered_count = 0
        self.init_viewer()

        self.btn_import.setEnabled(False)
        self.btn_refresh_fit.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_start.setEnabled(False)

        self.update_status('Measurement started...')
        self.data_thread.start()

    def on_stop_measurement(self):
        self.data_thread.stop()
        self.label_info.setText(f'测量已停止 | 点云点数: {len(self.collected_points)}')
        self.update_status(f'Measurement complete - {len(self.collected_points)} points collected')

        self.btn_import.setEnabled(True)
        self.btn_refresh_fit.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_start.setEnabled(True)

    def on_point_ready(self, point):
        self.collected_points.append(point)
        count = len(self.collected_points)

        if count % 100 == 0 or count == 1:
            self.render_point_cloud(self.collected_points, apply_sor=False, reset_camera=not self.camera_initialized)
            self.camera_initialized = True
            self.last_rendered_count = count

        self.label_info.setText(f'点云点数: {count} | 状态: 测量中...')
        self.update_status(f'Scanning... {count} points')

    def render_point_cloud(self, points, apply_sor=False, reset_camera=False):
        if not points:
            return

        array = np.asarray(points, dtype=np.float64)
        if array.ndim != 2 or array.shape[1] != 3:
            return

        if apply_sor and self.chk_enable_sor.isChecked():
            try:
                array = statistical_outlier_removal(
                    array,
                    nb_neighbors=self.spin_nb_neighbors.value(),
                    std_ratio=self.spin_std_ratio.value(),
                )
            except Exception as exc:
                self.update_status(f'SOR failed: {exc}')

        if len(array) == 0:
            return

        if self.current_actor is not None:
            try:
                self.viewer.remove_actor(self.current_actor)
            except Exception:
                pass

        cloud = pv.PolyData(array)
        cloud['z'] = array[:, 2]
        color_mode = 'z' if self.combo_preview_mode.currentIndex() == 0 or not apply_sor else 'z'

        self.current_actor = self.viewer.add_points(
            cloud,
            scalars=color_mode,
            cmap='turbo',
            point_size=4,
            render_points_as_spheres=False,
            emissive=True,
            reset_camera=reset_camera,
        )
        self.viewer.set_background('#1a1a1a')
        self.viewer.add_axes()
        self.viewer.render()

    def on_refresh_fit(self):
        if len(self.collected_points) < 10:
            self.label_info.setText('点数不足（需要 >=10）')
            self.update_status('Error: Insufficient points')
            return

        self.update_status('Applying SOR filter...')
        self.render_point_cloud(self.collected_points, apply_sor=True, reset_camera=True)
        filtered_count = len(self.collected_points)
        self.label_info.setText(f'已刷新拟合 | 点云点数: {filtered_count}')
        self.update_status(f'Surface fit complete - {filtered_count} points visualized')

    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 CSV 文件', '.', 'CSV Files (*.csv);;All Files (*)')
        if not path:
            return

        try:
            df = pd.read_csv(path)
        except Exception as exc:
            self.label_info.setText(f'读取失败: {exc}')
            self.update_status('Import failed')
            return

        if not {'x', 'y', 'z'}.issubset(df.columns):
            self.label_info.setText('CSV 必须包含列: x, y, z')
            self.update_status('Import failed: invalid columns')
            return

        self.collected_points = list(zip(df['x'], df['y'], df['z']))
        self.label_info.setText(f'已加载: {path}，共 {len(df)} 点')
        self.update_status(f'Imported: {path}')
        self.render_point_cloud(self.collected_points, apply_sor=True, reset_camera=True)

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存图片', 'point_cloud.png', 'PNG Files (*.png);;All Files (*)')
        if not path:
            return

        try:
            self.viewer.screenshot(path)
            self.label_info.setText(f'已导出图片: {path}')
            self.update_status(f'Exported: {path}')
        except Exception as exc:
            self.label_info.setText(f'导出失败: {exc}')
            self.update_status('Export failed')

    def update_status(self, message):
        self.status_bar.showMessage(f'[{message}]')

    def apply_dark_theme(self):
        dark_stylesheet = """
        QMainWindow, QWidget {
            background-color: #1a1a1a;
            color: #d7ffff;
            font-family: Segoe UI;
            font-size: 10pt;
        }
        QLabel {
            color: #d7ffff;
        }
        QLabel#infoLabel {
            color: #0FF;
            font-weight: 600;
        }
        QPushButton {
            background-color: #303030;
            color: #d7ffff;
            border: 1px solid #4a4a4a;
            border-radius: 4px;
            padding: 7px 12px;
            min-height: 26px;
        }
        QPushButton:hover {
            background-color: #3a3a3a;
            border-color: #0FF;
        }
        QPushButton:pressed {
            background-color: #222222;
        }
        QPushButton:disabled {
            background-color: #242424;
            color: #777777;
            border-color: #444444;
        }
        QPushButton#startButton {
            background-color: #0a7a2f;
            color: #ffffff;
            border: 1px solid #20c45b;
        }
        QPushButton#startButton:hover {
            background-color: #10933a;
        }
        QPushButton#stopButton {
            background-color: #8c1d1d;
            color: #ffffff;
            border: 1px solid #ff5656;
        }
        QPushButton#stopButton:hover {
            background-color: #b32525;
        }
        QGroupBox {
            color: #0FF;
            border: 1px solid #444444;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QCheckBox {
            color: #d7ffff;
            spacing: 6px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            border-radius: 2px;
            border: 1px solid #0FF;
            background: #2a2a2a;
        }
        QCheckBox::indicator:checked {
            background: #0FF;
        }
        QSpinBox, QDoubleSpinBox, QComboBox {
            background-color: #262626;
            color: #d7ffff;
            border: 1px solid #4a4a4a;
            border-radius: 4px;
            padding: 4px 6px;
            selection-background-color: #0FF;
            selection-color: #000000;
            min-height: 22px;
        }
        QComboBox::drop-down {
            border: 0px;
            width: 20px;
            background: #313131;
        }
        QComboBox QAbstractItemView {
            background-color: #202020;
            color: #d7ffff;
            selection-background-color: #0FF;
            selection-color: #000000;
        }
        QStatusBar {
            background-color: #232323;
            color: #0FF;
            border-top: 1px solid #444444;
        }
        """
        QApplication.instance().setStyleSheet(dark_stylesheet)

    def closeEvent(self, event):
        try:
            self.data_thread.stop()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

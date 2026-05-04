from __future__ import annotations

import sys
import threading
from pathlib import Path
from queue import Queue

import numpy as np
import pandas as pd
from scipy.interpolate import griddata

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItemIterator,
    QTreeWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import pyvista as pv
from pyvistaqt import QtInteractor

from data_source import SimulatedDataSource
from point_processing import statistical_outlier_removal

try:
    import open3d as o3d
except Exception as exc:  # pragma: no cover - GUI import fallback
    o3d = None
    OPEN3D_IMPORT_ERROR = exc
else:
    OPEN3D_IMPORT_ERROR = None


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE_DIR = PROJECT_DIR.parent / 'PCD-PCL-main' / 'PCD-PCL-main'
SUPPORTED_POINT_EXTENSIONS = {'.csv', '.ply', '.pcd', '.xyz'}
GROOVE_DEPTH_TARGET_MM = 3.0
GROOVE_WIDTH_TARGET_MM = 10.0


class DataThread(QObject):
    """Background reader that forwards point tuples to the GUI thread."""

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
            if point is not None:
                self.point_ready.emit(point)
            else:
                threading.Event().wait(0.01)


def ensure_point_array(points) -> np.ndarray:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError('point cloud must be Nx3')
    return array


def load_point_cloud_file(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == '.csv':
        df = pd.read_csv(path)
        if {'x', 'y', 'z'}.issubset(df.columns):
            array = df[['x', 'y', 'z']].to_numpy(dtype=np.float64)
        elif df.shape[1] >= 3:
            array = df.iloc[:, :3].to_numpy(dtype=np.float64)
        else:
            raise ValueError('CSV must contain x, y, z columns or at least 3 columns')
        return ensure_point_array(array)

    if suffix in {'.ply', '.pcd', '.xyz'}:
        if o3d is None:
            raise RuntimeError(f'Open3D is not available: {OPEN3D_IMPORT_ERROR}')
        cloud = o3d.io.read_point_cloud(str(path))
        array = np.asarray(cloud.points, dtype=np.float64)
        return ensure_point_array(array)

    raise ValueError(f'unsupported file type: {path.suffix}')


def scan_point_files(directory: Path):
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.suffix.lower() in SUPPORTED_POINT_EXTENSIONS:
            yield path


def load_point_cloud_directory(directory: Path) -> list[Path]:
    files = list(scan_point_files(directory))
    if not files:
        raise ValueError('directory does not contain supported point cloud files')
    return files


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('灵寻巧度 · 玉尺系列 | CMM Desktop Suite')
        self.resize(1680, 980)
        self.setDockNestingEnabled(True)

        self.collected_points: list[tuple[float, float, float]] = []
        self.current_array = np.empty((0, 3), dtype=np.float64)
        self.current_surface = None
        self.current_actor = None
        self.probe_actor = None
        self.camera_initialized = False
        self.current_source_path: Path | None = None
        self.current_mode = 'points'
        self.dataset_files: dict[str, Path] = {}
        self._busy_depth = 0

        self.data_queue = Queue()
        self.data_source = SimulatedDataSource(self.data_queue, total_points=2000)
        self.data_thread = DataThread(self.data_source)
        self.data_thread.point_ready.connect(self.on_point_ready)
        self.data_thread.connected.connect(self.on_connected)

        self._build_actions()
        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._apply_theme()
        self._build_default_tree()
        self._update_properties('系统就绪', {
            '单位': 'mm',
            '显示模式': '点云',
            '数据源': '未加载',
        })
        self._log('系统已启动，等待导入点云或开始测量。')

    def _build_actions(self):
        self.action_import_file = QAction('导入点云文件', self)
        self.action_import_file.triggered.connect(self.on_import_file)

        self.action_import_directory = QAction('导入点云目录', self)
        self.action_import_directory.triggered.connect(self.on_import_directory)

        self.action_open_sample_dir = QAction('打开 PCD-PCL 示例目录', self)
        self.action_open_sample_dir.triggered.connect(self.on_open_sample_directory)

        self.action_start = QAction('开始测量', self)
        self.action_start.triggered.connect(self.on_start_measurement)

        self.action_stop = QAction('停止测量', self)
        self.action_stop.triggered.connect(self.on_stop_measurement)
        self.action_stop.setEnabled(False)

        self.action_refresh = QAction('刷新拟合', self)
        self.action_refresh.triggered.connect(self.on_refresh_fit)

        self.action_surface_mode = QAction('曲面预览', self)
        self.action_surface_mode.setCheckable(True)
        self.action_surface_mode.triggered.connect(self.on_toggle_surface_mode)

        self.action_clear = QAction('清空场景', self)
        self.action_clear.triggered.connect(self.clear_scene)

        self.action_export = QAction('导出截图', self)
        self.action_export.triggered.connect(self.on_export)

        self.action_home = QAction('回原点', self)
        self.action_home.triggered.connect(self.reset_camera)

        self.action_exit = QAction('退出', self)
        self.action_exit.triggered.connect(self.close)

    def _build_ui(self):
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        viewport_frame = QFrame(central)
        viewport_frame.setObjectName('ViewportFrame')
        viewport_layout = QVBoxLayout(viewport_frame)
        viewport_layout.setContentsMargins(0, 0, 0, 0)

        self.viewer = QtInteractor(viewport_frame)
        self.viewer.set_background('#1b1f23')
        viewport_layout.addWidget(self.viewer)

        central_layout.addWidget(viewport_frame)
        self.setCentralWidget(central)

        self._build_left_dock()
        self._build_right_dock()
        self._build_bottom_dock()

        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_progress = QProgressBar(self)
        self.status_progress.setRange(0, 100)
        self.status_progress.setValue(0)
        self.status_bar.addPermanentWidget(self.status_progress, 1)
        self.status_label = QLabel('Ready', self)
        self.status_bar.addPermanentWidget(self.status_label, 0)

        self._init_viewer()

    def _build_left_dock(self):
        self.left_tree = QTreeWidget(self)
        self.left_tree.setHeaderLabels(['测量树', '状态'])
        self.left_tree.itemSelectionChanged.connect(self.on_tree_selection_changed)

        self.left_dock = QDockWidget('Measurement Tree', self)
        self.left_dock.setWidget(self.left_tree)
        self.left_dock.setObjectName('leftDock')
        self.left_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)

    def _build_right_dock(self):
        self.property_panel = QWidget(self)
        form = QFormLayout(self.property_panel)
        form.setLabelAlignment(Qt.AlignLeft)
        self.property_labels = {}
        for key in ['数据源', '文件名', '点数', 'X 范围', 'Y 范围', 'Z 范围', 'Z 均值', 'Z 标准差', '合格判定']:
            label = QLabel('-', self.property_panel)
            label.setWordWrap(True)
            self.property_labels[key] = label
            form.addRow(f'{key}：', label)

        self.measurement_labels = {}
        for key in ['基准平面', '凹槽底面', '当前槽深', '当前槽宽', '槽深公差', '槽宽公差']:
            label = QLabel('-', self.property_panel)
            label.setWordWrap(True)
            self.measurement_labels[key] = label
            form.addRow(f'{key}：', label)

        self.property_dock = QDockWidget('Property Manager', self)
        self.property_dock.setWidget(self.property_panel)
        self.property_dock.setObjectName('propertyDock')
        self.property_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self.property_dock)

    def _build_bottom_dock(self):
        bottom_widget = QWidget(self)
        splitter = QSplitter(Qt.Horizontal, bottom_widget)
        splitter.setChildrenCollapsible(False)

        left_box = QGroupBox('任务列表', bottom_widget)
        left_box.setMinimumHeight(160)
        left_layout = QVBoxLayout(left_box)
        self.task_list = QListWidget(left_box)
        self.task_list.setMinimumWidth(220)
        left_layout.addWidget(self.task_list)

        right_box = QGroupBox('控制台', bottom_widget)
        right_box.setMinimumHeight(160)
        right_layout = QVBoxLayout(right_box)
        self.console = QTextEdit(right_box)
        self.console.setReadOnly(True)
        self.console.setMinimumWidth(360)
        right_layout.addWidget(self.console)

        splitter.addWidget(left_box)
        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([320, 520])

        layout = QVBoxLayout(bottom_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        bottom_widget.setMinimumHeight(240)

        self.bottom_dock = QDockWidget('任务 / 控制台', self)
        self.bottom_dock.setWidget(bottom_widget)
        self.bottom_dock.setObjectName('bottomDock')
        self.bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.bottom_dock.setMinimumHeight(260)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)

    def _build_menus(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu('文件')
        file_menu.addAction(self.action_import_file)
        file_menu.addAction(self.action_import_directory)
        file_menu.addAction(self.action_open_sample_dir)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export)
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)

        measurement_menu = menu_bar.addMenu('测量')
        measurement_menu.addAction(self.action_start)
        measurement_menu.addAction(self.action_stop)
        measurement_menu.addAction(self.action_refresh)
        measurement_menu.addAction(self.action_surface_mode)
        measurement_menu.addAction(self.action_clear)

        view_menu = menu_bar.addMenu('视图')
        view_menu.addAction(self.left_dock.toggleViewAction())
        view_menu.addAction(self.property_dock.toggleViewAction())
        view_menu.addAction(self.bottom_dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction(self.action_home)

        help_menu = menu_bar.addMenu('帮助')
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.on_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self):
        toolbar = QToolBar('主工具栏', self)
        toolbar.setMovable(True)
        toolbar.setFloatable(True)
        toolbar.addAction(self.action_import_file)
        toolbar.addAction(self.action_import_directory)
        toolbar.addSeparator()
        toolbar.addAction(self.action_start)
        toolbar.addAction(self.action_stop)
        toolbar.addAction(self.action_refresh)
        toolbar.addAction(self.action_surface_mode)
        toolbar.addSeparator()
        toolbar.addAction(self.action_home)
        toolbar.addAction(self.action_export)
        toolbar.addAction(self.action_clear)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

    def _apply_theme(self):
        app = QApplication.instance()
        if app is None:
            return

        font = QFont('Segoe UI', 10)
        app.setFont(font)
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor('#1f2329'))
        palette.setColor(QPalette.WindowText, QColor('#e6eef7'))
        palette.setColor(QPalette.Base, QColor('#171a1f'))
        palette.setColor(QPalette.AlternateBase, QColor('#21262d'))
        palette.setColor(QPalette.ToolTipBase, QColor('#f5f7fa'))
        palette.setColor(QPalette.ToolTipText, QColor('#101214'))
        palette.setColor(QPalette.Text, QColor('#e6eef7'))
        palette.setColor(QPalette.Button, QColor('#2a3038'))
        palette.setColor(QPalette.ButtonText, QColor('#e6eef7'))
        palette.setColor(QPalette.Highlight, QColor('#00d6c9'))
        palette.setColor(QPalette.HighlightedText, QColor('#101214'))
        app.setPalette(palette)

        app.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #1f2329;
                color: #e6eef7;
                font-family: Segoe UI;
                font-size: 10pt;
            }
            QMenuBar {
                background: #1b1f24;
                color: #e6eef7;
                border-bottom: 1px solid #2f363d;
            }
            QMenuBar::item:selected {
                background: #2f363d;
            }
            QMenu {
                background-color: #1b1f24;
                color: #e6eef7;
                border: 1px solid #2f363d;
            }
            QMenu::item:selected {
                background-color: #00d6c9;
                color: #101214;
            }
            QToolBar {
                background: #1b1f24;
                border-bottom: 1px solid #2f363d;
                spacing: 6px;
                padding: 4px;
            }
            QDockWidget {
                titlebar-close-icon: none;
                titlebar-normal-icon: none;
            }
            QDockWidget::title {
                background: #232830;
                padding: 6px;
                border-bottom: 1px solid #2f363d;
            }
            QTreeWidget, QListWidget, QTextEdit, QGroupBox, QFrame#ViewportFrame {
                background-color: #171a1f;
                border: 1px solid #2f363d;
                border-radius: 4px;
            }
            QLabel[toleranceState='pass'] {
                color: #4de27a;
                font-weight: 600;
            }
            QLabel[toleranceState='warn'] {
                color: #ff7070;
                font-weight: 600;
            }
            QTreeWidget::item:selected, QListWidget::item:selected {
                background-color: #00d6c9;
                color: #101214;
            }
            QLabel {
                color: #e6eef7;
            }
            QPushButton {
                background-color: #2a3038;
                color: #e6eef7;
                border: 1px solid #3c4651;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                border-color: #00d6c9;
            }
            QStatusBar {
                background: #1b1f24;
                color: #00d6c9;
                border-top: 1px solid #2f363d;
            }
            """
        )

    def _build_default_tree(self):
        self.left_tree.clear()
        self.hardware_root = QTreeWidgetItem(['设备状态', '在线'])
        self.coordinate_root = QTreeWidgetItem(['坐标系', 'WCS'])
        self.dataset_root = QTreeWidgetItem(['点云数据集', '未加载'])
        self.feature_root = QTreeWidgetItem(['特征清单', '待分析'])

        self.left_tree.addTopLevelItem(self.hardware_root)
        self.left_tree.addTopLevelItem(self.coordinate_root)
        self.left_tree.addTopLevelItem(self.dataset_root)
        self.left_tree.addTopLevelItem(self.feature_root)
        self.left_tree.expandAll()

    def _init_viewer(self):
        self.viewer.clear()
        self.viewer.set_background('#1b1f23')
        self.viewer.add_axes()
        self.viewer.show_bounds(grid='front', color='#40464f', location='outer')
        self.viewer.view_isometric()
        self.viewer.render()

    def _log(self, message: str):
        self.console.append(f'[INFO] {message}')
        self.status_label.setText(message)

    def _set_busy(self, message: str):
        self._busy_depth += 1
        if self._busy_depth == 1:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        self.status_label.setText(message)
        self.console.append(f'[INFO] {message}')
        QApplication.processEvents()

    def _clear_busy(self):
        if self._busy_depth > 0:
            self._busy_depth -= 1
        if self._busy_depth == 0:
            QApplication.restoreOverrideCursor()
        QApplication.processEvents()

    def _add_task(self, message: str):
        self.task_list.addItem(message)
        self.task_list.scrollToBottom()

    def _stats_from_array(self, array: np.ndarray) -> dict[str, str]:
        if len(array) == 0:
            return {
                '数据源': '-',
                '文件名': '-',
                '点数': '0',
                'X 范围': '-',
                'Y 范围': '-',
                'Z 范围': '-',
                'Z 均值': '-',
                'Z 标准差': '-',
                '合格判定': '不合格',
            }

        x_min, y_min, z_min = np.min(array, axis=0)
        x_max, y_max, z_max = np.max(array, axis=0)
        z_mean = float(np.mean(array[:, 2]))
        z_std = float(np.std(array[:, 2]))
        count = len(array)
        pass_flag = count >= 10 and np.isfinite(z_std)

        return {
            '数据源': str(self.current_source_path) if self.current_source_path else '实时测量/模拟源',
            '文件名': self.current_source_path.name if self.current_source_path else '实时采集',
            '点数': f'{count}',
            'X 范围': f'{x_min:.3f} ~ {x_max:.3f} mm',
            'Y 范围': f'{y_min:.3f} ~ {y_max:.3f} mm',
            'Z 范围': f'{z_min:.3f} ~ {z_max:.3f} mm',
            'Z 均值': f'{z_mean:.3f} mm',
            'Z 标准差': f'{z_std:.3f} mm',
            '合格判定': '合格' if pass_flag else '警告',
        }

    def _analyze_groove(self, array: np.ndarray) -> dict[str, float | str]:
        if len(array) == 0:
            return {
                'base_plane': '-',
                'groove_floor': '-',
                'depth': '-',
                'width': '-',
                'depth_state': 'warn',
                'width_state': 'warn',
            }

        z = array[:, 2]
        x = array[:, 0]

        base_plane = float(np.percentile(z, 90))
        groove_floor = float(np.percentile(z, 10))
        depth = base_plane - groove_floor
        groove_mask = z <= (base_plane - depth * 0.5)

        if np.any(groove_mask):
            width = float(np.max(x[groove_mask]) - np.min(x[groove_mask]))
        else:
            width = 0.0

        depth_ok = abs(depth - GROOVE_DEPTH_TARGET_MM) <= 0.15
        width_ok = abs(width - GROOVE_WIDTH_TARGET_MM) <= 0.5
        return {
            'base_plane': f'{base_plane:.3f} mm',
            'groove_floor': f'{groove_floor:.3f} mm',
            'depth': f'{depth:.3f} mm',
            'width': f'{width:.3f} mm',
            'depth_state': 'pass' if depth_ok else 'warn',
            'width_state': 'pass' if width_ok else 'warn',
        }

    def _set_measurement_labels(self, analysis: dict[str, float | str]):
        for key, value in {
            '基准平面': analysis['base_plane'],
            '凹槽底面': analysis['groove_floor'],
            '当前槽深': analysis['depth'],
            '当前槽宽': analysis['width'],
        }.items():
            self.measurement_labels[key].setText(str(value))

        self.measurement_labels['槽深公差'].setText('合格' if analysis['depth_state'] == 'pass' else '超差')
        self.measurement_labels['槽宽公差'].setText('合格' if analysis['width_state'] == 'pass' else '超差')
        self.measurement_labels['槽深公差'].setProperty('toleranceState', analysis['depth_state'])
        self.measurement_labels['槽宽公差'].setProperty('toleranceState', analysis['width_state'])
        for label in (self.measurement_labels['槽深公差'], self.measurement_labels['槽宽公差']):
            label.style().unpolish(label)
            label.style().polish(label)
            label.update()

    def _update_measurement_panel(self, array: np.ndarray):
        analysis = self._analyze_groove(array)
        self._set_measurement_labels(analysis)
        return analysis

    def _update_properties(self, title: str, values: dict[str, str]):
        for key, label in self.property_labels.items():
            label.setText(values.get(key, '-'))
        self._refresh_tree_status(title, values)

    def _refresh_tree_status(self, title: str, values: dict[str, str]):
        self.hardware_root.setText(1, '在线' if self.data_source.is_connected() else '离线')
        self.coordinate_root.setText(1, 'WCS / mm')
        self.dataset_root.setText(1, values.get('文件名', '未加载'))
        self.feature_root.setText(1, title)

    def _load_file_into_tree(self, path: Path):
        item = QTreeWidgetItem([path.name, path.suffix.lower().lstrip('.')])
        item.setData(0, Qt.UserRole, str(path))
        self.dataset_root.addChild(item)
        self.dataset_root.setExpanded(True)
        self.dataset_files[path.name] = path

    def _select_tree_item_by_path(self, path: Path):
        iterator = QTreeWidgetItemIterator(self.left_tree)
        while iterator.value():
            item = iterator.value()
            stored = item.data(0, Qt.UserRole)
            if stored == str(path):
                self.left_tree.setCurrentItem(item)
                return
            iterator += 1

    def _render_points(self, points, reset_camera: bool = False):
        array = ensure_point_array(points)
        self.current_array = array
        self.viewer.clear()
        self.viewer.set_background('#1b1f23')
        self.viewer.add_axes()
        self.viewer.show_bounds(grid='front', color='#40464f', location='outer')

        if len(array) == 0:
            self.viewer.render()
            return

        cloud = pv.PolyData(array)
        cloud['z'] = array[:, 2]

        if self.current_mode == 'surface' and len(array) >= 3:
            try:
                x_min, y_min = np.min(array[:, :2], axis=0)
                x_max, y_max = np.max(array[:, :2], axis=0)
                xi = np.linspace(x_min, x_max, 120)
                yi = np.linspace(y_min, y_max, 120)
                grid_x, grid_y = np.meshgrid(xi, yi)
                grid_z = griddata(
                    (array[:, 0], array[:, 1]),
                    array[:, 2],
                    (grid_x, grid_y),
                    method='cubic',
                )
                if np.isnan(grid_z).any():
                    nearest_z = griddata(
                        (array[:, 0], array[:, 1]),
                        array[:, 2],
                        (grid_x, grid_y),
                        method='nearest',
                    )
                    grid_z = np.where(np.isnan(grid_z), nearest_z, grid_z)
                mesh = pv.StructuredGrid(grid_x, grid_y, grid_z)
                mesh['height'] = grid_z.ravel()
                self.current_surface = mesh
                self.viewer.add_mesh(mesh, scalars='height', cmap='turbo', opacity=0.92, show_scalar_bar=True)
            except Exception as exc:
                self._log(f'曲面拟合失败，回退为点云显示：{exc}')
                self.current_mode = 'points'
                self.action_surface_mode.setChecked(False)
                self.viewer.add_points(cloud, scalars='z', cmap='turbo', point_size=4, render_points_as_spheres=False)
        else:
            self.current_surface = None
            self.viewer.add_points(cloud, scalars='z', cmap='turbo', point_size=4, render_points_as_spheres=False)

        if len(array) > 0:
            probe = pv.Sphere(radius=max(float(np.ptp(array[:, 0])), 1.0) * 0.01, center=array[-1])
            self.probe_actor = self.viewer.add_mesh(probe, color='#ff4d4d', specular=0.6)

        if reset_camera or not self.camera_initialized:
            self.viewer.reset_camera()
        self.viewer.render()
        self.camera_initialized = True

    def _load_points_from_path(self, path: Path, update_tree: bool = True):
        try:
            self._set_busy(f'正在加载点云: {path.name}')
            array = load_point_cloud_file(path)
        except Exception as exc:
            QMessageBox.critical(self, '导入失败', f'无法读取文件：{path}\n\n{exc}')
            self._log(f'导入失败：{path} -> {exc}')
            self._clear_busy()
            return
        finally:
            if self._busy_depth:
                self._clear_busy()

        self.current_source_path = path
        self.collected_points = [tuple(point) for point in array.tolist()]
        if update_tree:
            self._load_file_into_tree(path)
        self._set_busy('正在更新三维视图与槽特征测算...')
        self._render_points(self.collected_points, reset_camera=True)

        values = self._stats_from_array(array)
        self._update_properties('点云导入', values)
        analysis = self._update_measurement_panel(array)
        self.status_progress.setValue(100)
        self._add_task(f'加载 {path.name}')
        self._log(
            f'已导入 {path.name}，共 {len(array)} 个点。槽深 {analysis["depth"]}，槽宽 {analysis["width"]}。'
        )
        self._clear_busy()

    def on_tree_selection_changed(self):
        items = self.left_tree.selectedItems()
        if not items:
            return

        item = items[0]
        stored = item.data(0, Qt.UserRole)
        if stored:
            path = Path(stored)
            if path.exists():
                self._load_points_from_path(path, update_tree=False)
                return

        if item is self.hardware_root:
            self._update_properties('设备状态', {
                '数据源': '模拟/硬件抽象层',
                '文件名': '-',
                '点数': str(len(self.collected_points)),
                'X 范围': '-',
                'Y 范围': '-',
                'Z 范围': '-',
                'Z 均值': '-',
                'Z 标准差': '-',
                '合格判定': '在线' if self.data_source.is_connected() else '离线',
            })

    def on_import_file(self):
        start_dir = str(DEFAULT_SAMPLE_DIR if DEFAULT_SAMPLE_DIR.exists() else PROJECT_DIR)
        path, _ = QFileDialog.getOpenFileName(
            self,
            '导入点云文件',
            start_dir,
            'Point Clouds (*.csv *.ply *.pcd *.xyz);;CSV Files (*.csv);;All Files (*)',
        )
        if not path:
            return
        self._load_points_from_path(Path(path))

    def on_import_directory(self):
        start_dir = str(DEFAULT_SAMPLE_DIR if DEFAULT_SAMPLE_DIR.exists() else PROJECT_DIR)
        directory = QFileDialog.getExistingDirectory(self, '导入点云目录', start_dir)
        if not directory:
            return

        self._load_directory_into_tree(Path(directory))

    def _load_directory_into_tree(self, directory_path: Path):
        try:
            files = load_point_cloud_directory(directory_path)
        except Exception as exc:
            QMessageBox.information(self, '未找到点云', '该目录中没有可识别的 CSV/PLY/PCD/XYZ 文件。')
            self._log(f'目录扫描失败：{directory_path} -> {exc}')
            return

        self.dataset_root.setText(1, directory_path.name)
        self.dataset_root.setExpanded(True)
        self.dataset_files.clear()
        self.dataset_root.takeChildren()

        for file_path in files:
            self._load_file_into_tree(file_path)

        self.left_tree.expandAll()
        self.left_tree.setCurrentItem(self.dataset_root.child(0))
        self._log(f'已扫描目录 {directory_path}，找到 {len(files)} 个点云文件。')
        self._add_task(f'目录导入 {directory_path.name}')

    def on_open_sample_directory(self):
        directory = DEFAULT_SAMPLE_DIR if DEFAULT_SAMPLE_DIR.exists() else PROJECT_DIR
        self._log(f'示例目录：{directory}')
        self._load_directory_into_tree(directory)

    def on_start_measurement(self):
        self.clear_scene(keep_tree=True)
        self.collected_points = []
        self.current_source_path = None
        self.action_start.setEnabled(False)
        self.action_stop.setEnabled(True)
        self.status_progress.setValue(0)
        self._add_task('开始测量')
        self._log('开始测量，采集线程已启动。')
        self.data_thread.start()

    def on_stop_measurement(self):
        self.data_thread.stop()
        self.action_start.setEnabled(True)
        self.action_stop.setEnabled(False)
        self.status_progress.setValue(100 if self.collected_points else 0)
        self._add_task('停止测量')
        self._log(f'测量结束，共采集 {len(self.collected_points)} 个点。')

    def on_connected(self, status: bool):
        self.action_start.setEnabled(not status)
        self.action_stop.setEnabled(status)
        self.hardware_root.setText(1, '在线' if status else '离线')

    def on_point_ready(self, point):
        self.collected_points.append(tuple(point))
        count = len(self.collected_points)

        if count == 1 or count % 50 == 0:
            self._render_points(self.collected_points, reset_camera=(count == 1 and not self.camera_initialized))

        if count % 20 == 0:
            self.status_progress.setValue(min(100, count % 100))

        if count == 1 or count % 10 == 0:
            self._log(f'接收到点：({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f}) mm')

        if count % 200 == 0:
            analysis = self._update_measurement_panel(np.asarray(self.collected_points, dtype=np.float64))
            self._log(f'实时测算：槽深 {analysis["depth"]}，槽宽 {analysis["width"]}')

    def on_refresh_fit(self):
        if len(self.collected_points) < 10:
            QMessageBox.information(self, '点数不足', '刷新拟合至少需要 10 个点。')
            self._log('拟合失败：点数不足。')
            return

        array = ensure_point_array(self.collected_points)
        filtered = array
        try:
            self._set_busy('正在进行滤波计算...')
            filtered = statistical_outlier_removal(array, nb_neighbors=30, std_ratio=1.5)
        except Exception as exc:
            self._log(f'Open3D 滤波失败，继续使用原始点云：{exc}')
        finally:
            self._clear_busy()

        self.current_mode = 'surface'
        self.action_surface_mode.setChecked(True)
        self._set_busy('正在刷新拟合曲面...')
        self._render_points(filtered, reset_camera=True)
        self.collected_points = [tuple(point) for point in filtered.tolist()]
        self._update_properties('曲面拟合', self._stats_from_array(filtered))
        self._update_measurement_panel(filtered)
        self._add_task('刷新拟合')
        self._log(f'曲面拟合完成，显示 {len(filtered)} 个点。')
        self._clear_busy()

    def on_toggle_surface_mode(self, checked: bool):
        self.current_mode = 'surface' if checked else 'points'
        if self.collected_points:
            self._render_points(self.collected_points, reset_camera=False)
        self._log('显示模式切换为曲面预览。' if checked else '显示模式切换为点云预览。')

    def clear_scene(self, keep_tree: bool = False):
        self.collected_points = []
        self.current_array = np.empty((0, 3), dtype=np.float64)
        self.current_surface = None
        self.current_actor = None
        self.probe_actor = None
        self.camera_initialized = False
        self.viewer.clear()
        self._init_viewer()
        self.status_progress.setValue(0)
        if not keep_tree:
            self._build_default_tree()
            self.dataset_files.clear()
        self._update_properties('场景已清空', {
            '数据源': '-',
            '文件名': '-',
            '点数': '0',
            'X 范围': '-',
            'Y 范围': '-',
            'Z 范围': '-',
            'Z 均值': '-',
            'Z 标准差': '-',
            '合格判定': '-',
        })
        self._log('场景已清空。')

    def reset_camera(self):
        self.viewer.view_isometric()
        self.viewer.render()
        self._log('相机已重置到等轴视图。')

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            '导出截图',
            'cmm_view.png',
            'PNG Files (*.png);;All Files (*)',
        )
        if not path:
            return
        try:
            self.viewer.screenshot(path)
            self._log(f'已导出截图：{path}')
            self._add_task('导出截图')
        except Exception as exc:
            QMessageBox.critical(self, '导出失败', str(exc))
            self._log(f'导出失败：{exc}')

    def on_about(self):
        QMessageBox.information(
            self,
            '关于',
            '灵寻巧度 · 玉尺系列\nCMM Desktop Suite\n\n支持 CSV / PLY / PCD / XYZ 点云导入，以及模拟测量与曲面拟合。',
        )

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

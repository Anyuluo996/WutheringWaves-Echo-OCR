"""
主窗口模块
PySide6 GUI 界面
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut, QPixmap, QImage
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QTextEdit,
    QSpinBox, QGroupBox, QMessageBox, QFileDialog
)
import yaml

from core.data_manager import DataManager
from core.calculator import EchoCalculator
from core.ocr_parser import EchoOCRParser
from core.screenshot import ScreenshotTool
from core.hotkey_manager import GlobalHotkeyManager  # 导入全局热键管理器
from gui.screenshot_selector import ScreenshotSelector
from gui.snipping_widget import SnippingWidget
from gui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class ScreenshotThread(QThread):
    """截图线程"""
    finished = Signal(object)  # PIL Image

    def __init__(self):
        super().__init__()
        self.tool = ScreenshotTool()

    def run(self):
        """执行截图"""
        img = self.tool.capture_fullscreen(save=True)
        self.finished.emit(img)


class OCRThread(QThread):
    """OCR 线程"""
    finished = Signal(dict)

    def __init__(self, pil_image):
        super().__init__()
        self.pil_image = pil_image
        # 延迟导入，避免 DLL 冲突
        from core.ocr_engine import OCREngine
        self.ocr_engine = OCREngine()

    def run(self):
        """执行 OCR 识别"""
        try:
            # 检查 OCR 是否可用
            if not self.ocr_engine.is_available():
                self.finished.emit({
                    "success": False,
                    "error": "OCR 模型未加载，请下载模型文件到 models/ 目录"
                })
                return

            # 动态导入 cv2 和 np
            import cv2
            import numpy as np

            # 转换 PIL Image 到 OpenCV 格式
            img_cv = cv2.cvtColor(np.array(self.pil_image), cv2.COLOR_RGB2BGR)
            results = self.ocr_engine.recognize(img_cv)

            # 解析 OCR 结果
            parser = EchoOCRParser()
            parsed = parser.parse(results)

            self.finished.emit({"success": True, "parsed": parsed, "raw": results})
        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            self.finished.emit({"success": False, "error": str(e)})


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.data_manager = DataManager()
        self.calculator = EchoCalculator()
        self.config = self._load_config()
        self.screenshot_tool = ScreenshotTool()
        self.ocr_parser = EchoOCRParser()

        # 初始化全局热键管理器
        self.hotkey_manager = GlobalHotkeyManager()
        self.hotkey_manager.triggered.connect(self._on_hotkey_triggered)

        # 延迟导入 OCREngine，避免 DLL 冲突
        from core.ocr_engine import OCREngine
        self.ocr_engine = OCREngine()

        # 启用拖拽
        self.setAcceptDrops(True)

        self._init_ui()
        self._setup_hotkeys()
        self._check_ocr_status()

    def _load_config(self) -> dict:
        """加载配置文件"""
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        default_config = {
            "window": {"width": 800, "height": 600, "remember_position": False},
            "hotkeys": {"screenshot": "Ctrl+Shift+A", "ocr": "Ctrl+Shift+S"},
            "ocr": {"dpi_aware": True, "timeout": 5000},
            "default_role": "今汐"
        }

        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or default_config
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")

        return default_config

    def _init_ui(self):
        """初始化 UI"""
        self.setWindowTitle("WutheringWaves-Echo-OCR - 鸣潮声骸评分工具")
        self._apply_dpi_scaling()

        # 主窗口尺寸
        window_config = self.config.get("window", {})
        self.resize(window_config.get("width", 800), window_config.get("height", 600))

        # 中心组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 角色选择区
        main_layout.addWidget(self._create_role_section())

        # 声骸信息区
        main_layout.addWidget(self._create_echo_section())

        # 操作按钮区
        main_layout.addWidget(self._create_action_section())

        # 结果显示区
        main_layout.addWidget(self._create_result_section())

        # 状态栏
        self.statusBar().showMessage("就绪")

    def _apply_dpi_scaling(self):
        """应用 DPI 缩放"""
        if self.config.get("ocr", {}).get("dpi_aware", True):
            from PySide6.QtWidgets import QApplication
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )

    def _create_role_section(self) -> QGroupBox:
        """创建角色选择区"""
        group = QGroupBox("角色选择")
        layout = QHBoxLayout()

        self.role_combo = QComboBox()
        self._load_roles()

        layout.addWidget(QLabel("选择角色:"))
        layout.addWidget(self.role_combo)
        group.setLayout(layout)

        return group

    def _create_echo_section(self) -> QGroupBox:
        """创建声骸信息区"""
        group = QGroupBox("声骸信息")
        layout = QVBoxLayout()

        # 成本选择
        cost_layout = QHBoxLayout()
        cost_layout.addWidget(QLabel("声骸成本:"))
        self.cost_spin = QSpinBox()
        self.cost_spin.setRange(1, 4)
        self.cost_spin.setValue(4)
        self.cost_spin.setSuffix("c")
        cost_layout.addWidget(self.cost_spin)
        layout.addLayout(cost_layout)

        # 主词条输入
        layout.addWidget(QLabel("主词条属性:"))
        self.main_prop_input = QTextEdit()
        self.main_prop_input.setMaximumHeight(50)
        self.main_prop_input.setPlaceholderText("输入主词条属性（如：暴击）")
        layout.addWidget(self.main_prop_input)

        # 副词条输入
        layout.addWidget(QLabel("副词条属性（每行一个，格式：属性名 数值）:"))
        self.sub_props_input = QTextEdit()
        self.sub_props_input.setMaximumHeight(120)
        self.sub_props_input.setPlaceholderText("例如：\n暴击 3.5\n暴击伤害 6.2\n攻击% 5.3")
        layout.addWidget(self.sub_props_input)

        group.setLayout(layout)
        return group

    def _create_action_section(self) -> QGroupBox:
        """创建操作按钮区"""
        group = QGroupBox("操作")
        layout = QHBoxLayout()

        # 快速截图评分按钮
        self.quick_snip_button = QPushButton("⚡ 快速截图评分")
        self.quick_snip_button.setToolTip(f"快捷键: {self.config.get('hotkeys', {}).get('quick_snip', 'Ctrl+Shift+Q')}")
        self.quick_snip_button.clicked.connect(self._on_quick_snip)
        layout.addWidget(self.quick_snip_button)

        # 截图按钮
        self.screenshot_button = QPushButton("📷 截图")
        self.screenshot_button.setToolTip(f"快捷键: {self.config.get('hotkeys', {}).get('screenshot', 'Ctrl+Shift+A')}")
        self.screenshot_button.clicked.connect(self._on_screenshot)
        layout.addWidget(self.screenshot_button)

        # OCR 识别按钮
        self.ocr_button = QPushButton("🔍 OCR 识别")
        self.ocr_button.setToolTip(f"快捷键: {self.config.get('hotkeys', {}).get('ocr', 'Ctrl+Shift+S')}")
        self.ocr_button.clicked.connect(self._on_ocr)
        layout.addWidget(self.ocr_button)

        # 计算得分按钮
        self.calc_button = QPushButton("📊 计算得分")
        self.calc_button.clicked.connect(self._on_calculate)
        layout.addWidget(self.calc_button)

        # 设置按钮
        self.settings_button = QPushButton("⚙️ 设置")
        self.settings_button.clicked.connect(self._on_settings)
        layout.addWidget(self.settings_button)

        group.setLayout(layout)
        return group

    def _create_result_section(self) -> QGroupBox:
        """创建结果显示区"""
        group = QGroupBox("评分结果")
        layout = QVBoxLayout()

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText(
            "计算结果将显示在这里...\n\n"
            "💡 提示: 您可以直接拖拽图片文件到这里进行 OCR 识别\n"
            "   支持格式: PNG, JPG, JPEG, BMP, GIF"
        )
        layout.addWidget(self.result_text)

        group.setLayout(layout)
        return group

    def _load_roles(self):
        """加载角色列表"""
        roles = self.data_manager.get_all_roles()
        self.role_combo.clear()
        self.role_combo.addItems(roles)

        # 设置默认角色
        default_role = self.config.get("default_role", "今汐")
        index = self.role_combo.findText(default_role)
        if index >= 0:
            self.role_combo.setCurrentIndex(index)

        # 连接角色改变信号，同步到快速截图
        self.role_combo.currentIndexChanged.connect(self._on_role_changed)

    def _setup_hotkeys(self):
        """设置全局快捷键"""
        hotkeys = self.config.get("hotkeys", {})

        # 使用 GlobalHotkeyManager 注册全局热键
        # 注意：这里传递动作名称，而不是直接连接函数
        # HotkeyManager 会通过信号在主线程回调
        self.hotkey_manager.update_hotkeys(hotkeys)
        logger.info(f"全局快捷键已设置: {hotkeys}")

    def _on_role_changed(self, index):
        """主窗口角色改变时，同步到快速截图"""
        from gui.snipping_widget import SnippingWidget
        new_role = self.role_combo.currentText()
        # 更新快速截图的记忆角色
        SnippingWidget.last_selected_role = new_role
        logger.info(f"主窗口角色已更改为 '{new_role}'，已同步到快速截图")

    @Slot(str)
    def _on_hotkey_triggered(self, action_name: str):
        """
        全局热键触发回调
        注意：这个函数会由 HotkeyManager 的信号触发，运行在主线程
        """
        logger.info(f"热键触发: {action_name}")

        if action_name == "quick_snip":
            self._on_quick_snip()
        elif action_name == "screenshot":
            self._on_screenshot()
        elif action_name == "ocr":
            self._on_ocr()

    def _check_ocr_status(self):
        """检查 OCR 状态"""
        if self.ocr_engine.is_available():
            self.statusBar().showMessage("就绪 | OCR 已启用")
        else:
            self.statusBar().showMessage("就绪 | OCR 未启用（需要下载模型）")

    @Slot()
    def _on_screenshot(self):
        """截图按钮点击事件"""
        self.statusBar().showMessage("请拖拽鼠标选择截图区域（ESC取消）...")
        self.screenshot_button.setEnabled(False)

        # 显示区域选择器（模态对话框）
        selector = ScreenshotSelector()
        selector.selected.connect(self._on_region_selected)
        selector.cancelled.connect(self._on_screenshot_cancelled)

        # 使用 exec() 模态显示，阻塞直到用户选择或取消
        selector.exec()

    @Slot(tuple)
    def _on_region_selected(self, rect):
        """区域选择完成"""
        x, y, width, height = rect
        self.statusBar().showMessage(f"正在截图 ({width}x{height})...")

        # 截取选定区域
        img = self.screenshot_tool.capture_region(x, y, width, height, save=True)
        if img:
            self.statusBar().showMessage(f"截图成功，已保存到: {self.screenshot_tool.save_dir}")
            self._start_ocr(img)
        else:
            self.statusBar().showMessage("截图失败")
            self.screenshot_button.setEnabled(True)

    @Slot()
    def _on_screenshot_cancelled(self):
        """截图取消"""
        self.statusBar().showMessage("截图已取消")
        self.screenshot_button.setEnabled(True)

    @Slot()
    def _on_ocr(self):
        """OCR 识别按钮点击事件"""
        # 获取最新截图
        latest = self.screenshot_tool.get_latest_screenshot()
        if not latest:
            QMessageBox.warning(self, "提示", "未找到截图，请先截图")
            return

        # 加载图片
        from PIL import Image
        img = Image.open(latest)
        self._start_ocr(img)

    def _start_ocr(self, pil_image):
        """开始 OCR 识别"""
        self.statusBar().showMessage("正在 OCR 识别...")
        self.ocr_button.setEnabled(False)

        self.ocr_thread = OCRThread(pil_image)
        self.ocr_thread.finished.connect(self._on_ocr_finished)
        self.ocr_thread.start()

    @Slot(dict)
    def _on_ocr_finished(self, result: dict):
        """OCR 完成事件"""
        self.ocr_button.setEnabled(True)
        self.screenshot_button.setEnabled(True)

        if not result.get("success"):
            self.statusBar().showMessage("OCR 识别失败")
            QMessageBox.critical(self, "错误", result.get("error", "OCR 识别失败"))
            return

        parsed = result.get("parsed")
        if parsed:
            # 填充表单
            cost = parsed.get("cost", 4)
            if isinstance(cost, str):
                cost = int(cost)
            self.cost_spin.setValue(cost)

            # 格式化主词条（支持2个主词条）
            main_props = parsed.get("main_props", [])
            if main_props:
                # 显示所有主词条
                main_prop_texts = [f"{prop} {value}" for prop, value in main_props]
                main_prop_text = "\n".join(main_prop_texts)
            else:
                # 向后兼容：使用 main_prop
                main_prop = parsed.get("main_prop")
                if main_prop and isinstance(main_prop, tuple):
                    main_prop_text = f"{main_prop[0]} {main_prop[1]}"
                else:
                    main_prop_text = main_prop or ""
            self.main_prop_input.setPlainText(main_prop_text)

            # 显示主词条数量信息
            if len(main_props) > 1:
                self.result_text.append(f"\n[系统] 识别到 {len(main_props)} 个主词条（1固定+1随机）")

            # 显示所有主词条候选（如果有更多）
            all_main_candidates = parsed.get("all_main_candidates", [])
            if len(all_main_candidates) > len(main_props):
                candidate_text = "\n".join([f"{prop} {value}" for prop, value in all_main_candidates])
                self.result_text.append(f"\n[系统] 检测到 {len(all_main_candidates)} 个主词条候选，")
                self.result_text.append(f"[系统] 已选择前 {len(main_props)} 个，其余已丢弃")

            # 填充副词条
            sub_props = parsed.get("sub_props", [])
            sub_text = "\n".join([f"{prop} {value}" for prop, value in sub_props])
            self.sub_props_input.setPlainText(sub_text)

            self.statusBar().showMessage("OCR 识别完成")
            self.result_text.append(f"\n[OCR] 识别到 {len(sub_props)} 个副词条")
        else:
            self.statusBar().showMessage("OCR 解析失败")
            QMessageBox.warning(self, "警告", "OCR 识别完成，但未能解析出声骸信息")

    @Slot()
    def _on_calculate(self):
        """计算得分按钮点击事件"""
        role_name = self.role_combo.currentText()
        cost = self.cost_spin.value()
        main_prop = self.main_prop_input.toPlainText().strip()
        sub_props_text = self.sub_props_input.toPlainText().strip()

        if not main_prop:
            QMessageBox.warning(self, "提示", "请输入主词条属性")
            return

        # 解析副词条
        sub_props = []
        if sub_props_text:
            for line in sub_props_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    prop_name = parts[0]
                    try:
                        value = float(parts[1])
                        sub_props.append((prop_name, value))
                    except ValueError:
                        logger.warning(f"副词条数值格式错误: {line}")

        logger.info(f"[主窗口] 开始计算得分: role={role_name}, cost={cost}")
        logger.info(f"[主窗口] 主词条原始文本: '{main_prop}'")
        logger.info(f"[主窗口] 副词条数量: {len(sub_props)}")

        # 计算得分
        result = self.calculator.calculate(role_name, main_prop, cost, sub_props)

        if result:
            output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 评分结果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
角色: {result['role']} ({result['config_name']})
声骸成本: {cost}c

主词条: {main_prop}
主词条得分: {result['main_score']:.2f}

副词条得分: {result['sub_score']:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
原始总分: {result['total_raw']:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 对齐总分: {result['total_aligned']}/50
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            self.result_text.setText(output.strip())
            self.statusBar().showMessage(f"计算完成，得分: {result['total_aligned']}/50")
        else:
            self.result_text.setText("计算失败，请检查输入")
            self.statusBar().showMessage("计算失败")

    @Slot()
    def _on_quick_snip(self):
        """快速截图评分 - 全屏蒙版模式"""
        from PySide6.QtCore import QTimer

        self.statusBar().showMessage("准备快速截图评分...")

        # 隐藏主窗口（最小化）
        self.showMinimized()

        # 延时 200ms 确保窗口动画完成
        QTimer.singleShot(200, self._start_snipping)

    def _start_snipping(self):
        """启动截图蒙版"""
        # 获取当前选择的角色
        current_role = self.role_combo.currentText()

        # 创建 SnippingWidget 并传递默认角色
        self.snipper = SnippingWidget(default_role=current_role)
        self.snipper.closed.connect(self._on_snipping_closed)
        self.snipper.show()

    @Slot()
    def _on_snipping_closed(self, role: str = None):
        """截图结束后恢复主窗口"""
        self.showNormal()
        self.activateWindow()
        self.statusBar().showMessage("就绪")

        # 如果快速截图选择了角色，同步到主窗口
        if role:
            index = self.role_combo.findText(role)
            if index >= 0:
                self.role_combo.setCurrentIndex(index)
                logger.info(f"快速截图选择的角色 '{role}' 已同步到主窗口")
                self.statusBar().showMessage(f"已切换角色: {role}", 3000)

    # ========== 拖拽功能 ==========
    def dragEnterEvent(self, event):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            # 检查是否是图片文件
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                        event.acceptProposedAction()
                        return

    def dragMoveEvent(self, event):
        """拖拽移动事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """拖拽放下事件 - 处理图片文件"""
        urls = event.mimeData().urls()
        if not urls:
            return

        # 找到第一个图片文件
        for url in urls:
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    logger.info(f"拖拽图片文件: {file_path}")
                    self._process_dropped_image(file_path)
                    event.acceptProposedAction()
                    return

    def _process_dropped_image(self, file_path: str):
        """处理拖拽的图片文件"""
        try:
            from PIL import Image

            # 加载图片
            img = Image.open(file_path)
            self.statusBar().showMessage(f"已加载图片: {file_path}")

            # 启动 OCR 识别
            self._start_ocr(img)

        except Exception as e:
            logger.error(f"处理拖拽图片失败: {e}")
            self.statusBar().showMessage(f"加载图片失败: {str(e)}")
            QMessageBox.warning(self, "错误", f"无法加载图片:\n{str(e)}")

    @Slot()
    def _on_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self.config, self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()

    def _on_settings_changed(self):
        """设置更改后刷新"""
        # 重新加载配置
        self.config = self._load_config()

        # 重新注册全局热键
        self._setup_hotkeys()

        # 更新按钮提示
        hotkeys = self.config.get("hotkeys", {})
        self.quick_snip_button.setToolTip(f"快捷键: {hotkeys.get('quick_snip', 'Ctrl+Shift+Q')}")
        self.screenshot_button.setToolTip(f"快捷键: {hotkeys.get('screenshot', 'Ctrl+Shift+A')}")
        self.ocr_button.setToolTip(f"快捷键: {hotkeys.get('ocr', 'Ctrl+Shift+S')}")

        self.statusBar().showMessage("设置已更改，全局快捷键已更新", 5000)


def main():
    """测试主窗口"""
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

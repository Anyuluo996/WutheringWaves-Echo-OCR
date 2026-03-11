"""
设置对话框
用于修改快捷键和其他配置
"""

import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QFormLayout,
    QKeySequenceEdit, QMessageBox
)
from PySide6.QtCore import Qt, Signal
import yaml

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """设置对话框"""
    settings_changed = Signal()  # 设置更改信号

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.config_path = Path(__file__).parent.parent / "config" / "settings.yaml"

        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(560, 420)

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)

        # 快捷键设置组
        hotkey_group = QGroupBox("快捷键设置")
        hotkey_layout = QFormLayout()

        # 快速截图评分
        self.quick_snip_edit = QKeySequenceEdit()
        quick_snip = self.config.get("hotkeys", {}).get("quick_snip", "Ctrl+Shift+Q")
        self.quick_snip_edit.setKeySequence(quick_snip)
        hotkey_layout.addRow("快速截图评分:", self.quick_snip_edit)

        # 截图
        self.screenshot_edit = QKeySequenceEdit()
        screenshot = self.config.get("hotkeys", {}).get("screenshot", "Ctrl+Shift+A")
        self.screenshot_edit.setKeySequence(screenshot)
        hotkey_layout.addRow("截图:", self.screenshot_edit)

        # OCR识别
        self.ocr_edit = QKeySequenceEdit()
        ocr = self.config.get("hotkeys", {}).get("ocr", "Ctrl+Shift+S")
        self.ocr_edit.setKeySequence(ocr)
        hotkey_layout.addRow("OCR识别:", self.ocr_edit)

        hotkey_group.setLayout(hotkey_layout)
        layout.addWidget(hotkey_group)

        # GitHub 更新设置组
        github_group = QGroupBox("GitHub 更新设置")
        github_layout = QFormLayout()

        github_config = self.config.get("github", {})

        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("例如: http://127.0.0.1:17890")
        self.proxy_edit.setText(str(github_config.get("proxy_url", "") or ""))
        github_layout.addRow("代理地址:", self.proxy_edit)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("可选，用于提高 GitHub 访问成功率/限速配额")
        self.token_edit.setText(str(github_config.get("token", "") or ""))
        github_layout.addRow("GitHub Token:", self.token_edit)

        github_group.setLayout(github_layout)
        layout.addWidget(github_group)

        # 说明文字
        tip_label = QLabel(
            "💡 提示:\n"
            "  - 点击输入框后，按下想要的快捷键组合\n"
            "  - 快捷键格式: Ctrl+Shift+字母 或 Ctrl+Alt+字母\n"
            "  - ✨ 全局热键，游戏内也能使用\n"
            "  - GitHub 更新可选配置代理与 Token\n"
            "  - 修改后立即生效，无需重启"
        )
        tip_label.setStyleSheet("color: #666; font-size: 11px; padding: 10px;")
        layout.addWidget(tip_label)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def _save_settings(self):
        """保存设置"""
        try:
            # 获取新的快捷键设置
            hotkeys = {
                "quick_snip": self.quick_snip_edit.keySequence().toString(),
                "screenshot": self.screenshot_edit.keySequence().toString(),
                "ocr": self.ocr_edit.keySequence().toString(),
            }

            # 更新配置
            if "hotkeys" not in self.config:
                self.config["hotkeys"] = {}
            self.config["hotkeys"].update(hotkeys)

            github_settings = {
                "proxy_url": self.proxy_edit.text().strip(),
                "token": self.token_edit.text().strip(),
            }
            self.config.setdefault("github", {})
            self.config["github"].update(github_settings)

            # 保存到文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.config, f, allow_unicode=True, sort_keys=False)

            logger.info(f"设置已保存: hotkeys={hotkeys}, github_proxy={github_settings['proxy_url']}")

            QMessageBox.information(
                self,
                "设置已保存",
                f"快捷键设置已保存:\n\n"
                f"快速截图评分: {hotkeys['quick_snip']}\n"
                f"截图: {hotkeys['screenshot']}\n"
                f"OCR识别: {hotkeys['ocr']}\n"
                f"代理地址: {github_settings['proxy_url'] or '未配置'}\n"
                f"GitHub Token: {'已配置' if github_settings['token'] else '未配置'}\n\n"
                f"✨ 全局热键已立即生效，游戏内也可使用"
            )

            self.settings_changed.emit()
            self.accept()

        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            QMessageBox.critical(
                self,
                "错误",
                f"保存设置失败:\n{str(e)}"
            )

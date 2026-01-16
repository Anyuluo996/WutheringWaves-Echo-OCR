"""
全局快捷键管理器
使用 keyboard 库实现系统级热键，并通过 Qt 信号发送给主线程
"""

import logging
import keyboard
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class GlobalHotkeyManager(QObject):
    """
    全局热键管理器
    继承 QObject 以支持信号槽，确保回调在主线程执行
    """
    # 定义信号，当热键触发时发送动作名称
    triggered = Signal(str)

    def __init__(self):
        super().__init__()
        self._registered_hooks = []  # 追踪已注册的 hook

    def register_hotkey(self, hotkey_str: str, action_name: str):
        """
        注册全局热键

        Args:
            hotkey_str: 快捷键字符串 (如 "Ctrl+Shift+A")
            action_name: 触发时发送的动作标识 (如 "screenshot")
        """
        try:
            # 转换 Qt 风格快捷键到 keyboard 库风格
            # Qt: "Ctrl+Shift+A" -> keyboard: "ctrl+shift+a"
            # 主要差异在于大小写和某些键名，keyboard 库容错性较好
            key_seq = hotkey_str.lower()

            # 注册热键，当触发时发射信号
            # suppress=False 表示不拦截按键，让游戏也能收到（防止冲突时游戏卡死）
            hook = keyboard.add_hotkey(
                key_seq,
                lambda: self.triggered.emit(action_name),
                suppress=False
            )

            self._registered_hooks.append(hook)
            logger.info(f"注册全局热键: {hotkey_str} -> {action_name}")

        except Exception as e:
            logger.error(f"注册热键失败 '{hotkey_str}': {e}")

    def clear_hotkeys(self):
        """清除所有已注册的热键"""
        try:
            # 手动移除所有已注册的 hook
            for hook in self._registered_hooks:
                keyboard.remove_hotkey(hook)
            self._registered_hooks.clear()
            logger.info("已清除所有全局热键")
        except Exception as e:
            logger.error(f"清除热键时出错: {e}")

    def update_hotkeys(self, config_hotkeys: dict):
        """
        根据配置更新所有热键

        Args:
            config_hotkeys: 字典 {"action_name": "hotkey_str"}
        """
        self.clear_hotkeys()

        for action, key in config_hotkeys.items():
            if key:
                self.register_hotkey(key, action)

"""
WutheringWaves-Echo-OCR
《鸣潮》声骸 OCR 识别与评分工具
"""

import sys
import os
import ctypes
import logging
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from gui.main_window import MainWindow

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def configure_qt_dpi():
    """在 QApplication 创建前配置 DPI 行为"""
    os.environ.setdefault("QT_FONT_DPI", "96")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

def is_admin():
    """检查当前是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run_as_admin():
    """尝试以管理员权限重新运行程序"""
    try:
        if getattr(sys, 'frozen', False):
            # 如果是打包后的 .exe
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, "", None, 1
            )
        else:
            # 如果是 Python 脚本
            # 重新组装命令行参数
            args = " ".join(f'"{arg}"' for arg in sys.argv)
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, args, None, 1
            )
    except Exception as e:
        logger.error(f"请求管理员权限失败: {e}")
        return False
    return True

def main():
    """程序入口"""
    configure_qt_dpi()
    admin_ready = is_admin()

    # 1. 检查管理员权限
    if not admin_ready:
        print("当前无管理员权限，尝试提权...")

        # 尝试提权
        if run_as_admin():
            # 提权请求已发送，当前普通进程退出
            sys.exit(0)

    # 2. 创建 QApplication
    if QApplication.instance():
        app = QApplication.instance()
    else:
        app = QApplication(sys.argv)

    if not admin_ready:
        QMessageBox.warning(
            None,
            "权限不足",
            "为了在游戏中响应快捷键，本程序必须以管理员身份运行。\n\n"
            "请右键点击程序 -> '以管理员身份运行'。"
        )

    # 3. 设置应用程序信息
    app.setApplicationName("WutheringWaves-Echo-OCR")
    app.setOrganizationName("WW-Echo-OCR")

    # 4. 启动主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

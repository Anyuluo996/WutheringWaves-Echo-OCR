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

    # 1. 检查管理员权限
    if not is_admin():
        print("当前无管理员权限，尝试提权...")
        # 初始化一个临时的 QApplication 来显示错误（如果提权失败）
        temp_app = QApplication(sys.argv)

        # 尝试提权
        if run_as_admin():
            # 提权请求已发送，当前普通进程退出
            sys.exit(0)
        else:
            # 提权失败（用户点了否，或者报错），提示用户
            QMessageBox.warning(
                None,
                "权限不足",
                "为了在游戏中响应快捷键，本程序必须以管理员身份运行。\n\n"
                "请右键点击程序 -> '以管理员身份运行'。"
            )
            # 虽然失败，但我们尝试继续运行，虽然快捷键可能失效
            pass

    # 2. 开启高 DPI 缩放支持 (必须在创建 QApplication 之前)
    os.environ["QT_FONT_DPI"] = "96"  # 强制字体 DPI

    # 设置缩放策略：跟随系统设置
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 3. 如果之前没有创建 App (即已是 Admin)，则创建
    if QApplication.instance():
        app = QApplication.instance()
    else:
        app = QApplication(sys.argv)

    # 设置应用程序信息
    app.setApplicationName("WutheringWaves-Echo-OCR")
    app.setOrganizationName("WW-Echo-OCR")

    # 4. 启动主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""
截图工具模块 - Qt 原生版
解决 DPI 偏移问题的终极方案：使用 Qt 自身的 grabWindow
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# 移除 PIL.ImageGrab 依赖，改用 PySide6
from PySide6.QtGui import QGuiApplication, QPixmap, QImage
from PySide6.QtCore import QPoint, QRect, QBuffer, QIODevice

# 如果需要将 Qt 图片转为 PIL 图片给 OCR 用
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("PIL 未安装，将无法转换为 Image 对象")

logger = logging.getLogger(__name__)


class ScreenshotTool:
    """截图工具类"""

    def __init__(self, save_dir: Optional[Path] = None):
        """
        初始化截图工具
        """
        if save_dir is None:
            save_dir = Path(__file__).parent.parent / "data" / "screenshots"

        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def _qpixmap_to_pil(self, pixmap: QPixmap) -> Optional['Image.Image']:
        """将 QPixmap 转换为 PIL Image"""
        if not PIL_AVAILABLE:
            return None

        try:
            # 将 QPixmap 转为 QImage
            qimage = pixmap.toImage()
            # 保存到内存 buffer
            buffer = QBuffer()
            buffer.open(QIODevice.ReadWrite)
            qimage.save(buffer, "PNG")

            # 从内存 buffer 读取为 PIL Image
            pil_im = Image.open(io.BytesIO(buffer.data().data()))
            return pil_im
        except Exception as e:
            logger.error(f"图片转换失败: {e}")
            return None

    def capture_fullscreen(self, save: bool = True):
        """
        截取全屏 (截取鼠标所在的主屏幕)
        """
        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                logger.error("无法获取屏幕对象")
                return None

            # 抓取整个屏幕
            # grabWindow(0) 表示抓取根窗口（即全屏）
            pixmap = screen.grabWindow(0)

            if save:
                self._save_pixmap(pixmap, "screenshot")

            return self._qpixmap_to_pil(pixmap)
        except Exception as e:
            logger.error(f"全屏截图失败: {e}")
            return None

    def capture_region(
        self,
        x: int, y: int, width: int, height: int,
        save: bool = True
    ):
        """
        截取指定区域 (零偏移方案)

        Args:
            x, y, width, height: PySide6 逻辑坐标 (直接从 GUI 传进来)
        """
        try:
            # 1. 找到包含该坐标中心点的屏幕
            # 防止跨屏截图时找不到正确的 devicePixelRatio
            center_x = x + width // 2
            center_y = y + height // 2
            screen = QGuiApplication.screenAt(QPoint(center_x, center_y))

            if not screen:
                screen = QGuiApplication.primaryScreen()

            # 2. 获取该屏幕的几何信息
            geom = screen.geometry()

            # 3. 计算相对于该屏幕左上角的坐标
            # grabWindow 的 x, y 是相对于该 screen 的，不是全局坐标
            local_x = x - geom.x()
            local_y = y - geom.y()

            # 4. 截图
            # Qt 会自动处理 DPI 缩放，我们传入逻辑宽高即可
            pixmap = screen.grabWindow(0, local_x, local_y, width, height)

            if save:
                self._save_pixmap(pixmap, "region")

            return self._qpixmap_to_pil(pixmap)

        except Exception as e:
            logger.error(f"区域截图失败: {e}")
            return None

    def _save_pixmap(self, pixmap: QPixmap, prefix: str):
        """保存 QPixmap 到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = self.save_dir / filename
        pixmap.save(str(filepath), "PNG")
        logger.info(f"截图已保存: {filepath}")

    def get_latest_screenshot(self) -> Optional[Path]:
        screenshots = list(self.save_dir.glob("*.png"))
        if screenshots:
            return max(screenshots, key=lambda p: p.stat().st_mtime)
        return None

def main():
    """测试截图工具 (需要创建 QApplication)"""
    import sys

    # 必须先创建 App 实例，否则无法使用 QScreen
    app = QGuiApplication(sys.argv)

    tool = ScreenshotTool()
    print("正在截取屏幕左上角 500x500 区域...")

    # 注意：这里的 0,0 是指主显示器的逻辑左上角
    img = tool.capture_region(0, 0, 500, 500)

    if img:
        print(f"截图成功，尺寸: {img.size}")
        # img.show()

if __name__ == "__main__":
    main()

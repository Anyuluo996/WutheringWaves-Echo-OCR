"""
截图区域选择窗口
允许用户用鼠标拖拽选择截图区域
"""

import logging
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QScreen, QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QWidget

logger = logging.getLogger(__name__)


class ScreenshotSelector(QDialog):
    """截图区域选择器"""

    # 信号：选择完成，传递 (x, y, width, height)
    selected = Signal(tuple)
    # 信号：取消选择
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setModal(True)

        # 获取主屏幕
        screen = QApplication.primaryScreen()
        self.device_pixel_ratio = screen.devicePixelRatio()

        # 使用主屏幕几何信息
        self.screen_rect = screen.geometry()
        self.setGeometry(self.screen_rect)

        # 抓取主屏幕
        try:
            self.screenshot = screen.grabWindow(0)
        except Exception as e:
            logger.error(f"grabWindow 失败: {e}")
            self.screenshot = screen.grabDesktop()

        # 选择状态
        self.selecting = False
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.selection_rect = QRect()

        logger.info(f"截图选择器初始化，屏幕尺寸: {self.screen_rect.width()}x{self.screen_rect.height()}")

    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        self.grabKeyboard()
        self.setFocus()
        logger.info("截图选择器已显示")

    def keyPressEvent(self, event):
        """按键事件"""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("用户按 ESC 取消截图选择")
            self.cancelled.emit()
            self.accept()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # 回车键确认选择
            if self.selecting:
                logger.info("用户按回车确认选择")
                self._finish_selection()

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.selecting = True
            self.start_point = event.pos()
            self.end_point = event.pos()
            logger.debug(f"开始选择，起点: {self.start_point.x()}, {self.start_point.y()}")
            self.update()

    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.selecting:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton and self.selecting:
            self.selecting = False
            self.end_point = event.pos()
            self._finish_selection()

    def _finish_selection(self):
        """完成选择"""
        x1 = min(self.start_point.x(), self.end_point.x())
        y1 = min(self.start_point.y(), self.end_point.y())
        x2 = max(self.start_point.x(), self.end_point.x())
        y2 = max(self.start_point.y(), self.end_point.y())

        width = x2 - x1
        height = y2 - y1

        # 忽略太小的选择
        if width < 10 or height < 10:
            logger.info(f"选择区域太小 ({width}x{height})，已忽略")
            return

        # 使用 mapToGlobal 将窗口内坐标转换为屏幕全局坐标（Qt 标准做法）
        top_left_global = self.mapToGlobal(QPoint(x1, y1))

        actual_x = top_left_global.x()
        actual_y = top_left_global.y()
        actual_width = width
        actual_height = height

        result = (actual_x, actual_y, actual_width, actual_height)
        logger.info(f"选择区域（窗口坐标）: x={x1}, y={y1}, width={width}, height={height}")
        logger.info(f"选择区域（全局坐标）: x={actual_x}, y={actual_y}, width={actual_width}, height={actual_height}")
        logger.info(f"使用 Qt 同源坐标系，ScreenshotTool 将使用相同的 grabWindow API")
        self.selected.emit(result)
        self.accept()

    def paintEvent(self, event):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        try:
            # 绘制半透明背景截图
            painter.drawPixmap(0, 0, self.screenshot)

            # 绘制半透明黑色遮罩
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

            if self.selecting or (not self.start_point.isNull() and not self.end_point.isNull()):
                # 计算选择矩形
                x = min(self.start_point.x(), self.end_point.x())
                y = min(self.start_point.y(), self.end_point.y())
                width = abs(self.end_point.x() - self.start_point.x())
                height = abs(self.end_point.y() - self.start_point.y())

                if width > 0 and height > 0:
                    # 清除选择区域的遮罩，显示原始截图
                    painter.drawPixmap(x, y, self.screenshot,
                                    x, y, width, height)

                    # 绘制红色选择边框
                    pen = QPen(QColor(255, 50, 50), 2)
                    pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.drawRect(x, y, width, height)

                    # 显示尺寸信息背景
                    text = f"{width} x {height}"
                    font_metrics = painter.fontMetrics()
                    text_width = font_metrics.horizontalAdvance(text)
                    text_height = font_metrics.height()

                    # 绘制文字背景
                    bg_rect = QRect(x + 2, y + 2, text_width + 8, text_height + 4)
                    painter.fillRect(bg_rect, QColor(0, 0, 0, 200))

                    # 显示尺寸信息
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(x + 6, y + 2 + text_height - 2, text)
        finally:
            # 确保正确结束绘制
            painter.end()


def select_region(parent=None) -> Optional[Tuple[int, int, int, int]]:
    """
    显示区域选择对话框

    Args:
        parent: 父窗口

    Returns:
        (x, y, width, height) 或 None（取消）
    """
    selector = ScreenshotSelector()
    result = [None]

    def on_selected(rect):
        result[0] = rect
        logger.info(f"区域选择完成: {rect}")

    def on_cancelled():
        result[0] = None
        logger.info("区域选择已取消")

    selector.selected.connect(on_selected)
    selector.cancelled.connect(on_cancelled)

    # 使用 exec() 模态显示
    selector.exec()

    return result[0]


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    result = select_region()
    if result:
        print(f"选择区域: {result}")
    else:
        print("已取消")

    sys.exit()

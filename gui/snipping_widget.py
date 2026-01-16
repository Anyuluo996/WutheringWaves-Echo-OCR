"""
截图评分蒙版组件
集成截图、角色选择、OCR后台线程、结果绘制
"""

import sys
import numpy as np
from PySide6.QtWidgets import QWidget, QApplication, QComboBox, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QRect, QPoint, Signal, QThread, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QPixmap, QImage, QScreen

# 引入核心业务逻辑
from core.ocr_engine import OCREngine
from core.ocr_parser import EchoOCRParser
from core.calculator import EchoCalculator
from core.data_manager import DataManager

import logging
logger = logging.getLogger(__name__)


class OCRWorker(QThread):
    """后台执行 OCR 和计算的线程，防止界面卡顿"""
    finished = Signal(dict)  # 发送结果字典
    error = Signal(str)

    def __init__(self, image, role_name):
        super().__init__()
        self.image = image
        self.role_name = role_name

    def run(self):
        try:
            logger.info(f"开始处理截图，角色: {self.role_name}")

            # 1. OCR 识别
            ocr_engine = OCREngine()
            if not ocr_engine.is_available():
                self.error.emit("OCR 模型未加载")
                return

            # QImage -> Numpy
            qimage = self.image.toImage()
            width = qimage.width()
            height = qimage.height()

            # 格式转换: ARGB32 -> RGB
            qimage = qimage.convertToFormat(QImage.Format_RGB888)

            # 获取图像数据并处理内存对齐
            ptr = qimage.bits()
            bytes_per_line = qimage.bytesPerLine()

            # 使用 bytesPerLine() 处理可能的行对齐
            # 创建完整的字节数组,然后只取有效宽度
            total_size = bytes_per_line * height
            arr = np.frombuffer(ptr, dtype=np.uint8, count=total_size).reshape((height, bytes_per_line))

            # 只提取有效的 RGB 数据 (去掉行尾填充)
            arr = arr[:, :width * 3].reshape((height, width, 3)).copy()

            logger.info(f"图像尺寸: {width}x{height}")

            # 2. 执行识别
            ocr_results = ocr_engine.recognize(arr)
            logger.info(f"OCR 识别到 {len(ocr_results)} 条结果")

            # 3. 解析数据
            parser = EchoOCRParser()
            parse_result = parser.parse(ocr_results)

            if not parse_result:
                self.error.emit("未识别到有效声骸信息")
                return

            logger.info(f"解析结果: COST={parse_result['cost']}, "
                       f"主词条={parse_result['main_prop']}, "
                       f"副词条={len(parse_result['sub_props'])}个")

            # 格式化主词条为字符串 (兼容 calculator.calculate 的要求)
            main_props = parse_result.get('main_props', [])
            if main_props:
                # 将多个主词条格式化为字符串
                main_prop_text = " ".join([f"{prop} {value}" for prop, value in main_props])
            else:
                # 向后兼容：使用 main_prop
                main_prop = parse_result.get('main_prop')
                if main_prop and isinstance(main_prop, tuple):
                    main_prop_text = f"{main_prop[0]} {main_prop[1]}"
                else:
                    main_prop_text = str(main_prop) if main_prop else ""

            # 4. 计算分数
            calculator = EchoCalculator()
            calc_result = calculator.calculate(
                self.role_name,
                main_prop_text,
                parse_result['cost'],
                parse_result['sub_props']
            )

            if calc_result:
                logger.info(f"计算完成: 总分={calc_result['total_aligned']:.1f}")
                self.finished.emit(calc_result)
            else:
                self.error.emit("计算失败 (可能是权重配置缺失)")

        except Exception as e:
            logger.exception("OCR 处理异常")
            self.error.emit(f"处理出错: {str(e)}")


class SnippingWidget(QWidget):
    """全屏截图与评分蒙版"""

    # 定义关闭信号，携带选择的角色
    closed = Signal(str)  # 参数：选择的角色名

    # 记忆上次选择的角色（类变量）
    last_selected_role = None

    def __init__(self, default_role: str = None):
        super().__init__()

        # 使用记忆的角色，如果没有则使用默认角色
        self.initial_role = self.last_selected_role or default_role or "今汐"

        # 窗口设置：无边框、置顶、全屏
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

        # 状态变量
        self.start_pos = None
        self.current_pos = None
        self.is_selecting = False
        self.result_data = None  # 存储计算结果
        self.error_msg = None
        self.is_processing = False
        self.default_role = default_role  # 保存默认角色

        # 1. 获取全屏截图 (背景底图)
        screen = QApplication.primaryScreen()
        self.original_pixmap = screen.grabWindow(0)

        # 调整自身大小覆盖全屏
        geometry = screen.geometry()
        self.setGeometry(geometry)

        # 2. 初始化界面控件 (角色选择)
        self._init_ui()

        logger.info(f"截图蒙版初始化完成，屏幕尺寸: {geometry.width()}x{geometry.height()}, 默认角色: {default_role}")

    def _init_ui(self):
        """初始化悬浮控件"""
        # 角色选择下拉框
        self.role_combo = QComboBox(self)
        self.role_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 防止抢占按键

        # 加载角色数据
        try:
            dm = DataManager()
            roles = dm.get_all_roles()
            if roles:
                self.role_combo.addItems(roles)
                logger.info(f"加载了 {len(roles)} 个角色配置")
            else:
                self.role_combo.addItem("默认")
        except Exception as e:
            logger.warning(f"加载角色数据失败: {e}")
            self.role_combo.addItem("默认")

        # 设置默认角色（使用记忆的角色）
        if self.initial_role:
            index = self.role_combo.findText(self.initial_role)
            if index >= 0:
                self.role_combo.setCurrentIndex(index)
                logger.info(f"设置记忆角色: {self.initial_role}")

        # 设置下拉框样式
        self.role_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #333;
                border-radius: 4px;
                padding: 5px;
                font-size: 14px;
                font-weight: bold;
                color: #000;
            }
            QComboBox::drop-down { border: none; }
        """)

        # 将下拉框放置在屏幕顶部中间
        self.role_combo.resize(150, 40)
        self.role_combo.move((self.width() - 150) // 2, 50)
        self.role_combo.show()

        # 提示标签
        tip_text = f"当前角色: {self.role_combo.currentText()}\n按住鼠标左键框选声骸属性面板 / 右键或ESC退出"
        self.tip_label = QLabel(tip_text, self)
        self.tip_label.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold; "
            "background-color: rgba(0,0,0,100); padding: 8px 15px; border-radius: 5px;"
        )
        self.tip_label.adjustSize()
        self.tip_label.move((self.width() - self.tip_label.width()) // 2, 100)
        self.tip_label.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        try:
            # 1. 绘制全屏背景图 (看起来像是静止的屏幕)
            painter.drawPixmap(0, 0, self.original_pixmap)

            # 2. 绘制半透明黑色蒙层 (让用户知道进入了截图模式)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

            # 3. 绘制选区 (挖空效果，显示原始亮度)
            if self.start_pos and self.current_pos:
                rect = self._get_selection_rect()

                # 将选区部分的蒙层擦除 (绘制原始截图的该部分)
                painter.drawPixmap(rect, self.original_pixmap, rect)

                # 绘制边框
                pen = QPen(QColor(0, 174, 255), 2)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawRect(rect)

                # 4. 绘制结果 (如果有)
                if self.result_data:
                    self._draw_result(painter, rect)
                elif self.error_msg:
                    self._draw_error(painter, rect)
                elif self.is_processing:
                    self._draw_loading(painter, rect)

        finally:
            painter.end()

    def _draw_result(self, painter, rect):
        """绘制评分结果 - 显示每个词条的详细得分"""
        score = self.result_data['total_aligned']
        grade = "S" if score >= 40 else ("A" if score >= 30 else "B")

        # 决定颜色
        text_color = QColor("#FFD700") if score >= 40 else QColor("#FFFFFF")
        bg_color = QColor(0, 0, 0, 220)
        highlight_color = QColor("#FFD700") if score >= 40 else QColor("#00BFFF")

        # 准备文本内容
        lines = [
            f"角色: {self.result_data['role']}",
            f"评分: {score:.1f} / 50",
            f"评级: {grade}",
        ]

        # 主词条详情
        main_details = self.result_data.get('main_details', [])
        if main_details:
            lines.append("")
            lines.append("【主词条】")
            for prop, prop_score in main_details:
                lines.append(f"  {prop}: {prop_score:.2f}")

        # 副词条详情
        sub_details = self.result_data.get('sub_details', [])
        if sub_details:
            lines.append("")
            lines.append("【副词条】")
            for prop, prop_score in sub_details:
                lines.append(f"  {prop}: {prop_score:.2f}")

        # 总计
        lines.append("")
        lines.append(f"总分: {score:.1f}")

        # 计算文本框尺寸
        x = rect.right() + 10
        y = rect.top()
        if x + 250 > self.width():  # 如果靠右，就放左边
            x = rect.left() - 260

        line_height = 20
        padding = 15
        total_height = len(lines) * line_height + padding * 2

        text_rect = QRect(x, y, 250, total_height)

        # 绘制背景框
        painter.fillRect(text_rect, bg_color)

        # 绘制边框 (S级用金色边框)
        pen = QPen(highlight_color, 2)
        painter.setPen(pen)
        painter.drawRect(text_rect)

        # 绘制文本
        painter.setPen(text_color)
        painter.setFont(QFont("Microsoft YaHei", 10))

        for i, line in enumerate(lines):
            line_rect = QRect(x, y + padding + i * line_height, 250, line_height)

            if line.startswith("评分:"):
                # 总分放大高亮
                painter.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
                painter.drawText(line_rect, Qt.AlignmentFlag.AlignLeft, line)
                painter.setFont(QFont("Microsoft YaHei", 10))
            elif line.startswith("【"):
                # 分类标题加粗
                painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
                painter.drawText(line_rect, Qt.AlignmentFlag.AlignLeft, line)
                painter.setFont(QFont("Microsoft YaHei", 10))
            else:
                painter.drawText(line_rect, Qt.AlignmentFlag.AlignLeft, line)

        # 提示点击关闭
        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(QColor("#AAAAAA"))
        tip_rect = QRect(x, y + total_height - 20, 250, 20)
        painter.drawText(tip_rect, Qt.AlignmentFlag.AlignCenter, "点击任意处关闭")

    def _draw_error(self, painter, rect):
        """绘制错误信息"""
        x = rect.right() + 10
        y = rect.top()
        text_rect = QRect(x, y, 200, 60)
        painter.fillRect(text_rect, QColor(200, 0, 0, 200))
        painter.setPen(Qt.GlobalColor.white)
        painter.setFont(QFont("Microsoft YaHei", 10))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"错误:\n{self.error_msg}")

    def _draw_loading(self, painter, rect):
        """绘制加载提示"""
        x = rect.right() + 10
        y = rect.top()
        text_rect = QRect(x, y, 150, 40)
        painter.fillRect(text_rect, QColor(0, 0, 0, 180))
        painter.setPen(Qt.GlobalColor.white)
        painter.setFont(QFont("Microsoft YaHei", 10))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "正在识别...")

    def _get_selection_rect(self):
        """计算标准化的矩形 (处理反向拖拽)"""
        if not self.start_pos or not self.current_pos:
            return QRect()
        return QRect(self.start_pos, self.current_pos).normalized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 如果已经有结果了，点击任意处关闭
            if self.result_data or self.error_msg:
                # 发出关闭信号，携带选择的角色
                role_to_emit = getattr(self, 'selected_role', self.role_combo.currentText())
                self.closed.emit(role_to_emit)
                self.close()
                return

            # 如果正在下拉框上操作，不开始截图
            if self.role_combo.geometry().contains(event.pos()):
                return super().mousePressEvent(event)

            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_selecting = True
            self.tip_label.hide()  # 隐藏提示
            self.role_combo.hide()  # 隐藏下拉框，防止干扰视线
            self.update()

        elif event.button() == Qt.MouseButton.RightButton:
            self.close()  # 右键取消

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.current_pos = event.pos()

            # 开始处理
            rect = self._get_selection_rect()
            if rect.width() > 10 and rect.height() > 10:
                self._start_processing(rect)
            else:
                # 选区太小，重置
                self.start_pos = None
                self.current_pos = None
                self.role_combo.show()
                self.tip_label.show()
                self.update()

    def _start_processing(self, rect):
        """开始 OCR 流程"""
        self.is_processing = True
        self.update()

        # 截取选区图像 (从原始 pixmap 截取)
        crop_pixmap = self.original_pixmap.copy(rect)

        # 获取当前选择的角色（使用下拉框当前文本，而不是初始化时的角色）
        current_role = self.role_combo.currentText()
        self.selected_role = current_role  # 保存选择的角色

        # 记忆角色选择（类变量，下次打开时使用）
        SnippingWidget.last_selected_role = current_role

        logger.info(f"开始 OCR 处理，选区: {rect.width()}x{rect.height()}, 角色: {current_role}")

        # 启动后台线程
        self.worker = OCRWorker(crop_pixmap, current_role)
        self.worker.finished.connect(self._on_success)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_success(self, result):
        """处理成功"""
        self.is_processing = False
        self.result_data = result
        logger.info("OCR 处理成功，显示结果")
        self.update()  # 触发重绘，显示结果

    def _on_error(self, msg):
        """处理错误"""
        self.is_processing = False
        self.error_msg = msg
        logger.error(f"OCR 处理失败: {msg}")
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            logger.info("用户按 ESC 取消截图")
            # 发出关闭信号，携带选择的角色
            role_to_emit = getattr(self, 'selected_role', self.role_combo.currentText())
            self.closed.emit(role_to_emit)
            self.close()


def main():
    """测试截图蒙版"""
    app = QApplication(sys.argv)

    widget = SnippingWidget()
    widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

"""
OCR 引擎模块 - 单例模式封装 RapidOCR
"""

import sys
import logging
import threading
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


class OCREngine:
    """OCR 引擎单例类"""

    _instance: Optional['OCREngine'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'OCREngine':
        """实现单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化 OCR 引擎"""
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True

        # 获取模型路径：支持开发环境和打包环境
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller/Nuitka 打包后的路径
            base_path = Path(sys._MEIPASS)
            self.model_path = base_path / "models"
        else:
            # 开发环境的路径
            self.model_path = Path(__file__).parent.parent / "models"

        self.ocr = None
        self._init_ocr()

    def _init_ocr(self):
        """初始化 OCR 引擎（延迟加载）"""
        try:
            from rapidocr_onnxruntime import RapidOCR

            # 支持多种模型文件名
            det_candidates = [
                "ch_PP-OCRv5_det_infer.onnx",
                "ch_PP-OCRv5_mobile_det.onnx",
                "ch_PP-OCRv4_det_infer.onnx"
            ]
            rec_candidates = [
                "ch_PP-OCRv5_rec_infer.onnx",
                "ch_PP-OCRv5_rec_mobile_infer.onnx",
                "ch_PP-OCRv4_rec_infer.onnx"
            ]

            det_model = None
            rec_model = None

            for det_name in det_candidates:
                path = self.model_path / det_name
                if path.exists():
                    det_model = path
                    break

            for rec_name in rec_candidates:
                path = self.model_path / rec_name
                if path.exists():
                    rec_model = path
                    break

            if det_model is None or rec_model is None:
                logger.warning(
                    f"OCR 模型文件缺失，请下载模型到 {self.model_path}:\n"
                    f"  检测模型: ch_PP-OCRv5_det_infer.onnx 或 ch_PP-OCRv5_mobile_det.onnx\n"
                    f"  识别模型: ch_PP-OCRv5_rec_infer.onnx 或 ch_PP-OCRv5_rec_mobile_infer.onnx\n"
                    f"下载地址: https://github.com/RapidAI/RapidOCR-OnnxRuntime"
                )
                return

            # 在打包环境下，禁用配置文件加载
            # RapidOCR 会尝试从其安装目录加载 config.yaml
            # 但打包后这个路径不存在，会导致错误
            try:
                self.ocr = RapidOCR(
                    det_model_path=str(det_model),
                    rec_model_path=str(rec_model),
                    use_gpu=False,
                    print_verbose=False  # 禁用详细日志
                )
                logger.info(f"OCR 引擎初始化成功 - 检测: {det_model.name}, 识别: {rec_model.name}")
            except Exception as e:
                # 如果默认初始化失败，尝试不使用配置文件
                logger.warning(f"RapidOCR 默认初始化失败: {e}，尝试不使用配置文件...")
                self.ocr = RapidOCR(
                    det_model_path=str(det_model),
                    rec_model_path=str(rec_model),
                    use_gpu=False,
                    print_verbose=False,
                    det_use_cuda=None,  # 强制不使用 CUDA
                    rec_use_cuda=None
                )
                logger.info(f"OCR 引擎初始化成功（无配置模式）- 检测: {det_model.name}, 识别: {rec_model.name}")

        except ImportError as e:
            logger.error(f"RapidOCR 导入失败: {e}")
        except Exception as e:
            logger.error(f"OCR 引擎初始化失败: {e}")

    def is_available(self) -> bool:
        """检查 OCR 是否可用"""
        return self.ocr is not None

    def recognize(self, image) -> List[Tuple[str, float, Tuple]]:
        """
        识别图片中的文字

        Args:
            image: 输入图片（numpy array 或图片路径）

        Returns:
            识别结果列表，每项为 (text, confidence, bbox)
        """
        if self.ocr is None:
            logger.warning("OCR 引擎未初始化")
            return []

        try:
            result, _ = self.ocr(image)
            if result is None:
                return []

            # RapidOCR 返回格式：[[bbox, text, confidence], ...]
            # 我们需要转换为：(text, confidence, bbox)
            processed_results = []
            for item in result:
                if len(item) >= 3:
                    bbox = item[0]
                    text = item[1]
                    confidence = item[2] if len(item) > 2 else 0.0
                    processed_results.append((text, confidence, bbox))

            return processed_results
        except Exception as e:
            logger.error(f"OCR 识别失败: {e}")
            return []


def main():
    """测试 OCR 引擎"""
    import cv2
    from pathlib import Path

    logging.basicConfig(level=logging.INFO)

    ocr = OCREngine()

    if not ocr.is_available():
        print("OCR 引擎不可用，请检查模型文件")
        return

    # 测试图片路径
    test_image = Path(__file__).parent.parent / "data" / "test.png"

    if not test_image.exists():
        print(f"测试图片不存在: {test_image}")
        print("请将测试图片放在 data/test.png")
        return

    img = cv2.imread(str(test_image))
    results = ocr.recognize(img)

    print("OCR 识别结果：")
    for text, confidence, bbox in results:
        print(f"文字: {text}, 置信度: {confidence:.2f}")


if __name__ == "__main__":
    main()

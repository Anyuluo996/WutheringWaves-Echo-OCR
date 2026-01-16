"""
OCR 结果解析器
从 OCR 识别结果中提取声骸属性信息
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from difflib import get_close_matches

logger = logging.getLogger(__name__)


class OCRCostParser:
    """声骸成本解析器"""

    # 标准化成本映射
    COST_PATTERNS = {
        r"1[Cc]": 1,
        r"一[CCc]": 1,
        r"3[Cc]": 3,
        r"三[CCc]": 3,
        r"4[Cc]": 4,
        r"四[CCc]": 4,
    }

    @classmethod
    def parse(cls, text: str) -> Optional[int]:
        """解析声骸成本"""
        text = text.strip()
        for pattern, cost in cls.COST_PATTERNS.items():
            if re.search(pattern, text):
                return cost
        return None


class OCRPropertyParser:
    """声骸属性解析器"""

    # 属性名标准化映射
    PROP_MAP = {
        "攻击": "攻击",
        "攻击百分比": "攻击%",
        "攻击%": "攻击%",
        "攻击％": "攻击%",
        "生命": "生命",
        "生命百分比": "生命%",
        "生命%": "生命%",
        "生命％": "生命%",
        "防御": "防御",
        "防御百分比": "防御%",
        "防御%": "防御%",
        "防御％": "防御%",
        "暴击": "暴击",
        "暴击伤害": "暴击伤害",
        "暴击率": "暴击",
        "暴击%": "暴击",
        "共鸣效率": "共鸣效率",
        "属性伤害加成": "属性伤害加成",
        "普攻伤害加成": "普攻伤害加成",
        "重击伤害加成": "重击伤害加成",
        "共鸣技能伤害加成": "共鸣技能伤害加成",
        "共鸣解放伤害加成": "共鸣解放伤害加成",
        "治疗效果加成": "治疗效果加成",
    }

    @classmethod
    def normalize(cls, prop_name: str) -> Optional[str]:
        """标准化属性名"""
        prop_name = prop_name.strip().replace(" ", "")

        # 直接匹配
        if prop_name in cls.PROP_MAP:
            return cls.PROP_MAP[prop_name]

        # 模糊匹配
        matches = get_close_matches(prop_name, cls.PROP_MAP.keys(), n=1, cutoff=0.6)
        if matches:
            return cls.PROP_MAP[matches[0]]

        return None

    @classmethod
    def extract_value(cls, text: str) -> Optional[float]:
        """提取数值（处理 OCR 错误）"""
        # 处理常见 OCR 错误
        text = text.replace("O", "0").replace("o", "0")
        text = text.replace("l", "1").replace("I", "1").replace("i", "1")
        text = text.replace(",", ".")

        # 提取数字
        match = re.search(r"\d+\.?\d*", text)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None


class EchoOCRParser:
    """声骸 OCR 结果解析器"""

    def __init__(self):
        self.cost_parser = OCRCostParser()
        self.prop_parser = OCRPropertyParser()

    def parse(self, ocr_results: List) -> Optional[Dict]:
        """
        解析 OCR 结果，提取声骸信息

        Args:
            ocr_results: OCR 识别结果 [(text, confidence, bbox), ...]
                        或 RapidOCR 返回的格式

        Returns:
            解析结果 {
                'cost': int,
                'main_prop': str,
                'sub_props': List[Tuple[str, float]]
            }
        """
        if not ocr_results:
            return None

        # 处理不同的 OCR 返回格式
        processed_results = []
        for item in ocr_results:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                text = item[0]
                confidence = item[1] if len(item) > 1 else 0.0
                bbox = item[2] if len(item) > 2 else None

                # 确保 text 是字符串
                if isinstance(text, (list, tuple)):
                    text = " ".join(str(t) for t in text)
                elif not isinstance(text, str):
                    text = str(text)

                processed_results.append((text, confidence, bbox))

        if not processed_results:
            return None

        # 提取所有文本
        all_texts = [text for text, _, _ in processed_results]

        # 解析成本
        cost = self._parse_cost(all_texts)
        if cost is None:
            cost = 4  # 默认 4c

        # 解析主词条和副词条
        main_prop, sub_props = self._parse_properties(processed_results)

        return {
            'cost': cost,
            'main_prop': main_prop,
            'sub_props': sub_props,
            'raw_texts': all_texts
        }

    def _parse_cost(self, texts: List[str]) -> Optional[int]:
        """解析声骸成本"""
        combined = " ".join(texts)
        return self.cost_parser.parse(combined)

    def _parse_properties(
        self,
        ocr_results: List[Tuple[str, float, Tuple]]
    ) -> Tuple[Optional[str], List[Tuple[str, float]]]:
        """
        解析主词条和副词条

        Returns:
            (main_prop, sub_props)
        """
        props = []

        # 先提取所有属性名和数值
        all_props = []  # 存储属性名
        all_values = []  # 存储数值

        for text, confidence, bbox in ocr_results:
            text = text.strip()
            if not text:
                continue

            # 尝试识别为属性名
            normalized_prop = self.prop_parser.normalize(text)
            if normalized_prop:
                # 记录属性名及其位置（Y坐标）
                if len(bbox) > 0:
                    y_pos = bbox[0][1] if isinstance(bbox[0], list) else 0
                else:
                    y_pos = 0
                all_props.append((normalized_prop, y_pos))
                continue

            # 尝试提取数值
            value = self.prop_parser.extract_value(text)
            if value is not None:
                # 记录数值及其位置
                if len(bbox) > 0:
                    y_pos = bbox[0][1] if isinstance(bbox[0], list) else 0
                else:
                    y_pos = 0
                all_values.append((value, y_pos))

        # 匹配属性和数值（根据 Y 坐标就近匹配）
        matched_props = []
        for prop_name, prop_y in all_props:
            # 找到最近的数值
            best_value = None
            min_distance = float('inf')

            for value, value_y in all_values:
                distance = abs(prop_y - value_y)
                if distance < min_distance:
                    min_distance = distance
                    best_value = value

            # 如果找到数值且距离合理（同一行或相邻行）
            if best_value is not None and min_distance < 50:
                matched_props.append((prop_name, best_value))

        # 分离主词条和副词条
        if not matched_props:
            return None, []

        # 简单策略：属性名和数值匹配的第一对作为主词条
        # 或者：数值最大的作为主词条
        main_prop = None
        sub_props = []

        # 按数值排序
        sorted_props = sorted(matched_props, key=lambda x: x[1], reverse=True)

        if sorted_props:
            # 数值最大的为主词条
            main_prop = sorted_props[0][0]
            # 其余为副词条
            sub_props = sorted_props[1:]

        return main_prop, sub_props


def main():
    """测试解析器"""
    # 测试数据
    test_ocr_results = [
        ("暴击", 0.95, (0, 0, 100, 30)),
        ("暴击 3.5", 0.92, (0, 40, 100, 70)),
        ("暴击伤害 6.2", 0.90, (0, 80, 100, 110)),
        ("攻击% 5.3", 0.88, (0, 120, 100, 150)),
        ("共鸣技能伤害加成 7.8", 0.85, (0, 160, 100, 190)),
    ]

    parser = EchoOCRParser()
    result = parser.parse(test_ocr_results)

    if result:
        print("解析结果:")
        print(f"成本: {result['cost']}c")
        print(f"主词条: {result['main_prop']}")
        print("副词条:")
        for prop, value in result['sub_props']:
            print(f"  {prop}: {value}")


if __name__ == "__main__":
    main()

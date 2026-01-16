"""
OCR 结果解析器 - 增强版
集成词条识别逻辑文档的所有优化功能
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from difflib import get_close_matches
from copy import deepcopy

logger = logging.getLogger(__name__)


class TraditionalConverter:
    """繁体字转换器"""

    # 繁简对照表
    TRADITIONAL_MAP = {
        '攻擊': '攻击',
        '暴擊': '暴击',
        '傷害': '伤害',
        '防禦': '防御',
        '共鳴': '共鸣',
        '屬性': '属性',
        '治療': '治疗',
        '效率': '效率',
        '加成': '加成',
        '擊': '击',
        '撃': '击',  # 日文汉字
        '擴': '扩',
        '減': '减',
        '禦': '御',
    }

    @classmethod
    def convert(cls, text: str) -> str:
        """转换繁体字为简体"""
        result = text
        for trad, simp in cls.TRADITIONAL_MAP.items():
            result = result.replace(trad, simp)
        return result


class NumericCleaner:
    """数值清理器 - 处理 OCR 识别错误"""

    # 副词条档位范围（用于智能修复）
    SUB_PROP_RANGES = {
        "暴击": (6.0, 10.5),
        "暴击伤害": (12.0, 21.0),
        "攻击%": (6.0, 12.0),
        "生命%": (6.0, 12.0),
        "防御%": (8.0, 15.0),
        "攻击": (30, 60),
        "生命": (320, 580),
        "防御": (40, 70),
        "共鸣效率": (6.5, 12.5),
        # 伤害加成类（所有伤害加成档位相同）
        "属性伤害加成": (6.0, 12.0),
        "普攻伤害加成": (6.0, 12.0),
        "重击伤害加成": (6.0, 12.0),
        "共鸣技能伤害加成": (6.0, 12.0),
        "共鸣解放伤害加成": (6.0, 12.0),
        "治疗效果加成": (6.0, 12.0),
    }

    @classmethod
    def clean(cls, text: str) -> str:
        """
        清理 OCR 识别错误的数值文本

        处理规则：
        - o/O → 0
        - l/I/i → 1
        - S/s → 5
        - z → 2
        - 移除无关字符
        """
        # 字符替换
        text = text.replace('o', '0').replace('O', '0')
        text = text.replace('l', '1').replace('I', '1').replace('i', '1')
        text = text.replace('S', '5').replace('s', '5')
        text = text.replace('z', '2').replace('Z', '2')
        text = text.replace('。', '.').replace('．', '.')
        text = text.replace('％', '%').replace('96', '%')

        # 移除无关字符，保留数字、小数点、百分号、正负号
        text = re.sub(r'[^\d.%+-]', '', text)

        return text

    @classmethod
    def extract_value(cls, text: str, prop_name: str = None) -> Optional[float]:
        """
        从文本中提取数值，智能修复 OCR 错误

        处理场景：
        - 10.9 识别为 109 -> 除以 10
        - 7.5 识别为 75 -> 除以 10
        - 12.6 识别为 126 -> 除以 10

        Args:
            text: OCR 识别的文本
            prop_name: 属性名（可选，用于更精准的修复）
        """
        cleaned = cls.clean(text)
        match = re.search(r'[\d.]+', cleaned)
        if not match:
            return None

        try:
            value = float(match.group())

            # 智能修复：检查数值是否需要除以 10 或 100
            if prop_name:
                value = cls._fix_value_by_prop(prop_name, value)

            return value
        except ValueError:
            pass

        return None

    @classmethod
    def _fix_value_by_prop(cls, prop_name: str, value: float) -> float:
        """
        根据属性名智能修复数值

        如果数值明显超出合理范围，尝试除以 10 或 100
        """
        # 标准化属性名：移除可能的 % 后缀
        if prop_name.endswith('%'):
            base_prop = prop_name[:-1]
        else:
            base_prop = prop_name

        # 获取该属性的合理范围
        if base_prop in cls.SUB_PROP_RANGES:
            min_val, max_val = cls.SUB_PROP_RANGES[base_prop]

            # 策略1: 如果值本身在范围内，直接返回
            if min_val <= value <= max_val:
                return value

            # 策略2: 尝试除以 10（无论当前值多大，只要结果在范围内就修复）
            value_div10 = value / 10.0
            if min_val <= value_div10 <= max_val:
                logger.info(f"数值修复: {prop_name} {value} -> {value_div10} (除以 10)")
                return value_div10

            # 策略3: 尝试除以 100
            value_div100 = value / 100.0
            if min_val <= value_div100 <= max_val:
                logger.info(f"数值修复: {prop_name} {value} -> {value_div100} (除以 100)")
                return value_div100

        return value


class PropertyMatcher:
    """属性名称匹配器"""

    # 标准词条名称
    STANDARD_TERMS = [
        "攻击", "攻击%",
        "生命", "生命%",
        "防御", "防御%",
        "暴击", "暴击伤害",
        "共鸣效率",
        "属性伤害加成",
        "普攻伤害加成", "重击伤害加成",
        "共鸣技能伤害加成", "共鸣解放伤害加成",
        "治疗效果加成",
    ]

    # 别名映射表
    TERM_ALIASES = {
        # 攻击类
        "攻击力": "攻击",
        "攻击力%": "攻击%",
        "攻击百分比": "攻击%",

        # 生命类
        "生命值": "生命",
        "生命值%": "生命%",
        "生命百分比": "生命%",

        # 防御类
        "防御力": "防御",
        "防御力%": "防御%",
        "防御百分比": "防御%",

        # 暴击类
        "暴击率": "暴击",
        "暴击概率": "暴击",
        "暴伤": "暴击伤害",
        "暴击伤害%": "暴击伤害",

        # 共鸣效率
        "共鸣充能": "共鸣效率",
        "充能效率": "共鸣效率",

        # 属性伤害
        "元素伤害": "属性伤害加成",
        "元素伤害加成": "属性伤害加成",
        "湮灭伤害加成": "属性伤害加成",
        "导电伤害加成": "属性伤害加成",
        "热熔伤害加成": "属性伤害加成",
        "衍射伤害加成": "属性伤害加成",
        "气动伤害加成": "属性伤害加成",
        "冷凝伤害加成": "属性伤害加成",
    }

    @classmethod
    def normalize(cls, prop_name: str) -> Optional[str]:
        """
        标准化属性名

        优先级：
        1. 繁体字转换
        2. 精确匹配
        3. 别名匹配
        4. 模糊匹配 (60% 相似度)
        """
        # 1. 繁体字转换
        prop_name = TraditionalConverter.convert(prop_name)
        prop_name = prop_name.strip().replace(" ", "")

        # 2. 精确匹配
        if prop_name in cls.STANDARD_TERMS:
            return prop_name

        # 3. 别名匹配
        if prop_name in cls.TERM_ALIASES:
            return cls.TERM_ALIASES[prop_name]

        # 4. 模糊匹配
        matches = get_close_matches(prop_name, cls.STANDARD_TERMS, n=1, cutoff=0.6)
        if matches:
            logger.debug(f"模糊匹配: '{prop_name}' → '{matches[0]}'")
            return matches[0]

        logger.debug(f"无法匹配属性名: '{prop_name}'")
        return None


class CostAnalyzer:
    """COST 分析器 - 智能判断声骸 COST"""

    # 固定词条 (100% 准确)
    FIXED_INDICATORS = {
        "4": {"攻击": 150},
        "3": {"攻击": 100},
        "1": {"生命": 2280},
    }

    # 强特征词条
    STRONG_FEATURES = {
        "3": {"属性伤害加成": 30.0},
    }

    # 独有词条
    EXCLUSIVE_TERMS = {
        "4": ["暴击", "暴击伤害", "治疗效果加成"],
        "3": ["共鸣效率"],
    }

    # 变动词条数值特征 (允许 5% 误差)
    VARIABLE_RANGES = {
        "4": {
            "攻击%": 33.0,
            "生命%": 33.0,
            "防御%": 41.8,
        },
        "3": {
            "攻击%": 30.0,
            "生命%": 30.0,
            "防御%": 38.0,
        },
        "1": {
            "攻击%": 18.0,
            "生命%": 22.8,
            "防御%": 18.0,
        },
    }

    @classmethod
    def detect_cost(cls, props: List[Tuple[str, float]]) -> str:
        """
        自动判断 COST

        判断优先级：
        1. 固定词条 (100% 准确)
        2. 强特征词条
        3. 独有词条
        4. 变动词条数值特征
        5. 兜底: 返回 C4
        """
        if not props:
            return "4"

        logger.debug(f"开始判断 COST，词条数量: {len(props)}")

        # 1. 检查固定词条
        for cost, fixed_props in cls.FIXED_INDICATORS.items():
            for prop_name, prop_value in props:
                if prop_name in fixed_props:
                    if abs(prop_value - fixed_props[prop_name]) < 0.1:
                        logger.info(f"✅ 通过固定词条判断 COST: {prop_name}={prop_value} → C{cost}")
                        return cost

        # 2. 检查强特征词条
        for cost, features in cls.STRONG_FEATURES.items():
            for prop_name, prop_value in props:
                if prop_name in features:
                    if abs(prop_value - features[prop_name]) < 1.5:  # 5% 误差
                        logger.info(f"✅ 通过强特征词条判断 COST: {prop_name}={prop_value} → C{cost}")
                        return cost

        # 3. 检查独有词条 (主词条数值范围)
        for cost, exclusive_terms in cls.EXCLUSIVE_TERMS.items():
            for prop_name, prop_value in props:
                if prop_name in exclusive_terms:
                    # 主词条数值通常较大
                    if prop_value > 20:  # 主词条阈值
                        logger.info(f"✅ 通过独有词条判断 COST: {prop_name}={prop_value} → C{cost}")
                        return cost

        # 4. 综合评分：变动词条匹配
        scores = {"4": 0, "3": 0, "1": 0}

        for prop_name, prop_value in props:
            for cost, ranges in cls.VARIABLE_RANGES.items():
                if prop_name in ranges:
                    expected = ranges[prop_name]
                    if abs(prop_value - expected) / expected <= 0.05:  # 5% 误差
                        scores[cost] += 1
                        logger.debug(f"匹配变动词条: C{cost} {prop_name}={prop_value} (期望={expected})")

        logger.debug(f"COST 评分: {scores}")

        # 判断得分
        max_score = max(scores.values())
        if max_score > 0:
            # 找出所有最高分的 COST
            candidates = [cost for cost, score in scores.items() if score == max_score]

            if len(candidates) == 1:
                result = candidates[0]
                logger.info(f"✅ 通过变动词条判断 COST: {result} (得分={max_score})")
                return result
            elif max_score >= 2:  # 得分差距明显
                # 优先返回高 COST
                result = sorted(candidates, key=lambda x: int(x), reverse=True)[0]
                logger.info(f"✅ 通过变动词条判断 COST: {result} (得分={max_score}, 多候选)")
                return result

        # 5. 兜底：返回 C4
        logger.warning("⚠️ 未找到明确的主词条特征，默认判断为 C4")
        return "4"


class PropertyValueValidator:
    """词条数值验证器 - 严格档位验证"""

    # 主词条数值范围
    MAIN_PROP_RANGES = {
        "攻击": {"4": 150, "3": 100},
        "暴击": {"4": 22.0},
        "暴击伤害": {"4": 44.0},
        "治疗效果加成": {"4": 26.4},
        "生命%": {"4": 33.0, "3": 30.0, "1": 22.8},
        "防御%": {"4": 41.8, "3": 38.0, "1": 18.0},
        "攻击%": {"4": 33.0, "3": 30.0, "1": 18.0},
        "属性伤害加成": {"3": 30.0},
        "共鸣效率": {"3": 32.0},
        "生命": {"1": 2280},
    }

    # 副词条档位 (固定值，不允许范围内任意值)
    SUB_PROP_TIERS = {
        "攻击": [30, 40, 50, 60],
        "攻击%": [6.46, 7.10, 7.90, 8.60, 9.40, 10.10, 10.90, 11.60],
        "生命": [320, 360, 390, 430, 470, 510, 540, 580],
        "生命%": [6.40, 7.10, 7.90, 8.60, 9.40, 10.10, 10.90, 11.60],
        "防御": [40, 50, 60, 70],
        "防御%": [8.10, 9.0, 10.0, 10.90, 11.80, 12.80, 13.80, 14.7],
        "暴击": [6.30, 6.90, 7.50, 8.10, 8.70, 9.30, 9.90, 10.50],
        "暴击伤害": [12.6, 13.8, 15.0, 16.2, 17.4, 18.6, 19.8, 21.0],
        "共鸣效率": [6.80, 7.60, 8.40, 9.20, 10.00, 10.80, 11.60, 12.40],
        "普攻伤害加成": [6.40, 7.10, 7.90, 8.60, 9.40, 10.10, 10.90, 11.60],
        "重击伤害加成": [6.40, 7.10, 7.90, 8.60, 9.40, 10.10, 10.90, 11.60],
        "共鸣技能伤害加成": [6.40, 7.10, 7.90, 8.60, 9.40, 10.10, 10.90, 11.60],
        "共鸣解放伤害加成": [6.40, 7.10, 7.90, 8.60, 9.40, 10.10, 10.90, 11.60],
    }

    @classmethod
    def is_main_prop(cls, prop_name: str, value: float, cost: str) -> bool:
        """
        判断是否为主词条

        Args:
            prop_name: 属性名称
            value: 数值
            cost: COST ("1", "3", "4")

        Returns:
            True 如果是主词条
        """
        if prop_name not in cls.MAIN_PROP_RANGES:
            return False

        cost_ranges = cls.MAIN_PROP_RANGES[prop_name]
        if cost not in cost_ranges:
            return False

        expected = cost_ranges[cost]
        tolerance = expected * 0.05  # 5% 误差

        return abs(value - expected) <= tolerance

    @classmethod
    def is_valid_sub_prop(cls, prop_name: str, value: float) -> bool:
        """
        验证是否为有效的副词条档位

        Args:
            prop_name: 属性名称
            value: 数值

        Returns:
            True 如果匹配某个档位
        """
        if prop_name not in cls.SUB_PROP_TIERS:
            return False

        tiers = cls.SUB_PROP_TIERS[prop_name]
        tolerance = 0.05  # 固定档位，允许极小误差

        for tier in tiers:
            if abs(value - tier) <= tolerance:
                return True

        return False

    @classmethod
    def validate_prop(cls, prop_name: str, value: float, cost: str) -> str:
        """
        验证词条并返回类型

        优先级策略：
        1. 优先判断为副词条（因为声骸有4个副词条，更容易发生冲突）
        2. 如果不是副词条，再检查主词条

        Returns:
            "main", "sub", 或 "invalid"
        """
        # 先检查副词条（优先级更高，避免误判）
        if cls.is_valid_sub_prop(prop_name, value):
            return "sub"

        # 再检查主词条
        if cls.is_main_prop(prop_name, value, cost):
            return "main"

        return "invalid"


class EchoOCRParser:
    """声骸 OCR 结果解析器 - 增强版"""

    def __init__(self):
        self.property_matcher = PropertyMatcher()
        self.cost_analyzer = CostAnalyzer()
        self.validator = PropertyValueValidator()
        self.numeric_cleaner = NumericCleaner()

    def parse(self, ocr_results: List) -> Optional[Dict]:
        """
        解析 OCR 结果，提取声骸信息

        Args:
            ocr_results: OCR 识别结果 [(text, confidence, bbox), ...]

        Returns:
            解析结果 {
                'cost': str,
                'main_prop': Tuple[str, float],
                'sub_props': List[Tuple[str, float]],
                'raw_texts': List[str],
                'debug_info': Dict
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

                # 繁体字转换
                text = TraditionalConverter.convert(text)

                processed_results.append((text, confidence, bbox))

        if not processed_results:
            return None

        logger.info(f"处理了 {len(processed_results)} 条 OCR 结果")

        # 提取所有文本
        all_texts = [text for text, _, _ in processed_results]

        # 解析属性和数值
        matched_props = self._parse_properties(processed_results)

        if not matched_props:
            logger.warning("未能匹配到任何词条")
            return {
                'cost': '4',
                'main_prop': None,
                'sub_props': [],
                'raw_texts': all_texts,
                'debug_info': {'message': '未能匹配到任何词条'}
            }

        # 自动判断 COST
        cost = self.cost_analyzer.detect_cost([(p[0], p[1]) for p in matched_props])

        # 按Y坐标排序（从上到下）
        matched_props_sorted = sorted(matched_props, key=lambda x: x[2])

        # 基于位置判断主副词条：前2个是主词条，后5个是副词条
        main_candidates = []  # 主词条候选
        sub_props = []
        invalid_props = []

        for idx, (prop_name, prop_value, y_pos) in enumerate(matched_props_sorted):
            # 前2个：主词条候选
            # 后5个：副词条
            is_main_position = idx < 2

            # 先进行档位验证
            prop_type = self.validator.validate_prop(prop_name, prop_value, cost)

            if is_main_position:
                # 主词条位置：档位匹配为主词条则为主词条候选，否则记录为无效
                if prop_type == "main":
                    main_candidates.append((prop_name, prop_value))
                    logger.info(f"✅ [位置{idx+1}] 识别为主词条候选: {prop_name} = {prop_value} (Y={y_pos:.1f})")
                else:
                    logger.warning(f"⚠️ [位置{idx+1}] 主词条位置但档位不符: {prop_name} = {prop_value} (档位={prop_type}, Y={y_pos:.1f})")
                    invalid_props.append((prop_name, prop_value, f"主词条位置但档位={prop_type}"))
            else:
                # 副词条位置：档位匹配为副词条则为副词条，否则记录为无效
                if prop_type == "sub":
                    sub_props.append((prop_name, prop_value))
                    logger.debug(f"✅ [位置{idx+1}] 识别为副词条: {prop_name} = {prop_value} (Y={y_pos:.1f})")
                elif prop_type == "main":
                    logger.warning(f"⚠️ [位置{idx+1}] 副词条位置但符合主词条档位: {prop_name} = {prop_value} (Y={y_pos:.1f})")
                    # 强制作为副词条（基于位置的优先级更高）
                    sub_props.append((prop_name, prop_value))
                    logger.info(f"   → 强制判定为副词条（基于位置）")
                else:
                    logger.warning(f"❌ [位置{idx+1}] 无效词条: {prop_name} = {prop_value} (Y={y_pos:.1f})")
                    invalid_props.append((prop_name, prop_value, f"档位={prop_type}"))

                    # 提供更详细的错误信息
                    if prop_name in self.validator.SUB_PROP_TIERS:
                        valid_tiers = self.validator.SUB_PROP_TIERS[prop_name]
                        logger.warning(f"   {prop_name} 的有效副词条档位: {valid_tiers}")
                        # 找到最接近的档位
                        closest = min(valid_tiers, key=lambda x: abs(x - prop_value))
                        diff = abs(prop_value - closest)
                        logger.warning(f"   最接近的副词条档位: {closest} (差距: {diff:.1f})")
                    if prop_name in self.validator.MAIN_PROP_RANGES and cost in self.validator.MAIN_PROP_RANGES[prop_name]:
                        main_value = self.validator.MAIN_PROP_RANGES[prop_name][cost]
                        logger.warning(f"   {prop_name} 的有效主词条档位 (C{cost}): {main_value}")
                        diff = abs(prop_value - main_value)
                        logger.warning(f"   与主词条差距: {diff:.1f}")

        # 从主词条候选中选择2个（1个固定 + 1个随机）
        main_props = []  # 存储2个主词条
        all_main_candidates = []  # 保存所有主词条候选

        if main_candidates:
            all_main_candidates = main_candidates.copy()  # 记录所有候选

            if len(main_candidates) == 1:
                # 只有1个主词条候选
                main_props = [main_candidates[0]]
            elif len(main_candidates) == 2:
                # 刚好2个，直接使用
                main_props = main_candidates
            else:
                # 多于2个，需要选择：优先固定词条 + 优先级最高的随机词条

                # 1. 优先选择固定词条（100% 准确）
                # C4: 攻击=150, C3: 攻击=100, C1: 生命=2280
                fixed_props = {
                    ("攻击", 150.0): "4",
                    ("攻击", 100.0): "3",
                    ("生命", 2280.0): "1",
                }

                # 先选择固定词条
                fixed_main = None
                for candidate in main_candidates:
                    if candidate in fixed_props:
                        fixed_main = candidate
                        logger.info(f"✅ 识别为固定主词条: {candidate[0]} = {candidate[1]} (C{fixed_props[candidate]})")
                        break

                if fixed_main:
                    main_props.append(fixed_main)
                    remaining_candidates = [c for c in main_candidates if c != fixed_main]

                    # 2. 从剩余候选中选择随机主词条（按优先级）
                    priority_order = ["暴击伤害", "暴击", "治疗效果加成", "属性伤害加成",
                                     "共鸣效率", "攻击%", "生命%", "防御%"]

                    random_main = None
                    for priority_name in priority_order:
                        for candidate in remaining_candidates:
                            if candidate[0] == priority_name:
                                random_main = candidate
                                break
                        if random_main:
                            break

                    if not random_main:
                        # 按优先级没找到，选择数值最大的
                        random_main = max(remaining_candidates, key=lambda x: x[1])

                    main_props.append(random_main)
                    logger.info(f"✅ 识别为随机主词条: {random_main[0]} = {random_main[1]}")

                    # 其余主词条候选：丢弃（一个声骸只有2个主词条）
                    for candidate in remaining_candidates:
                        if candidate != random_main:
                            logger.info(f"⚠️ 主词条候选被丢弃: {candidate[0]} = {candidate[1]} "
                                      f"(一个声骸只有2个主词条: 1固定+1随机)")
                else:
                    # 没有固定词条，选择优先级最高的2个
                    priority_order = ["暴击伤害", "暴击", "治疗效果加成", "属性伤害加成",
                                     "共鸣效率", "攻击%", "生命%", "防御%", "攻击", "生命"]

                    selected = []
                    for priority_name in priority_order:
                        if len(selected) >= 2:
                            break
                        for candidate in main_candidates:
                            if candidate[0] == priority_name and candidate not in selected:
                                selected.append(candidate)
                                break

                    # 如果优先级选择不足2个，按数值补充
                    if len(selected) < 2:
                        for candidate in sorted(main_candidates, key=lambda x: x[1], reverse=True):
                            if candidate not in selected:
                                selected.append(candidate)
                            if len(selected) >= 2:
                                break

                    main_props = selected[:2]

                    for prop in main_props:
                        logger.info(f"✅ 识别为主词条: {prop[0]} = {prop[1]}")

                    # 其余丢弃
                    for candidate in main_candidates:
                        if candidate not in main_props:
                            logger.info(f"⚠️ 主词条候选被丢弃: {candidate[0]} = {candidate[1]}")

            logger.info(f"✅ 最终识别到 {len(main_props)} 个主词条")

        # 提取主词条（保持向后兼容：返回第一个，或者返回元组）
        main_prop = main_props[0] if main_props else None

        return {
            'cost': cost,
            'main_prop': main_prop,  # 向后兼容：返回第一个主词条
            'main_props': main_props,  # 新增：所有主词条（2个：1固定+1随机）
            'sub_props': sub_props,
            'raw_texts': all_texts,
            'all_main_candidates': all_main_candidates,
            'debug_info': {
                'total_props': len(matched_props),
                'main_count': len(main_props),
                'sub_count': len(sub_props),
                'all_main_candidates_count': len(all_main_candidates),
            }
        }

    def _parse_properties(
        self,
        ocr_results: List[Tuple[str, float, Tuple]]
    ) -> List[Tuple[str, float, float]]:
        """
        解析属性和数值

        Returns:
            [(属性名, 数值, Y坐标), ...]
        """
        props = []
        all_prop_names = []  # (属性名, y坐标)
        all_values = []  # (数值, y坐标)

        for text, confidence, bbox in ocr_results:
            text = text.strip()
            if not text:
                continue

            # 过滤掉明显无关的文本
            if self._is_irrelevant_text(text):
                continue

            # 新增：尝试分离属性名和数值（处理"暴击伤害44.0"这种情况）
            separated = self._separate_prop_and_value(text)
            if separated:
                # 成功分离
                prop_name, prop_value = separated
                y_pos = self._get_y_position(bbox)

                # 验证属性名
                normalized_prop = self.property_matcher.normalize(prop_name)
                if normalized_prop:
                    all_prop_names.append((normalized_prop, y_pos))
                    logger.debug(f"分离属性名: '{text}' → '{normalized_prop}' + {prop_value}")
                    # 同时记录数值
                    all_values.append((prop_value, y_pos, False))
                    continue

            # 尝试识别为属性名
            normalized_prop = self.property_matcher.normalize(text)
            if normalized_prop:
                y_pos = self._get_y_position(bbox)
                all_prop_names.append((normalized_prop, y_pos))
                logger.debug(f"识别属性名: '{text}' → '{normalized_prop}'")
                continue

            # 尝试提取数值
            value = self.numeric_cleaner.extract_value(text)
            if value is not None:
                # 检查是否包含百分比符号
                has_percent = '%' in text or '％' in text or '96' in text
                y_pos = self._get_y_position(bbox)
                all_values.append((value, y_pos, has_percent))
                logger.debug(f"提取数值: '{text}' → {value}")
                continue

        # 匹配属性和数值 (根据 Y 坐标就近匹配)
        matched = self._match_props_to_values(all_prop_names, all_values)

        # 智能推断：修正 OCR 错误的属性名
        matched = self._intelligent_infer(matched)

        return matched

    def _separate_prop_and_value(self, text: str) -> Optional[Tuple[str, float]]:
        """
        尝试分离属性名和数值

        处理情况：
        - "暴击伤害44.0" → ("暴击伤害", 44.0)
        - "攻击150" → ("攻击", 150.0)
        - "生命%22.8%" → ("生命%", 22.8)
        """
        # 匹配模式：属性名(可能含%) + 数值(可能含%)
        # 例如：暴击伤害44.0、攻击150、生命%22.8%

        # 模式1：属性名 + 数值（无分隔符）
        match = re.match(r'([^\d\.]+)(\d+\.?\d*)%?', text)
        if match:
            prop_part = match.group(1).strip()
            value_part = match.group(2)

            # 提取数值
            value = self.numeric_cleaner.extract_value(value_part)
            if value is not None:
                # 检查属性名是否有效
                normalized = self.property_matcher.normalize(prop_part)
                if normalized:
                    return (normalized, value)

        return None

    def _is_irrelevant_text(self, text: str) -> bool:
        """过滤无关文本"""
        # 游戏界面信息
        irrelevant_patterns = [
            r'FPS\d+',
            r'GPU\d+',
            r'\d+ x \d+',  # 尺寸标注
            # 移除 r'^\d+$' - 纯数字可能是有效数值（如攻击150、防御60）
        ]

        for pattern in irrelevant_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        # 检查是否为特别大的纯数字（可能是坐标或ID）
        if re.match(r'^\d{5,}$', text):  # 5位及以上纯数字
            return True

        return False

    def _intelligent_infer(
        self,
        matched: List[Tuple[str, float, float]]
    ) -> List[Tuple[str, float, float]]:
        """
        智能推断：修正 OCR 错误的属性名和数值

        处理场景：
        1. "生命" 7.9 → "生命%" 7.9 (OCR 丢失了%)
        2. "攻击" 10.1 → "攻击%" 10.1 (OCR 丢失了%)
        3. "共鸣解放伤害加成" 109.0 → "共鸣解放伤害加成" 10.9 (小数点丢失)

        Args:
            matched: [(属性名, 数值, Y坐标), ...]

        Returns:
            [(属性名, 数值, Y坐标), ...]
        """
        inferred = []

        for prop_name, value, y_pos in matched:
            # 先修正数值（如果数值异常）
            fixed_value = self.numeric_cleaner._fix_value_by_prop(prop_name, value)

            # 再检查是否需要修正属性名
            corrected_name = self._infer_prop_name(prop_name, fixed_value)
            if corrected_name != prop_name:
                logger.info(f"✅ 智能推断: '{prop_name}' {fixed_value} → '{corrected_name}' {fixed_value}")
                inferred.append((corrected_name, fixed_value, y_pos))
            else:
                # 即使属性名不需要修正，数值可能已被修正
                if fixed_value != value:
                    logger.info(f"✅ 数值修正: '{prop_name}' {value} → {fixed_value}")
                inferred.append((prop_name, fixed_value, y_pos))

        return inferred

    def _infer_prop_name(self, prop_name: str, value: float) -> str:
        """
        根据数值推断正确的属性名

        规则：
        1. 优先检查：如果固定值在副词条档位中存在，不推断为百分比
        2. 如果属性名是固定值类型（攻击、生命、防御），但数值很小（<100）
           → 推断为百分比类型
        3. 检查推断后的属性名是否有匹配的档位
        4. 特殊值推断：22.8 → 生命%, 18.0 → 攻击%/防御%
        """
        # 固定值属性名 → 可能的百分比属性名
        fixed_to_percent_map = {
            "攻击": "攻击%",
            "生命": "生命%",
            "防御": "防御%",
        }

        # 特殊值映射（C1 主词条）
        special_values = {
            22.8: "生命%",  # C1 生命%主词条
            18.0: None,    # 可能是攻击%或防御%，需要根据上下文
        }

        # 规则0：优先检查 - 如果固定值在副词条档位中存在，不推断为百分比
        # 这是为了避免把"攻击 30"（副词条）误推断为"攻击%" 30.0（主词条）
        if prop_name in fixed_to_percent_map and value < 100:
            # 检查当前固定值属性是否在副词条档位中
            if prop_name in self.validator.SUB_PROP_TIERS:
                tiers = self.validator.SUB_PROP_TIERS[prop_name]
                for tier in tiers:
                    if abs(value - tier) <= 0.1:  # 匹配副词条档位
                        logger.debug(f"✅ 保留为副词条: '{prop_name}' {value} (匹配副词条档位)")
                        return prop_name  # 不推断，保持原样

            # 检查百分比版本是否在副词条档位中（如果是，应该推断为百分比）
            percent_name = fixed_to_percent_map[prop_name]
            if percent_name in self.validator.SUB_PROP_TIERS:
                tiers = self.validator.SUB_PROP_TIERS[percent_name]
                for tier in tiers:
                    if abs(value - tier) <= 0.1:  # 匹配副词条档位
                        logger.debug(f"✅ 推断为副词条: '{prop_name}' {value} → '{percent_name}' {value}")
                        return percent_name  # 推断为百分比版本

        # 规则1：特殊值优先推断
        if value in special_values:
            target_prop = special_values[value]
            if target_prop:
                if prop_name in ["生命", "攻击", "防御"]:
                    logger.info(f"✅ 特殊值推断: '{prop_name}' {value} → '{target_prop}' {value}")
                    return target_prop

        # 规则2：如果是固定值属性名，且数值很小（<100），可能需要加%
        if prop_name in fixed_to_percent_map and value < 100:
            percent_name = fixed_to_percent_map[prop_name]

            # 检查百分比属性是否有这个档位（排除副词条档位中已存在的值）
            if percent_name in self.validator.SUB_PROP_TIERS:
                tiers = self.validator.SUB_PROP_TIERS[percent_name]
                for tier in tiers:
                    if abs(value - tier) <= 0.1:  # 档位匹配
                        # 只有当原属性名不在副词条档位中时，才推断为百分比
                        if prop_name not in self.validator.SUB_PROP_TIERS:
                            return percent_name  # 返回百分比版本

            # 检查是否为主词条档位
            if percent_name in self.validator.MAIN_PROP_RANGES:
                for cost, main_value in self.validator.MAIN_PROP_RANGES[percent_name].items():
                    if abs(value - main_value) <= 1.0:  # 主词条允许1%误差
                        logger.info(f"✅ 主词条推断: '{prop_name}' {value} → '{percent_name}' {value} (C{cost})")
                        return percent_name

        # 如果没有匹配，返回原属性名
        return prop_name

    def _get_y_position(self, bbox) -> float:
        """获取 bbox 的 Y 坐标"""
        if bbox and len(bbox) > 0:
            if isinstance(bbox[0], list):
                return bbox[0][1]
            else:
                return float(bbox[1])
        return 0.0

    def _match_props_to_values(
        self,
        prop_names: List[Tuple[str, float]],
        values: List[Tuple[float, float, bool]]
    ) -> List[Tuple[str, float, float]]:
        """
        匹配属性名和数值

        Args:
            prop_names: [(属性名, y坐标), ...]
            values: [(数值, y坐标, 是否包含%), ...]

        Returns:
            [(属性名, 数值, Y坐标), ...]
        """
        matched = []
        used_values = set()  # 记录已使用的数值索引

        # 按距离排序所有可能的配对
        all_pairs = []
        for prop_idx, (prop_name, prop_y) in enumerate(prop_names):
            for val_idx, (value, value_y, _) in enumerate(values):
                distance = abs(prop_y - value_y)
                if distance < 50:  # 距离阈值
                    all_pairs.append((distance, prop_idx, val_idx, prop_name, value, value_y))

        # 按距离排序（最近的优先）
        all_pairs.sort(key=lambda x: x[0])

        # 贪心匹配：优先匹配距离最近的
        for distance, prop_idx, val_idx, prop_name, value, value_y in all_pairs:
            if val_idx not in used_values:
                matched.append((prop_name, value, value_y))
                used_values.add(val_idx)
                logger.debug(f"匹配词条: {prop_name} = {value} (距离={distance:.1f})")

        return matched


def main():
    """测试解析器"""
    # 模拟 OCR 结果
    test_ocr_results = [
        ("攻击", 0.95, (0, 0, 100, 30)),
        ("150", 0.92, (0, 40, 100, 70)),
        ("暴击", 0.90, (0, 80, 100, 110)),
        ("22.0%", 0.88, (0, 120, 100, 150)),
        ("暴击伤害", 0.85, (0, 160, 100, 190)),
        ("44.0%", 0.87, (0, 200, 100, 230)),
    ]

    parser = EchoOCRParser()
    result = parser.parse(test_ocr_results)

    if result:
        print("\n" + "=" * 60)
        print("解析结果")
        print("=" * 60)
        print(f"COST: C{result['cost']}")
        if result['main_prop']:
            print(f"主词条: {result['main_prop'][0]} = {result['main_prop'][1]}")
        print(f"副词条 ({len(result['sub_props'])} 个):")
        for prop, value in result['sub_props']:
            print(f"  {prop}: {value}")
        print(f"\n原始文本: {result['raw_texts']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()

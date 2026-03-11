"""
评分计算器模块
负责根据角色权重配置计算声骸得分
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from core.data_manager import DataManager, WeightConfig

logger = logging.getLogger(__name__)


class EchoCalculator:
    """声骸评分计算器"""

    # 声骸成本
    COST_MAP = {
        "1c": 1,
        "3c": 3,
        "4c": 4
    }

    # 属性标准化映射（处理 OCR 识别错误）
    PROP_NORMALIZE = {
        "攻击": "攻击",
        "攻击%": "攻击%",
        "攻击％": "攻击%",
        "生命": "生命",
        "生命%": "生命%",
        "生命％": "生命%",
        "防御": "防御",
        "防御%": "防御%",
        "防御％": "防御%",
        "暴击": "暴击",
        "暴击伤害": "暴击伤害",
        "暴击伤害%": "暴击伤害",
        "共鸣效率": "共鸣效率",
        "属性伤害加成": "属性伤害加成",
        "普攻伤害加成": "普攻伤害加成",
        "重击伤害加成": "重击伤害加成",
        "共鸣技能伤害加成": "共鸣技能伤害加成",
        "共鸣解放伤害加成": "共鸣解放伤害加成",
        "治疗效果加成": "治疗效果加成",
    }

    def __init__(self):
        """初始化计算器"""
        self.data_manager = DataManager()

    def normalize_prop_name(self, prop_name: str) -> Optional[str]:
        """
        标准化属性名称（处理 OCR 识别错误）

        Args:
            prop_name: 原始属性名

        Returns:
            标准化后的属性名，无法识别返回 None
        """
        # 移除空格
        prop_name = prop_name.replace(" ", "")

        # 直接匹配
        if prop_name in self.PROP_NORMALIZE:
            return self.PROP_NORMALIZE[prop_name]

        # 模糊匹配（使用 difflib）
        from difflib import get_close_matches
        matches = get_close_matches(prop_name, self.PROP_NORMALIZE.keys(), n=1, cutoff=0.6)
        if matches:
            return self.PROP_NORMALIZE[matches[0]]

        logger.warning(f"无法识别的属性: {prop_name}")
        return None

    def extract_number(self, text: str) -> Optional[float]:
        """
        从文本中提取数值（处理 OCR 常见错误）

        Args:
            text: 包含数值的文本

        Returns:
            提取的数值，失败返回 None
        """
        # 处理 OCR 常见错误
        text = text.replace("O", "0").replace("o", "0")  # O -> 0
        text = text.replace("l", "1").replace("I", "1").replace("i", "1")  # l/I/i -> 1
        text = text.replace(",", ".").replace(" ", "")  # , -> .

        # 提取数字（支持小数）
        match = re.search(r"\d+\.?\d*", text)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None

        return None

    def _get_score_max(self, config: WeightConfig, cost_key: str) -> float:
        """安全获取对应 cost 的最高分"""
        cost_index_map = {"1": 0, "3": 1, "4": 2}
        score_max_index = cost_index_map.get(cost_key)
        if score_max_index is None:
            logger.warning(f"无法识别的声骸成本: {cost_key}")
            return 0.0

        if score_max_index >= len(config.score_max):
            logger.warning(f"score_max 缺少成本 {cost_key}c 对应索引: {config.score_max}")
            return 0.0

        try:
            score_max = float(config.score_max[score_max_index])
        except (TypeError, ValueError):
            logger.warning(f"score_max 数值无效: {config.score_max}")
            return 0.0

        if score_max <= 0:
            logger.warning(f"score_max 非正数，无法对齐计算: {score_max}")
            return 0.0

        return score_max

    def calculate_main_score(
        self,
        prop_name: str,
        cost: int,
        config: WeightConfig,
        score_max: float = None
    ) -> Tuple[float, List[Tuple[str, float]]]:
        """
        计算主词条得分

        Args:
            prop_name: 主词条属性名
            cost: 声骸成本 (1/3/4)
            config: 角色权重配置
            score_max: 最高分（用于对齐）

        Returns:
            (主词条得分, [(属性名, 得分), ...])
        """
        cost_key = str(cost)
        if cost_key not in config.main_props:
            logger.warning(f"不支持的声骸成本: {cost}")
            return 0.0, []

        main_weights = config.main_props[cost_key]
        details = []

        # 处理多个主词条 (空格分隔)
        prop_parts = prop_name.split()
        i = 0
        total_score = 0.0

        logger.info(f"[计算器] 开始计算主词条得分: prop_name='{prop_name}', cost={cost}")
        logger.info(f"[计算器] 主词条原始文本: '{prop_name}'")
        logger.info(f"[计算器] 分词结果: {prop_parts}")

        while i < len(prop_parts):
            if i + 1 < len(prop_parts):
                # 属性名 + 数值
                p_name = prop_parts[i]
                try:
                    p_value = float(prop_parts[i + 1])
                    normalized_prop = self.normalize_prop_name(p_name)
                    if normalized_prop:
                        weight = main_weights.get(normalized_prop, 0.0)
                        score = p_value * weight  # 主词条也要计算: 数值 × 权重
                        total_score += score
                        logger.info(f"[计算器] 主词条: {p_name} {p_value} -> 权重={weight}, 得分={score:.2f}, 累计={total_score:.2f}")
                        details.append((f"{p_name} {p_value}", score))
                    else:
                        logger.warning(f"[计算器] 无法识别属性名: {p_name}")
                    i += 2
                    continue
                except ValueError:
                    pass

            # 单独的属性名（兼容旧输入：只有属性名，没有数值）
            normalized_prop = self.normalize_prop_name(prop_parts[i])
            if normalized_prop:
                weight = main_weights.get(normalized_prop, 0.0)
                score = weight
                total_score += score
                logger.info(f"[计算器] 主词条(无数值兼容): {prop_parts[i]} -> 权重={weight}, 得分={score}")
                details.append((prop_parts[i], score))
            else:
                logger.warning(f"[计算器] 无法识别属性名: {prop_parts[i]}")
            i += 1

        logger.info(f"[计算器] 主词条总分: {total_score}, 详情: {details}")
        return total_score, details

    def calculate_sub_score(
        self,
        sub_props: List[Tuple[str, float]],
        config: WeightConfig,
        score_max: float = None
    ) -> Tuple[float, List[Tuple[str, float]]]:
        """
        计算副词条得分

        Args:
            sub_props: 副词条列表 [(属性名, 数值), ...]
            config: 角色权重配置
            score_max: 最高分（用于对齐）

        Returns:
            (副词条得分, [(属性名, 得分), ...])
        """
        score = 0.0
        details = []

        for prop_name, value in sub_props:
            normalized_prop = self.normalize_prop_name(prop_name)
            if normalized_prop is None:
                continue

            weight = config.sub_props.get(normalized_prop, 0.0)
            prop_score = value * weight
            score += prop_score
            details.append((f"{prop_name} {value}", prop_score))

        return score, details

    def calculate(
        self,
        role_name: str,
        main_prop: str,
        cost: int,
        sub_props: List[Tuple[str, float]]
    ) -> Optional[Dict]:
        """
        计算声骸总分

        Args:
            role_name: 角色名称（目录名）
            main_prop: 主词条属性名
            cost: 声骸成本 (1/3/4)
            sub_props: 副词条列表 [(属性名, 数值), ...]

        Returns:
            计算结果字典 {
                'role': 角色名,
                'main_score': 主词条得分,
                'sub_score': 副词条得分,
                'total_raw': 原始总分,
                'total_aligned': 对齐总分,
                'max_score': 对齐满分 (50)
            }
            失败返回 None
        """
        config = self.data_manager.get_config(role_name)
        if config is None:
            logger.error(f"未找到角色配置: {role_name}")
            return None

        # 验证成本
        cost_key = str(cost)
        if cost_key not in config.main_props:
            logger.error(f"不支持的声骸成本: {cost}")
            return None

        score_max = self._get_score_max(config, cost_key)

        # 计算主词条得分（原始权重）
        main_score_raw, main_details_raw = self.calculate_main_score(main_prop, cost, config)

        # 计算副词条得分（原始权重 × 数值）
        sub_score_raw, sub_details_raw = self.calculate_sub_score(sub_props, config)

        # 原始总分
        total_raw = main_score_raw + sub_score_raw

        # 对齐分数 (50分制)
        aligned_score = (total_raw / score_max) * 50 if score_max > 0 else 0

        # 分别对齐主词条和副词条得分
        main_score_aligned = (main_score_raw / score_max) * 50 if score_max > 0 else 0
        sub_score_aligned = (sub_score_raw / score_max) * 50 if score_max > 0 else 0

        # 对齐每个词条的详细得分
        if score_max > 0:
            main_details_aligned = [(name, (score / score_max) * 50) for name, score in main_details_raw]
            sub_details_aligned = [(name, (score / score_max) * 50) for name, score in sub_details_raw]
        else:
            main_details_aligned = [(name, 0.0) for name, _ in main_details_raw]
            sub_details_aligned = [(name, 0.0) for name, _ in sub_details_raw]

        logger.info(f"[计算器] 原始得分: 主={main_score_raw:.3f}, 副={sub_score_raw:.3f}, 总={total_raw:.3f}")
        logger.info(f"[计算器] 对齐得分(50分制): 主={main_score_aligned:.2f}, 副={sub_score_aligned:.2f}, 总={aligned_score:.2f}")
        logger.info(f"[计算器] 最高分: {score_max}")

        return {
            "role": role_name,
            "config_name": config.name,
            "main_score": round(main_score_aligned, 2),  # 对齐后的主词条得分
            "sub_score": round(sub_score_aligned, 2),    # 对齐后的副词条得分
            "total_raw": total_raw,
            "total_aligned": round(aligned_score, 2),
            "max_score": 50,
            "main_details": main_details_aligned,  # 对齐后的主词条详情
            "sub_details": sub_details_aligned     # 对齐后的副词条详情
        }


def main():
    """测试计算器"""
    logging.basicConfig(level=logging.INFO)

    calculator = EchoCalculator()

    # 测试用例：今汐 4c 声骸
    role_name = "今汐"
    main_prop = "暴击"
    cost = 4
    sub_props = [
        ("暴击", 3.5),
        ("暴击伤害", 6.2),
        ("攻击%", 5.3),
        ("共鸣技能伤害加成", 7.8)
    ]

    result = calculator.calculate(role_name, main_prop, cost, sub_props)

    if result:
        print("\n评分结果:")
        print("=" * 50)
        print(f"角色: {result['role']} ({result['config_name']})")
        print(f"主词条得分: {result['main_score']}")
        print(f"副词条得分: {result['sub_score']:.2f}")
        print(f"原始总分: {result['total_raw']:.2f}")
        print(f"对齐总分: {result['total_aligned']}/{result['max_score']}")


if __name__ == "__main__":
    main()

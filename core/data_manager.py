"""
数据管理器模块
负责动态加载 data/weights/ 目录下的所有角色配置文件
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WeightConfig:
    """权重配置数据类"""
    name: str  # 角色配置名称
    main_props: Dict[str, Dict[str, float]]  # 主词条权重 {cost: {prop: weight}}
    sub_props: Dict[str, float]  # 副词条权重 {prop: weight}
    score_max: List[float]  # 未对齐最高分 [1c, 3c, 4c]


class DataManager:
    """数据管理器单例类"""

    _instance: Optional['DataManager'] = None

    def __new__(cls) -> 'DataManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化数据管理器"""
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True
        self.weights_dir = Path(__file__).parent.parent / "data" / "weights"
        self._configs: Dict[str, WeightConfig] = {}
        self._load_all_configs()

    def _load_all_configs(self) -> None:
        """扫描并加载所有角色配置文件"""
        if not self.weights_dir.exists():
            logger.warning(f"权重目录不存在: {self.weights_dir}")
            return

        for role_dir in self.weights_dir.iterdir():
            if not role_dir.is_dir():
                continue

            calc_file = role_dir / "calc.json"
            if not calc_file.exists():
                logger.warning(f"角色配置文件不存在: {calc_file}")
                continue

            try:
                config = self._load_config_file(calc_file)
                if config:
                    # 使用角色目录名作为键
                    role_name = role_dir.name
                    self._configs[role_name] = config
                    logger.info(f"成功加载角色配置: {role_name} - {config.name}")
            except Exception as e:
                logger.error(f"加载角色配置失败: {calc_file}, 错误: {e}")

    def _load_config_file(self, file_path: Path) -> Optional[WeightConfig]:
        """
        加载单个配置文件

        Args:
            file_path: 配置文件路径

        Returns:
            WeightConfig 对象，失败返回 None
        """
        try:
            # 使用 utf-8-sig 自动处理 BOM
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)

            return WeightConfig(
                name=data.get('name', ''),
                main_props=data.get('main_props', {}),
                sub_props=data.get('sub_props', {}),
                score_max=data.get('score_max', [])
            )
        except json.JSONDecodeError as e:
            logger.error(f"JSON 格式错误: {file_path}, 错误: {e}")
            return None
        except Exception as e:
            logger.error(f"读取配置文件失败: {file_path}, 错误: {e}")
            return None

    def get_config(self, role_name: str) -> Optional[WeightConfig]:
        """
        获取指定角色的配置

        Args:
            role_name: 角色名称（目录名）

        Returns:
            WeightConfig 对象，不存在返回 None
        """
        return self._configs.get(role_name)

    def get_all_roles(self) -> List[str]:
        """
        获取所有已加载的角色列表

        Returns:
            角色名称列表
        """
        return list(self._configs.keys())

    def reload_configs(self) -> None:
        """重新加载所有配置文件"""
        self._configs.clear()
        self._load_all_configs()


def main():
    """测试数据管理器"""
    logging.basicConfig(level=logging.INFO)

    manager = DataManager()

    print("\n已加载的角色配置:")
    print("=" * 50)
    for role_name in manager.get_all_roles():
        config = manager.get_config(role_name)
        if config:
            print(f"\n角色: {role_name}")
            print(f"配置名: {config.name}")
            print(f"主词条权重: {config.main_props}")
            print(f"副词条权重: {config.sub_props}")
            print(f"最高分: {config.score_max}")


if __name__ == "__main__":
    main()

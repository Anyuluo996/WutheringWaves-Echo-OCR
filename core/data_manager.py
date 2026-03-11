"""
数据管理器模块
负责本地权重释放、格式校验、动态加载与 GitHub 更新
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

logger = logging.getLogger(__name__)

SUPPORTED_COST_KEYS = {"1", "3", "4"}
GITHUB_DOWNLOAD_TIMEOUT_SECONDS = 30
GITHUB_API_WEIGHT_URLS = [
    "https://api.github.com/repos/Anyuluo996/WutheringWaves-Echo-OCR/zipball/main",
    "https://api.github.com/repos/Anyuluo996/WutheringWaves-Echo-OCR/zipball/master",
]
DEFAULT_GITHUB_WEIGHT_URLS = [
    "https://codeload.github.com/Anyuluo996/WutheringWaves-Echo-OCR/zip/refs/heads/main",
    "https://codeload.github.com/Anyuluo996/WutheringWaves-Echo-OCR/zip/refs/heads/master",
]


@dataclass
class WeightConfig:
    """权重配置数据类"""
    name: str  # 角色配置名称
    main_props: Dict[str, Dict[str, float]]  # 主词条权重 {cost: {prop: weight}}
    sub_props: Dict[str, float]  # 副词条权重 {prop: weight}
    score_max: List[float]  # 未对齐最高分 [1c, 3c, 4c]


@dataclass
class WeightOperationResult:
    """权重同步/更新结果"""
    added_files: int = 0
    updated_files: int = 0
    copied_builtin_files: int = 0
    skipped_files: int = 0
    repaired_files: List[str] = field(default_factory=list)
    invalid_files: List[str] = field(default_factory=list)
    loaded_roles: int = 0
    source_url: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "added_files": self.added_files,
            "updated_files": self.updated_files,
            "copied_builtin_files": self.copied_builtin_files,
            "skipped_files": self.skipped_files,
            "repaired_files": list(self.repaired_files),
            "invalid_files": list(self.invalid_files),
            "loaded_roles": self.loaded_roles,
            "source_url": self.source_url,
        }


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
        self.builtin_weights_dir = Path(__file__).parent.parent / "data" / "weights"
        self.weights_dir = self._resolve_local_weights_dir()
        self._configs: Dict[str, WeightConfig] = {}
        self._last_report: Dict[str, object] = {}
        self.reload_configs()

    def _resolve_local_weights_dir(self) -> Path:
        """解析本地可写权重目录"""
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data) / "WutheringWaves-Echo-OCR"
        else:
            base_dir = Path.home() / ".wuthering_waves_echo_ocr"
        return base_dir / "data" / "weights"

    def _read_json_file(self, file_path: Path) -> Tuple[Optional[dict], bool]:
        """读取 JSON 文件，兼容 BOM，并返回是否检测到 BOM"""
        try:
            raw = file_path.read_bytes()
            has_bom = raw.startswith(b"\xef\xbb\xbf")
            data = json.loads(raw.decode("utf-8-sig"))
            return data, has_bom
        except json.JSONDecodeError as e:
            logger.error(f"JSON 格式错误: {file_path}, 错误: {e}")
            return None, False
        except UnicodeDecodeError as e:
            logger.error(f"JSON 编码错误: {file_path}, 错误: {e}")
            return None, False
        except Exception as e:
            logger.error(f"读取配置文件失败: {file_path}, 错误: {e}")
            return None, False

    def _write_json_file(self, file_path: Path, data: dict) -> None:
        """将 JSON 以 UTF-8 无 BOM 格式写回文件"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, ensure_ascii=False, indent=2)
        file_path.write_text(content + "\n", encoding="utf-8")

    def _to_float(self, value) -> Optional[float]:
        """保守地将值转换为 float"""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None

    def _normalize_cost_key(self, cost_key) -> Optional[str]:
        """标准化 cost key，仅保留 1/3/4"""
        text = str(cost_key).strip().lower()
        if text.endswith("c"):
            text = text[:-1]
        return text if text in SUPPORTED_COST_KEYS else None

    def _sanitize_weight_data(self, data: dict, role_name: str) -> Tuple[Optional[dict], bool, List[str]]:
        """校验并尽量修复权重结构"""
        issues: List[str] = []
        changed = False

        if not isinstance(data, dict):
            return None, False, ["根节点不是对象"]

        name = str(data.get("name") or role_name).strip() or role_name
        if name != data.get("name"):
            changed = True
            issues.append("name 缺失或为空，已自动补全")

        main_props_raw = data.get("main_props")
        if not isinstance(main_props_raw, dict):
            return None, changed, ["main_props 不是对象"]

        main_props: Dict[str, Dict[str, float]] = {}
        for raw_cost, raw_props in main_props_raw.items():
            cost_key = self._normalize_cost_key(raw_cost)
            if cost_key is None:
                changed = True
                issues.append(f"忽略不支持的 cost: {raw_cost}")
                continue
            if not isinstance(raw_props, dict):
                changed = True
                issues.append(f"{cost_key}c 主词条不是对象，已跳过")
                continue

            normalized_props: Dict[str, float] = {}
            for raw_prop_name, raw_weight in raw_props.items():
                prop_name = str(raw_prop_name).strip()
                weight = self._to_float(raw_weight)
                if not prop_name or weight is None:
                    changed = True
                    issues.append(f"{cost_key}c 存在无法识别的主词条权重，已跳过")
                    continue
                normalized_props[prop_name] = weight
                if raw_prop_name != prop_name or raw_weight != weight:
                    changed = True

            if normalized_props:
                main_props[cost_key] = normalized_props
            else:
                changed = True
                issues.append(f"{cost_key}c 主词条为空，已跳过")

        if not main_props:
            return None, changed, issues + ["没有可用的 main_props"]

        sub_props_raw = data.get("sub_props", {})
        if not isinstance(sub_props_raw, dict):
            sub_props_raw = {}
            changed = True
            issues.append("sub_props 不是对象，已重置为空")

        sub_props: Dict[str, float] = {}
        for raw_prop_name, raw_weight in sub_props_raw.items():
            prop_name = str(raw_prop_name).strip()
            weight = self._to_float(raw_weight)
            if not prop_name or weight is None:
                changed = True
                issues.append("存在无法识别的副词条权重，已跳过")
                continue
            sub_props[prop_name] = weight
            if raw_prop_name != prop_name or raw_weight != weight:
                changed = True

        score_max_raw = data.get("score_max", [])
        if not isinstance(score_max_raw, (list, tuple)):
            score_max_raw = []
            changed = True
            issues.append("score_max 不是数组，已重置")

        score_max: List[float] = []
        for index in range(3):
            if index < len(score_max_raw):
                value = self._to_float(score_max_raw[index])
                if value is None:
                    value = 0.0
                    changed = True
                    issues.append(f"score_max[{index}] 无法转换为数字，已置为 0")
            else:
                value = 0.0
                changed = True
                issues.append(f"score_max 缺少索引 {index}，已补 0")
            score_max.append(value)

        if not any(value > 0 for value in score_max):
            return None, changed, issues + ["score_max 全部无效"]

        normalized_data = {
            "name": name,
            "main_props": main_props,
            "sub_props": sub_props,
            "score_max": score_max,
        }
        return normalized_data, changed or normalized_data != data, issues

    def _try_restore_from_builtin(self, local_file_path: Path) -> bool:
        """当本地文件损坏时，尝试使用内置权重恢复"""
        try:
            relative_path = local_file_path.relative_to(self.weights_dir)
        except ValueError:
            return False

        builtin_file = self.builtin_weights_dir / relative_path
        if not builtin_file.exists():
            return False

        local_file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(builtin_file, local_file_path)
        logger.warning(f"本地权重损坏，已从内置权重恢复: {local_file_path}")
        return True

    def _load_config_file(self, file_path: Path, result: Optional[WeightOperationResult] = None) -> Optional[WeightConfig]:
        """加载单个配置文件并执行格式校验/自动修复"""
        role_name = file_path.parent.name
        data, has_bom = self._read_json_file(file_path)

        if data is None and self._try_restore_from_builtin(file_path):
            data, has_bom = self._read_json_file(file_path)

        if data is None:
            if result is not None:
                result.invalid_files.append(str(file_path))
            return None

        normalized_data, changed, issues = self._sanitize_weight_data(data, role_name)
        if normalized_data is None:
            logger.error(f"权重格式无效，已跳过: {file_path} | {'; '.join(issues)}")
            if result is not None:
                result.invalid_files.append(str(file_path))
            return None

        if has_bom or changed:
            self._write_json_file(file_path, normalized_data)
            logger.info(f"已自动修复权重文件: {file_path}")
            if result is not None:
                result.repaired_files.append(str(file_path))

        if issues:
            logger.info(f"权重校验信息: {file_path} | {'; '.join(issues)}")

        return WeightConfig(
            name=normalized_data["name"],
            main_props=normalized_data["main_props"],
            sub_props=normalized_data["sub_props"],
            score_max=normalized_data["score_max"],
        )

    def _sync_builtin_weights_to_local(self) -> int:
        """首次启动时将内置权重释放到本地可写目录，仅复制缺失文件"""
        if not self.builtin_weights_dir.exists():
            logger.warning(f"内置权重目录不存在: {self.builtin_weights_dir}")
            return 0

        copied_count = 0
        for source_file in self.builtin_weights_dir.rglob("*.json"):
            if not source_file.is_file():
                continue
            relative_path = source_file.relative_to(self.builtin_weights_dir)
            target_file = self.weights_dir / relative_path
            if target_file.exists():
                continue
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
            copied_count += 1

        if copied_count:
            logger.info(f"已释放 {copied_count} 个内置权重文件到本地: {self.weights_dir}")
        return copied_count

    def _load_all_configs(self) -> None:
        """扫描并加载所有角色配置文件"""
        result = WeightOperationResult()
        result.copied_builtin_files = self._sync_builtin_weights_to_local()

        if not self.weights_dir.exists():
            logger.warning(f"权重目录不存在: {self.weights_dir}")
            self._last_report = result.to_dict()
            return

        for role_dir in sorted(self.weights_dir.iterdir(), key=lambda item: item.name):
            if not role_dir.is_dir():
                continue

            calc_file = role_dir / "calc.json"
            if not calc_file.exists():
                logger.warning(f"角色配置文件不存在: {calc_file}")
                continue

            try:
                config = self._load_config_file(calc_file, result)
                if config:
                    role_name = role_dir.name
                    self._configs[role_name] = config
                    logger.info(f"成功加载角色配置: {role_name} - {config.name}")
            except Exception as e:
                logger.error(f"加载角色配置失败: {calc_file}, 错误: {e}")

        result.loaded_roles = len(self._configs)
        self._last_report = result.to_dict()

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
        return sorted(self._configs.keys())

    def get_last_report(self) -> Dict[str, object]:
        """获取最近一次加载/同步报告"""
        return dict(self._last_report)

    def reload_configs(self) -> Dict[str, object]:
        """重新加载所有配置文件"""
        self._configs.clear()
        self._load_all_configs()
        return self.get_last_report()

    def _normalize_optional_text(self, value: Optional[str]) -> Optional[str]:
        """将可选字符串规整为去空白后的值"""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _build_github_weight_urls(
        self,
        github_urls: Optional[List[str]] = None,
        github_token: Optional[str] = None,
    ) -> List[str]:
        """根据是否配置 Token 生成下载地址列表"""
        if github_urls:
            return github_urls

        urls: List[str] = []
        if self._normalize_optional_text(github_token):
            urls.extend(GITHUB_API_WEIGHT_URLS)
        urls.extend(DEFAULT_GITHUB_WEIGHT_URLS)
        return urls

    def _build_request(self, url: str, github_token: Optional[str] = None) -> Request:
        """构造 GitHub 下载请求，可选附带 Token"""
        headers = {
            "User-Agent": "WutheringWaves-Echo-OCR",
            "Accept": "application/vnd.github+json, application/octet-stream, application/zip",
        }
        token = self._normalize_optional_text(github_token)
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        return Request(url, headers=headers)

    def _build_url_opener(self, proxy_url: Optional[str] = None):
        """构造下载器，可选附带 HTTP/HTTPS 代理"""
        normalized_proxy = self._normalize_optional_text(proxy_url)
        if normalized_proxy:
            return build_opener(ProxyHandler({"http": normalized_proxy, "https": normalized_proxy}))
        return build_opener()

    def _download_github_zip(
        self,
        urls: List[str],
        target_path: Path,
        proxy_url: Optional[str] = None,
        github_token: Optional[str] = None,
    ) -> str:
        """下载 GitHub zip 包，按顺序尝试候选地址"""
        last_error = None
        opener = self._build_url_opener(proxy_url)
        for url in urls:
            try:
                request = self._build_request(url, github_token)
                with opener.open(request, timeout=GITHUB_DOWNLOAD_TIMEOUT_SECONDS) as response, open(target_path, "wb") as output:
                    output.write(response.read())
                return url
            except (HTTPError, URLError, TimeoutError) as e:
                last_error = e
                logger.warning(f"下载权重失败，尝试下一个地址: {url} | {e}")
        raise RuntimeError(f"无法从 GitHub 下载权重压缩包: {last_error}")

    def _extract_remote_weights_dir(self, temp_dir: Path) -> Path:
        """从 zip 解压结果中定位 data/weights 目录"""
        for child in temp_dir.iterdir():
            if child.is_dir():
                weights_dir = child / "data" / "weights"
                if weights_dir.exists():
                    return weights_dir
        raise RuntimeError("下载包中未找到 data/weights 目录")

    def _merge_remote_weights(self, remote_weights_dir: Path) -> WeightOperationResult:
        """将远程权重合并到本地目录，保留本地额外自定义文件"""
        result = WeightOperationResult()

        for source_file in remote_weights_dir.rglob("*.json"):
            if not source_file.is_file():
                continue

            relative_path = source_file.relative_to(remote_weights_dir)
            target_file = self.weights_dir / relative_path
            data, _ = self._read_json_file(source_file)
            if data is None:
                result.invalid_files.append(str(source_file))
                continue

            normalized_data, changed, issues = self._sanitize_weight_data(data, source_file.parent.name)
            if normalized_data is None:
                logger.error(f"远程权重格式无效，已跳过: {source_file} | {'; '.join(issues)}")
                result.invalid_files.append(str(source_file))
                continue

            normalized_text = json.dumps(normalized_data, ensure_ascii=False, indent=2) + "\n"
            existing_text = None
            if target_file.exists():
                try:
                    existing_text = target_file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    existing_text = target_file.read_text(encoding="utf-8-sig")

            target_file.parent.mkdir(parents=True, exist_ok=True)
            if existing_text == normalized_text:
                result.skipped_files += 1
                continue

            target_file.write_text(normalized_text, encoding="utf-8")
            if existing_text is None:
                result.added_files += 1
            else:
                result.updated_files += 1

            if changed:
                result.repaired_files.append(str(target_file))

        return result

    def update_weights_from_github(
        self,
        github_urls: Optional[List[str]] = None,
        proxy_url: Optional[str] = None,
        github_token: Optional[str] = None,
    ) -> Dict[str, object]:
        """从 GitHub 拉取最新权重文件并重新加载本地配置"""
        urls = self._build_github_weight_urls(github_urls, github_token)
        normalized_proxy = self._normalize_optional_text(proxy_url)
        normalized_token = self._normalize_optional_text(github_token)

        with tempfile.TemporaryDirectory(prefix="ww_echo_weights_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            zip_path = temp_dir / "weights.zip"

            source_url = self._download_github_zip(
                urls,
                zip_path,
                proxy_url=normalized_proxy,
                github_token=normalized_token,
            )
            with zipfile.ZipFile(zip_path, "r") as zip_file:
                zip_file.extractall(temp_dir)

            remote_weights_dir = self._extract_remote_weights_dir(temp_dir)
            result = self._merge_remote_weights(remote_weights_dir)
            result.source_url = source_url

        reload_report = self.reload_configs()
        result.loaded_roles = int(reload_report.get("loaded_roles", len(self._configs)))

        summary = result.to_dict()
        summary["weights_dir"] = str(self.weights_dir)
        summary["used_proxy"] = bool(normalized_proxy)
        summary["used_github_token"] = bool(normalized_token)
        return summary


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

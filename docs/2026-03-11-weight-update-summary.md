## 变更概述

- 修复主词条仅输入属性名时得分为 `0` 的问题
- 修复 `score_max` 缺失/无效时的对齐计算崩溃风险
- 将内置权重释放到本地可写目录
- 增加权重格式校验、自动修复、坏文件跳过与内置恢复
- 增加“更新权重”按钮，支持从 GitHub 拉取最新权重
- 主窗口关闭时增加全局热键清理
- 修正主程序 DPI 配置与 `QApplication` 初始化顺序

## 本地权重目录

- Windows 优先使用：`%LOCALAPPDATA%/WutheringWaves-Echo-OCR/data/weights`
- 其他环境回退到：`~/.wuthering_waves_echo_ocr/data/weights`
- 启动时自动将仓库内置 `data/weights` 中缺失的文件复制到本地目录

## 权重校验与自动处理

- 读取 JSON 时兼容 UTF-8 BOM
- 写回统一为 UTF-8 无 BOM
- 自动规范 `1/3/4c` cost key
- 自动将可转换字符串权重转成数字
- 自动补齐或修正 `score_max`
- 本地损坏文件优先尝试从内置权重恢复
- 无法修复的文件会跳过并记录到报告中

## GitHub 更新

- 使用标准库 `urllib.request` 下载 GitHub codeload zip
- 依次尝试 `main` / `master` 分支
- 远程权重先校验再写入本地目录
- 同名官方文件会覆盖，本地额外自定义文件会保留

## 验证

- 对修改过的 Python 文件执行语法检查
- 补充并运行 `tests/test_core.py`
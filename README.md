# WutheringWaves-Echo-OCR

<div align="center">

![Logo](android-chrome-512x512.png)

**《鸣潮》声骸 OCR 识别与评分工具**

轻量、高性能、易用的声骸评分工具

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

## ✨ 特性

- 🎯 **精准 OCR 识别**：基于 RapidOCR（PP-OCRv4）引擎，高精度识别声骸属性
- 📊 **智能评分系统**：支持多角色权重配置，自动计算声骸得分
- 🖼️ **便捷截图识别**：支持快捷键截图，一键识别声骸
- 🎨 **友好界面**：基于 PySide6 的现代化 GUI 界面
- 🚀 **高性能**：轻量级设计，快速响应
- 🌍 **多角色支持**：动态加载角色权重配置，支持所有游戏角色


## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Anyuluo996/WutheringWaves-Echo-OCR.git
cd WutheringWaves-Echo-OCR
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行程序

```bash
python main.py
```

### 4. 使用快捷键

- **截图识别**：`Ctrl + Shift + Q`
- 更多快捷键可在设置中自定义

## 📁 项目结构

```
WutheringWaves-Echo-OCR/
├── main.py                 # 程序入口
├── requirements.txt        # 依赖列表
├── README.md              # 项目说明
│
├── core/                  # 核心业务逻辑
│   ├── ocr_engine.py      # OCR 引擎（单例模式）
│   ├── ocr_parser.py      # OCR 结果解析器
│   ├── calculator.py      # 评分计算器
│   ├── data_manager.py    # 数据管理器
│   ├── screenshot.py      # 截图功能
│   └── hotkey_manager.py  # 快捷键管理
│
├── gui/                   # 图形界面
│   ├── main_window.py     # 主窗口
│   ├── snipping_widget.py # 截图控件
│   ├── settings_dialog.py # 设置对话框
│   └── screenshot_selector.py # 截图选择器
│
├── data/                  # 数据目录
│   └── weights/          # 角色权重配置
│       ├── 今汐/calc.json
│       ├── 吟霖/calc.json
│       └── ...
│
├── config/               # 配置文件
│   └── settings.yaml    # 用户设置
│
└── models/              # OCR 模型文件
    ├── det.onnx        # 检测模型
    └── rec.onnx        # 识别模型


```

## 🎮 使用说明

### 截图识别

1. 运行程序后，按 `Ctrl + Shift + Q` 启动截图
2. 框选游戏中的声骸属性区域
3. 松开鼠标自动识别并评分

### 角色权重配置

每个角色的权重配置位于 `data/weights/{角色名}/calc.json`：

```json
{
  "name": "今汐-通用",
  "main_props": {
    "4": {
      "攻击": 0.025,
      "攻击%": 0.275,
      "暴击": 0.5,
      "暴击伤害": 0.25
    }
  },
  "sub_props": {
    "攻击": 0.1,
    "攻击%": 1.1,
    "暴击": 2.0,
    "暴击伤害": 1.0
  },
  "score_max": [76.254, 79.804, 83.804]
}
```

### 评分算法

```
单项得分 = (数值 × 权重 ÷ 未对齐最高分) × 对齐分(50)
总得分 = 主词条得分 + 副词条得分
```

## 🔧 开发说明

### 手动构建（仅用于开发测试）

```bash
# 安装依赖
pip install -r requirements.txt
pip install nuitka imageio

# 转换图标（PNG -> ICO）
python -c "from PIL import Image; img = Image.open('android-chrome-512x512.png'); sizes = [(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]; img.save('android-chrome-512x512.ico', format='ICO', sizes=sizes)"

# 构建可执行文件
python -m nuitka --standalone --onefile \
       --enable-plugin=pyside6 \
       --windows-uac-admin \
       --include-package-data=rapidocr_onnxruntime \
       --include-data-dir=models=models \
       --include-data-dir=data=data \
       --include-data-dir=config=config \
       --windows-company-name="WW-Echo-OCR" \
       --windows-product-name="鸣潮声骸评分工具" \
       --windows-file-version="1.0.0.0" \
       --windows-product-version="1.0.0.0" \
       --windows-file-description="鸣潮辅助工具" \
       --windows-icon-from-ico=android-chrome-512x512.ico \
       --disable-console \
       --output-filename="鸣潮声骸评分工具.exe" \
       --output-dir=dist \
       main.py
```


## 🐛 故障排除

### OCR 识别不准确

1. 确保截图区域完整包含声骸属性
2. 检查游戏分辨率和缩放比例
3. 尝试调整游戏内 UI 大小

### 程序无法启动

1. 检查 Python 版本是否 >= 3.10
2. 重新安装依赖：`pip install -r requirements.txt --force-reinstall`
3. 检查是否安装了 Visual C++ Redistributable

### 快捷键不生效

1. 检查是否与其他软件快捷键冲突
2. 尝试以管理员身份运行程序
3. 在设置中重新设置快捷键

## 📊 技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python 3.10+ |
| **GUI 框架** | PySide6 (Qt for Python) |
| **OCR 引擎** | RapidOCR (PP-OCRv5/v4) |
| **图像处理** | OpenCV, Pillow, NumPy |
| **数据格式** | JSON, YAML |
| **打包工具** | Nuitka |
| **测试框架** | pytest, pytest-qt |

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request


## 🙏 致谢

- [RapidOCR](https://github.com/RapidAI/RapidOCR) - 优秀的 OCR 引擎
- [PySide6](https://wiki.qt.io/Qt_for_Python) - Qt for Python
- [XutheringWavesUID](https://github.com/Loping151/XutheringWavesUID) - 权重算法
- 《鸣潮》游戏开发商库洛游戏



---

<div align="center">



</div>

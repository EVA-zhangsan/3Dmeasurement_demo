# 灵寻玉尺 · 3D Measurement Demo

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-2ea44f)
![Status](https://img.shields.io/badge/Status-v2.0%20Production%20Ready-brightgreen)
![AI Assisted](https://img.shields.io/badge/Development-AI%20Assisted-ff6b35)

一个面向工业三维测量场景的 Python 原型系统，用于在无硬件阶段快速验证完整链路：
数据采集模拟 -> 点云可视化 -> 曲面拟合 -> 结果导出 -> 靶标验证。

## 项目简介

本项目聚焦于凹槽类几何特征的测量流程验证，提供两种使用方式：

1. GUI 实时模式：启动模拟扫描，实时查看三维点云与拟合曲面。
2. CLI 离线模式：批量生成 CSV 数据并输出曲面 PNG。

核心能力：

- 1ms/点的栅格扫描模拟（40x40 可达 1600 点）
- 支持 CSV/PLY/PCD/XYZ 数据导入（Open3D 可用时）
- 立方插值 + 可选滤波（高斯 / 中值）
- 工业风可视化界面与状态反馈
- 标准凹槽靶标生成与槽深/槽宽验证

## 快速开始

### 1. 克隆并进入项目

```bash
git clone https://github.com/EVA-zhangsan/3Dmeasurement_demo.git
cd 3Dmeasurement_demo
```

### 2. 创建虚拟环境并安装依赖

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 运行 GUI（推荐）

```powershell
python gui.py
```

或在 Windows 下双击：

```text
run_gui.bat
```

## 使用示例

### CLI：生成模拟数据

```powershell
python simulate_and_fit.py generate --out data_sim.csv --points 1600
```

### CLI：拟合并导出曲面图

```powershell
python simulate_and_fit.py fit --in data_sim.csv --out surface.png --grid 200 --method cubic
```

### 生成标准凹槽靶标

```powershell
python generate_target.py
```

会输出 `standard_groove.ply`，理论参数：槽深 3.0 mm，槽宽 10.0 mm。

## 主要功能

- 实时采集：线程化数据源读取，动态显示点云
- 曲面拟合：griddata 立方插值，支持平滑滤波
- 质量增强：统计离群点去除（Open3D）
- 导出能力：支持 PNG 截图导出
- 交互防呆：测量期间自动禁用冲突操作

## 项目结构

```text
measurement_demo/
├─ gui.py                    # 主 GUI（PySide6 + PyVista）
├─ gui_pyvista.py            # 旧版/实验界面
├─ data_source.py            # 数据源抽象与模拟采集
├─ point_processing.py       # 点云处理（离群点过滤）
├─ simulate_and_fit.py       # CLI 数据生成与拟合导出
├─ generate_target.py        # 标准凹槽靶标生成
├─ requirements.txt          # Python 依赖
├─ check_deployment.py       # 部署检查脚本
└─ *.md                      # 说明、验证与交付文档
```

## AI 在开发中的应用

本项目采用 AI 协同开发方式：

- 快速完成原型搭建与模块重构
- 辅助参数调优（刷新频率、滤波强度、可视化呈现）
- 自动化生成与维护技术文档和交付说明

AI 主要用于提升研发效率与工程规范性，核心测量逻辑仍基于物理建模与数值计算。

## 当前进度

- 已完成：v2.0 工业级原型闭环（演示与交付就绪）
- 进行中：真实硬件串口/TCP 数据源接入
- 下一步：自动化测试与 CI 工作流

## 文档索引

- `INDUSTRIAL_UI_COMPLETE.md`：工业级界面改造细节
- `VERIFICATION.md`：物理坐标与算法验证
- `DEPLOYMENT.md`：交付清单与部署指南
- `PYVISTA_OPEN3D_UPGRADE.md`：PyVista/Open3D 升级记录

## 许可证

当前仓库尚未添加许可证文件。建议补充 `LICENSE`（如 MIT）以便开源协作。
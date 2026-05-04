极简版高精度三维测量仪器 — 模拟与拟合演示

说明
- 目的：在没有硬件前，提供一个可运行的模拟数据生成、CSV 导入/导出、网格化拟合与 3D 曲面输出的最小原型。
- 技术栈：Python (numpy, scipy, matplotlib, pandas)

快速开始
1. 建议先创建并激活虚拟环境：

## 功能（工业级版本 v2.0）
python -m venv .venv
1. **高性能采集**：1ms/点栅格扫描（比原来快 20 倍）
2. **CSV 导入/导出**：支持外部数据 + 暗黑背景 PNG 导出
3. **工业级 3D 可视化**：matplotlib + turbo colormap + 荧光青色文字
4. **高质量曲面拟合**：立方插值 + σ=2.5 高斯滤波
5. **防呆交互设计**：测量期间自动禁用冲突按钮
6. **实时状态栏**：动态显示采集/拟合/导出状态
7. **暗黑主题**：OLED 友好 + 高对比度（#0FF 青色文字）

```powershell
python simulate_and_fit.py generate --out data_sim.csv --points 1000
```
```powershell
python simulate_and_fit.py fit --in data_sim.csv --out surface.png --grid 200
- `simulate_and_fit.py` 包含三部分：模拟数据生成、CSV IO、网格化拟合与图像导出。
- 目前为离线模式（模拟/CSV），后续会添加串口/TCP 的抽象层以接入真实传感器。
```powershell
pip install -r requirements.txt
python gui.py
```

功能说明：
- **导入本地 CSV 文件**：加载已有的 CSV 数据并立即渲染为 3D 拟合曲面。
- **开始/停止测量**：启动模拟传感器或真实硬件，实时收集点云数据，动态显示在 3D 散点图上。
- **刷新拟合**：对已收集的点云进行网格化插值，生成光滑的 3D 曲面。
- **启用滤波**：支持中值滤波或高斯滤波，可在导出前对网格数据进行平滑处理。
- **导出图片**：将当前 3D 图保存为 PNG 文件。

架构：
- `data_source.py`：通信抽象层，包含模拟数据生成器（线程模式）、串口/TCP 占位符。
- `gui.py`：基于 PySide6 + Matplotlib 的实时可视化界面。
- `simulate_and_fit.py`：离线数据生成与命令行工具。

## 标准靶标与测量验证

如果你要做算法验证，建议先生成一个可控的凹槽靶标：

```powershell
Set-Location 'D:\Desktop\过控\measurement_demo'
.\.venv\Scripts\Activate.ps1
python generate_target.py
```

运行后会在当前目录生成 `standard_groove.ply`。然后启动 `python gui.py`，通过“导入点云文件”加载它，就可以在右侧属性面板看到基准平面、凹槽底面、当前槽深和当前槽宽的计算结果。
# rm-border - 批量去除图片白边/透明边缘工具

一个功能完整的 Python 命令行工具，用于批量去除图像的白边或透明边缘，支持多种图像格式和矢量格式的光栅化处理。

## 特性

✅ **多格式支持**
- 光栅图像：PNG, JPG, BMP, TIFF, EMF
- 矢量格式（自动光栅化）：PDF（第一页）、EPS、PS

✅ **智能边缘检测**
- 自动检测 Alpha 透明通道
- 支持自定义背景色检测（默认白色）
- 可调节容差值以适应不同场景

✅ **灵活的边距控制**
- 支持统一边距设置
- 支持分别指定上、右、下、左边距

✅ **强大的输出管理**
- 默认输出到原文件同级目录
- 自定义输出目录
- 正则表达式重命名支持

✅ **高质量矢量格式处理**
- 默认 300 DPI 光栅化（可自定义）
- 支持 Ghostscript 和 ImageMagick 双引擎

## 安装

### 1. Python 依赖

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install Pillow>=10.0.0 pdf2image>=1.16.0 Wand>=0.6.11
```

### 2. 系统级依赖

#### Ghostscript（必需，用于 EPS/PS 处理）

**Windows:**
1. 下载：https://www.ghostscript.com/releases/gsdnld.html
2. 安装后将 `bin` 目录添加到 PATH 环境变量
3. 验证：`gswin64c --version`

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install ghostscript
```

**macOS:**
```bash
brew install ghostscript
```

#### Poppler（可选，用于 PDF 处理）

**Windows:**
1. 下载：https://github.com/oschwartz10612/poppler-windows/releases/
2. 解压后将 `bin` 目录添加到 PATH 环境变量
3. 验证：`pdfinfo -v`

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install poppler-utils
```

**macOS:**
```bash
brew install poppler
```

#### ImageMagick + Wand（可选，用于 EPS/PS/EMF 处理）

**Windows:**
1. 下载：https://imagemagick.org/script/download.php
2. 安装时勾选"安装开发头和库"
3. 设置环境变量 `IMAGEMAGICK_BINARY` 指向 `magick.exe`

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install libmagickwand-dev
pip install Wand
```

**macOS:**
```bash
brew install imagemagick
pip install Wand
```

## 使用方法

### 基本语法

```bash
python rm_border.py -i <输入文件或目录> [选项]
```

### 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--input` | `-i` | **（必需）** 输入文件或目录路径 | - |
| `--output_dir` | `-o` | 输出目录 | 与输入文件同级 |
| `--background` | `-bg` | 背景色（十六进制） | `#FFFFFF`（白色） |
| `--padding` | `-p` | 保留边距（单值或四值） | `0` |
| `--dpi` | - | 矢量格式光栅化 DPI | `300` |
| `--rename_pattern` | - | 正则表达式模式 | - |
| `--rename_template` | - | 重命名模板 | - |
| `--recursive` | - | 递归处理子目录 | `False` |
| `--format` | - | 输出格式（png/jpg/jpeg/bmp/tiff） | `png` |
| `--tolerance` | - | 背景色容差 | `10` |
| `--verbose` | `-v` | 显示详细调试信息 | `False` |

## 使用示例

### 1. 基本用法

#### 去除单张图片白边

```bash
python rm_border.py -i image.png
```

输出：`image_processed.png`（同级目录）

#### 去除黑边（指定背景色）

```bash
python rm_border.py -i image.png --background #000000
```

#### 保留 10 像素边距

```bash
python rm_border.py -i image.png --padding 10
```

#### 分别指定四边边距（上、右、下、左）

```bash
python rm_border.py -i image.png -p 5 10 5 10
```

### 2. 批量处理

#### 处理整个目录

```bash
python rm_border.py -i ./images/
```

#### 输出到指定目录

```bash
python rm_border.py -i ./images/ --output_dir ./output/
```

#### 递归处理子目录

```bash
python rm_border.py -i ./project/ --recursive --output_dir ./output/
```

### 3. 处理矢量格式

#### 处理 PDF（自动光栅化第一页）

```bash
python rm_border.py -i document.pdf --dpi 300
```

#### 处理 EPS 文件

```bash
python rm_border.py -i figure.eps --dpi 600
```

#### 处理 PostScript 文件

```bash
python rm_border.py -i diagram.ps
```

### 4. 正则重命名

#### 从文件名提取数字并重命名

假设有文件：`figure_01.eps`, `figure_02.eps`, ...

```bash
python rm_border.py -i figure_01.eps \
  --rename_pattern "figure_(\d+)" \
  --rename_template "clean_{1}.png"
```

输出：`clean_01.png`

#### 复杂重命名示例

从 `report_2024_chart.png` 提取 `2024` 和 `chart`：

```bash
python rm_border.py -i report_2024_chart.png \
  --rename_pattern "report_(\d+)_(\w+)" \
  --rename_template "{1}_{2}_cropped"
```

输出：`2024_chart_cropped.png`

### 5. 高级用法

#### 输出为 JPEG 格式（去除透明度）

```bash
python rm_border.py -i image.png --format jpg
```

#### 处理透明背景 PNG 并保留透明区域

```bash
python rm_border.py -i transparent.png -p 20
```

#### 高分辨率光栅化 + 自定义背景色 + 边距

```bash
python rm_border.py -i vector.pdf \
  --dpi 600 \
  --background #F5F5F5 \
  --padding 15 20 15 20 \
  --output_dir ./high_res/
```

#### 批量处理并详细日志

```bash
python rm_border.py -i ./batch/ -o ./output/ -v
```

## 输出文件命名规则

### 默认模式
```
输入：image.png
输出：image_processed.png
```

### 自定义输出目录
```
输入：./src/image.png
输出：./output/image_processed.png
```

### 正则重命名
```
输入：figure_01.eps
正则：figure_(\d+)
模板：clean_{1}.png
输出：clean_01.png
```

## 算法说明

### 边缘检测策略

1. **Alpha 通道检测**（优先级最高）
   - 如果图像包含 Alpha 通道，直接基于透明度检测内容区域
   - 适用于透明背景的 PNG 等格式

2. **背景色对比检测**
   - 创建纯色背景图像
   - 计算与原图的差异
   - 应用容差过滤
   - 提取非背景区域的边界框

### Padding 应用

边界框计算完成后，按照用户指定的 padding 值向外扩展：

```
最终边界框 = 原始内容边界框 - padding
```

确保不会超出图像实际尺寸。

## 故障排除

### 问题 1：Ghostscript 未找到

**错误信息：**
```
EPS/PS 光栅化失败。请安装以下依赖之一...
```

**解决方案：**
- 确保 Ghostscript 已正确安装
- 将 Ghostscript 的 `bin` 目录添加到 PATH
- Windows 验证：`gswin64c --version`

### 问题 2：PDF 处理失败

**错误信息：**
```
处理 PDF 需要安装 pdf2image 和 poppler
```

**解决方案：**
- 安装 pdf2image：`pip install pdf2image`
- 安装 poppler（见安装部分的系统依赖说明）

### 问题 3：无法检测到有效内容

**错误信息：**
```
无法检测到有效内容，图像可能完全是背景色
```

**解决方案：**
- 检查背景色设置是否正确
- 调整容差值：`--tolerance 20`
- 使用 `--verbose` 查看详细日志

### 问题 4：边界框无效

**错误信息：**
```
计算出的边界框无效（padding 可能过大）
```

**解决方案：**
- 减小 padding 值
- 检查图像尺寸是否过小

## 性能优化建议

1. **批量处理大文件**
   - 使用 `--verbose` 监控进度
   - 考虑降低 DPI（如 150-200）

2. **内存优化**
   - 处理超大图像时，确保系统有足够内存
   - 建议至少 2GB 可用内存

3. **并行处理**（未来版本）
   - 当前版本为串行处理
   - 可考虑使用 `multiprocessing` 加速

## 更新日志

### v1.0.0 (2026-04-07)
- ✨ 初始版本发布
- ✨ 支持 PNG, JPG, BMP, TIFF, EMF, PDF, EPS, PS 格式
- ✨ Alpha 通道和背景色检测
- ✨ 灵活的 padding 控制
- ✨ 正则重命名支持
- ✨ 完整的错误处理和文档

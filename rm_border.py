#!/usr/bin/env python3
"""
rm-border: 批量去除图片白边或透明边缘的命令行工具

支持格式：
- 光栅图像：PNG, JPG, BMP, TIFF, EMF
- 矢量格式（自动光栅化）：PDF（第一页）, EPS, PS

依赖：
- Python 3.8+
- Ghostscript（用于 EPS/PS 处理）
- ImageMagick（可选，用于 EPS/PS/EMF 处理）
- pdf2image/poppler（用于 PDF 处理）

使用示例：
    # 基本用法 - 去除白边
    python rm_border.py -i image.png
    
    # 指定背景色和边距
    python rm_border.py -i image.png --background #000000 --padding 10
    
    # 分别指定四边边距（上、右、下、左）
    python rm_border.py -i image.png -p 5 10 5 10
    
    # 批量处理目录
    python rm_border.py -i ./images/ --output_dir ./output/
    
    # 正则重命名
    python rm_border.py -i figure_01.eps --rename_pattern "figure_(\d+)" --rename_template "clean_{1}.png"

    # 智能识别边界颜色并去除
    python rm_border.py -i image.png -a
    
    # 自定义 DPI（用于矢量格式）
    python rm_border.py -i document.pdf --dpi 600
"""

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Tuple, Optional, Union, List
from PIL import Image, ImageChops
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# 支持的格式定义
RASTER_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.emf'}
VECTOR_FORMATS = {'.pdf', '.eps', '.ps'}
ALL_SUPPORTED_FORMATS = RASTER_FORMATS | VECTOR_FORMATS


def parse_padding(padding_arg: str) -> Tuple[int, int, int, int]:
    """
    解析 padding 参数
    
    支持格式：
    - 单一数值：四边相同，如 "10" -> (10, 10, 10, 10)
    - 四个数值：上、右、下、左，如 "5 10 5 10" -> (5, 10, 5, 10)
    
    Args:
        padding_arg: 用户输入的 padding 字符串
        
    Returns:
        Tuple[int, int, int, int]: (top, right, bottom, left)
        
    Raises:
        ValueError: 格式不正确时抛出
    """
    parts = padding_arg.split()
    
    if len(parts) == 1:
        # 单一数值，四边相同
        val = int(parts[0])
        return (val, val, val, val)
    elif len(parts) == 4:
        # 四个数值：上、右、下、左
        return tuple(int(x) for x in parts)
    else:
        raise ValueError(
            "Padding 格式错误：请提供单一数值或四个数值（用空格分隔）\n"
            "示例：--padding 10 或 --padding 5 10 5 10"
        )


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """
    将十六进制颜色转换为 RGB 元组
    
    Args:
        hex_color: 十六进制颜色字符串，如 "#FFFFFF" 或 "FFFFFF"
        
    Returns:
        Tuple[int, int, int]: RGB 值元组
        
    Raises:
        ValueError: 颜色格式不正确时抛出
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        raise ValueError(f"无效的颜色值：{hex_color}。请使用六位十六进制格式，如 #FFFFFF")
    
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f"无效的颜色值：{hex_color}。请使用六位十六进制格式，如 #FFFFFF")


def detect_content_bbox(
    image: Image.Image,
    bg_color: Tuple[int, int, int],
    padding: Tuple[int, int, int, int],
    tolerance: int = 10
) -> Tuple[int, int, int, int]:
    """
    检测图像内容的边界框
    
    算法逻辑：
    1. 如果图像有 Alpha 通道，基于透明度检测内容区域
    2. 否则基于背景色和容差值检测内容区域
    
    Args:
        image: PIL Image 对象
        bg_color: 背景色 RGB 元组
        padding: (top, right, bottom, left) 边距
        tolerance: 颜色容差，默认 10
        
    Returns:
        Tuple[int, int, int, int]: (left, upper, right, lower) 边界框
    """
    # 确保图像为 RGB 或 RGBA 模式
    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGBA')
    
    bbox = None

    # 策略 1：如果有 Alpha 通道，基于透明度检测
    if image.mode == 'RGBA':
        # 提取 Alpha 通道
        alpha = image.split()[3]
        # 找到非完全透明的区域
        alpha_bbox = alpha.getbbox()

        # 仅当 alpha 检测到的边界不等于整个图片时才使用
        # （等于整个图片说明没有透明边界，应继续走背景色检测）
        if alpha_bbox and alpha_bbox != (0, 0, image.width, image.height):
            bbox = alpha_bbox
            logger.debug("使用 Alpha 通道检测边界框")
        else:
            logger.debug("Alpha 通道未检测到透明边界，回退到背景色检测")
    
    # 策略 2：如果没有 Alpha 通道或 Alpha 检测失败，基于背景色检测
    if bbox is None:
        logger.debug("使用背景色对比检测边界框")
        
        # 创建背景色图像
        bg = Image.new('RGB', image.size, bg_color)
        
        # 转换为 RGB（如果有 Alpha 通道，先合成到白色背景）
        if image.mode == 'RGBA':
            # 创建白色背景
            white_bg = Image.new('RGB', image.size, (255, 255, 255))
            white_bg.paste(image, mask=image.split()[3])
            rgb_image = white_bg
        else:
            rgb_image = image.convert('RGB')
        
        # 计算差异图像
        diff = ImageChops.difference(rgb_image, bg)
        
        # 应用容差：将差异小于容差的像素视为背景
        if tolerance > 0:
            # 增强对比度，使容差处理更有效
            diff = diff.point(lambda x: 255 if x > tolerance else 0)
        
        # 获取边界框
        bbox = diff.getbbox()
    
    if bbox is None:
        raise ValueError("无法检测到有效内容，图像可能完全是背景色")
    
    # 应用 padding
    left, upper, right, lower = bbox
    pad_top, pad_right, pad_bottom, pad_left = padding
    
    # 计算新的边界（确保不超出图像范围）
    new_left = max(0, left - pad_left)
    new_upper = max(0, upper - pad_top)
    new_right = min(image.width, right + pad_right)
    new_lower = min(image.height, lower + pad_bottom)
    
    # 验证边界框有效性
    if new_right <= new_left or new_lower <= new_upper:
        raise ValueError("计算出的边界框无效（padding 可能过大）")
    
    logger.debug(
        f"原始边界框：{bbox}，应用 padding 后：({new_left}, {new_upper}, {new_right}, {new_lower})"
    )
    
    return (new_left, new_upper, new_right, new_lower)


# ============================================================
# 自动边界检测
# ============================================================

def _get_dominant_color_row(image: Image.Image, y: int) -> Tuple[int, int, int]:
    """获取第 y 行的主色调（出现次数最多的颜色）"""
    row = image.crop((0, y, image.width, y + 1))
    return Counter(row.getdata()).most_common(1)[0][0]


def _get_dominant_color_col(image: Image.Image, x: int) -> Tuple[int, int, int]:
    """获取第 x 列的主色调（出现次数最多的颜色）"""
    col = image.crop((x, 0, x + 1, image.height))
    return Counter(col.getdata()).most_common(1)[0][0]


def _is_row_pure(
    image: Image.Image, y: int,
    target_color: Tuple[int, int, int],
    tolerance: int,
    threshold: float = 0.95
) -> bool:
    """检查第 y 行是否为目标颜色的纯色行（匹配像素占比 >= threshold）"""
    w = image.width
    row = image.crop((0, y, w, y + 1))
    bg = Image.new('RGB', (w, 1), target_color)
    diff = ImageChops.difference(row, bg)
    diff = diff.point(lambda x: 255 if x > tolerance else 0)
    gray = diff.convert('L')
    match_count = gray.histogram()[0]
    return match_count / w >= threshold


def _is_col_pure(
    image: Image.Image, x: int,
    target_color: Tuple[int, int, int],
    tolerance: int,
    threshold: float = 0.95
) -> bool:
    """检查第 x 列是否为目标颜色的纯色列（匹配像素占比 >= threshold）"""
    h = image.height
    col = image.crop((x, 0, x + 1, h))
    bg = Image.new('RGB', (1, h), target_color)
    diff = ImageChops.difference(col, bg)
    diff = diff.point(lambda x: 255 if x > tolerance else 0)
    gray = diff.convert('L')
    match_count = gray.histogram()[0]
    return match_count / h >= threshold


def _detect_single_edge(
    image: Image.Image,
    side: str,
    tolerance: int,
    purity_threshold: float
) -> Tuple[Tuple[int, int, int], int]:
    """
    检测单条边的边界颜色和宽度。

    Args:
        image: RGB 模式的 PIL Image
        side: 'top' / 'right' / 'bottom' / 'left'
        tolerance: 颜色容差
        purity_threshold: 纯色行/列的最低匹配占比

    Returns:
        (border_color, border_width)
    """
    w, h = image.size

    if side == 'top':
        color = _get_dominant_color_row(image, 0)
        width = 0
        for y in range(h):
            if _is_row_pure(image, y, color, tolerance, purity_threshold):
                width += 1
            else:
                break
        return color, width

    elif side == 'bottom':
        color = _get_dominant_color_row(image, h - 1)
        width = 0
        for y in range(h - 1, -1, -1):
            if _is_row_pure(image, y, color, tolerance, purity_threshold):
                width += 1
            else:
                break
        return color, width

    elif side == 'left':
        color = _get_dominant_color_col(image, 0)
        width = 0
        for x in range(w):
            if _is_col_pure(image, x, color, tolerance, purity_threshold):
                width += 1
            else:
                break
        return color, width

    elif side == 'right':
        color = _get_dominant_color_col(image, w - 1)
        width = 0
        for x in range(w - 1, -1, -1):
            if _is_col_pure(image, x, color, tolerance, purity_threshold):
                width += 1
            else:
                break
        return color, width

    raise ValueError(f"无效的边方向：{side}")


def detect_auto_border(
    image: Image.Image,
    tolerance: int = 10,
    purity_threshold: float = 0.95
) -> Tuple[int, int, int, int]:
    """
    智能识别四条边的边界宽度。

    算法：
    1. 分别从四条边向内扫描，找到连续纯色段的宽度
    2. 根据四条边的纯色段颜色进行一致性判断：
       - 四色相同 → 四侧都有边界
       - 三色相同 → 以相同三色的侧边为边界
       - 两色相同 → 以相同颜色的侧边为边界
       - 全部不同 → 所有检测到纯色段的侧边均视为边界

    Args:
        image: PIL Image 对象
        tolerance: 颜色容差
        purity_threshold: 纯色行/列的最低匹配占比

    Returns:
        Tuple[int, int, int, int]: (top, right, bottom, left) 各边应裁剪的宽度
    """
    rgb = image.convert('RGB')
    w, h = rgb.size

    # 检测四条边
    sides = ['top', 'right', 'bottom', 'left']
    colors = {}
    widths = {}

    for side in sides:
        color, width = _detect_single_edge(rgb, side, tolerance, purity_threshold)
        colors[side] = color
        widths[side] = width
        logger.debug(f"自动检测 {side}: 颜色={color}, 宽度={width}")

    # 筛选出有边界的侧边（宽度 > 0）
    bordered = [s for s in sides if widths[s] > 0]

    if not bordered:
        logger.debug("自动检测：未发现边界")
        return (0, 0, 0, 0)

    # 按颜色分组
    color_groups = {}
    for side in bordered:
        c = colors[side]
        color_groups.setdefault(c, []).append(side)

    # 找到最大的颜色组
    largest_group = max(color_groups.values(), key=len)
    side_idx = {'top': 0, 'right': 1, 'bottom': 2, 'left': 3}

    if len(largest_group) >= 2:
        # 多个侧边共享同一颜色 → 仅裁剪这些侧边
        result = [0, 0, 0, 0]
        for side in largest_group:
            result[side_idx[side]] = widths[side]
        result = tuple(result)
        logger.debug(
            f"自动检测：主色 {colors[largest_group[0]]} 共 {len(largest_group)} 侧，"
            f"裁剪宽度={result}"
        )
        return result
    else:
        # 所有侧边颜色各不相同 → 裁剪所有检测到边界的侧边
        result = tuple(widths[s] for s in sides)
        logger.debug(f"自动检测：各侧颜色不同，裁剪宽度={result}")
        return result


def rasterize_pdf(
    pdf_path: str,
    dpi: int = 300,
    page: int = 1
) -> Image.Image:
    """
    将 PDF 光栅化为 PIL Image
    
    处理策略（按优先级）：
    1. 使用 Wand (ImageMagick) - 推荐，功能强大
    2. 使用 pdf2image (poppler) - 备选方案
    
    Args:
        pdf_path: PDF 文件路径
        dpi: 光栅化分辨率，默认 300
        page: 页码（从 1 开始），默认 1
        
    Returns:
        Image.Image: 光栅化后的图像
        
    Raises:
        ImportError: 所需的库未安装时抛出
        FileNotFoundError: 文件不存在时抛出
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")
    
    # 策略 1：尝试使用 Wand (ImageMagick)
    try:
        return _rasterize_pdf_with_wand(pdf_path, dpi, page)
    except ImportError:
        logger.debug("Wand/ImageMagick 未安装，尝试 pdf2image")
    except Exception as e:
        logger.warning(f"Wand 处理失败：{e}，尝试 pdf2image")
    
    # 策略 2：使用 pdf2image (poppler)
    try:
        return _rasterize_pdf_with_pdf2image(pdf_path, dpi, page)
    except ImportError:
        raise ImportError(
            "PDF 光栅化失败。请安装以下依赖之一：\n"
            "1. Wand + ImageMagick（推荐）: pip install Wand\n"
            "   - ImageMagick: https://imagemagick.org/script/download.php\n"
            "   - Windows 需设置 IMAGEMAGICK_BINARY 环境变量\n"
            "2. pdf2image + poppler: pip install pdf2image\n"
            "   - Windows: https://github.com/oschwartz10612/poppler-windows/releases/\n"
            "   - 并将 poppler 的 bin 目录添加到 PATH 环境变量"
        )


def _rasterize_pdf_with_wand(
    pdf_path: str,
    dpi: int,
    page: int
) -> Image.Image:
    """
    使用 Wand (ImageMagick) 光栅化 PDF
    
    Args:
        pdf_path: PDF 文件路径
        dpi: 分辨率
        page: 页码（从 1 开始）
        
    Returns:
        Image.Image: 光栅化后的图像
    """
    try:
        from wand.image import Image as WandImage
    except ImportError:
        raise ImportError("Wand 未安装。安装方法：pip install Wand")
    
    logger.info(f"使用 Wand 光栅化 PDF（第 {page} 页，DPI: {dpi}）...")
    
    with WandImage(filename=pdf_path, resolution=dpi) as img:
        # 选择指定页（Wand 页码从 0 开始）
        if page > 1 and len(img.sequence) >= page:
            img.sequence.length = page
            img.sequence.index = page - 1
        
        # 转换为 PNG 格式到内存
        img.format = 'png'
        img_data = img.make_blob()
        
        # 转换为 PIL Image
        from io import BytesIO
        pil_image = Image.open(BytesIO(img_data))
        pil_image.load()
        
        return pil_image.copy()


def _rasterize_pdf_with_pdf2image(
    pdf_path: str,
    dpi: int,
    page: int
) -> Image.Image:
    """
    使用 pdf2image (poppler) 光栅化 PDF
    
    Args:
        pdf_path: PDF 文件路径
        dpi: 分辨率
        page: 页码（从 1 开始）
        
    Returns:
        Image.Image: 光栅化后的图像
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError(
            "pdf2image 未安装。安装方法：pip install pdf2image\n"
            "还需安装 poppler: https://github.com/oschwartz10612/poppler-windows/releases/"
        )
    
    logger.info(f"使用 pdf2image 光栅化 PDF（第 {page} 页，DPI: {dpi}）...")
    
    # 转换指定页（pdf2image 页码从 1 开始）
    images = convert_from_path(
        pdf_path,
        dpi=dpi,
        first_page=page,
        last_page=page
    )
    
    if not images:
        raise ValueError(f"PDF 文件不包含第 {page} 页")
    
    return images[0]


def rasterize_eps_ps(
    file_path: str,
    dpi: int = 300
) -> Image.Image:
    """
    将 EPS/PS 文件光栅化为 PIL Image
    
    优先使用 Wand (ImageMagick)，如果失败则尝试直接使用 Pillow（需要 Ghostscript）
    
    Args:
        file_path: EPS/PS 文件路径
        dpi: 光栅化分辨率，默认 300
        
    Returns:
        Image.Image: 光栅化后的图像
        
    Raises:
        ImportError: 所需的库未安装时抛出
        FileNotFoundError: 文件不存在时抛出
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在：{file_path}")
    
    # 策略 1：尝试使用 Wand (ImageMagick)
    try:
        return _rasterize_with_wand(file_path, dpi)
    except ImportError:
        logger.debug("Wand/ImageMagick 未安装，尝试直接使用 Pillow")
    except Exception as e:
        logger.warning(f"Wand 处理失败：{e}，尝试直接使用 Pillow")
    
    # 策略 2：使用 Pillow（需要 Ghostscript 已安装并配置）
    try:
        return _rasterize_with_pillow(file_path, dpi)
    except Exception as e:
        raise RuntimeError(
            f"EPS/PS 光栅化失败。请安装以下依赖之一：\n"
            f"1. Wand + ImageMagick: pip install Wand\n"
            f"   - ImageMagick: https://imagemagick.org/script/download.php\n"
            f"   - Windows 需设置 IMAGEMAGICK_BINARY 环境变量\n"
            f"2. Ghostscript: https://www.ghostscript.com/download.html\n"
            f"   - 需将 gs 添加到 PATH 环境变量\n"
            f"错误详情：{e}"
        )


def _rasterize_with_wand(file_path: str, dpi: int) -> Image.Image:
    """
    使用 Wand (ImageMagick) 光栅化 EPS/PS
    
    Args:
        file_path: 文件路径
        dpi: 分辨率
        
    Returns:
        Image.Image: 光栅化后的图像
    """
    try:
        from wand.image import Image as WandImage
    except ImportError:
        raise ImportError(
            "Wand 未安装。安装方法：pip install Wand\n"
            "还需安装 ImageMagick: https://imagemagick.org/script/download.php"
        )
    
    logger.info(f"使用 Wand 光栅化文件（DPI: {dpi}）...")
    
    with WandImage(filename=file_path, resolution=dpi) as img:
        # 转换为 PNG 格式到内存
        img.format = 'png'
        img_data = img.make_blob()
        
        # 转换为 PIL Image
        from io import BytesIO
        pil_image = Image.open(BytesIO(img_data))
        pil_image.load()
        
        return pil_image.copy()


def _rasterize_with_pillow(file_path: str, dpi: int) -> Image.Image:
    """
    使用 Pillow 光栅化 EPS/PS（需要 Ghostscript）
    
    Args:
        file_path: 文件路径
        dpi: 分辨率
        
    Returns:
        Image.Image: 光栅化后的图像
    """
    logger.info(f"使用 Pillow + Ghostscript 光栅化文件（DPI: {dpi}）...")
    
    # 打开 EPS/PS 文件
    with Image.open(file_path) as img:
        # 设置分辨率（DPI）
        # Pillow 会使用 Ghostscript 进行光栅化
        img.load(scale=dpi/72)
        return img.copy()


def generate_output_path(
    input_path: str,
    output_dir: Optional[str],
    rename_pattern: Optional[str],
    rename_template: Optional[str],
    output_format: str
) -> str:
    """
    生成输出文件路径
    
    Args:
        input_path: 输入文件路径
        output_dir: 输出目录（可选）
        rename_pattern: 正则表达式模式（可选）
        rename_template: 重命名模板（可选）
        output_format: 输出格式（如 'png', 'jpg'）
        
    Returns:
        str: 输出文件完整路径
    """
    input_path = Path(input_path)
    stem = input_path.stem
    
    # 应用正则重命名
    if rename_pattern and rename_template:
        try:
            match = re.search(rename_pattern, input_path.name)
            if match:
                # 使用匹配组替换模板
                new_name = rename_template
                for i, group in enumerate(match.groups(), 1):
                    new_name = new_name.replace(f"{{{i}}}", group)
                
                # 检查模板是否已包含后缀
                # 如果模板包含 '.' 且最后一部分是有效扩展名，则使用模板的后缀
                if '.' in new_name:
                    parts = new_name.rsplit('.', 1)
                    potential_ext = f'.{parts[-1]}'
                    if potential_ext.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}:
                        stem = parts[0]
                        suffix = potential_ext
                    else:
                        stem = new_name
                        suffix = f".{output_format.lower()}"
                else:
                    stem = new_name
                    suffix = f".{output_format.lower()}"
                
                logger.debug(f"正则重命名：{input_path.name} -> {stem}{suffix}")
            else:
                logger.warning(
                    f"文件名 '{input_path.name}' 不匹配正则模式 '{rename_pattern}'，使用默认命名"
                )
                stem = f"{stem}_processed"
                suffix = f".{output_format.lower()}"
        except re.error as e:
            logger.error(f"正则表达式错误：{e}")
            stem = f"{stem}_processed"
            suffix = f".{output_format.lower()}"
    else:
        # 默认命名：原文件名_processed
        stem = f"{stem}_processed"
        suffix = f".{output_format.lower()}"
    
    # 确定输出目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = input_path.parent
    
    # 创建目录（如果不存在）
    out_dir.mkdir(parents=True, exist_ok=True)
    
    return str(out_dir / f"{stem}{suffix}")


def process_image(
    input_path: str,
    output_path: str,
    bg_color: Tuple[int, int, int],
    padding: Tuple[int, int, int, int],
    dpi: int,
    output_format: str,
    tolerance: int = 10,
    auto: bool = False
) -> bool:
    """
    处理单个图像文件

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        bg_color: 背景色 RGB 元组
        padding: (top, right, bottom, left) 边距
        dpi: 矢量格式光栅化 DPI
        output_format: 输出格式
        tolerance: 颜色容差
        auto: 是否启用智能边界识别

    Returns:
        bool: 处理成功返回 True
    """
    input_path_obj = Path(input_path)
    ext = input_path_obj.suffix.lower()

    logger.info(f"处理文件：{input_path}")

    try:
        # 根据格式选择处理方式
        if ext == '.pdf':
            # PDF 光栅化
            image = rasterize_pdf(input_path, dpi=dpi)
        elif ext in {'.eps', '.ps'}:
            # EPS/PS 光栅化
            image = rasterize_eps_ps(input_path, dpi=dpi)
        elif ext in RASTER_FORMATS:
            # 直接打开光栅图像
            image = Image.open(input_path)
            image.load()
        else:
            logger.error(f"不支持的格式：{ext}")
            return False

        # 检测边界框并裁剪
        if auto:
            border_top, border_right, border_bottom, border_left = \
                detect_auto_border(image, tolerance)
            pad_top, pad_right, pad_bottom, pad_left = padding
            left = max(0, border_left - pad_left)
            upper = max(0, border_top - pad_top)
            right = min(image.width, image.width - border_right + pad_right)
            lower = min(image.height, image.height - border_bottom + pad_bottom)
            if right <= left or lower <= upper:
                logger.warning("自动检测边界后裁剪区域无效，保留原图")
                bbox = (0, 0, image.width, image.height)
            else:
                bbox = (left, upper, right, lower)
                logger.debug(
                    f"自动检测边界: top={border_top}, right={border_right}, "
                    f"bottom={border_bottom}, left={border_left}，"
                    f"裁剪区域={bbox}"
                )
        else:
            bbox = detect_content_bbox(image, bg_color, padding, tolerance)

        cropped = image.crop(bbox)
        
        # 保存输出
        save_kwargs = {}
        if output_format.lower() in ('jpg', 'jpeg'):
            # JPEG 不支持透明度
            if cropped.mode == 'RGBA':
                # 转换为 RGB（白色背景）
                white_bg = Image.new('RGB', cropped.size, (255, 255, 255))
                white_bg.paste(cropped, mask=cropped.split()[3])
                cropped = white_bg
            save_kwargs['quality'] = 95
        elif output_format.lower() == 'png':
            save_kwargs['optimize'] = True
        
        cropped.save(output_path, **save_kwargs)
        logger.info(f"已保存：{output_path}")
        return True
        
    except Exception as e:
        logger.error(f"处理失败 {input_path}：{e}")
        return False


def collect_files(input_path: str, recursive: bool = False) -> List[str]:
    """
    收集待处理的文件
    
    Args:
        input_path: 输入路径（文件或目录）
        recursive: 是否递归处理子目录
        
    Returns:
        List[str]: 文件路径列表
    """
    input_path_obj = Path(input_path)
    
    if input_path_obj.is_file():
        return [str(input_path_obj)]
    
    if input_path_obj.is_dir():
        files = []
        if recursive:
            # 递归收集所有子目录中的文件
            for ext in ALL_SUPPORTED_FORMATS:
                files.extend([str(p) for p in input_path_obj.rglob(f"*{ext}")])
        else:
            # 仅当前目录
            for ext in ALL_SUPPORTED_FORMATS:
                files.extend([str(p) for p in input_path_obj.glob(f"*{ext}")])
        
        return sorted(files)
    
    raise FileNotFoundError(f"输入路径不存在：{input_path}")


def create_argument_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 配置好的参数解析器
    """
    parser = argparse.ArgumentParser(
        prog='rm-border',
        description='批量去除图片白边或透明边缘的工具',
        epilog="""
示例用法：
  # 基本用法 - 去除白边
  python rm_border.py -i image.png
  
  # 指定背景色和边距
  python rm_border.py -i image.png --background #000000 --padding 10
  
  # 分别指定四边边距（上、右、下、左）
  python rm_border.py -i image.png -p 5 10 5 10
  
  # 批量处理目录
  python rm_border.py -i ./images/ --output_dir ./output/
  
  # 正则重命名（从 figure_01.eps 提取 01，输出 clean_01.png）
  python rm_border.py -i figure_01.eps --rename_pattern "figure_(\\d+)" --rename_template "clean_{1}.png"
  
  # 自定义 DPI（用于矢量格式）
  python rm_border.py -i document.pdf --dpi 600
  
  # 输出为 JPEG 格式
  python rm_border.py -i image.png --format jpg

  # 智能识别边界颜色并去除
  python rm_border.py -i image.png -a
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='输入文件或目录路径。支持单个文件或整个目录'
    )
    
    parser.add_argument(
        '-o', '--output_dir',
        help='输出目录（默认与输入文件同级）'
    )
    
    parser.add_argument(
        '-bg', '--background',
        default='#FFFFFF',
        help='背景色，十六进制格式（默认：#FFFFFF 白色）'
    )
    
    parser.add_argument(
        '-p', '--padding',
        default='0',
        help='保留边距，单一数值或四个数值（上 右 下 左），默认：0'
    )
    
    parser.add_argument(
        '--dpi',
        type=int,
        default=300,
        help='矢量格式光栅化 DPI（默认：300）'
    )
    
    parser.add_argument(
        '--rename_pattern',
        help='用于重命名的正则表达式模式，例如："figure_(\\d+)"'
    )
    
    parser.add_argument(
        '--rename_template',
        help='重命名模板，使用 {1}, {2} 等引用正则捕获组，例如："clean_{1}.png"'
    )
    
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='递归处理子目录中的文件'
    )
    
    parser.add_argument(
        '-f', '--format',
        default='png',
        choices=['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
        help='输出格式（默认：png）'
    )
    
    parser.add_argument(
        '-t', '--tolerance',
        type=int,
        default=10,
        help='背景色容差（默认：10）'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='显示详细调试信息'
    )

    parser.add_argument(
        '-a', '--auto',
        action='store_true',
        help='智能识别边界颜色并去除（与 --background 互斥，启用时忽略 --background）'
    )

    return parser


def main():
    """主函数"""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        # 解析 padding
        padding = parse_padding(args.padding)
        logger.debug(f"解析后的 padding: {padding}")
        
        # 解析背景色
        bg_color = hex_to_rgb(args.background)
        logger.debug(f"背景色 RGB: {bg_color}")
        
        # 收集文件
        files = collect_files(args.input, args.recursive)
        
        if not files:
            logger.warning("未找到支持格式的图像文件")
            sys.exit(0)
        
        logger.info(f"找到 {len(files)} 个文件待处理")
        
        # 处理文件
        success_count = 0
        fail_count = 0
        
        for file_path in files:
            # 生成输出路径
            output_path = generate_output_path(
                file_path,
                args.output_dir,
                args.rename_pattern,
                args.rename_template,
                args.format
            )
            
            # 处理图像
            if process_image(
                file_path,
                output_path,
                bg_color,
                padding,
                args.dpi,
                args.format,
                args.tolerance,
                auto=args.auto
            ):
                success_count += 1
            else:
                fail_count += 1
        
        # 输出统计
        logger.info(f"\n处理完成：成功 {success_count} 个，失败 {fail_count} 个")
        
        if fail_count > 0:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.warning("\n操作已取消")
        sys.exit(130)
    except Exception as e:
        logger.error(f"程序错误：{e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

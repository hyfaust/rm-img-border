# rm-border — Batch Image Border Removal Tool

**English** | [中文](README_CN.md)

A Python CLI tool for batch-removing borders and transparent edges from images. Supports raster formats, vector auto-rasterization, manual background-color matching, and intelligent auto-detection of border regions.

## Features

- **Multi-format support** — PNG, JPG, BMP, TIFF, EMF; auto-rasterized PDF (first page), EPS, PS
- **Three detection modes** — Alpha-channel, background-color comparison, and `--auto` smart scan
- **Tolerance control** — adjustable color-matching threshold for noisy or anti-aliased edges
- **Per-side padding** — uniform or independent top/right/bottom/left margins
- **Batch processing** — single file, whole directory, or recursive sub-directory traversal
- **Regex rename** — extract and reassemble filename parts via capture groups
- **High-quality rasterization** — configurable DPI with Ghostscript and ImageMagick backends

## Installation

### Python dependencies

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install Pillow>=10.0.0 pdf2image>=1.16.0 Wand>=0.6.11
```

### System dependencies

#### Ghostscript (required for EPS/PS)

| Platform | Install |
|----------|---------|
| Windows  | Download from https://www.ghostscript.com/releases/gsdnld.html, add `bin` to PATH |
| Linux    | `sudo apt-get install ghostscript` |
| macOS    | `brew install ghostscript` |

Verify: `gswin64c --version` (Windows) or `gs --version` (Linux/macOS)

#### Poppler (optional, for PDF)

| Platform | Install |
|----------|---------|
| Windows  | Download from https://github.com/oschwartz10612/poppler-windows/releases/, add `bin` to PATH |
| Linux    | `sudo apt-get install poppler-utils` |
| macOS    | `brew install poppler` |

#### ImageMagick + Wand (optional, for EPS/PS/EMF)

| Platform | Install |
|----------|---------|
| Windows  | Download from https://imagemagick.org/script/download.php, enable "Install development headers", set `IMAGEMAGICK_BINARY` env var |
| Linux    | `sudo apt-get install libmagickwand-dev && pip install Wand` |
| macOS    | `brew install imagemagick && pip install Wand` |

## Usage

```
python rm_border.py -i <file_or_directory> [options]
```

### Command-line arguments

| Long | Short | Description | Default |
|------|-------|-------------|---------|
| `--input` | `-i` | **(required)** Input file or directory | — |
| `--output_dir` | `-o` | Output directory | Same as input |
| `--background` | `-bg` | Background color in hex | `#FFFFFF` |
| `--padding` | `-p` | Margin to keep (1 or 4 values: top right bottom left) | `0` |
| `--dpi` | — | Rasterization DPI for vector formats | `300` |
| `--rename_pattern` | — | Regex pattern for renaming | — |
| `--rename_template` | — | Rename template (`{1}`, `{2}` for capture groups) | — |
| `--recursive` | `-r` | Process sub-directories recursively | `False` |
| `--format` | `-f` | Output format: png / jpg / jpeg / bmp / tiff | `png` |
| `--tolerance` | `-t` | Background color tolerance | `10` |
| `--auto` | `-a` | Smart border detection (ignores `--background`) | `False` |
| `--verbose` | `-v` | Enable debug logging | `False` |

## Examples

### Basic

```bash
# Remove white border (default background)
python rm_border.py -i image.png

# Remove black border
python rm_border.py -i image.png -bg #000000

# Keep 10 px margin on all sides
python rm_border.py -i image.png -p 10

# Keep different margins (top right bottom left)
python rm_border.py -i image.png -p 5 10 5 10
```

### Batch

```bash
# Process all images in a directory
python rm_border.py -i ./images/

# Recursive with custom output directory
python rm_border.py -i ./project/ -r -o ./output/

# Verbose logging
python rm_border.py -i ./batch/ -o ./output/ -v
```

### Vector formats

```bash
python rm_border.py -i document.pdf --dpi 300
python rm_border.py -i figure.eps --dpi 600
python rm_border.py -i diagram.ps
```

### Regex rename

```bash
# figure_01.eps → clean_01.png
python rm_border.py -i figure_01.eps \
  --rename_pattern "figure_(\d+)" \
  --rename_template "clean_{1}.png"

# report_2024_chart.png → 2024_chart_cropped.png
python rm_border.py -i report_2024_chart.png \
  --rename_pattern "report_(\d+)_(\w+)" \
  --rename_template "{1}_{2}_cropped"
```

### Smart auto-detection

```bash
# Auto-detect and remove borders — no background color needed
python rm_border.py -i image.png -a

# With custom tolerance
python rm_border.py -i image.png -a -t 15

# With padding
python rm_border.py -i image.png -a -p 5

# Batch auto-detection
python rm_border.py -i ./images/ -a -r -o ./output/
```

> When `-a` is enabled, the tool scans all four edges inward to find contiguous
> solid-color border segments and trims them automatically. The `--background`
> flag is ignored in this mode.

### Output format

```bash
# Export as JPEG (alpha channel composited onto white)
python rm_border.py -i image.png -f jpg
```

## Output naming

| Scenario | Input | Output |
|----------|-------|--------|
| Default | `image.png` | `image_processed.png` |
| Custom output dir | `./src/image.png` | `./output/image_processed.png` |
| Regex rename | `figure_01.eps` | `clean_01.png` |

## Algorithm

### Edge detection

1. **Alpha channel** (highest priority) — If the image has an alpha channel with actual transparent pixels, the content bounding box is derived from transparency. If all pixels are fully opaque (no transparent border), the tool falls through to background-color detection.

2. **Background color comparison** — A solid-color reference image is created from the specified `--background` value. The per-pixel absolute difference is computed via `ImageChops.difference`. Each channel is thresholded against `--tolerance`: channels with difference ≤ tolerance are considered background. `getbbox()` then yields the content bounding box.

### Tolerance

Tolerance controls how strictly a pixel must match the background color to be treated as background:

- `ImageChops.difference` computes the absolute R/G/B difference between each pixel and the background.
- A pixel is classified as **content** if *any* channel's difference exceeds the tolerance.
- **Lower** values = stricter (only very close colors count as background).
- **Higher** values = looser (larger color deviations still count as background).

### Smart auto-detection (`--auto`)

When `-a` is enabled, a four-edge independent scan is performed:

1. **Sample edge color** — The dominant color of the outermost row/column on each edge is taken as the candidate border color.
2. **Scan inward** — Rows (top/bottom) or columns (left/right) are checked sequentially. A row/column is "pure" if ≥ 95 % of its pixels match the candidate border color within tolerance. Scanning stops at the first non-pure row/column.
3. **Color consistency** — The four detected border colors are compared:
   - All four identical → all four sides are borders; trim all.
   - Three identical → trim those three sides.
   - Two identical → trim those two sides.
   - All different → every side with a detected pure segment is trimmed independently.

### Padding

After the content bounding box is computed, padding is applied by expanding outward:

```
final_box = content_box ± padding
```

Clamped to image boundaries so the crop never exceeds the original dimensions.

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| EPS/PS rasterization failed | Ghostscript not installed or not in PATH | Install Ghostscript and add its `bin` to PATH |
| PDF processing failed | pdf2image or poppler missing | `pip install pdf2image` and install poppler |
| No valid content detected | Background color mismatch or tolerance too low | Check `--background`, increase `--tolerance`, use `-v` |
| Invalid bounding box | Padding too large for image size | Reduce `--padding` |

## Performance tips

- Use `-v` to monitor progress during batch runs.
- Lower `--dpi` (e.g. 150–200) for faster vector rasterization.
- Ensure ≥ 2 GB free memory when processing very large images.

## Changelog

### v1.1.0 (2026-05-13)
- Fix: `--background` now works correctly on RGBA images where all pixels are fully opaque
- New: `--auto` / `-a` — intelligent four-edge border detection and removal
- New: short flags `-t` (tolerance), `-r` (recursive), `-f` (format)

### v1.0.0 (2026-04-07)
- Initial release
- PNG, JPG, BMP, TIFF, EMF, PDF, EPS, PS support
- Alpha-channel and background-color detection
- Flexible padding control
- Regex rename support

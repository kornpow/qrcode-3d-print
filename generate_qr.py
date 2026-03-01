# /// script
# requires-python = ">=3.9"
# dependencies = ["qrcode"]
# ///

"""
Generates two 3D-printable STL files for a two-color QR code hang tag.

Usage:
    uv run generate_qr.py

Settings are read from config.toml. CLI flags override config values.

Output:
    output_base.stl  — tag body (Color 1)
    output_qr.stl    — QR blocks + label text (Color 2)

CLI flags:
    --config path        config file (default: config.toml)
    --text "..."         text to encode
    --out path.stl       base output path
    --width 68.8         tag width in mm
    --height 91.8        tag height in mm
    --padding 2          uniform gap around all content in mm
    --thickness 3        base plate thickness in mm
    --qr-thickness 2     raised height of QR blocks in mm
    --quiet-zone 2       quiet-zone blocks (spec=4, 2 works on modern scanners)
    --deboss             recess QR into tag instead of raising it
    --corner-radius 10   corner radius in mm (0 = sharp corners)
    --hole               add a hanging hole
    --hole-radius 4      hole radius in mm
    --label "My Tag"     identifier text below QR
    --date "02/26/26"    date string ("today" = today's date)
    --label-size 5       font size in mm
    --label-height 1.5   raised height of label text in mm
"""

import argparse
import datetime
import pathlib
import subprocess
import sys
import textwrap
import tomllib
import qrcode

BASE = pathlib.Path(__file__).parent
OPENSCAD = "/opt/homebrew/bin/openscad"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--config", default=str(BASE / "config.toml"))
parser.add_argument("--text", default=None)
parser.add_argument("--out", default=None)
parser.add_argument("--width", type=float, default=None)
parser.add_argument("--height", type=float, default=None)
parser.add_argument("--padding", type=float, default=None)
parser.add_argument("--thickness", type=float, default=None)
parser.add_argument("--qr-thickness", type=float, default=None)
parser.add_argument("--quiet-zone", type=int, default=None)
parser.add_argument("--deboss", action="store_true", default=None)
parser.add_argument("--corner-radius", type=float, default=None)
parser.add_argument("--hole", action="store_true", default=None)
parser.add_argument("--hole-radius", type=float, default=None)
parser.add_argument("--label", default=None)
parser.add_argument("--date", default=None)
parser.add_argument("--label-size", type=float, default=None)
parser.add_argument("--label-height", type=float, default=None)
cli = parser.parse_args()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
cfg: dict = {}
config_path = pathlib.Path(cli.config)
if config_path.exists():
    with open(config_path, "rb") as f:
        cfg = tomllib.load(f)


def c(section, key, default):
    return cfg.get(section, {}).get(key, default)


def c_root(key, default):
    return cfg.get(key, default)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
text_val = cli.text or c_root("text", None)
out_val = cli.out or c_root("out", str(BASE / "output.stl"))
tag_w = cli.width or c("tag", "width", None)
tag_h = cli.height or c("tag", "height", None)
padding = cli.padding if cli.padding is not None else c("tag", "padding", 2.0)
thickness = cli.thickness or c("tag", "thickness", 3.0)
qr_thickness = cli.qr_thickness or c("qr", "qr_thickness", 2.0)
quiet_blocks = (
    cli.quiet_zone if cli.quiet_zone is not None else c("qr", "quiet_zone_blocks", 2)
)
deboss = cli.deboss or c("qr", "deboss", False)
corner_radius = (
    cli.corner_radius
    if cli.corner_radius is not None
    else c("tag", "corner_radius", 10.0)
)
hole = cli.hole or c("hole", "enabled", False)
hole_r = cli.hole_radius or c("hole", "radius", 4.0)
hole_x_offset = c("hole", "x", 0.0)
label_text = cli.label if cli.label is not None else c("label", "text", "")
label_date = cli.date if cli.date is not None else c("label", "date", "")
label_size = cli.label_size or c("label", "size", 5.0)
label_height = cli.label_height or c("label", "height", 1.5)

if label_date and label_date.lower() == "today":
    label_date = datetime.date.today().strftime("%m/%d/%y")

_out = pathlib.Path(out_val)
out_base = str(_out.with_name(_out.stem + "_base" + _out.suffix))
out_qr = str(_out.with_name(_out.stem + "_qr" + _out.suffix))

# ---------------------------------------------------------------------------
# Read text to encode
# ---------------------------------------------------------------------------
if text_val:
    text = text_val.strip()
else:
    input_file = BASE / "input.txt"
    if not input_file.exists():
        sys.exit(
            "No text to encode: set 'text' in config.toml, use --text, or create input.txt."
        )
    text = input_file.read_text().strip()
    if not text or text == "Replace this with your text":
        sys.exit("Please edit input.txt with the text you want to encode.")

print(f"Encoding: {text!r}")

# ---------------------------------------------------------------------------
# Generate QR matrix
# ---------------------------------------------------------------------------
qr_obj = qrcode.QRCode(
    error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=0
)
qr_obj.add_data(text)
qr_obj.make(fit=True)

matrix = qr_obj.get_matrix()
qr_grid = len(matrix)
print(f"QR grid: {qr_grid}x{qr_grid}")

# ---------------------------------------------------------------------------
# Layout — all in mm, origin at bottom-left of tag (0, 0)
#
# Y layout (bottom to top):
#   0
#   └─ padding
#      └─ date text (label_size * 0.8 tall)
#         └─ line_gap (if both label and date present)
#            └─ label text (label_size tall)
#               └─ padding
#                  └─ quiet zone
#                     └─ QR code
#                        └─ quiet zone
#                           └─ hole zone (hole_r*2 + padding)
#                              └─ tag_h
#
# X layout (left to right):
#   0
#   └─ padding
#      └─ quiet zone
#         └─ QR code
#            └─ quiet zone
#               └─ padding
#                  └─ tag_w
# ---------------------------------------------------------------------------

line_gap = padding * 0.5

# Label area: how much vertical space the text occupies
label_area_h = 0.0
if label_date:
    label_area_h += label_size * 0.8
if label_text:
    label_area_h += label_size
if label_date and label_text:
    label_area_h += line_gap

# Hole zone: height reserved at the top for the hanging hole
hole_zone = (hole_r * 2 + padding) if hole else padding

# Total blocks to scale: QR grid + quiet zone on each side
qr_units = qr_grid + quiet_blocks * 2

# Derive scale from width (primary). If --height is given via CLI, clamp to fit.
if tag_w:
    scale = round((tag_w - padding * 2) / qr_units, 4)
else:
    scale = c("qr", "scale", 2.0)
    tag_w = round(qr_units * scale + padding * 2, 1)

if tag_h:
    # Explicit height given (CLI override) — clamp scale so QR fits vertically
    scale_h = (tag_h - padding - label_area_h - padding - hole_zone) / qr_units
    scale = round(min(scale, scale_h), 4)
else:
    # Auto-derive height from content
    tag_h = round(qr_units * scale + padding + label_area_h + padding + hole_zone, 1)

qr_mm = qr_grid * scale
qz_mm = quiet_blocks * scale

# Absolute Y positions
qr_bottom_y = padding + label_area_h + padding + qz_mm  # bottom edge of QR blocks
hole_center_y = tag_h - hole_zone / 2  # center of hanging hole

# Label baseline Y positions (OpenSCAD text valign="bottom")
date_baseline_y = padding
label_baseline_y = padding + (label_size * 0.8 + line_gap if label_date else 0)

print(
    f"Tag: {tag_w}x{tag_h}mm  |  QR: {qr_mm:.1f}mm  |  "
    f"scale: {scale}  |  quiet: {qz_mm:.1f}mm  |  padding: {padding}mm"
)

# ---------------------------------------------------------------------------
# OpenSCAD geometry helpers
# ---------------------------------------------------------------------------


def rounded_rect(w, h, t, r):
    """Rounded rectangle, origin at (0,0,0) bottom-left."""
    r = min(r, w / 2, h / 2)
    if r <= 0:
        return f"cube([{w}, {h}, {t}]);"
    return textwrap.dedent(f"""\
        hull() {{
            translate([{r},   {r},   0]) cylinder(h={t}, r={r}, $fn=64);
            translate([{w - r}, {r},   0]) cylinder(h={t}, r={r}, $fn=64);
            translate([{r},   {h - r}, 0]) cylinder(h={t}, r={r}, $fn=64);
            translate([{w - r}, {h - r}, 0]) cylinder(h={t}, r={r}, $fn=64);
        }}""")


def gen_qr_blocks(matrix, scale, qz_mm, qr_bottom_y, z, height):
    """One cube per dark QR cell at its absolute position."""
    lines = []
    n = len(matrix)
    s = f"{scale + 0.001:.4f}"  # tiny overlap to avoid z-fighting
    for row_i, row in enumerate(matrix):
        for col_i, cell in enumerate(row):
            if not cell:
                continue
            x = padding + qz_mm + col_i * scale
            y = qr_bottom_y + (n - 1 - row_i) * scale  # row 0 = top of QR
            lines.append(
                f"    translate([{x:.4f}, {y:.4f}, {z}]) cube([{s}, {s}, {height}]);"
            )
    return "\n".join(lines)


def gen_label(
    label_text,
    label_date,
    label_size,
    label_height,
    label_baseline_y,
    date_baseline_y,
    thickness,
    tag_w,
    padding,
    stretch=0.8,
):
    """Text geometry for label and date, stretched across a fraction of tag width."""
    parts = []
    avail_w = tag_w - padding * 2
    target_w = avail_w * stretch
    x_offset = padding + (avail_w - target_w) / 2  # center the stretched text
    if label_date:
        parts.append(
            textwrap.dedent(f"""\
            translate([{x_offset:.4f}, {date_baseline_y:.4f}, {thickness}])
            resize([{target_w:.4f}, 0, 0])
            linear_extrude(height={label_height})
            text("{label_date}", size={label_size * 0.8:.4f},
                 halign="left", valign="bottom", font="Liberation Sans");""")
        )
    if label_text:
        parts.append(
            textwrap.dedent(f"""\
            translate([{x_offset:.4f}, {label_baseline_y:.4f}, {thickness}])
            resize([{target_w:.4f}, 0, 0])
            linear_extrude(height={label_height})
            text("{label_text}", size={label_size:.4f},
                 halign="left", valign="bottom", font="Liberation Sans:style=Bold");""")
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Build SCAD source for each body
# ---------------------------------------------------------------------------
cx = tag_w / 2  # horizontal center


def make_base_scad():
    base = rounded_rect(tag_w, tag_h, thickness, corner_radius)

    hole_geo = ""
    if hole:
        hx = cx + hole_x_offset
        hole_geo = textwrap.dedent(f"""
        translate([{hx:.4f}, {hole_center_y:.4f}, -1])
            cylinder(h={thickness + 2}, r={hole_r}, $fn=64);""")

    if deboss:
        # Subtract QR blocks from the base
        blocks = gen_qr_blocks(matrix, scale, qz_mm, qr_bottom_y, z=0, height=thickness)
        return textwrap.dedent(f"""\
            // Base plate (deboss: QR recessed)
            difference() {{
                {base}
                union() {{
            {blocks}
                }}{hole_geo}
            }}
            """)
    else:
        return textwrap.dedent(f"""\
            // Base plate
            difference() {{
                {base}{hole_geo}
            }}
            """)


def make_qr_scad():
    blocks = gen_qr_blocks(
        matrix, scale, qz_mm, qr_bottom_y, z=thickness, height=qr_thickness
    )
    label = gen_label(
        label_text,
        label_date,
        label_size,
        label_height,
        label_baseline_y,
        date_baseline_y,
        thickness,
        tag_w,
        padding,
    )
    parts = []
    if blocks:
        parts.append(f"    // QR blocks\n{blocks}")
    if label:
        parts.append(f"    // label\n{label}")
    return "// QR blocks + label\nunion() {\n" + "\n".join(parts) + "\n}\n"


# ---------------------------------------------------------------------------
# Write .scad and render to STL
# ---------------------------------------------------------------------------
scad_base = str(_out.with_name(_out.stem + "_base.scad"))
scad_qr = str(_out.with_name(_out.stem + "_qr.scad"))

pathlib.Path(scad_base).write_text(make_base_scad())
pathlib.Path(scad_qr).write_text(make_qr_scad())


def render(scad_path, stl_path):
    result = subprocess.run(
        [OPENSCAD, "-o", stl_path, "--backend=Manifold", scad_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(f"OpenSCAD failed on {scad_path}")


print("Rendering base...")
render(scad_base, out_base)
print(f"  -> {out_base}")

print("Rendering QR + label...")
render(scad_qr, out_qr)
print(f"  -> {out_qr}")

print(f"\nDone.")
print(f"  Color 1 (base):     {out_base}")
print(f"  Color 2 (QR+label): {out_qr}")

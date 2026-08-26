#!/usr/bin/env python3
"""Embed view screenshots into docs/snapper_schematic.svg.

Each <image id="shot_<name>"> in the SVG receives a base64 PNG built
from the screenshot file given for <name>; the image's declared width
and height set the aspect the screenshot is cropped and resized to.
Usage: embed_schematic_shots.py SVG name=path [name=path ...]
Screenshots are viewport captures of the deployed views; the top
`--crop-top` pixels (site header) are dropped before resizing.
"""
import argparse
import base64
import io
import re
import sys

from PIL import Image

SCALE = 2  # rendered pixels per SVG unit, for crisp thumbnails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("shots", nargs="+", help="name=path")
    ap.add_argument("--crop-top", type=int, default=150)
    args = ap.parse_args()
    svg = open(args.svg).read()
    for spec in args.shots:
        name, path = spec.split("=", 1)
        m = re.search(
            r'<image ([^>]*?)id="shot_%s"([^>]*?)xlink:href="[^"]*"' % re.escape(name), svg)
        if not m:
            sys.exit(f"no <image id=\"shot_{name}\"> in {args.svg}")
        attrs = m.group(1) + m.group(2)
        w = int(float(re.search(r'width="([\d.]+)"', attrs).group(1)))
        h = int(float(re.search(r'height="([\d.]+)"', attrs).group(1)))
        im = Image.open(path).convert("RGB")
        im = im.crop((0, args.crop_top, im.width, im.height))
        target_ratio = w / h
        cur_ratio = im.width / im.height
        if cur_ratio > target_ratio:
            new_w = int(im.height * target_ratio)
            im = im.crop((0, 0, new_w, im.height))
        else:
            new_h = int(im.width / target_ratio)
            im = im.crop((0, 0, im.width, new_h))
        im = im.resize((w * SCALE, h * SCALE), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        svg = svg[:m.start()] + (
            '<image %sid="shot_%s"%sxlink:href="data:image/png;base64,%s"'
            % (m.group(1), name, m.group(2), data)) + svg[m.end():]
        print(f"{name}: {path} -> {w}x{h} ({len(data)//1024} KiB base64)")
    open(args.svg, "w").write(svg)


if __name__ == "__main__":
    main()

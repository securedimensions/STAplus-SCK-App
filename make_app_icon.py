#!/usr/bin/env python3
"""Build the app icon: logo.icns on macOS, logo.ico on Windows."""

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "logo.png")
ICNS = os.path.join(ROOT, "logo.icns")
ICO = os.path.join(ROOT, "logo.ico")
SRGB = "/System/Library/ColorSync/Profiles/sRGB Profile.icc"
SIZES = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)


def sips(*args, **kwargs):
    subprocess.check_call(["sips", *args], stdout=subprocess.DEVNULL, **kwargs)


def pixel_size(path):
    out = subprocess.check_output(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path], text=True)
    width = height = None
    for line in out.splitlines():
        if "pixelWidth" in line:
            width = int(line.split()[-1])
        elif "pixelHeight" in line:
            height = int(line.split()[-1])
    if not width or not height:
        raise RuntimeError(f"Could not read size of {path}")
    return width, height


def main_windows():
    from PIL import Image

    if not os.path.isfile(SRC):
        raise SystemExit(f"Missing {SRC}")
    image = Image.open(SRC).convert("RGBA")
    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.size[0]) // 2, (side - image.size[1]) // 2))
    square.save(
        ICO,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Wrote {ICO}")


def main():
    if sys.platform == "win32":
        main_windows()
        return
    if not os.path.isfile(SRC):
        raise SystemExit(f"Missing {SRC}")
    work = tempfile.mkdtemp(prefix="sck-icon-", dir=ROOT)
    try:
        srgb = os.path.join(work, "srgb.png")
        square = os.path.join(work, "square.png")
        sips_args = ["-s", "format", "png"]
        if os.path.isfile(SRGB):
            sips_args += ["-m", SRGB]
        sips(*sips_args, SRC, "--out", srgb)
        width, height = pixel_size(srgb)
        side = max(width, height)
        sips("--padToHeightWidth", str(side), str(side), srgb, "--out", square)
        iconset = os.path.join(work, "logo.iconset")
        os.mkdir(iconset)
        for name, size in SIZES:
            sips("-z", str(size), str(size), square, "--out", os.path.join(iconset, name))
        subprocess.check_call(["iconutil", "-c", "icns", iconset, "-o", ICNS])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Wrote {ICNS}")


if __name__ == "__main__":
    main()

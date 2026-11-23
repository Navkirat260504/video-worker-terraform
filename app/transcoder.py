"""transcoder.py - converts one video file into 360p/480p/720p mp4 files.

Can be used on its own for testing:
    python transcoder.py input.mov ./out
"""
import os
import subprocess
import sys

SIZES = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080}


def source_height(src):
    """Return the height of the first video stream, using ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=height", "-of", "csv=p=0", src],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return int(out)


def pick_sizes(height):
    """Only keep sizes that are not bigger than the source (no upscaling).
    If the source is smaller than every size, make only the smallest one."""
    chosen = {n: h for n, h in SIZES.items() if h <= height}
    if not chosen:
        smallest = min(SIZES, key=SIZES.get)
        chosen = {smallest: SIZES[smallest]}
    return chosen


def transcode(src, outdir, on_done=None):
    """Make every size. Returns {name: path}. on_done(name, path) is called
    after each size, so the caller can upload it straight away."""
    os.makedirs(outdir, exist_ok=True)
    results = {}
    for name, h in pick_sizes(source_height(src)).items():
        out = os.path.join(outdir, f"{name}.mp4")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src,
             "-vf", f"scale=-2:{h}", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", out],
            check=True,
        )
        results[name] = out
        if on_done:
            on_done(name, out)
    return results


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python transcoder.py <input> <output-folder>")
    for n, p in transcode(sys.argv[1], sys.argv[2]).items():
        print(n, "->", p)

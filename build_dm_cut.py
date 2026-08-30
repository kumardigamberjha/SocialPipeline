"""Build the 40-second cold-outreach cut, 9:16 and 16:9, from ``beats_dm.json``.

The shipped 2:48 film (``release_demo_16x9.mp4``) is the wrong asset for a cold
LinkedIn DM: it is 60 MB, it is 16:9, it sits at -21.7 LUFS, and it opens on an
empty dashboard. This builds a separate short cut that opens on the strongest
frame in the whole library — the Channel Strategy audit reading a client's CTR
back to them as 0.00% — and closes on a single ask.

Why this does not reuse ``render_demo_segment`` / ``render_reel_wide``: both
letterbox a whole 1920x1080 screen into a fixed window (1056x594 in the vertical
case, a 0.55x downscale). That is fine for a shot whose job is atmosphere and
fatal for a shot whose job is to be *read* on a phone. Every beat here is a
punch-in on one panel instead, so the geometry has to follow the crop. The
primitives — narration, fonts, probing, the music mix — are imported, not forked.

    .venv/bin/python build_dm_cut.py                 # both aspects
    .venv/bin/python build_dm_cut.py --aspect 9x16
    .venv/bin/python build_dm_cut.py --no-music

Needs network: narration is edge-tts, the same voice the shipped films used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from build_final_synchronized_videos import (
    BG_HEX, CYAN, SLATE_200, SLATE_400, VIOLET, WHITE,
    OUT_DIR, TAKES, get_font, generate_voice, probe_duration, resolve_source, run_cmd,
)
from build_release_film import MUSIC, MUSIC_VOLUME, _glow, _fit, write_srt

ROOT = Path(__file__).resolve().parent
BEATS = ROOT / "website" / "video" / "beats_dm.json"
STILLS = ROOT / "website" / "assets" / "stills"
WORK = OUT_DIR / "dm_build"

FPS = 30
BORDER = 6
LOUDNESS = dict(I="-14", TP="-1.5", LRA="11")

# Two layouts, one beat sheet. VW/VH_MAX is the box the punched-in panel is fitted
# into; everything else lays out around wherever that lands.
GEOM = {
    "9x16": dict(W=1080, H=1920, VW=1000, VH_MAX=1150, VCY=1015,
                 MARGIN=54, HEAD=78, CAP=44, out=OUT_DIR / "dm_cut_9x16.mp4"),
    # 700/600 is the most height a 16:9 frame can give the panel and still leave
    # room for a two-line headline above it and the caption below.
    "16x9": dict(W=1920, H=1080, VW=1500, VH_MAX=700, VCY=600,
                 MARGIN=90, HEAD=62, CAP=36, out=OUT_DIR / "dm_cut_16x9.mp4"),
}


def _even(n: float) -> int:
    return int(round(n / 2)) * 2


def window(crop: list[int] | None, g: dict) -> tuple[int, int]:
    """Size of the video window: the crop fitted into the layout's box."""
    cw, ch = (crop[0], crop[1]) if crop else (1920, 1080)
    w, h = g["VW"], _even(g["VW"] * ch / cw)
    if h > g["VH_MAX"]:
        h, w = g["VH_MAX"], _even(g["VH_MAX"] * cw / ch)
    return _even(w), _even(h)


# ── chrome ───────────────────────────────────────────────────────────────────

def create_overlay(beat: dict, g: dict, rect: tuple[int, int, int, int], path: Path) -> None:
    """Headline above the panel, one caption below it. No badge, no chips.

    The shipped lower-third is ~34px type on a 1920 frame; on a phone that is
    unreadable, and this cut has to work muted. Everything here is sized so the
    on-screen text carries the pitch on its own.
    """
    W, H, m = g["W"], g["H"], g["MARGIN"]
    vx, vy, vw, vh = rect
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _glow(img, (-200, -320, W + 200, vy - 40), VIOLET, 44)
    _glow(img, (-200, vy + vh + 40, W + 200, H + 320), CYAN, 32)
    d = ImageDraw.Draw(img)

    head = beat.get("headline", "")
    f, lines, size = _fit(d, head, lambda s: get_font(s), g["HEAD"], W - 2 * m, 3)
    step = int(size * 1.16)
    y = vy - 52 - step * len(lines)
    for line in lines:
        d.text((m, y), line, font=f, fill=WHITE + (255,))
        y += step

    cap = beat.get("caption", "")
    if cap:
        fc, cl, cs = _fit(d, cap, lambda s: get_font(s), g["CAP"], W - 2 * m - 40, 2)
        cy = vy + vh + 54
        d.rounded_rectangle([m, cy - 6, m + 8, cy + len(cl) * int(cs * 1.3) - 8],
                            radius=4, fill=CYAN + (255,))
        for line in cl:
            d.text((m + 34, cy), line, font=fc, fill=SLATE_200 + (255,))
            cy += int(cs * 1.3)

    img.save(path)


def create_card(beat: dict, g: dict, path: Path) -> None:
    """Closing card. One claim, one question, one address — nothing else."""
    W, H, m = g["W"], g["H"], g["MARGIN"]
    img = Image.new("RGBA", (W, H), (2, 6, 23, 255))
    _glow(img, (-200, -300, W + 200, H // 2), VIOLET, 40)
    _glow(img, (-200, H // 2, W + 200, H + 300), CYAN, 30)
    d = ImageDraw.Draw(img)

    big = [l for l in beat.get("card_big", "").split("\n") if l]
    size = g["HEAD"] + 18
    f = get_font(size)
    while size > 30 and max(d.textlength(l, font=f) for l in big) > W - 2 * m:
        size -= 4
        f = get_font(size)
    step = int(size * 1.18)

    small = beat.get("card_small", "")
    link = beat.get("card_link", "")
    f_small = get_font(int(g["HEAD"] * 0.62))
    f_link = get_font(int(g["CAP"] * 1.05), mono=True)

    block = step * len(big) + 46 + int(size * 0.72) + 66 + int(g["CAP"] * 1.3)
    y = (H - block) // 2
    for line in big:
        d.text(((W - d.textlength(line, font=f)) / 2, y), line, font=f, fill=WHITE + (255,))
        y += step

    y += 46
    d.text(((W - d.textlength(small, font=f_small)) / 2, y), small,
           font=f_small, fill=CYAN + (255,))
    y += int(size * 0.72) + 66

    lw = d.textlength(link, font=f_link)
    d.rounded_rectangle([(W - lw) / 2 - 30, y - 16, (W + lw) / 2 + 30, y + int(g["CAP"] * 1.3) + 14],
                        radius=14, outline=CYAN + (150,), width=2)
    d.text(((W - lw) / 2, y), link, font=f_link, fill=SLATE_200 + (255,))
    img.save(path)


# ── stills ───────────────────────────────────────────────────────────────────

def extract_still(beat: dict) -> Path:
    """Freeze one frame out of a take.

    The audit and roadmap takes scroll continuously, so a fixed crop on the
    moving source slides its own subject out of frame. These beats exist to be
    read, so they are frozen at a known-good timestamp and given a slow push-in
    instead. Extraction is from the take, so the build stays reproducible from
    the source recordings.
    """
    STILLS.mkdir(parents=True, exist_ok=True)
    out = STILLS / f"{beat['id']}.png"
    if not out.exists():
        src = resolve_source(TAKES, beat["source"])
        run_cmd(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{beat['at']:.3f}",
                 "-i", str(src), "-frames:v", "1", str(out)])
    return out


# ── render ───────────────────────────────────────────────────────────────────

def render(beat: dict, dur: float, voice: Path, g: dict, aspect: str, out_mp4: Path) -> None:
    W, H = g["W"], g["H"]
    kind = beat["kind"]

    if kind == "card":
        png = WORK / f"{beat['id']}_{aspect}_card.png"
        create_card(beat, g, png)
        inputs = ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(png)]
        vf = f"[0:v]fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS,format=yuv420p[v]"
    else:
        crop = beat.get("crop")
        vw, vh = window(crop, g)
        vx, vy = (W - vw) // 2, g["VCY"] - vh // 2
        overlay = WORK / f"{beat['id']}_{aspect}_overlay.png"
        create_overlay(beat, g, (vx, vy, vw, vh), overlay)
        crop_f = f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}," if crop else ""

        if kind == "still":
            src = extract_still(beat)
            inputs = ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(src)]
            # Pre-upscale before zoompan: zoompan rounds its pan offsets to whole
            # pixels, and on a 1x source that rounding is visible as jitter.
            pan = (f"{crop_f}scale=iw*2:ih*2:flags=lanczos,"
                   f"zoompan=z='min(1+0.00022*on,1.055)':d=1:fps={FPS}:s={vw}x{vh}:"
                   f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',")
            head = f"[0:v]{pan}trim=duration={dur:.3f},setpts=PTS-STARTPTS"
        else:
            src = resolve_source(TAKES, beat["source"])
            in_t = float(beat.get("in", 0.0))
            left = probe_duration(src) - in_t
            speed = min(2.5, max(1.0, left / dur)) if left > dur * 1.12 else 1.0
            inputs = ["-ss", f"{in_t:.3f}", "-i", str(src)]
            head = (f"[0:v]setpts=PTS/{speed:.4f},tpad=stop_mode=clone:stop_duration=6,"
                    f"trim=duration={dur:.3f},setpts=PTS-STARTPTS,"
                    f"{crop_f}scale={vw}:{vh}:flags=lanczos,fps={FPS}")

        inputs += ["-f", "lavfi", "-i", f"color=c={BG_HEX}:s={W}x{H}:r={FPS}:d={dur:.3f}",
                   "-loop", "1", "-i", str(overlay)]
        vf = (
            f"{head},pad={vw + BORDER * 2}:{vh + BORDER * 2}:{BORDER}:{BORDER}:0x22d3ee@0.42[app];"
            f"[1:v][app]overlay={vx - BORDER}:{vy - BORDER}:shortest=1[base];"
            f"[base][2:v]overlay=0:0:shortest=1,format=yuv420p[v]"
        )

    n_a = len([a for a in inputs if a == "-i"])
    inputs += ["-i", str(voice)]
    af = (f"[{n_a}:a]afade=t=in:st=0:d=0.03,"
          f"afade=t=out:st={max(probe_duration(voice) - 0.05, 0.1):.3f}:d=0.05,"
          f"apad=whole_dur={dur:.3f},atrim=duration={dur:.3f},aresample=48000[a]")

    run_cmd(["ffmpeg", "-y", "-loglevel", "error", *inputs,
             "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
             "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
             "-movflags", "+faststart", str(out_mp4)])


# ── loudness ─────────────────────────────────────────────────────────────────

def normalize(src: Path, dst: Path) -> None:
    """Two-pass loudnorm to -14 LUFS.

    The shipped film measures -21.7 LUFS integrated. On a phone speaker in a
    noisy room that reads as broken audio, which costs the view before the pitch
    lands. Two passes rather than one because the single-pass filter is dynamic
    and drifts on a cut this short.
    """
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(src),
         "-af", f"loudnorm=I={LOUDNESS['I']}:TP={LOUDNESS['TP']}:LRA={LOUDNESS['LRA']}:print_format=json",
         "-f", "null", "/dev/null"],
        capture_output=True, text=True)
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", probe.stderr, re.S)
    if not m:
        raise RuntimeError(f"loudnorm measurement failed:\n{probe.stderr[-1500:]}")
    s = json.loads(m.group(0))
    run_cmd([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-af", (f"loudnorm=I={LOUDNESS['I']}:TP={LOUDNESS['TP']}:LRA={LOUDNESS['LRA']}:"
                f"measured_I={s['input_i']}:measured_TP={s['input_tp']}:"
                f"measured_LRA={s['input_lra']}:measured_thresh={s['input_thresh']}:"
                f"offset={s['target_offset']}:linear=true:print_format=summary"),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", str(dst)])


def mix_music(src: Path, dst: Path) -> bool:
    if not MUSIC.exists():
        return False
    n = probe_duration(src)
    run_cmd([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-stream_loop", "-1", "-i", str(MUSIC), "-filter_complex",
        f"[1:a]volume={MUSIC_VOLUME},atrim=0:{n:.3f},afade=t=in:st=0:d=0.8,"
        f"afade=t=out:st={max(0.0, n - 2.0):.3f}:d=2.0[m];"
        f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"aresample=48000[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-ar", "48000", "-movflags", "+faststart", str(dst)])
    return True


# ── build ────────────────────────────────────────────────────────────────────

async def build(aspect: str, music: bool) -> Path:
    spec = json.loads(BEATS.read_text())
    beats = spec["beats"]
    g = GEOM[aspect]
    voices, segs = WORK / "voices", WORK / f"segments_{aspect}"
    for p in (voices, segs):
        p.mkdir(parents=True, exist_ok=True)

    print(f"\n── {aspect}: narrating {len(beats)} beats ──")
    durations = {}
    for b in beats:
        wav = voices / f"{b['id']}.wav"
        if not wav.exists():
            await generate_voice(b["vo"], b.get("voice", spec["voice"]),
                                 b.get("rate", spec["rate"]), wav)
        if not wav.exists():
            raise RuntimeError(f"no narration for {b['id']} — edge-tts needs network access")
        # Fixed slots, unlike the long films: a 40s target cannot be a function
        # of how many words the narration happens to contain.
        durations[b["id"]] = float(b["dur"])
        slack = durations[b["id"]] - probe_duration(wav)
        flag = "  ← VO OVERRUNS SLOT" if slack < 0 else ""
        print(f"   {b['id']:16s} slot {durations[b['id']]:4.1f}s  vo {probe_duration(wav):4.1f}s{flag}")

    print(f"── {aspect}: rendering ──")
    files = []
    for i, b in enumerate(beats, 1):
        seg = segs / f"{b['id']}.mp4"
        render(b, durations[b["id"]], voices / f"{b['id']}.wav", g, aspect, seg)
        files.append(seg)
        print(f"   [{i}/{len(beats)}] {b['id']}")

    lst = WORK / f"concat_{aspect}.txt"
    lst.write_text("".join(f"file '{f.resolve()}'\n" for f in files))
    joined = WORK / f"concat_{aspect}.mp4"
    run_cmd(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(joined)])

    staged = WORK / f"staged_{aspect}.mp4"
    if music and mix_music(joined, staged):
        print(f"   music bed at {MUSIC_VOLUME:.0%}")
    else:
        staged = joined
    normalize(staged, g["out"])

    write_srt(beats, durations, ROOT / "website" / "video" / f"dm-{aspect}.srt")
    size = g["out"].stat().st_size / 1e6
    print(f"✅ {g['out'].name}  {probe_duration(g['out']):.1f}s  {size:.1f} MB")
    return g["out"]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aspect", choices=[*GEOM, "both"], default="both")
    ap.add_argument("--no-music", action="store_true")
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    for asp in ([*GEOM] if a.aspect == "both" else [a.aspect]):
        await build(asp, music=not a.no_music)


if __name__ == "__main__":
    asyncio.run(main())

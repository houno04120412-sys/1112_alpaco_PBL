"""Render the motion HTML with Playwright.

  python tools/render.py motion.html --beats          one still per beat + contact sheet (check pass)
  python tools/render.py motion.html                  60fps mp4: 4 subframes/frame blended with ffmpeg tmix,
                                                      UI sounds placed by their measured peak, loop-wrapped mix
Options: --song file.mp3 (music bed from its first downbeat), --workers N, --out DIR
"""
import argparse
import json
import multiprocessing as mp
import pathlib
import shutil
import subprocess
import sys
import time
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
SR = 48000


def open_page(p, html):
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1440}, device_scale_factor=1)
    pg.goto(pathlib.Path(html).resolve().as_uri() + "?render=1")
    pg.wait_for_function("window.MOTION !== undefined")
    geist = pg.evaluate("document.fonts.ready.then(() => document.fonts.check('600 24px Geist'))")
    return b, pg, geist


def shoot(pg, t, path):
    pg.evaluate(f"window.MOTION.seek({t!r})")
    pg.screenshot(path=str(path))


def worker(job):
    from playwright.sync_api import sync_playwright
    html, items = job
    with sync_playwright() as p:
        b, pg, _ = open_page(p, html)
        for t, path in items:
            shoot(pg, t, path)
        b.close()


# ---------- audio ----------
def _tone(f0, f1, dur, amp):
    n = int(dur * SR)
    f = f0 * (f1 / f0) ** (np.arange(n) / n)
    return amp * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-np.arange(n) / (n / 5))


def _hiss(dur, amp, lo, hi, seed):
    n = int(dur * SR)
    x = np.random.default_rng(seed).uniform(-1, 1, n)
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1 / SR)
    X[(fr < lo) | (fr > hi)] = 0
    x = np.fft.irfft(X, n)
    return amp * x / (np.abs(x).max() + 1e-9) * np.exp(-np.arange(n) / (n / 5))


def _mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[: len(p)] += p
    return out


def _pad(x, lead):
    return np.concatenate([np.zeros(int(lead * SR)), x])


SFX = {
    "kick": _tone(150, 42, .28, .9), "hat": _hiss(.05, .12, 7000, 16000, 1), "clap": _hiss(.14, .3, 1000, 2200, 2),
    "click": _mix(_hiss(.03, .25, 3000, 12000, 3), _tone(1800, 1500, .04, .12)),
    "grab": _tone(900, 700, .06, .14), "release": _tone(700, 900, .06, .12), "key": _tone(2400, 2200, .025, .1),
    "enter": _tone(660, 640, .12, .18), "toggle": _mix(_hiss(.025, .2, 3500, 12000, 4), _tone(1200, 1000, .05, .12)),
    "success": _mix(_tone(880, 880, .22, .12), _pad(_tone(1320, 1320, .3, .1), .08)),
    "morph": _tone(320, 560, .09, .07), "hover": _tone(1600, 1600, .03, .06),
}


def place(buf, snd, t):
    """Add snd so that its measured peak lands exactly at t; wraps around so the loop is seamless."""
    peak = int(np.argmax(np.abs(snd)))
    start = int(round(t * SR)) - peak
    idx = (start + np.arange(len(snd))) % len(buf)
    np.add.at(buf, idx, snd)


def build_audio(info, out_wav, song=None):
    T, B = info["T"], info["B"]
    n = int(round(T * SR))
    sfx = np.zeros(n)
    for e in info["events"]:
        place(sfx, SFX[e["type"]], e["t"])
    if song:
        sys.path.insert(0, str(ROOT / "tools"))
        import beatgrid
        fd = beatgrid.analyze_file(song)["first_downbeat"]
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(fd), "-i", str(song), "-t", str(T), "-ac", "1",
                              "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
        music = np.zeros(n)
        m = np.frombuffer(raw, np.float32)[:n]
        music[: len(m)] = m
        f = int(.015 * SR)
        music[:f] *= np.linspace(0, 1, f)
        music[-f:] *= np.linspace(1, 0, f)
    else:
        music = np.zeros(n)
        for k in range(info["beats"]):
            place(music, SFX["kick"], k * B)
            place(music, SFX["hat"], (k + .5) * B)
            if k % 2 == 1:
                place(music, SFX["clap"], k * B)
    mix = .7 * music + .9 * sfx
    mix *= .89 / (np.abs(mix).max() + 1e-9)
    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def run(cmd):
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html")
    ap.add_argument("--beats", action="store_true")
    ap.add_argument("--song")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--sub", type=int, default=4)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out")
    ap.add_argument("--keep-frames", action="store_true")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    html = pathlib.Path(a.html).resolve()
    out = pathlib.Path(a.out) if a.out else ROOT / "artifacts" / "runs" / (
        time.strftime("%Y%m%d-%H%M%S") + ("-beats" if a.beats else "-render"))
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b, pg, geist = open_page(p, html)
        info = pg.evaluate("window.MOTION.info()")
        if a.beats:
            for k in range(info["beats"]):
                shoot(pg, (k + .45) * info["B"], out / f"beat_{k:02d}.png")
        b.close()
    if not geist:
        print("WARN Geist web font not loaded (offline?) - fallback font used")
    (out / "timeline.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    if a.beats:
        run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(out / "beat_%02d.png"),
             "-vf", "scale=360:360,tile=7x4:padding=4:color=white", "-frames:v", "1", str(out / "contact.png")])
        print(f"PASS beats={info['beats']} contact={out / 'contact.png'}")
        return 0

    fps, sub = a.fps, a.sub
    nfr = int(round(info["T"] * fps))
    frames = out / "frames"
    frames.mkdir(exist_ok=True)
    allj = [((k + j / sub) / fps, frames / f"f_{k * sub + j:05d}.png") for k in range(nfr) for j in range(sub)]
    chunk = -(-len(allj) // a.workers)
    t0 = time.time()
    with mp.Pool(a.workers) as pool:
        pool.map(worker, [(str(html), allj[i:i + chunk]) for i in range(0, len(allj), chunk)])
    print(f"captured {len(allj)} subframes in {time.time() - t0:.0f}s")
    video = out / "video.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps * sub), "-i", str(frames / "f_%05d.png"),
         "-vf", f"tmix=frames={sub},select='eq(mod(n\\,{sub})\\,{sub - 1})',setpts=N/({fps}*TB)",
         "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", str(video)])
    wav = out / "audio.wav"
    build_audio(info, wav, a.song)
    final = out / "motion.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-shortest", str(final)])
    got = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                          "stream=nb_read_frames,r_frame_rate", "-of", "json", str(final)],
                         capture_output=True, text=True, check=True).stdout
    st = json.loads(got)["streams"][0]
    ok = int(st["nb_read_frames"]) == nfr and st["r_frame_rate"] == f"{fps}/1"
    if not a.keep_frames:
        shutil.rmtree(frames)
    print(("PASS" if ok else "FAIL"), json.dumps({"file": str(final), "frames": st["nb_read_frames"],
                                                    "expected": nfr, "rate": st["r_frame_rate"]}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

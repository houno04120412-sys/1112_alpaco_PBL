"""Beat grid of a song with numpy: tempo, beat times and the first downbeat.

Usage:
  python tools/beatgrid.py song.mp3        -> JSON on stdout
  python tools/beatgrid.py --self-test     -> PASS/FAIL on a synthetic track
"""
import argparse
import json
import subprocess
import sys

import numpy as np

SR, HOP, NFFT = 22050, 256, 1024


def load_mono(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def _flux(logm):
    f = np.maximum(0.0, np.diff(logm, axis=0)).sum(axis=1)
    f = np.concatenate([[0.0], f])
    k = np.ones(16) / 16
    return np.maximum(0.0, f - np.convolve(f, k, mode="same"))


def analyze(y, sr=SR, prefer=120.0):
    n = 1 + (len(y) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    mag = np.abs(np.fft.rfft(y[idx] * np.hanning(NFFT), axis=1))
    logm = np.log1p(100 * mag)
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    env, low = _flux(logm), _flux(logm[:, freqs < 150])
    fr = sr / HOP
    spec = np.fft.rfft(env, 2 * len(env))
    ac = np.fft.irfft(spec * np.conj(spec))[: len(env)]
    bpms = np.arange(80, 160, 0.05)
    lags = 60 * fr / bpms
    score = np.interp(lags, np.arange(len(ac)), ac) * np.exp(-0.5 * (np.log2(bpms / prefer) / 0.5) ** 2)
    bpm = float(bpms[np.argmax(score)])
    period = 60 * fr / bpm
    grid = np.arange(0, len(env) - 1, period)
    phases = np.arange(0, period, 0.25)
    ph = phases[np.argmax([np.interp(p + grid[grid + p < len(env) - 1], np.arange(len(env)), env).sum() for p in phases])]
    beats = ph + grid[grid + ph < len(env) - 1]
    lowe = np.interp(beats, np.arange(len(low)), low)
    j = int(np.argmax([lowe[i::4].sum() for i in range(4)]))
    times = (beats * HOP + NFFT / 2) / sr
    return {"bpm": bpm, "first_downbeat": float(times[j]), "beat_times": [round(float(t), 4) for t in times[:64]]}


def analyze_file(path):
    return analyze(load_mono(path))


def self_test():
    sr, bpm, off = SR, 120.0, 0.31
    y = np.zeros(int(sr * 30), np.float32)
    rng = np.random.default_rng(1)
    for k in range(int((30 - off) / (60 / bpm))):
        s = int((off + k * 60 / bpm) * sr)
        t = np.arange(int(0.15 * sr)) / sr
        if k % 4 == 0:
            seg = np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.05)
        else:
            seg = rng.uniform(-0.4, 0.4, len(t)) * np.exp(-t / 0.01)
        y[s:s + len(seg)] += seg[: len(y) - s]
    r = analyze(y, sr)
    ok = abs(r["bpm"] - bpm) < 1 and abs(r["first_downbeat"] - off) < 0.03
    print(("PASS" if ok else "FAIL"), json.dumps({"bpm": r["bpm"], "first_downbeat": r["first_downbeat"], "expected": [bpm, off]}))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song", nargs="?")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if not a.song:
        ap.error("song path required")
    print(json.dumps(analyze_file(a.song), indent=1))

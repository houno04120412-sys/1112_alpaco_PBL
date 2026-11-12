# One-shape UI motion — workflow

Any company material → `data/<name>.json` → HTML (live demo) → 60fps MP4.

```powershell
$py = "C:\Users\houno\projects_powershell\1112_alpaco_PBL\.venv\Scripts\python.exe"
cd C:\Users\houno\projects_powershell\1112_alpaco_PBL\export\1112
& $py tools\build.py data\company.json                  # validate + build <company>_motion.html (PASS/FAIL)
& $py tools\render.py northbeam_advisory_motion.html --beats   # one still per beat -> contact.png (check)
& $py tools\render.py northbeam_advisory_motion.html           # 60fps mp4, 4 subframes + tmix, synced SFX
```

- New client: copy `data/company.json`, replace the text/numbers (the build rejects text that would be cramped).
- Song (e.g. Mixkit, ~120 BPM): `build.py ... --song song.mp3` (numpy beat grid, first downbeat) and `render.py ... --song song.mp3`.
- Live demo: open the HTML in Chrome. Click = sound (built-in 120 BPM beat + UI sounds), Space = pause, `?t=7.5` = still at 7.5 s.
- `tools/beatgrid.py --self-test` checks the beat detector.

Beat grid (120 BPM, 7 bars, 28 beats, loop 14 s):

| Bar | Beats 0-3 (per bar) |
|---|---|
| 1 | hover button · click → loader · loader pulse · check |
| 2 | dynamic island · music player · play→pause morph · progress runs |
| 3 | grab scrubber · drag · release · morph to volume slider |
| 4 | grab volume · drag past max (stretch) · release spring-back · morph to toggle |
| 5 | toggle flips on · knob → tab indicator · tab 2 · tab 3 |
| 6 | tabs open into chart · line draws · hover tooltip · collapse to ⌘K |
| 7 | palette opens · type to filter · enter → toast · back to button |

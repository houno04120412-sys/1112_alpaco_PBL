"""Build the motion HTML from a company data JSON.

Usage:
  python tools/build.py data/company.json [--out motion.html] [--song song.mp3]

--song analyzes the track (beatgrid.py), sets bpm/first downbeat and copies it next to the HTML.
Prints PASS/FAIL with the reasons; exit code 0 only on PASS.
"""
import argparse
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "template" / "motion.template.html"
ICONS = {"arrow", "check", "search", "doc", "send", "share", "calendar", "user", "chart", "checkCircle"}


def validate(d):
    err = []

    def text(path, limit):
        cur = d
        for k in path.split("."):
            cur = cur.get(k) if isinstance(cur, dict) else None
        if not isinstance(cur, str) or not cur.strip():
            err.append(f"{path}: missing")
        elif len(cur) > limit:
            err.append(f"{path}: {len(cur)} chars > {limit} (would be cramped)")

    for p, n in [("company", 40), ("brand_mark", 2), ("button.label", 22), ("island.label", 28),
                 ("player.title", 24), ("player.subtitle", 34), ("chart.label", 30), ("chart.value", 6),
                 ("chart.delta", 10), ("chart.tooltip", 22), ("palette.placeholder", 28),
                 ("palette.query", 6), ("toast.title", 30), ("toast.action", 8)]:
        text(p, n)
    tabs = d.get("tabs", [])
    if len(tabs) != 3 or any(not isinstance(t, str) or len(t) > 10 for t in tabs):
        err.append("tabs: need exactly 3 labels, each <= 10 chars")
    ch = d.get("chart", {})
    if len(ch.get("series", [])) != 8 or not all(isinstance(v, (int, float)) for v in ch.get("series", [])):
        err.append("chart.series: need 8 numbers")
    if len(ch.get("x_labels", [])) != 8:
        err.append("chart.x_labels: need 8 labels")
    if ch.get("hover_index") not in range(1, 7):
        err.append("chart.hover_index: must be 1..6")
    pal = d.get("palette", {})
    items = pal.get("items", [])
    if not 3 <= len(items) <= 5:
        err.append("palette.items: need 3..5 items")
    for i, it in enumerate(items):
        if len(it.get("label", "")) > 30:
            err.append(f"palette.items[{i}].label > 30 chars")
        if it.get("icon") not in ICONS:
            err.append(f"palette.items[{i}].icon must be one of {sorted(ICONS)}")
        if len(it.get("hint", "")) > 3:
            err.append(f"palette.items[{i}].hint > 3 chars")
    q = pal.get("query", "").lower()
    if items and q:
        hits = [i for i, it in enumerate(items) if q in it.get("label", "").lower()]
        if not hits:
            err.append("palette.query matches no item")
        elif hits[0] != pal.get("target"):
            err.append(f"palette.target must be the first item matching the query (index {hits[0]})")
        if len(hits) == len(items):
            err.append("palette.query filters nothing; pick a query that removes some items")
    return err


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data")
    ap.add_argument("--out")
    ap.add_argument("--song")
    a = ap.parse_args()
    data = json.loads(pathlib.Path(a.data).read_text(encoding="utf-8"))
    errs = validate(data)
    if errs:
        print("FAIL")
        for e in errs:
            print(" -", e)
        return 1
    out = pathlib.Path(a.out) if a.out else ROOT / (
        "".join(c if c.isalnum() else "_" for c in data["company"].lower()).strip("_") + "_motion.html")
    if a.song:
        sys.path.insert(0, str(ROOT / "tools"))
        import beatgrid
        g = beatgrid.analyze_file(a.song)
        song = pathlib.Path(a.song)
        dst = out.parent / song.name
        if song.resolve() != dst.resolve():
            shutil.copyfile(song, dst)
        data["bpm"] = round(g["bpm"], 3)
        data["audio"] = {"src": song.name, "first_downbeat": round(g["first_downbeat"], 4)}
        print(f"beatgrid: bpm={g['bpm']:.2f} first_downbeat={g['first_downbeat']:.3f}s")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "/*__DATA__*/null" in html
    html = html.replace("/*__DATA__*/null", payload, 1).replace(
        "<title>Motion</title>", f"<title>{data['company']} — motion</title>", 1)
    out.write_text(html, encoding="utf-8")
    print(f"PASS {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Generates the text blocks in README.md.

  portrait   the neofetch-style block: assets/avatar.gif turned into characters, next to the info card.
             Hair becomes 0 and o (curls), the beard becomes 1 (stubble), and facial features are drawn
             with whichever ASCII glyph best matches their shape.
  activity   contributions by month as unicode bars. The daily workflow runs this one.

    pip install pillow numpy                                 # portrait only
    python3 assets/build.py portrait
    GITHUB_TOKEN=$(gh auth token) python3 assets/build.py activity

Each block is written between its <!-- name:start --> and <!-- name:end --> markers.
The 3D shelf is a separate page: shelf/index.html.
"""

import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
README = HERE.parent / "README.md"
GITHUB_USER = "Ahmadhassan30"

# --------------------------------------------------------------------------- the info card

INFO = [
    "ahmad@hassan",
    "────────────",
    ("role", "software engineer"),
    ("", "researcher"),
    ("research", "computational neuroscience"),
    ("", "ai systems · multi-agent"),
    ("builds", "agents · retrieval · web"),
    ("music", "producer"),
    ("reads", "dostoevsky · kafka · tolstoy"),
    ("langs", "python · typescript · rust"),
    ("os", "linux"),
    ("home", "pakistan"),
    ("web", "ahmadhassan.engineer"),
    "",
    "███ ▓▓▓ ▒▒▒ ░░░",
]

PORTRAIT = dict(cols=54, frame=0, crop=(86, 8, 360, 286))
GAP = 3
MONO_URL = "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"


def write_block(name, block):
    text = README.read_text(encoding="utf-8")
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    if start not in text or end not in text:
        raise SystemExit(f"{name} markers not found in README.md")
    new = re.sub(f"{re.escape(start)}.*?{re.escape(end)}", lambda m: f"{start}\n{block}\n{end}", text, flags=re.S)
    README.write_text(new, encoding="utf-8")
    print(f"{name:<10} README block updated")


# --------------------------------------------------------------------------- portrait

def ascii_portrait(cols, frame, crop):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    cell_aspect = 0.414                 # character width / line height in a GitHub code block
    cw, ch = 12, 29                     # matching resolution per character, same aspect
    im = Image.open(HERE / "avatar.gif")
    im.seek(frame)
    im = im.convert("RGBA").crop(crop)
    rows = round(cols * im.height / im.width * cell_aspect)
    a = np.asarray(im.resize((cols * cw, rows * ch), Image.LANCZOS)).astype(int)
    r_, g_, b_, alpha = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    lum = (0.2126 * r_ + 0.7152 * g_ + 0.0722 * b_) / 255
    opaque = alpha > 128
    skin = opaque & (r_ > 165) & (g_ > 95) & (r_ > g_) & (g_ > b_)
    mouth = opaque & (r_ > 140) & (g_ < 115) & (r_ - g_ > 55)
    beard = opaque & (lum > .16) & (lum < .42) & (r_ > g_) & (g_ >= b_ - 3) & ~skin & ~mouth
    hair = opaque & (lum <= .16) & (r_ - b_ >= 3)
    black = opaque & (lum <= .16) & ~hair
    ink = (opaque & (lum < .45)).astype(float)

    font_path = HERE / ".fontcache" / "mono.ttf"
    if not font_path.exists():
        font_path.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(MONO_URL, font_path)
    font = ImageFont.truetype(str(font_path), 22)
    strokes = " .,'`-_~=|/\\()o"
    glyphs = {}
    for c in strokes:
        img = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(img).text((0, ch * 0.78 - font.getmetrics()[0]), c, font=font, fill=255)
        glyphs[c] = np.asarray(img).astype(float) / 255

    def cell(m, r, c):
        return m[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]

    curl_cut = np.quantile(lum[hair], .72)
    lines = []
    for r in range(rows):
        s = ""
        for c in range(cols):
            if cell(opaque, r, c).mean() < .3:
                s += " "
                continue
            fh, fs, fb, fk, fm = (cell(m, r, c).mean() for m in (hair, skin, beard, black, mouth))
            if fh > .5 and fs < .15:                     # curls: dark strands 0, lighter strands o
                s += "o" if cell(lum, r, c)[cell(hair, r, c)].mean() > curl_cut else "0"
            elif fb > .45 and fs < .3:                   # stubble
                s += "1"
            elif fs > .2 or fm > .1:                     # face: draw the strokes by glyph shape
                patch = cell(ink, r, c)
                s += " " if patch.mean() < .07 else min(strokes, key=lambda g: ((glyphs[g] - patch) ** 2).sum())
            elif fh + fk > .5 and fh > fk * .5:
                s += "0"
            elif fb + fh > .45:
                s += "1"
            elif fk > .5:                                # the black tee, kept quiet
                s += "."
            else:
                s += " "
        lines.append(s.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def build_portrait():
    art = ascii_portrait(**PORTRAIT)
    keyw = max(len(item[0]) for item in INFO if isinstance(item, tuple)) + 2
    info = [item if isinstance(item, str) else f"{item[0]:<{keyw}}{item[1]}" for item in INFO]
    top = max(0, (len(art) - len(info)) // 2)
    width = PORTRAIT["cols"]
    out = []
    for i in range(max(len(art), top + len(info))):
        left = art[i] if i < len(art) else ""
        right = info[i - top] if 0 <= i - top < len(info) else ""
        out.append(f"{left:<{width}}{' ' * GAP}{right}".rstrip())
    write_block("portrait", "```text\n" + "\n".join(out) + "\n```")


# --------------------------------------------------------------------------- activity

def fetch_calendar():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    query = ("query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{"
             "totalContributions weeks{contributionDays{date contributionCount}}}}}}")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": GITHUB_USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def build_activity():
    cal = fetch_calendar()
    if not cal:
        print("no GITHUB_TOKEN set: activity block left as it is")
        return
    days = [(dt.date.fromisoformat(d["date"]), d["contributionCount"])
            for w in cal["weeks"] for d in w["contributionDays"]]
    by_month = {}
    for d, n in days:
        by_month[(d.year, d.month)] = by_month.get((d.year, d.month), 0) + n
    months = sorted(by_month)[-12:]
    peak = max(max(by_month[m] for m in months), 1)
    span = 36  # longest bar, in characters; partial blocks give eighth-character precision
    chart = []
    for y, m in months:
        v = by_month[(y, m)]
        units = round(v / peak * span * 8)
        bar = "█" * (units // 8) + " ▏▎▍▌▋▊▉"[units % 8].strip()
        bar = bar or ("▏" if v else "")
        chart.append(f"{dt.date(y, m, 1):%b %y}".lower() + f"   {bar:<{span + 1}}{v:>4}")

    recent = days[-365:]
    longest = run = 0
    for _, n in recent:
        run = run + 1 if n else 0
        longest = max(longest, run)
    active = sum(1 for _, n in recent if n)
    best_day, best_n = max(recent, key=lambda d: d[1])
    write_block("activity", "\n".join([
        "```text",
        "contributions by month",
        "",
        *chart,
        "",
        f"{cal['totalContributions']:,} in the last year · {active}/{len(recent)} days active · "
        f"longest streak {longest}d · best day {best_n} ({best_day:%d %b})".lower(),
        "```",
    ]))


if __name__ == "__main__":
    what = sys.argv[1:] or ["portrait", "activity"]
    if "portrait" in what:
        build_portrait()
    if "activity" in what:
        build_activity()

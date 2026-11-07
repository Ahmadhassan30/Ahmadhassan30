#!/usr/bin/env python3
"""Builds the two generated pieces of README.md.

  1. assets/shelf-{light,dark}.svg   the animated bookshelf
  2. the activity block in README.md  a unicode sparkline of the last year of contributions,
                                      written between <!-- activity:start --> and <!-- activity:end -->

    pip install fonttools brotli
    GITHUB_TOKEN=$(gh auth token) python3 assets/build.py   # both
    python3 assets/build.py shelf                            # shelf only, no token needed
    python3 assets/build.py activity                         # activity only (the daily workflow runs this)

The shelf's fonts (Inter and JetBrains Mono, SIL Open Font License) download once into
assets/.fontcache/ and get subset into the SVG, because an SVG shown through <img>
cannot load web fonts.
"""

import base64
import datetime as dt
import io
import json
import math
import os
import re
import sys
import urllib.request
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
README = HERE.parent / "README.md"
CACHE = HERE / ".fontcache"
GITHUB_USER = "Ahmadhassan30"


# --------------------------------------------------------------------------- shelf content

# (width, height, tone, author, note). author None = an unnamed spine.
SHELF = [
    (30, 150, "navy", None, None),
    (76, 196, "violet", "DOSTOEVSKY", "recursive psychology"),
    (26, 162, "lilac", None, None),
    (40, 174, "midnight", None, None),
    (68, 184, "indigo", "KAFKA", "systems as absurdity"),
    (33, 156, "plum", None, None),
    (90, 206, "iris", "TOLSTOY", "emergent complexity"),
    (28, 168, "slate", None, None),
    (42, 160, "navy", None, None),
    (73, 194, "plum", "NIETZSCHE", "epistemological provocation"),
    (31, 176, "violet", None, None),
    (26, 152, "lilac", None, None),
    (66, 186, "midnight", "PLATH", "precision under pressure"),
    (35, 166, "indigo", None, None),
    (45, 180, "navy", None, None),
]
SLOT_NOTE = ("YOUR PICK?", "click to recommend a book")
CAPTION = "auto-browsing  ·  click the shelf to recommend a book"

THEMES = {
    "light": {
        "ink": "#0d0d1f", "muted": "#70738f", "line": "#e4e4ef", "accent": "#5038f0",
        "pop": "#ffffff", "pop_edge": "#e2e2ee", "shadow": "#1b1650", "shadow_op": ".16",
        "tones": {"midnight": "#1a1a40", "navy": "#26307a", "indigo": "#3a35b0", "violet": "#5a45e6",
                  "iris": "#8b7ff5", "lilac": "#e6e2ff", "plum": "#4a2f8a", "slate": "#d2d5ee"},
        "pale": {"lilac", "slate"}, "on_dark": "#f2f0ff", "on_pale": "#1b1a3d",
    },
    "dark": {
        "ink": "#eeeefa", "muted": "#8b8dab", "line": "#23263d", "accent": "#9b8cff",
        "pop": "#161a30", "pop_edge": "#2c3050", "shadow": "#000000", "shadow_op": ".55",
        "tones": {"midnight": "#15173a", "navy": "#1d2456", "indigo": "#2b2e7c", "violet": "#4436b0",
                  "iris": "#6a5cf0", "lilac": "#c7c0ff", "plum": "#2f2263", "slate": "#232845"},
        "pale": {"lilac"}, "on_dark": "#ece9ff", "on_pale": "#1b1a3d",
    },
}


# --------------------------------------------------------------------------- fonts

FONT_URLS = {
    "inter": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf",
    "mono": "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}
# face -> (source, fixed axes, weight per theme). Pale-on-dark reads heavier, so dark is lighter.
FACES = {
    "title": ("inter", {"opsz": 20}, {"light": 600, "dark": 560}),
    "text": ("inter", {"opsz": 14}, {"light": 440, "dark": 400}),
    "mono": ("mono", {}, {"light": 460, "dark": 420}),
}
_static = {}


def static_font(face, theme):
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    key = (face, theme)
    if key not in _static:
        src, axes, weights = FACES[face]
        path = CACHE / f"{src}.ttf"
        if not path.exists():
            CACHE.mkdir(exist_ok=True)
            print(f"downloading {src} ...")
            urllib.request.urlretrieve(FONT_URLS[src], path)
        font = instancer.instantiateVariableFont(TTFont(path), {**axes, "wght": weights[theme]})
        buf = io.BytesIO()
        font.save(buf)
        _static[key] = buf.getvalue()
    return _static[key]


def width(face, s, size, ls=0.0):
    """Advance width, good enough for layout (kerning ignored)."""
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(static_font(face, "light")))
    cmap, adv, upm = font.getBestCmap(), font["hmtx"].metrics, font["head"].unitsPerEm
    return sum(adv[cmap[ord(c)]][0] for c in s) * size / upm + ls * len(s)


def embedded_font(face, theme, chars):
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(static_font(face, theme)))
    opts = subset.Options()
    opts.layout_features = ["kern"]
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]  # keep copyright + OFL licence fields
    opts.hinting = False
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)))
    sub.subset(font)
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


# --------------------------------------------------------------------------- shelf

def build_shelf():
    W, base, lift, step = 1000, 296, 14, 3.0
    parts, chars = [], {f: set() for f in FACES}

    def text(x, y, s, face, size, cls, anchor="start", ls=0.0):
        chars[face].update(s)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        l = f' letter-spacing="{ls}"' if ls else ""
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}" class="{face} {cls}" font-size="{size}"{a}{l}>{escape(s)}</text>')

    books, x = [], 4
    for w, h, tone, author, note in SHELF:
        books.append(dict(x=x, w=w, h=h, tone=tone, author=author, note=note))
        x += w + 5
    lean = dict(x=x + 30, w=34, h=176)
    slot = dict(x=lean["x"] + lean["w"] + 40, w=54, h=186, slot=True)
    stops = [b for b in books if b["author"]] + [slot]
    N, T = len(stops), len(stops) * step
    f = 100 / N

    def top_of(s):
        return base - s["h"] - (0 if s.get("slot") else lift)

    def cursor_at(s):
        return s["x"] + s["w"] / 2 + 3, top_of(s) + (s["h"] / 2 if s.get("slot") else 34)

    frames = []
    for i, s in enumerate(stops):
        cx, cy = cursor_at(s)
        frames.append(f"{i*f:.2f}%{{transform:translate({cx:.1f}px,{cy:.1f}px);animation-timing-function:ease-in-out}}")
        frames.append(f"{i*f + f*0.78:.2f}%{{transform:translate({cx:.1f}px,{cy:.1f}px);"
                      "animation-timing-function:cubic-bezier(.6,0,.3,1)}")
    cx0, cy0 = cursor_at(stops[0])
    frames.append(f"100%{{transform:translate({cx0:.1f}px,{cy0:.1f}px)}}")
    a, b, c = f * 0.1, f * 0.8, f * 0.95
    motion = f"""
.lift{{animation:lift {T}s cubic-bezier(.3,.7,.2,1) infinite both}}
@keyframes lift{{0%{{transform:translateY(0)}}{a:.2f}%,{b:.2f}%{{transform:translateY(-{lift}px)}}{c:.2f}%,100%{{transform:translateY(0)}}}}
.pop{{opacity:0;animation:pop {T}s ease infinite both}}
@keyframes pop{{0%{{opacity:0;transform:translateY(4px)}}{a+1:.2f}%,{b:.2f}%{{opacity:1;transform:translateY(0)}}{c:.2f}%,100%{{opacity:0;transform:translateY(4px)}}}}
.ghost{{transform:translate({cx0:.1f}px,{cy0:.1f}px);animation:ghost {T}s infinite}}
@keyframes ghost{{{"".join(frames)}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""
    parts.append('<defs><filter id="shadow" x="-30%" y="-40%" width="160%" height="200%">'
                 '<feDropShadow dx="0" dy="6" stdDeviation="9" flood-color="SHADOW" flood-opacity="SHOP"/>'
                 '</filter></defs>')

    stop_i = 0
    for bk in books:
        g = f'<g class="lift" style="animation-delay:{stop_i*step:.1f}s">' if bk["author"] else "<g>"
        g += f'<rect x="{bk["x"]}" y="{base - bk["h"]}" width="{bk["w"]}" height="{bk["h"]}" rx="3" class="t-{bk["tone"]}"/>'
        g += (f'<rect x="{bk["x"] + bk["w"] - 3}" y="{base - bk["h"]}" width="3" height="{bk["h"]}" rx="1.5" '
              'fill="#000" opacity=".14"/>')
        parts.append(g)
        if bk["author"]:
            parts.append(f'<g transform="translate({bk["x"] + bk["w"]/2:.1f},{base - bk["h"]/2:.1f}) rotate(90)">')
            text(0, 4, bk["author"], "title", 11.5, f"on-{bk['tone']}", "middle", 2.6)
            parts.append("</g>")
            stop_i += 1
        parts.append("</g>")

    parts.append(f'<g transform="rotate(-10 {lean["x"] + lean["w"]} {base})">'
                 f'<rect x="{lean["x"]}" y="{base - lean["h"]}" width="{lean["w"]}" height="{lean["h"]}" rx="3" class="t-iris"/>'
                 f'<rect x="{lean["x"] + lean["w"] - 3}" y="{base - lean["h"]}" width="3" height="{lean["h"]}" '
                 'fill="#000" opacity=".14"/></g>')
    parts.append(f'<rect x="{slot["x"]}" y="{base - slot["h"]}" width="{slot["w"]}" height="{slot["h"]}" rx="4" '
                 'class="s-muted" stroke-width="1" stroke-dasharray="3 4"/>')
    parts.append(f'<g transform="translate({slot["x"] + slot["w"]/2:.1f},{base - slot["h"]/2:.1f}) rotate(90)">')
    text(0, 4, "+ YOURS", "mono", 11, "muted", "middle", 2)
    parts.append("</g>")
    parts.append(f'<rect x="0" y="{base}" width="{W}" height="2" class="line"/>')

    for i, s in enumerate(stops):  # hover cards
        name, note = SLOT_NOTE if s.get("slot") else (s["author"], s["note"])
        tw = max(width("mono", name, 10.5, 1.8), width("text", note, 15)) + 30
        cx = s["x"] + s["w"] / 2
        bx = min(max(cx - tw / 2, 0), W - tw)
        by = top_of(s) - 70
        parts.append(f'<g class="pop" style="animation-delay:{i*step:.1f}s">'
                     f'<g filter="url(#shadow)"><rect x="{bx:.1f}" y="{by:.1f}" width="{tw:.1f}" height="54" rx="12" '
                     'class="pop-bg" stroke-width="1"/></g>'
                     f'<path d="M{cx-7:.1f},{by+53.5:.1f} L{cx:.1f},{by+61:.1f} L{cx+7:.1f},{by+53.5:.1f} Z" '
                     'class="pop-bg" stroke-width="0"/>')
        text(bx + 15, by + 22, name, "mono", 10.5, "accent", ls=1.8)
        text(bx + 15, by + 42, note, "text", 15, "ink")
        parts.append("</g>")

    parts.append('<g class="ghost"><path d="M0,0 L0,17 L4.6,12.8 L7.9,20 L11,18.6 L7.8,11.6 L13.6,11.6 Z" '
                 'fill="#fff" stroke="#0d0d1f" stroke-width="1.3" stroke-linejoin="round"/></g>')
    text(0, base + 32, CAPTION, "mono", 11.5, "muted", ls=0.6)
    H = base + 44

    label = ("A bookshelf: Dostoevsky (recursive psychology), Kafka (systems as absurdity), Tolstoy "
             "(emergent complexity), Nietzsche (epistemological provocation), Plath (precision under pressure), "
             "and an empty slot for your recommendation.")
    for theme, t in THEMES.items():
        fonts = "".join(f"@font-face{{font-family:'S {k}';src:url(data:font/woff2;base64,"
                        f"{embedded_font(k, theme, cs)}) format('woff2')}}" for k, cs in chars.items() if cs)
        css = (fonts + "text{white-space:pre}"
               + ".title{font-family:'S title',-apple-system,Helvetica,Arial,sans-serif}"
               + ".text{font-family:'S text',-apple-system,Helvetica,Arial,sans-serif}"
               + ".mono{font-family:'S mono',ui-monospace,Menlo,monospace}"
               + f".ink{{fill:{t['ink']}}}.muted{{fill:{t['muted']}}}.accent{{fill:{t['accent']}}}"
               + f".line{{fill:{t['line']}}}.s-muted{{stroke:{t['muted']};fill:none}}"
               + f".pop-bg{{fill:{t['pop']};stroke:{t['pop_edge']}}}"
               + "".join(f".t-{k}{{fill:{v}}}.on-{k}{{fill:{t['on_pale'] if k in t['pale'] else t['on_dark']}}}"
                         for k, v in t["tones"].items())
               + motion)
        body = "".join(parts).replace("SHADOW", t["shadow"]).replace("SHOP", t["shadow_op"])
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
               f'role="img" aria-label="{escape(label)}"><title>{escape(label)}</title>'
               f"<style><![CDATA[{css}]]></style>{body}</svg>\n")
        (HERE / f"shelf-{theme}.svg").write_text(svg, encoding="utf-8")
    print(f"shelf          {W}x{H}")


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
    block = "\n".join([
        "```text",
        "contributions by month",
        "",
        *chart,
        "",
        f"{cal['totalContributions']:,} in the last year · {active}/{len(recent)} days active · "
        f"longest streak {longest}d · best day {best_n} ({best_day:%d %b})".lower(),
        "```",
    ])
    text = README.read_text(encoding="utf-8")
    if "<!-- activity:start -->" not in text or "<!-- activity:end -->" not in text:
        raise SystemExit("activity markers not found in README.md")
    new = re.sub(r"<!-- activity:start -->.*?<!-- activity:end -->",
                 lambda m: f"<!-- activity:start -->\n{block}\n<!-- activity:end -->", text, flags=re.S)
    README.write_text(new, encoding="utf-8")
    print("activity       README block updated")


if __name__ == "__main__":
    what = sys.argv[1:] or ["shelf", "activity"]
    if "shelf" in what:
        build_shelf()
    if "activity" in what:
        build_activity()

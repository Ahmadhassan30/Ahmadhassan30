#!/usr/bin/env python3
"""Builds the SVG plates for README.md, once for GitHub's light theme and once for dark.

    pip install fonttools brotli
    python3 assets/build.py            # everything
    python3 assets/build.py activity   # only the activity plate (what the daily workflow runs)

Every word on the plates lives in the CONTENT section below. Edit, rebuild, commit.

The activity plate reads your contribution calendar from GitHub's API and needs a token:
    GITHUB_TOKEN=$(gh auth token) python3 assets/build.py
Without one it is skipped and the existing activity SVGs are left alone.

Fonts (Inter and JetBrains Mono, both SIL Open Font License) download once into
assets/.fontcache/, then get subset and embedded, because an SVG shown through <img>
cannot load web fonts. The avatar GIF is embedded the same way.
"""

import base64
import datetime as dt
import io
import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".fontcache"

FONT_URLS = {
    "inter": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf",
    "mono": "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}

# face -> (source, fixed axes, weight per theme). Pale-on-dark reads heavier, so dark is a touch lighter.
FACES = {
    "display": ("inter", {"opsz": 32}, {"light": 640, "dark": 600}),
    "title": ("inter", {"opsz": 20}, {"light": 600, "dark": 560}),
    "text": ("inter", {"opsz": 14}, {"light": 440, "dark": 400}),
    "mono": ("mono", {}, {"light": 460, "dark": 420}),
}

THEMES = {
    "light": {
        "ink": "#0d0d1f", "soft": "#3d3f5e", "muted": "#70738f", "line": "#e4e4ef", "panel": "#f7f7fb",
        "accent": "#5038f0", "accent_dim": "#c9c1ff",
        "pop": "#ffffff", "pop_edge": "#e2e2ee", "shadow": "#1b1650", "shadow_op": ".16",
        "card_edge": "#0a0b22",
        "tones": {
            "midnight": "#1a1a40", "navy": "#26307a", "indigo": "#3a35b0", "violet": "#5a45e6",
            "iris": "#8b7ff5", "lilac": "#e6e2ff", "plum": "#4a2f8a", "slate": "#d2d5ee",
        },
        "pale_tones": {"lilac", "slate"},
        "spine_on_dark": "#f2f0ff", "spine_on_pale": "#1b1a3d",
    },
    "dark": {
        "ink": "#eeeefa", "soft": "#c2c3dc", "muted": "#8b8dab", "line": "#23263d", "panel": "#0f1224",
        "accent": "#9b8cff", "accent_dim": "#3b3480",
        "pop": "#161a30", "pop_edge": "#2c3050", "shadow": "#000000", "shadow_op": ".55",
        "card_edge": "#23264d",
        "tones": {
            "midnight": "#15173a", "navy": "#1d2456", "indigo": "#2b2e7c", "violet": "#4436b0",
            "iris": "#6a5cf0", "lilac": "#c7c0ff", "plum": "#2f2263", "slate": "#232845",
        },
        "pale_tones": {"lilac"},
        "spine_on_dark": "#ece9ff", "spine_on_pale": "#1b1a3d",
    },
}

# The hero card is the same midnight blue in both themes.
HERO = {"ink": "#f4f3ff", "soft": "#b9bbe0", "muted": "#8e90bd", "dim": "#55588a",
        "accent": "#a398ff", "line": "#26285a", "dot": "#2a2d5c"}


# --------------------------------------------------------------------------- CONTENT

NAME = "Ahmad Hassan"
WINDOW_TITLE = "ahmad@hassan — ~/profile"
COMMAND = "whoami"
TAGLINE = [[("I build systems that reason in ", "muted"), ("steps", "ink")],
           [("and read books that reason in ", "muted"), ("centuries", "ink"), (".", "muted")]]
PILLS = ["GENERATIVE AI", "AGENTIC SYSTEMS", "FULL STACK"]

WORK = [
    ("Agents", "Multi-agent systems that coordinate, reflect and remember, built to run in production."),
    ("Retrieval", "Embedding pipelines and hybrid RAG that find the one passage that matters."),
    ("Interfaces", "Full stack web apps people actually want to use. Pretty buttons included."),
]

SHELF_SUBHEAD = "Stories are compressed causal reasoning. I read them as research."
# (width, height, tone, author, note). author None = an unnamed spine.
SHELF = [
    (26, 150, "navy", None, None),
    (64, 196, "violet", "DOSTOEVSKY", "recursive psychology"),
    (22, 162, "lilac", None, None),
    (34, 174, "midnight", None, None),
    (58, 184, "indigo", "KAFKA", "systems as absurdity"),
    (28, 156, "plum", None, None),
    (76, 206, "iris", "TOLSTOY", "emergent complexity"),
    (24, 168, "slate", None, None),
    (36, 160, "navy", None, None),
    (62, 194, "plum", "NIETZSCHE", "epistemological provocation"),
    (26, 176, "violet", None, None),
    (22, 152, "lilac", None, None),
    (56, 186, "midnight", "PLATH", "precision under pressure"),
    (30, 166, "indigo", None, None),
    (38, 180, "navy", None, None),
]
SLOT_NOTE = ("YOUR PICK?", "click to recommend a book")

STACK = [  # rendered as stack.yml
    ("ml", ["python", "pytorch", "tensorflow"]),
    ("backend", ["fastapi", "django", "node.js", "graphql"]),
    ("data", ["postgresql", "mongodb", "redis"]),
    ("web", ["react", "next.js", "tailwind", "figma"]),
    ("infra", ["aws", "docker", "kubernetes", "github-actions", "vercel", "nginx"]),
    ("system", ["linux", "ubuntu", "bash", "git"]),
]

QUOTE = ("“The question of whether a computer can think is no more interesting "
         "than the question of whether a submarine can swim.”")
QUOTE_BY = "EDSGER W. DIJKSTRA"

LINKS = [("site", "AHMADHASSAN.ENGINEER"), ("linkedin", "LINKEDIN"), ("email", "EMAIL")]
GITHUB_USER = "Ahmadhassan30"


# --------------------------------------------------------------------------- fonts

def ensure_fonts():
    CACHE.mkdir(exist_ok=True)
    for name, url in FONT_URLS.items():
        path = CACHE / f"{name}.ttf"
        if not path.exists():
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(url, path)


_static = {}


def static_font(face, theme):
    """The variable font pinned to this face's axes, as TTF bytes."""
    key = (face, theme)
    if key not in _static:
        src, axes, weights = FACES[face]
        font = TTFont(CACHE / f"{src}.ttf")
        font = instancer.instantiateVariableFont(font, {**axes, "wght": weights[theme]})
        buf = io.BytesIO()
        font.save(buf)
        _static[key] = buf.getvalue()
    return _static[key]


class Metrics:
    """Advance widths, good enough for layout (kerning ignored)."""

    def __init__(self, face):
        font = TTFont(io.BytesIO(static_font(face, "light")))
        self.upm = font["head"].unitsPerEm
        self.cmap = font.getBestCmap()
        self.adv = font["hmtx"].metrics

    def width(self, s, size, ls=0.0):
        total = 0
        for ch in s:
            glyph = self.cmap.get(ord(ch))
            if glyph is None:
                raise SystemExit(f"glyph missing for {ch!r} (U+{ord(ch):04X})")
            total += self.adv[glyph][0]
        return total * size / self.upm + ls * len(s)


def embedded_font(face, theme, chars):
    font = TTFont(io.BytesIO(static_font(face, theme)))
    opts = subset.Options()
    opts.layout_features = ["kern", "liga", "calt", "tnum"] if face != "mono" else ["kern"]
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]  # keep copyright + OFL licence fields
    opts.hinting = False
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)))
    sub.subset(font)
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


# --------------------------------------------------------------------------- drawing

class Plate:
    """Collects markup plus the characters used per face, so fonts can be subset."""

    def __init__(self, name, w, h, label, css=""):
        self.name, self.w, self.h, self.label, self.css = name, w, h, label, css
        self.parts = []
        self.chars = {f: set() for f in FACES}

    def add(self, *markup):
        self.parts.extend(markup)

    def text(self, x, y, runs, face="text", size=16, cls="ink", anchor="start", ls=0.0, attrs=""):
        """runs: a string, or a list of (text, colour_class) tuples."""
        if isinstance(runs, str):
            runs = [(runs, None)]
        spans = []
        for s, colour in runs:
            self.chars[face].update(s)
            spans.append(f'<tspan class="{colour}">{escape(s)}</tspan>' if colour else escape(s))
        ls_attr = f' letter-spacing="{ls}"' if ls else ""
        anchor_attr = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" class="{face} {cls}" font-size="{size}"'
            f'{anchor_attr}{ls_attr} {attrs}>{"".join(spans)}</text>'
        )

    def svg(self, theme, extra_css=""):
        t = THEMES[theme]
        font_css = "".join(
            f"@font-face{{font-family:'P {f}';src:url(data:font/woff2;base64,"
            f"{embedded_font(f, theme, cs)}) format('woff2')}}"
            for f, cs in self.chars.items() if cs
        )
        fallback = {"mono": "ui-monospace,Menlo,monospace"}
        face_css = "".join(
            f".{f}{{font-family:'P {f}',{fallback.get(f, '-apple-system,Helvetica,Arial,sans-serif')}}}"
            for f in FACES
        )
        colours = {k: t[k] for k in ("ink", "soft", "muted", "line", "panel", "accent", "accent_dim")}
        colour_css = "".join(f".{k}{{fill:{v}}}.s-{k}{{stroke:{v};fill:none}}" for k, v in colours.items())
        colour_css += "".join(f".h-{k}{{fill:{v}}}.hs-{k}{{stroke:{v};fill:none}}" for k, v in HERO.items())
        colour_css += "".join(f".t-{k}{{fill:{v}}}" for k, v in t["tones"].items())
        colour_css += "".join(
            f".spine-{k}{{fill:{t['spine_on_pale'] if k in t['pale_tones'] else t['spine_on_dark']}}}"
            for k in t["tones"])
        colour_css += (f".pop-bg{{fill:{t['pop']};stroke:{t['pop_edge']}}}"
                       f".card-edge{{stroke:{t['card_edge']};fill:none}}")
        css = (font_css + "text{white-space:pre;font-kerning:normal}" + face_css + colour_css + self.css
               + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
        body = "".join(self.parts).replace("SHADOW_COLOUR", t["shadow"]).replace("SHADOW_OPACITY", t["shadow_op"])
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.label)}">'
            f"<title>{escape(self.label)}</title><style><![CDATA[{css}]]></style>{body}</svg>\n"
        )


def line(x1, y1, x2, y2, cls="s-line", w=1.0, extra=""):
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'class="{cls}" stroke-width="{w}" {extra}/>')


def wrap(text, face, size, width):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if M[face].width(trial, size) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    return lines


def heading(p, number, label, title):
    """Eyebrow + headline, the way every section opens."""
    p.text(0, 18, [(number, "accent"), (f"  {label}", "muted")], "mono", 12.5, ls=2.4)
    p.text(-2, 70, title, "display", 44, "ink", ls=-1.4)


# --------------------------------------------------------------------------- plates

def hero():
    W, H, R = 1000, 420, 28
    L = 56
    cmd_x = L + M["mono"].width("❯ ", 17)
    cmd_w = M["mono"].width(COMMAND, 17)
    n = len(COMMAND)
    css = f"""
.type{{animation:type 1s steps({n},end) .6s both}}
@keyframes type{{from{{clip-path:inset(0 100% 0 0)}}to{{clip-path:inset(0 0 0 0)}}}}
.caret{{animation:caret 1s steps({n},end) .6s both,blink 1.1s steps(1) 1.6s infinite}}
@keyframes caret{{from{{transform:translateX(-{cmd_w:.1f}px)}}to{{transform:translateX(0)}}}}
@keyframes blink{{50%{{opacity:0}}}}
"""
    p = Plate("hero", W, H, f"{NAME}. Software engineer: generative AI, agentic systems, full stack. "
              "I build systems that reason in steps and read books that reason in centuries.", css)
    avatar = base64.b64encode((HERE / "avatar.gif").read_bytes()).decode()
    p.add(f'''<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0c0d2b"/><stop offset="1" stop-color="#05061a"/></linearGradient>
<radialGradient id="glow" cx="790" cy="300" r="330" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#5b46ff" stop-opacity=".46"/><stop offset=".5" stop-color="#4033d6" stop-opacity=".14"/><stop offset="1" stop-color="#4033d6" stop-opacity="0"/></radialGradient>
<radialGradient id="glow2" cx="560" cy="470" r="320" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#2148ff" stop-opacity=".2"/><stop offset="1" stop-color="#2148ff" stop-opacity="0"/></radialGradient>
<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1" fill="#fff"/></pattern>
<radialGradient id="fade" cx="170" cy="150" r="560" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<mask id="dotmask"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>
<clipPath id="card"><rect width="{W}" height="{H}" rx="{R}"/></clipPath>
</defs>
<g clip-path="url(#card)">
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<rect width="{W}" height="{H}" fill="url(#dots)" opacity=".055" mask="url(#dotmask)"/>
<rect width="{W}" height="{H}" fill="url(#glow2)"/>
<rect width="{W}" height="{H}" fill="url(#glow)"/>
<image href="data:image/gif;base64,{avatar}" x="572" y="48" width="412" height="374"/>
</g>
<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="{R}" class="card-edge" stroke-width="1"/>''')

    # window chrome: monochrome traffic lights and a title
    for i in range(3):
        p.add(f'<circle cx="{30 + i*19}" cy="27" r="5.5" class="h-dot"/>')
    p.text(W / 2, 31.5, WINDOW_TITLE, "mono", 12, "h-dim", "middle", ls=0.4)
    p.add(line(0, 54, W, 54, "hs-line", 1))

    p.text(L, 112, "❯", "mono", 17, "h-accent")
    p.text(cmd_x, 112, COMMAND, "mono", 17, "h-soft type")
    p.add(f'<rect x="{cmd_x + cmd_w + 3:.1f}" y="98" width="9" height="18" rx="1" class="h-accent caret"/>')

    p.text(L - 3, 196, NAME, "display", 76, "h-ink", ls=-2.6)
    for i, runs in enumerate(TAGLINE):
        p.text(L, 248 + i * 30, [(s, f"h-{c}") for s, c in runs], "text", 21, ls=-0.2)

    x = L
    for label in PILLS:
        w = M["mono"].width(label, 11, 1.6) + 28
        p.add(f'<rect x="{x:.1f}" y="320.5" width="{w:.1f}" height="30" rx="15" class="hs-line" stroke-width="1"/>')
        p.text(x + 14, 340, label, "mono", 11, "h-soft", ls=1.6)
        x += w + 10
    return p


def work():
    css = """
.flow{stroke-dasharray:2 4;animation:flow 1.6s linear infinite}
@keyframes flow{to{stroke-dashoffset:-12}}
.hop{opacity:0;animation:hop 4.5s linear infinite}
@keyframes hop{0%,30%{opacity:1}34%,100%{opacity:0}}
.ping{transform-box:fill-box;transform-origin:center;animation:ping 3s ease-out infinite}
@keyframes ping{0%{transform:scale(.5);opacity:1}80%,100%{transform:scale(1.3);opacity:0}}
.press{transform-box:fill-box;transform-origin:center;animation:press 3.2s ease-in-out infinite}
@keyframes press{0%,58%,72%,100%{transform:scale(1)}64%{transform:scale(.9)}}
.cursor{animation:cursor 3.2s ease-in-out infinite}
@keyframes cursor{0%,10%{transform:translate(18px,14px);opacity:0}25%{opacity:1}
 58%,72%{transform:translate(0,0);opacity:1}92%,100%{transform:translate(18px,14px);opacity:0}}
"""
    col_w, gap = 290, 65
    p = Plate("work", 1000, 324, "What I build. " + " ".join(f"{t}: {d}" for t, d in WORK), css)
    heading(p, "01", "WORK", "What I build.")
    for i, (title, desc) in enumerate(WORK):
        left = i * (col_w + gap)
        p.add(line(left, 112, left + col_w, 112, "s-line", 1))
        g = f'<g transform="translate({left},136)">'
        if i == 0:  # three agents passing messages
            pts = [(6, 40), (42, 40), (24, 8)]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                g += line(*pts[a], *pts[b], "s-muted flow", 1.2)
            for k, (x, y) in enumerate(pts):
                g += f'<circle cx="{x}" cy="{y}" r="5" class="s-soft" stroke-width="1.4"/>'
                g += f'<circle cx="{x}" cy="{y}" r="5" class="accent hop" style="animation-delay:{k*1.5}s"/>'
        elif i == 1:  # a query finding its nearest neighbours
            dots = [(3, 6), (12, 24), (6, 42), (19, 9), (23, 37), (36, 4), (45, 18), (40, 44),
                    (49, 32), (30, 47), (10, 14), (47, 6), (17, 47), (3, 30)]
            for x, y in dots:
                g += f'<circle cx="{x}" cy="{y}" r="1.7" class="muted"/>'
            g += '<circle cx="28" cy="24" r="14" class="s-accent ping" stroke-width="1.2"/>'
            g += (line(28, 24, 23, 37, "s-accent", 1) + line(28, 24, 36, 4, "s-accent", 1)
                  + line(28, 24, 19, 9, "s-accent", 1))
            g += '<circle cx="28" cy="24" r="3.4" class="accent"/>'
        else:  # a window with a very pretty button
            g += '<rect x="1" y="2" width="52" height="42" rx="7" class="s-soft" stroke-width="1.3"/>'
            g += line(1, 12, 53, 12, "s-line", 1.2)
            for k in range(3):
                g += f'<circle cx="{7 + k*5}" cy="7" r="1.4" class="muted"/>'
            g += line(8, 21, 38, 21, "s-line", 3, 'stroke-linecap="round"')
            g += '<rect x="8" y="29" width="22" height="8" rx="4" class="accent press"/>'
            g += ('<g class="cursor"><path d="M24,32 l0,10 l2.7,-2.5 l2.2,4.6 l1.9,-.9 l-2.2,-4.4 l3.7,0 z" '
                  'fill="#fff" stroke="#0d0d1f" stroke-width="1" stroke-linejoin="round"/></g>')
        p.add(g + "</g>")
        p.text(left, 222, title, "title", 21, "ink", ls=-0.3)
        for k, ln in enumerate(wrap(desc, "text", 16.5, col_w)):
            p.text(left, 252 + k * 25, ln, "text", 16.5, "muted")
    return p


def section(name, number, label, title):
    p = Plate(name, 1000, 90, title)
    heading(p, number, label, title)
    return p


def shelf():
    lift, step = 14, 3.0
    W, base = 1000, 420
    books, x = [], 4
    for w, h, tone, author, note in SHELF:
        w = round(w * 1.18)
        books.append(dict(x=x, w=w, h=h, tone=tone, author=author, note=note))
        x += w + 5
    lean = dict(x=x + 30, w=34, h=176)
    slot = dict(x=lean["x"] + lean["w"] + 40, w=54, h=186, slot=True)

    stops = [b for b in books if b["author"]] + [slot]
    N = len(stops)
    T = N * step
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
    css = f"""
.lift{{animation:lift {T}s cubic-bezier(.3,.7,.2,1) infinite both}}
@keyframes lift{{0%{{transform:translateY(0)}}{a:.2f}%,{b:.2f}%{{transform:translateY(-{lift}px)}}{c:.2f}%,100%{{transform:translateY(0)}}}}
.pop{{opacity:0;animation:pop {T}s ease infinite both}}
@keyframes pop{{0%{{opacity:0;transform:translateY(4px)}}{a+1:.2f}%,{b:.2f}%{{opacity:1;transform:translateY(0)}}{c:.2f}%,100%{{opacity:0;transform:translateY(4px)}}}}
.ghost{{transform:translate({cx0:.1f}px,{cy0:.1f}px);animation:ghost {T}s infinite}}
@keyframes ghost{{{"".join(frames)}}}
"""
    p = Plate("shelf", W, base + 52, "The shelf: Dostoevsky (recursive psychology), Kafka (systems as absurdity), "
              "Tolstoy (emergent complexity), Nietzsche (epistemological provocation), Plath (precision under "
              "pressure), and an empty slot for your recommendation.", css)
    heading(p, "03", "READING", "The shelf.")
    p.text(0, 108, SHELF_SUBHEAD, "text", 18, "muted")
    p.add('<defs><filter id="shadow" x="-30%" y="-40%" width="160%" height="200%">'
          '<feDropShadow dx="0" dy="6" stdDeviation="9" flood-color="SHADOW_COLOUR" flood-opacity="SHADOW_OPACITY"/>'
          '</filter></defs>')

    stop_i = 0
    for bk in books:
        g = f'<g class="lift" style="animation-delay:{stop_i*step:.1f}s">' if bk["author"] else "<g>"
        g += f'<rect x="{bk["x"]}" y="{base - bk["h"]}" width="{bk["w"]}" height="{bk["h"]}" rx="3" class="t-{bk["tone"]}"/>'
        g += (f'<rect x="{bk["x"] + bk["w"] - 3}" y="{base - bk["h"]}" width="3" height="{bk["h"]}" rx="1.5" '
              'fill="#000" opacity=".14"/>')
        p.add(g)
        if bk["author"]:
            cx, cy = bk["x"] + bk["w"] / 2, base - bk["h"] / 2
            p.add(f'<g transform="translate({cx:.1f},{cy:.1f}) rotate(90)">')
            p.text(0, 4, bk["author"], "title", 11.5, f"spine-{bk['tone']}", "middle", ls=2.6)
            p.add("</g>")
            stop_i += 1
        p.add("</g>")

    p.add(f'<g transform="rotate(-10 {lean["x"] + lean["w"]} {base})">'
          f'<rect x="{lean["x"]}" y="{base - lean["h"]}" width="{lean["w"]}" height="{lean["h"]}" rx="3" class="t-iris"/>'
          f'<rect x="{lean["x"] + lean["w"] - 3}" y="{base - lean["h"]}" width="3" height="{lean["h"]}" '
          'fill="#000" opacity=".14"/></g>')
    p.add(f'<rect x="{slot["x"]}" y="{base - slot["h"]}" width="{slot["w"]}" height="{slot["h"]}" rx="4" '
          f'class="s-muted" stroke-width="1" stroke-dasharray="3 4"/>')
    p.add(f'<g transform="translate({slot["x"] + slot["w"]/2:.1f},{base - slot["h"]/2:.1f}) rotate(90)">')
    p.text(0, 4, "+ YOURS", "mono", 11, "muted", "middle", ls=2)
    p.add("</g>")
    p.add(f'<rect x="0" y="{base}" width="{W}" height="2" class="line"/>')

    # popovers, like a hover card
    for i, s in enumerate(stops):
        name, note = SLOT_NOTE if s.get("slot") else (s["author"], s["note"])
        tw = max(M["mono"].width(name, 10.5, 1.8), M["text"].width(note, 15)) + 30
        cx = s["x"] + s["w"] / 2
        bx = min(max(cx - tw / 2, 0), W - tw)
        by = top_of(s) - 70
        p.add(f'<g class="pop" style="animation-delay:{i*step:.1f}s">'
              f'<g filter="url(#shadow)"><rect x="{bx:.1f}" y="{by:.1f}" width="{tw:.1f}" height="54" rx="12" '
              f'class="pop-bg" stroke-width="1"/></g>'
              f'<path d="M{cx-7:.1f},{by+53.5:.1f} L{cx:.1f},{by+61:.1f} L{cx+7:.1f},{by+53.5:.1f} Z" '
              f'class="pop-bg" stroke-width="0"/>')
        p.text(bx + 15, by + 22, name, "mono", 10.5, "accent", ls=1.8)
        p.text(bx + 15, by + 42, note, "text", 15, "ink")
        p.add("</g>")

    # the ghost cursor doing the hovering
    p.add('<g class="ghost"><path d="M0,0 L0,17 L4.6,12.8 L7.9,20 L11,18.6 L7.8,11.6 L13.6,11.6 Z" '
          'fill="#fff" stroke="#0d0d1f" stroke-width="1.3" stroke-linejoin="round"/></g>')
    p.text(0, base + 34, "auto-browsing  ·  click the shelf to recommend a book", "mono", 11.5, "muted", ls=0.6)
    return p


def stack():
    top, lh = 112, 34
    panel_h = 52 + len(STACK) * lh + 22
    p = Plate("stack", 1000, top + panel_h + 2,
              "Stack. " + "; ".join(f"{k}: {', '.join(v)}" for k, v in STACK))
    heading(p, "04", "STACK", "Tools I reach for.")
    p.add(f'<rect x=".5" y="{top + .5}" width="999" height="{panel_h}" rx="16" class="panel"/>',
          f'<rect x=".5" y="{top + .5}" width="999" height="{panel_h}" rx="16" class="s-line" stroke-width="1"/>')
    for i in range(3):
        p.add(f'<circle cx="{24 + i*16}" cy="{top + 24}" r="4.5" class="line"/>')
    p.text(500, top + 28.5, "stack.yml", "mono", 12, "muted", "middle")
    p.add(line(1, top + 48, 999, top + 48, "s-line", 1))
    keyw = max(M["mono"].width(k + ":", 14.5) for k, _ in STACK) + 22
    for i, (key, values) in enumerate(STACK):
        y = top + 80 + i * lh
        p.text(44, y, str(i + 1), "mono", 13, "muted", "end", attrs='opacity=".6"')
        runs = [("[", "muted")]
        for j, v in enumerate(values):
            if j:
                runs.append((", ", "muted"))
            runs.append((v, "ink"))
        runs.append(("]", "muted"))
        p.text(68, y, [(key, "accent"), (":", "muted")], "mono", 14.5)
        p.text(68 + keyw, y, runs, "mono", 14.5)
    return p


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
        data = json.load(resp)
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def activity(cal):
    weeks = [[(dt.date.fromisoformat(d["date"]), d["contributionCount"]) for d in w["contributionDays"]]
             for w in cal["weeks"]]
    days = [d for w in weeks for d in w]
    total = cal["totalContributions"]
    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    recent = days[-365:]
    active = sum(1 for _, n in recent if n)
    by_weekday = [0] * 7
    for d, n in days:
        by_weekday[d.weekday()] += n
    busiest = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"][
        by_weekday.index(max(by_weekday))]
    best_day, best_n = max(days, key=lambda d: d[1])
    ledger = [
        ("Longest streak", f"{longest} day" + ("" if longest == 1 else "s")),
        ("Days active", f"{active} of {len(recent)}"),
        ("Most active on", busiest),
        ("Best day", f"{best_n} on {best_day.day} {best_day:%b}"),
    ]
    p = Plate("activity", 1000, 400, f"{total:,} contributions in the past year. "
              + ". ".join(f"{a}: {b}" for a, b in ledger) + ".")
    heading(p, "05", "ACTIVITY", "Shipping, week by week.")

    p.text(-2, 186, f"{total:,}", "display", 64, "ink", ls=-2)
    p.text(0, 214, "contributions in the past year", "text", 16, "muted")
    for i, (label, value) in enumerate(ledger):
        y = 262 + i * 34
        p.add(line(0, y - 22, 260, y - 22, "s-line", 1))
        p.text(0, y, label, "text", 14.5, "muted")
        p.text(260, y, value, "title", 14.5, "ink", "end")

    left, right, bottom, top = 330, 1000, 360, 140
    sums = [sum(n for _, n in w) for w in weeks]
    peak = max(max(sums), 1)
    pitch = (right - left) / len(weeks)
    bw = pitch * 0.56
    peak_i = sums.index(peak)
    for i, (w, s) in enumerate(zip(weeks, sums)):
        x = left + i * pitch + (pitch - bw) / 2
        h = max((s / peak) * (bottom - top), 2)
        cls = "accent" if i in (peak_i, len(weeks) - 1) else "accent_dim"
        p.add(f'<rect x="{x:.2f}" y="{bottom - h:.2f}" width="{bw:.2f}" height="{h:.2f}" '
              f'rx="{min(bw/2, 2.5):.2f}" class="{cls}"/>')
        if any(d.day == 1 for d, _ in w) and i < len(weeks) - 2:
            month = next(d for d, _ in w if d.day == 1)
            p.text(x + bw / 2, bottom + 26, f"{month:%b}", "text", 12, "muted", "middle")
    px = left + peak_i * pitch + pitch / 2
    anchor = "end" if peak_i > len(weeks) * 0.7 else ("start" if peak_i < len(weeks) * 0.2 else "middle")
    p.text(px, top - 14, f"busiest week · {peak}", "mono", 11.5, "muted", anchor)
    return p


def footer():
    p = Plate("footer", 1000, 120, f"{QUOTE} ({QUOTE_BY.title()})")
    for i, ln in enumerate(wrap(QUOTE, "text", 19, 640)):
        p.text(500, 30 + i * 30, ln, "text", 19, "soft", "middle", ls=-0.2)
    p.text(500, 104, QUOTE_BY, "mono", 11.5, "muted", "middle", ls=2.4)
    return p


def link(slug, label):
    size, ls, pad = 12, 1.8, 20
    tw = M["mono"].width(label, size, ls)
    W = round(pad + tw + 10 + M["mono"].width("↗", 13) + pad)
    p = Plate(f"link-{slug}", W, 42, label.title())
    p.add(f'<rect x=".5" y=".5" width="{W-1}" height="41" rx="20.5" class="s-line" stroke-width="1"/>')
    p.text(pad, 25.5, label, "mono", size, "ink", ls=ls)
    p.text(W - pad, 26, "↗", "mono", 13, "accent", "end")
    return p


# --------------------------------------------------------------------------- main

def main():
    ensure_fonts()
    M.update({f: Metrics(f) for f in FACES})
    plates = []
    if sys.argv[1:] != ["activity"]:
        plates += [hero(), work(), section("research", "02", "RESEARCH", "Current research."),
                   shelf(), stack(), footer()]
        plates += [link(*l) for l in LINKS]
    cal = fetch_calendar()
    if cal:
        plates.append(activity(cal))
    else:
        print("no GITHUB_TOKEN set: activity plate skipped")
    for plate in plates:
        for theme in THEMES:
            out = HERE / f"{plate.name}-{theme}.svg"
            out.write_text(plate.svg(theme), encoding="utf-8")
        print(f"{plate.name:<14} {plate.w}x{plate.h}  {out.stat().st_size // 1024} KB")


M = {}

if __name__ == "__main__":
    main()

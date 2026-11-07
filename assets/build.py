#!/usr/bin/env python3
"""Typesets the SVG plates used by README.md: one copy for GitHub's light theme, one for dark.

    pip install fonttools brotli
    python3 assets/build.py

Every word on the plates lives in this file. Edit, rebuild, commit the SVGs.

The activity plate needs a GITHUB_TOKEN in the environment (the daily workflow
passes one; locally: GITHUB_TOKEN=$(gh auth token) python3 assets/build.py).
Without a token it is skipped and the existing activity SVGs stay as they are.
`python3 assets/build.py activity` rebuilds only that plate.

Fonts are EB Garamond and JetBrains Mono (both SIL Open Font License). They are
downloaded once into assets/.fontcache/, then subset to the glyphs each plate
uses and embedded, because an SVG shown through <img> cannot fetch web fonts.
"""

import base64
import datetime as dt
import io
import json
import math
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
    "serif": "https://github.com/google/fonts/raw/main/ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf",
    "italic": "https://github.com/google/fonts/raw/main/ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf",
    "mono": "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}

# Pale text on a dark page reads heavier, so the dark plates get slightly lighter weights.
WEIGHTS = {
    "light": {"serif": 460, "italic": 450, "mono": 430},
    "dark": {"serif": 420, "italic": 410, "mono": 400},
}

THEMES = {
    "light": {
        "page": "#ffffff", "plate": "#f6f1e7", "edge": "#e2dacb",
        "ink": "#1b1916", "soft": "#3f3b35", "muted": "#6b645a", "faint": "#d9d1c2",
        "rubric": "#b3301d", "gilt": "#a8843c",
        "spine_light": "#f4eddf", "spine_dark": "#2a2621",
        "spines": {
            "oxblood": "#8a3427", "slate": "#3d4b5d", "moss": "#58613f", "ochre": "#b08a3d",
            "bone": "#e8dfcb", "ink": "#2a2622", "plum": "#674257", "teal": "#3b5d58",
        },
    },
    "dark": {
        "page": "#0d1117", "plate": "#14120f", "edge": "#2c2925",
        "ink": "#ebe5d9", "soft": "#c9c2b5", "muted": "#8f887c", "faint": "#35322d",
        "rubric": "#ee6047", "gilt": "#c7a35e",
        "spine_light": "#ece4d3", "spine_dark": "#24201b",
        "spines": {
            "oxblood": "#6e2b22", "slate": "#2c3747", "moss": "#3e4530", "ochre": "#8c6b2e",
            "bone": "#d6ccb8", "ink": "#1d1b19", "plum": "#4b3041", "teal": "#29433f",
        },
    },
}

FAMILY = {"serif": "AH Serif", "italic": "AH Italic", "mono": "AH Mono"}


# --------------------------------------------------------------------------- fonts

def ensure_fonts():
    CACHE.mkdir(exist_ok=True)
    for face, url in FONT_URLS.items():
        path = CACHE / f"{face}.ttf"
        if not path.exists():
            print(f"downloading {face} ...")
            urllib.request.urlretrieve(url, path)


class Metrics:
    """Advance-width measuring, good enough for layout (kerning ignored)."""

    def __init__(self, face):
        font = TTFont(CACHE / f"{face}.ttf")
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


_static = {}


def embedded_font(face, theme, chars):
    key = (face, theme)
    if key not in _static:
        font = TTFont(CACHE / f"{face}.ttf")
        font = instancer.instantiateVariableFont(font, {"wght": WEIGHTS[theme][face]})
        buf = io.BytesIO()
        font.save(buf)
        _static[key] = buf.getvalue()
    font = TTFont(io.BytesIO(_static[key]))
    opts = subset.Options()
    opts.layout_features = ["kern", "liga", "clig", "calt"]
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

FACE_CLASS = {"serif": "serif", "italic": "italic", "mono": "mono"}


class Plate:
    """Collects markup plus the characters used per face, so fonts can be subset."""

    def __init__(self, name, w, h, label, css=""):
        self.name, self.w, self.h, self.label, self.css = name, w, h, label, css
        self.parts = []
        self.chars = {"serif": set(), "italic": set(), "mono": set()}

    def add(self, *markup):
        self.parts.extend(markup)

    def text(self, x, y, runs, face="serif", size=16, cls="ink", anchor="start",
             ls=0.0, attrs=""):
        """runs: a string, or a list of (text, colour_class[, face[, size]]) tuples."""
        if isinstance(runs, str):
            runs = [(runs, None)]
        spans = []
        for run in runs:
            s = run[0]
            colour = run[1] if len(run) > 1 else None
            rface = run[2] if len(run) > 2 else None
            rsize = f' font-size="{run[3]}"' if len(run) > 3 else ""
            self.chars[rface or face].update(s)
            classes = " ".join(c for c in (colour, FACE_CLASS[rface] if rface else None) if c)
            spans.append(f'<tspan class="{classes}"{rsize}>{escape(s)}</tspan>' if classes or rsize else escape(s))
        style = f' letter-spacing="{ls}"' if ls else ""
        anchor_attr = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" class="{FACE_CLASS[face]} {cls}" '
            f'font-size="{size}"{anchor_attr}{style} {attrs}>{"".join(spans)}</text>'
        )

    def svg(self, theme):
        t = THEMES[theme]
        faces = [f for f, cs in self.chars.items() if cs]
        font_css = "".join(
            f"@font-face{{font-family:'{FAMILY[f]}';"
            f"{'font-style:italic;' if f == 'italic' else ''}"
            f"src:url(data:font/woff2;base64,{embedded_font(f, theme, self.chars[f])}) format('woff2')}}"
            for f in faces
        )
        spine_css = "".join(
            f".sp-{k}{{fill:{v}}}" for k, v in t["spines"].items()
        )
        css = (
            font_css
            + "text{white-space:pre;font-kerning:normal;text-rendering:geometricPrecision}"
            + f".serif{{font-family:'{FAMILY['serif']}',Georgia,serif}}"
            + f".italic{{font-family:'{FAMILY['italic']}',Georgia,serif;font-style:italic}}"
            + f".mono{{font-family:'{FAMILY['mono']}',ui-monospace,Menlo,monospace}}"
            + f".ink{{fill:{t['ink']}}}.soft{{fill:{t['soft']}}}.muted{{fill:{t['muted']}}}"
            + f".rubric{{fill:{t['rubric']}}}.page{{fill:{t['page']}}}"
            + f".plate{{fill:{t['plate']};stroke:{t['edge']}}}"
            + f".frame{{fill:none;stroke:{t['edge']}}}"
            + f".l-ink{{stroke:{t['ink']};fill:none}}.l-soft{{stroke:{t['soft']};fill:none}}"
            + f".l-muted{{stroke:{t['muted']};fill:none}}.l-faint{{stroke:{t['faint']};fill:none}}"
            + f".l-rubric{{stroke:{t['rubric']};fill:none}}.l-gilt{{stroke:{t['gilt']};fill:none}}"
            + f".f-faint{{fill:{t['faint']}}}.f-muted{{fill:{t['muted']}}}.f-soft{{fill:{t['soft']}}}"
            + f".sp-text{{fill:{t['spine_light']}}}.sp-text-dark{{fill:{t['spine_dark']}}}"
            + spine_css
            + self.css
            + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.label)}">'
            f"<title>{escape(self.label)}</title><style><![CDATA[{css}]]></style>"
            + "".join(self.parts)
            + "</svg>\n"
        )


def line(x1, y1, x2, y2, cls="l-faint", w=1.0, extra=""):
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'class="{cls}" stroke-width="{w}" {extra}/>')


def wrap(text, face, size, width):
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if M[face].width(trial, size) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    return lines


def runs_width(runs, face, size, ls=0.0):
    return sum(M[r[2] if len(r) > 2 else face].width(r[0], size, ls) for r in runs)


# --------------------------------------------------------------------------- content

NAME_FIRST, NAME_LAST = "Ahmad", "Hassan"
ROLES = ["SOFTWARE ENGINEER", "GENERATIVE AI", "AGENTIC SYSTEMS", "FULL STACK"]
TAGLINE = [("I build systems that reason in ", "steps"), ("and read books that reason in ", "centuries")]

# Years are the usual "first published" dates: Crime and Punishment, War and Peace,
# Thus Spoke Zarathustra, The Metamorphosis, The Bell Jar.
TIMELINE = [  # (author, year, label position)
    ("Dostoevsky", 1866, "high"),
    ("Tolstoy", 1869, "below"),
    ("Nietzsche", 1883, "low"),
    ("Kafka", 1915, "high"),
    ("Plath", 1963, "low"),
]

BUILD = [
    ("Agents", "Multi-agent architectures that coordinate, reflect and remember, "
               "plus the production infrastructure that lets them run at scale."),
    ("Retrieval", "Embedding pipelines, vector search and hybrid RAG that find the one "
                  "passage that matters in an ocean of unstructured data."),
    ("Interfaces", "Full stack web apps that people actually want to use. "
                   "Yes, I also make the pretty buttons."),
]

TRANSLATIONS = [
    ("foreshadowing", "implicit prediction"),
    ("a motif", "a latent cluster"),
    ("an unreliable narrator", "a confident hallucination"),
    ("a payoff six hundred pages later", "a long-horizon dependency"),
    ("the world inside a novel", "a world model you can simulate"),
]

# (width, height, tone, author, what they taught) ; author None = an unnamed spine
SHELF = [
    (24, 168, "slate", None, None),
    (66, 226, "oxblood", "DOSTOEVSKY", "recursive psychology"),
    (20, 182, "bone", None, None),
    (30, 196, "teal", None, None),
    (58, 206, "ink", "KAFKA", "systems as absurdity"),
    (26, 174, "ochre", None, None),
    (80, 238, "moss", "TOLSTOY", "emergent complexity"),
    (22, 190, "plum", None, None),
    (32, 178, "slate", None, None),
    (64, 220, "ochre", "NIETZSCHE", "epistemological provocation"),
    (24, 196, "oxblood", None, None),
    (20, 170, "bone", None, None),
    (56, 210, "bone", "PLATH", "precision under pressure"),
    (28, 186, "teal", None, None),
    (36, 202, "ink", None, None),
]

TOOLS = [  # alphabetical, the way an index should be
    [("A", ["AWS"]), ("B", ["Bash"]), ("D", ["Django", "Docker"]), ("F", ["FastAPI", "Figma"])],
    [("G", ["Git", "GitHub Actions", "GraphQL"]), ("K", ["Kubernetes"]), ("L", ["Linux"]), ("M", ["MongoDB"])],
    [("N", ["Next.js", "Nginx", "Node.js"]), ("P", ["PostgreSQL", "PyTorch", "Python"])],
    [("R", ["React", "Redis"]), ("T", ["Tailwind CSS", "TensorFlow"]), ("U", ["Ubuntu"]), ("V", ["Vercel"])],
]

QUOTE = ["The question of whether a computer can think is no more interesting",
         "than the question of whether a submarine can swim."]
QUOTE_BY = "EDSGER W. DIJKSTRA"

LINKS = [("site", "AHMADHASSAN.ENGINEER"), ("linkedin", "LINKEDIN"), ("email", "EMAIL")]

CHAPTERS = [
    ("chapter-1", "CHAPTER I", "What I build"),
    ("chapter-2", "CHAPTER II", "Current research"),
    ("chapter-3", "CHAPTER III", "On literature & intelligence"),
    ("chapter-4", "BACK MATTER", "Index"),
    ("appendix", "APPENDIX", "Activity"),
]


# --------------------------------------------------------------------------- plates

def hero():
    W, H = 1000, 520
    css = """
.reader{animation:travel 10s cubic-bezier(.45,0,.25,1) infinite}
.trail{stroke-dasharray:668;animation:trail 10s cubic-bezier(.45,0,.25,1) infinite}
@keyframes travel{0%{transform:translateX(0);opacity:0}4%{opacity:1}62%{transform:translateX(668px);opacity:1}
 70%,100%{transform:translateX(668px);opacity:0}}
@keyframes trail{0%{stroke-dashoffset:668;opacity:.9}62%{stroke-dashoffset:0;opacity:.9}80%,100%{stroke-dashoffset:0;opacity:0}}
.step{opacity:0;animation:step 10s linear infinite}
@keyframes step{0%,62%{opacity:0}63.5%{opacity:1}72%,100%{opacity:0}}
.orbit{transform-origin:836px 206px;animation:spin 12s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.lit{opacity:0;animation:lit 12s linear infinite}
@keyframes lit{0%{opacity:1}12%,100%{opacity:0}}
.caret{animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
"""
    p = Plate("hero", W, H, "Ahmad Hassan. Software engineer: generative AI, agentic systems, "
              "full stack. I build systems that reason in steps and read books that reason in centuries.", css)
    p.add('<filter id="grain" x="0" y="0" width="100%" height="100%">'
          '<feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/>'
          '<feColorMatrix values="0 0 0 0 .5  0 0 0 0 .45  0 0 0 0 .4  0 0 0 .55 0"/></filter>')
    p.add(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" class="plate"/>',
          f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="10" filter="url(#grain)" opacity=".09"/>',
          f'<rect x="16.5" y="16.5" width="{W-33}" height="{H-33}" rx="5" class="frame" stroke-width="1"/>',
          f'<rect x="21.5" y="21.5" width="{W-43}" height="{H-43}" rx="3" class="frame" stroke-width=".6"/>')
    L, R = 56, W - 56

    # running head
    p.text(L, 64, [("Nº 30", "rubric"), ("   A WORKING DRAFT", "muted")], "mono", 12, ls=2.6)
    p.text(R, 64, "AGENTS · RETRIEVAL · INTERFACES", "mono", 12, "muted", "end", ls=2.6)
    p.add(line(L, 82, R, 82, "l-faint"))

    # name, with a rubricated initial
    p.text(L - 5, 198, [(NAME_FIRST[0], "rubric"), (NAME_FIRST[1:] + " ", "ink"), (NAME_LAST, "ink")],
           "serif", 112, ls=-1.2)

    roles = []
    for i, r in enumerate(ROLES):
        if i:
            roles.append(("  /  ", "rubric"))
        roles.append((r, "muted"))
    p.text(L, 240, roles, "mono", 12.5, ls=2.2)

    for i, (lead, key) in enumerate(TAGLINE):
        y = 302 + i * 36
        end = "." if i == len(TAGLINE) - 1 else ""
        p.text(L, y, [(lead, "ink"), (key, "rubric"), (end, "ink")], "italic", 29)
        if i == len(TAGLINE) - 1:
            cx = L + M["italic"].width(lead + key + end, 29) + 6
            p.add(f'<rect x="{cx:.1f}" y="{y-22}" width="2" height="27" class="rubric caret"/>')

    # fig. 1: the agent loop
    cx, cy, r = 836, 206, 70
    p.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" class="l-faint" stroke-width="1.2"/>',
          f'<circle cx="{cx}" cy="{cy}" r="34" class="l-faint" stroke-width="1" stroke-dasharray="2 4"/>')
    nodes = [("plan", 0), ("act", 90), ("observe", 180), ("reflect", 270)]
    for i, (label, deg) in enumerate(nodes):
        a = math.radians(deg)
        x, y = cx + r * math.sin(a), cy - r * math.cos(a)
        sx, sy = cx + 38 * math.sin(a), cy - 38 * math.cos(a)
        ex, ey = cx + (r - 9) * math.sin(a), cy - (r - 9) * math.cos(a)
        p.add(line(sx, sy, ex, ey, "l-faint", 1, 'stroke-dasharray="2 3"'),
              f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="plate l-soft" stroke-width="1.3"/>',
              f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="rubric lit" style="animation-delay:{i*3}s"/>')
        if deg == 0:
            p.text(x, y - 15, label, "mono", 12, "muted", "middle")
        elif deg == 90:
            p.text(x + 14, y + 4, label, "mono", 12, "muted")
        elif deg == 180:
            p.text(x, y + 25, label, "mono", 12, "muted", "middle")
        else:
            p.text(x - 14, y + 4, label, "mono", 12, "muted", "end")
    for deg in (45, 135, 225, 315):  # arrowheads, clockwise
        a = math.radians(deg)
        x, y = cx + r * math.sin(a), cy - r * math.cos(a)
        p.add(f'<path d="M-3.2,-3.6 L3.8,0 L-3.2,3.6 Z" class="f-muted" '
              f'transform="translate({x:.1f},{y:.1f}) rotate({deg})"/>')
    p.add(f'<g class="orbit"><circle cx="{cx}" cy="{cy-r}" r="3.4" class="rubric"/></g>')
    p.text(cx, cy + 6, "memory", "italic", 18, "ink", "middle")
    p.text(cx, cy + r + 56, "fig. 1 · a loop that remembers", "italic", 15, "muted", "middle")

    # the timeline: centuries on the left, steps on the right
    y0, x0, x1, y_start, y_end = 452, L, 724, 1860, 2026
    def X(year):
        return x0 + (year - y_start) / (y_end - y_start) * (x1 - x0)
    p.add(line(x0, y0, x1, y0, "l-muted", 1))
    for yr in range(y_start, y_end + 1, 10):
        big = yr % 50 == 0
        p.add(line(X(yr), y0 - (5 if big else 3), X(yr), y0 + (5 if big else 3), "l-muted", 1))
        if big:
            p.text(X(yr), y0 + 27, str(yr), "mono", 11, "muted", "middle")
    p.add(line(x0, y0, x1, y0, "l-rubric trail", 1.6))
    for author, yr, pos in TIMELINE:
        x = X(yr)
        if pos == "high":
            base, stem_top = y0 - 44, y0 - 58
        elif pos == "low":
            base, stem_top = y0 - 19, y0 - 33
        else:
            base, stem_top = y0 + 29, None
        if stem_top is not None:
            p.add(line(x, y0, x, stem_top, "l-faint", 1))
        else:
            p.add(line(x, y0, x, y0 + 30, "l-faint", 1))
        p.add(f'<circle cx="{x:.1f}" cy="{y0}" r="3" class="rubric"/>')
        p.text(x + 7, base, [(author, "soft"), (f"  {yr}", "muted", "mono", 11)], "italic", 17)
    # now
    p.add(line(x1, y0 - 9, x1, y0 + 9, "l-rubric", 1.6))
    p.text(x1, y0 + 27, "now", "mono", 11, "rubric", "middle")
    # the break, then steps
    for dx in (0, 5):
        p.add(line(733 + dx, y0 + 7, 739 + dx, y0 - 7, "l-muted", 1.2))
    p.add(line(752, y0, R, y0, "l-faint", 1))
    xs = [756 + i * 6.2 for i in range(31)]
    for i, x in enumerate(xs):
        p.add(line(x, y0 - 6, x, y0 + 6, "l-muted", 1.1),
              line(x, y0 - 6, x, y0 + 6, "l-rubric step", 1.6, f'style="animation-delay:{i*0.09:.2f}s"'))
    p.text(756, y0 - 19, "and then, in steps", "italic", 17, "soft")
    p.text(756, y0 + 27, "t = 0, 1, 2 … n", "mono", 11, "muted")
    p.add(f'<circle cx="{x0}" cy="{y0}" r="4.6" class="rubric reader"/>')
    return p


def chapter(name, label, title):
    p = Plate(name, 1000, 92, f"{label.title()}: {title}")
    p.text(0, 26, label, "mono", 12.5, "rubric", ls=3.2)
    p.text(-2, 76, title, "serif", 44, "ink", ls=-0.3)
    end = M["serif"].width(title, 44, -0.3) + 26
    p.add(line(end, 64, 1000, 64, "l-faint", 1))
    return p


def build_plate():
    css = """
.flow{stroke-dasharray:2 4;animation:flow 1.6s linear infinite}
@keyframes flow{to{stroke-dashoffset:-12}}
.hop{opacity:0;animation:hop 4.5s linear infinite}
@keyframes hop{0%,30%{opacity:1}34%,100%{opacity:0}}
.ping{transform-box:fill-box;transform-origin:center;animation:ping 3s ease-out infinite}
@keyframes ping{0%{transform:scale(.55);opacity:1}80%,100%{transform:scale(1.25);opacity:0}}
.press{transform-box:fill-box;transform-origin:center;animation:press 3.2s ease-in-out infinite}
@keyframes press{0%,58%,72%,100%{transform:scale(1)}64%{transform:scale(.9)}}
.cursor{animation:cursor 3.2s ease-in-out infinite}
@keyframes cursor{0%,10%{transform:translate(22px,16px);opacity:0}25%{opacity:1}
 58%,72%{transform:translate(0,0);opacity:1}92%,100%{transform:translate(22px,16px);opacity:0}}
"""
    p = Plate("build", 1000, 236, "What I build. Agents: " + BUILD[0][1] + " Retrieval: " + BUILD[1][1]
              + " Interfaces: " + BUILD[2][1], css)
    col_w, gap = 300, 50
    lefts = [0, col_w + gap, 2 * (col_w + gap)]
    for i, ((title, desc), left) in enumerate(zip(BUILD, lefts)):
        if i:
            p.add(line(left - gap / 2, 4, left - gap / 2, 228, "l-faint", 1))
        g = f'<g transform="translate({left},2)">'
        if i == 0:  # three agents passing messages
            pts = [(8, 50), (56, 50), (32, 10)]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                g += line(*pts[a], *pts[b], "l-muted flow", 1.3)
            for k, (x, y) in enumerate(pts):
                g += f'<circle cx="{x}" cy="{y}" r="6.5" class="page l-ink" stroke-width="1.4"/>'
                g += f'<circle cx="{x}" cy="{y}" r="6.5" class="rubric hop" style="animation-delay:{k*1.5}s"/>'
        elif i == 1:  # a query finding its nearest neighbours
            dots = [(4, 8), (16, 30), (9, 52), (24, 12), (29, 46), (44, 6), (56, 22), (50, 54),
                    (61, 40), (38, 58), (14, 18), (58, 8), (22, 58), (6, 38)]
            for x, y in dots:
                g += f'<circle cx="{x}" cy="{y}" r="2" class="f-muted"/>'
            g += '<circle cx="36" cy="30" r="17" class="l-rubric ping" stroke-width="1.2"/>'
            g += '<circle cx="36" cy="30" r="17" class="l-faint" stroke-width="1" stroke-dasharray="2 3"/>'
            g += line(36, 30, 29, 46, "l-rubric", 1) + line(36, 30, 44, 6, "l-rubric", 1) + line(36, 30, 24, 12, "l-rubric", 1)
            g += '<circle cx="36" cy="30" r="4" class="rubric"/>'
        else:  # a window with a very pretty button
            g += '<rect x="1" y="4" width="66" height="54" rx="6" class="l-ink" stroke-width="1.4"/>'
            g += line(1, 16, 67, 16, "l-ink", 1.2)
            for k in range(3):
                g += f'<circle cx="{8 + k*6}" cy="10" r="1.7" class="f-muted"/>'
            g += line(10, 27, 50, 27, "l-faint", 3.2, 'stroke-linecap="round"')
            g += line(10, 35, 38, 35, "l-faint", 3.2, 'stroke-linecap="round"')
            g += '<rect x="10" y="42" width="28" height="10" rx="5" class="rubric press"/>'
            g += ('<g class="cursor"><path d="M30,46 l0,12 l3.2,-3 l2.6,5.4 l2.2,-1 l-2.6,-5.2 l4.4,0 z" '
                  'class="page l-ink" stroke-width="1.1" stroke-linejoin="round"/></g>')
        p.add(g + "</g>")
        numeral = ["i.", "ii.", "iii."][i]
        p.text(left, 112, numeral, "mono", 13, "rubric")
        p.text(left + 44, 112, title, "serif", 34, "ink", ls=-0.2)
        for k, ln in enumerate(wrap(desc, "serif", 19, col_w)):
            p.text(left, 146 + k * 26, ln, "serif", 19, "soft")
    return p


def rosetta():
    css = """
.carry{animation:carry 4.2s cubic-bezier(.5,0,.3,1) infinite}
@keyframes carry{0%{transform:translateX(0);opacity:0}10%{opacity:1}70%{transform:translateX(84px);opacity:1}
 80%,100%{transform:translateX(84px);opacity:0}}
"""
    rows = len(TRANSLATIONS)
    top, step = 118, 60
    H = top + (rows - 1) * step + 128
    p = Plate("translation", 1000, H, "A translation table. " + "; ".join(
        f"{a} is {b}" for a, b in TRANSLATIONS) + ". Literature is compressed causal reasoning, stretched over time.", css)
    lx, rx = 440, 560
    p.text(lx, 34, "IN A NOVEL", "mono", 12.5, "muted", "end", ls=3)
    p.text(rx, 34, "IN A REASONING SYSTEM", "mono", 12.5, "muted", ls=3)
    p.text(500, 35, "↔", "mono", 15, "rubric", "middle")
    p.add(line(0, 56, 1000, 56, "l-faint", 1))
    for i, (a, b) in enumerate(TRANSLATIONS):
        y = top + i * step
        p.text(lx, y, a, "italic", 25, "ink", "end")
        p.text(rx, y, b, "serif", 25, "ink")
        cy = y - 8
        p.add(line(458, cy, 542, cy, "l-faint", 1),
              f'<circle cx="458" cy="{cy}" r="2.2" class="f-muted"/>',
              f'<circle cx="542" cy="{cy}" r="2.2" class="f-muted"/>',
              f'<circle cx="458" cy="{cy}" r="3.4" class="rubric carry" style="animation-delay:{i*0.45:.2f}s"/>')
    yb = top + (rows - 1) * step + 34
    p.add(line(0, yb, 1000, yb, "l-faint", 1))
    p.text(500, yb + 44, "Literature is compressed causal reasoning, stretched over time.", "italic", 24, "ink", "middle")
    p.text(500, yb + 76, "fig. 2 · a translation table", "italic", 15, "muted", "middle")
    return p


def shelf():
    css = """
.slip{transform-box:fill-box;transform-origin:50% 100%;animation:slip 5s ease-in-out infinite}
@keyframes slip{0%,100%{transform:rotate(-3deg)}50%{transform:rotate(4deg)}}
"""
    W, H, base = 1000, 330, 262
    p = Plate("shelf", W, H, "A bookshelf, in part: Dostoevsky (recursive psychology), Kafka (systems as "
              "absurdity), Tolstoy (emergent complexity), Nietzsche (epistemological provocation), "
              "Plath (precision under pressure), and an empty slot for your recommendation.", css)
    x = 30
    for k, (w, h, tone, author, note) in enumerate(SHELF):
        top = base - h
        g = f'<rect x="{x}" y="{top}" width="{w}" height="{h}" rx="1.5" class="sp-{tone} l-faint" stroke-width=".8"/>'
        g += f'<rect x="{x + w - 4}" y="{top}" width="4" height="{h}" fill="#000" opacity=".16"/>'
        g += f'<rect x="{x + 2}" y="{top}" width="1.4" height="{h}" fill="#fff" opacity=".07"/>'
        light_spine = tone == "bone"
        band = "l-gilt" if not light_spine else "l-muted"
        if author or k % 3 == 0:
            for by in (top + 14, top + 19, base - 19, base - 14):
                g += line(x + 3, by, x + w - 4, by, band, 0.9)
        p.add(g)
        if author:
            cx, cy = x + w / 2, top + h / 2
            text_cls = "sp-text-dark" if light_spine else "sp-text"
            p.add(f'<g transform="translate({cx:.1f},{cy:.1f}) rotate(90)">')
            if w >= 50:
                p.text(0, -3, author, "serif", 15, text_cls, "middle", ls=2.4)
                p.text(0, 13, note, "italic", 11.5, text_cls, "middle", attrs='opacity=".78"')
            else:
                p.text(0, 5, author, "serif", 15, text_cls, "middle", ls=2.4)
            p.add("</g>")
        if k == 8:  # a slip of paper marking a page
            p.add(f'<rect x="{x + 10}" y="{top - 16}" width="9" height="22" rx="1" class="rubric slip"/>')
        x += w + 3

    # one book leaning on the last, then an empty slot
    lw, lh = 30, 196
    lean_x = x + 34
    p.add(f'<g transform="rotate(-11 {lean_x + lw} {base})">'
          f'<rect x="{lean_x}" y="{base - lh}" width="{lw}" height="{lh}" rx="1.5" class="sp-plum l-faint" stroke-width=".8"/>'
          f'<rect x="{lean_x + lw - 4}" y="{base - lh}" width="4" height="{lh}" fill="#000" opacity=".16"/></g>')
    slot_x = lean_x + lw + 30
    p.add(f'<rect x="{slot_x}" y="{base - 206}" width="48" height="206" rx="2" class="l-muted" '
          f'stroke-width="1" stroke-dasharray="3 4"/>')
    p.add(f'<g transform="translate({slot_x + 24},{base - 103}) rotate(90)">')
    p.text(0, 5, "your recommendation?", "italic", 15, "muted", "middle")
    p.add("</g>")

    # a pile lying flat at the end
    sx = 836
    pile = [(sx - 6, 132, 18, "slate"), (sx + 6, 118, 22, "oxblood"), (sx - 2, 126, 15, "bone")]
    y = base
    for k, (px, pw, ph, tone) in enumerate(pile):
        y -= ph
        p.add(f'<rect x="{px}" y="{y}" width="{pw}" height="{ph}" rx="1.5" class="sp-{tone} l-faint" stroke-width=".8"/>',
              f'<rect x="{px}" y="{y + ph - 3}" width="{pw}" height="3" fill="#000" opacity=".14"/>')
    p.text(sx - 2 + 63, y + 11, "ARXIV, UNREAD", "mono", 8.5, "sp-text-dark", "middle", ls=1.6)

    p.add(f'<rect x="0" y="{base}" width="{W}" height="6" rx="1" class="f-faint"/>')
    p.add(line(10, base + 13, W - 10, base + 13, "l-faint", 1))
    p.text(500, H - 14, "fig. 3 · the shelf, in part. Recommendations welcome.", "italic", 15, "muted", "middle")
    return p


def index_plate():
    lh, top = 31, 30
    rows = max(sum(len(e) for _, e in col) for col in TOOLS)
    H = top + rows * lh + 50
    flat = ", ".join(t for col in TOOLS for _, entries in col for t in entries)
    p = Plate("index", 1000, H, "Index of tools: " + flat + ". See also: whatever the problem needs.")
    for c, col in enumerate(TOOLS):
        left = c * 250
        y = top
        for letter, entries in col:
            p.text(left, y, letter, "italic", 24, "rubric")
            for entry in entries:
                p.text(left + 32, y, entry, "serif", 21, "ink")
                y += lh
    yb = top + rows * lh - 6
    p.add(line(0, yb, 1000, yb, "l-faint", 1))
    p.text(1000, yb + 32, [("see also: ", "rubric"), ("whatever the problem needs.", "muted")],
           "italic", 18, anchor="end")
    return p


def colophon():
    p = Plate("colophon", 1000, 250, " ".join(QUOTE) + " (Edsger W. Dijkstra)")
    for dx, dy in ((-11, 8), (11, 8), (0, -10)):  # an asterism, drawn because the font lacks one
        p.text(500 + dx, 36 + dy, "*", "serif", 28, "rubric", "middle")
    for i, ln in enumerate(QUOTE):
        p.text(500, 92 + i * 38, ln, "italic", 29, "ink", "middle")
    p.text(500, 176, QUOTE_BY, "mono", 12, "muted", "middle", ls=3)
    p.add(line(440, 204, 560, 204, "l-faint", 1))
    p.text(500, 234, "Set in EB Garamond and JetBrains Mono. Rubrics in red, the way the scribes did it.",
           "italic", 15, "muted", "middle")
    return p


def link_plate(slug, label):
    size, ls, pad = 12.5, 2.4, 18
    tw = M["mono"].width(label, size, ls)
    aw = M["mono"].width("↗", 14)
    W = round(pad + tw + 8 + aw + pad)
    p = Plate(f"link-{slug}", W, 42, label.title())
    p.add(f'<rect x=".5" y=".5" width="{W-1}" height="41" rx="4" class="frame" stroke-width="1"/>')
    p.text(pad, 26, label, "mono", size, "ink", ls=ls)
    p.text(W - pad, 26.5, "↗", "mono", 14, "rubric", "end")
    return p


GITHUB_USER = "Ahmadhassan30"


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


def activity_plate(cal):
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

    def days_word(n):
        return f"{n} day" if n == 1 else f"{n} days"

    ledger = [
        ("LONGEST STREAK", days_word(longest)),
        ("DAYS ACTIVE", f"{active} of {len(recent)}"),
        ("MOST ACTIVE ON", busiest),
        ("BEST DAY", f"{best_n} on {best_day.day} {best_day:%b}"),
    ]
    p = Plate("activity", 1000, 292,
              f"{total:,} contributions in the past year. " + ". ".join(f"{a.title()}: {b}" for a, b in ledger) + ".")

    p.text(-3, 84, f"{total:,}", "serif", 84, "ink", ls=-1.5)
    p.text(0, 118, "contributions in the past year", "italic", 19, "soft")
    for i, (label, value) in enumerate(ledger):
        y = 170 + i * 31
        p.text(0, y, label, "mono", 11.5, "muted", ls=1.8)
        p.text(270, y, value, "italic", 19, "ink", "end")
        a = M["mono"].width(label, 11.5, 1.8) + 8
        b = 270 - M["italic"].width(value, 19) - 8
        p.add(line(a, y - 3.5, b, y - 3.5, "l-muted", 1.1, 'stroke-dasharray="0 5" stroke-linecap="round"'))

    left, right, base, top = 330, 1000, 248, 62
    sums = [sum(n for _, n in w) for w in weeks]
    peak = max(max(sums), 1)
    pitch = (right - left) / len(weeks)
    bw = pitch * 0.5
    peak_i = sums.index(peak)
    for i, (w, s) in enumerate(zip(weeks, sums)):
        x = left + i * pitch + (pitch - bw) / 2
        h = max((s / peak) * (base - top), 1.2)
        cls = "rubric" if i in (peak_i, len(weeks) - 1) else "f-muted"
        p.add(f'<rect x="{x:.2f}" y="{base - h:.2f}" width="{bw:.2f}" height="{h:.2f}" rx="{min(bw/2, 1.5):.2f}" '
              f'class="{cls}"/>')
        if any(d.day == 1 for d, _ in w) and i < len(weeks) - 2:
            month = next(d for d, _ in w if d.day == 1)
            p.text(x + bw / 2, base + 24, f"{month:%b}".upper(), "mono", 10.5, "muted", "middle", ls=1)
    p.add(line(left, base + 0.5, right, base + 0.5, "l-faint", 1))
    px = left + peak_i * pitch + pitch / 2
    p.text(px, top - 12, f"busiest week · {peak}", "italic", 15, "soft",
           "end" if peak_i > len(weeks) * 0.7 else ("start" if peak_i < len(weeks) * 0.2 else "middle"))
    p.text(right, 20, "fig. 4 · a year, week by week", "italic", 15, "muted", "end")
    return p


# --------------------------------------------------------------------------- main

def main():
    ensure_fonts()
    global M
    M = {f: Metrics(f) for f in FONT_URLS}
    only_activity = sys.argv[1:] == ["activity"]
    plates = []
    if not only_activity:
        plates += [hero(), build_plate(), rosetta(), shelf(), index_plate(), colophon()]
        plates += [chapter(*c) for c in CHAPTERS]
        plates += [link_plate(*l) for l in LINKS]
    cal = fetch_calendar()
    if cal:
        plates.append(activity_plate(cal))
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

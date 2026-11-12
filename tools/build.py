"""Build every image on the profile page (animated SVGs) and the README.

    python -I tools/build.py

Everything is drawn here and served from this repo, so the page never depends on a third-party
stats service being up. Fonts (Space Grotesk, JetBrains Mono, both OFL) are subset per image and
embedded; icons come from Simple Icons (CC0). The activity graphs are made by .github/workflows.
"""
import base64
import html
import io
import json
import math
import os
import re

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
ASSETS = os.path.join(ROOT, "assets")
os.makedirs(ASSETS, exist_ok=True)

USER = "allenwu-blip"
DEMO = "https://allenwu-blip.github.io/sparkle-demo/"

# ------------------------------------------------------------------ palette
BG0, BG1 = "#05070f", "#0a1020"
CARD = "#0b1222"
LINE = "#1d2742"
TEXT = "#e8edf8"
MUTED = "#8d99b8"
DIM = "#5b6788"
VIOLET, CYAN, PINK, LIME, AMBER = "#8b5cf6", "#22d3ee", "#f472b6", "#a3e635", "#fbbf24"

# ------------------------------------------------------------------ fonts
FONT_SRC = {
    "display": ("SpaceGrotesk.ttf", 700),
    "body": ("SpaceGrotesk.ttf", 500),
    "mono": ("JetBrainsMono.ttf", 500),
    "monob": ("JetBrainsMono.ttf", 700),
}
_static = {}


def static_font(key):
    """The variable font pinned to one weight, kept as bytes (re-loaded for each subset)."""
    if key not in _static:
        name, wght = FONT_SRC[key]
        f = instancer.instantiateVariableFont(TTFont(os.path.join(TOOLS, "fonts", name)), {"wght": wght})
        buf = io.BytesIO()
        f.save(buf)
        _static[key] = buf.getvalue()
    return _static[key]


_metrics = {}


def width(text, key, size):
    if key not in _metrics:
        f = TTFont(io.BytesIO(static_font(key)))
        _metrics[key] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
    cmap, hmtx, upm = _metrics[key]
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in text) * size / upm


def font_face(key, chars):
    f = TTFont(io.BytesIO(static_font(key)))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt"]
    s = subset.Subsetter(opts)
    s.populate(text="".join(sorted(set(chars))) + " ")
    s.subset(f)
    f.flavor = "woff2"
    buf = io.BytesIO()
    f.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:{key};src:url(data:font/woff2;base64,{b64}) format('woff2');}}"


def esc(s):
    return html.escape(s, quote=False)


class Svg:
    """Collects text per font so each image embeds only the glyphs it uses."""

    def __init__(self, w, h, title):
        self.w, self.h, self.title = w, h, title
        self.body = []
        self.defs = []
        self.css = []
        self.chars = {}
        self.n = 0

    def uid(self, p="i"):
        self.n += 1
        return f"{p}{self.n}"

    def add(self, s):
        self.body.append(s)

    def text(self, x, y, s, key, size, fill=TEXT, extra="", anchor="start"):
        self.chars.setdefault(key, set()).update(s)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        return f'<text x="{x:.1f}" y="{y:.1f}" font-family="{key}" font-size="{size}" fill="{fill}"{a} {extra}>{esc(s)}</text>'

    def tspans(self, x, y, parts, key, size, extra=""):
        """One line made of differently coloured pieces: [(text, colour), ...]."""
        out = []
        for s, col in parts:
            self.chars.setdefault(key, set()).update(s)
            out.append(f'<tspan fill="{col}">{esc(s)}</tspan>')
        return f'<text x="{x:.1f}" y="{y:.1f}" font-family="{key}" font-size="{size}" xml:space="preserve" {extra}>{"".join(out)}</text>'

    def save(self, name):
        faces = "".join(font_face(k, v) for k, v in self.chars.items())
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
               f'role="img" aria-label="{html.escape(self.title)}"><title>{esc(self.title)}</title>'
               f'<style>{faces}{"".join(self.css)}</style><defs>{"".join(self.defs)}</defs>{"".join(self.body)}</svg>')
        open(os.path.join(ASSETS, name), "w", encoding="utf-8").write(svg)
        print(f"  {name:<28} {len(svg) / 1024:6.1f} KB")


def frame(svg, r=22, glow=VIOLET):
    """Dark rounded panel with a slowly turning gradient rim."""
    g = svg.uid("rim")
    svg.defs.append(
        f'<linearGradient id="{g}" x1="0" y1="0" x2="1" y2="1" gradientUnits="objectBoundingBox">'
        f'<stop offset="0" stop-color="{glow}" stop-opacity=".75"/><stop offset=".35" stop-color="{LINE}"/>'
        f'<stop offset=".65" stop-color="{LINE}"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".6"/>'
        f'<animateTransform attributeName="gradientTransform" type="rotate" values="0 .5 .5;360 .5 .5" dur="14s" repeatCount="indefinite"/>'
        f"</linearGradient>")
    b = svg.uid("bg")
    svg.defs.append(f'<linearGradient id="{b}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG1}"/><stop offset="1" stop-color="{BG0}"/></linearGradient>')
    svg.add(f'<rect x="1" y="1" width="{svg.w - 2}" height="{svg.h - 2}" rx="{r}" fill="url(#{b})" stroke="url(#{g})" stroke-width="1.6"/>')


def dot_grid(svg, opacity=0.12, step=26):
    p, m, mg = svg.uid("dots"), svg.uid("fade"), svg.uid("fg")
    svg.defs.append(f'<pattern id="{p}" width="{step}" height="{step}" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.2" fill="#9fb0ff"/></pattern>')
    svg.defs.append(f'<radialGradient id="{mg}" cx=".5" cy=".45" r=".7"><stop offset="0" stop-color="#fff" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
                    f'<mask id="{m}"><rect width="{svg.w}" height="{svg.h}" fill="url(#{mg})"/></mask>')
    svg.add(f'<rect width="{svg.w}" height="{svg.h}" fill="url(#{p})" opacity="{opacity}" mask="url(#{m})"/>')


def discrete(attr, times, values, T):
    """SMIL step animation over one T-second loop: values[i] from times[i] on."""
    kt = ";".join(f"{min(1, t / T):.5f}" for t in times)
    vs = ";".join(f"{v:.2f}" if isinstance(v, float) else str(v) for v in values)
    return f'<animate attributeName="{attr}" values="{vs}" keyTimes="{kt}" dur="{T}s" calcMode="discrete" repeatCount="indefinite"/>'


def check(x, y, s=14, col=LIME):
    return f'<path d="M{x} {y - s * .45} l{s * .35} {s * .38} l{s * .62} {-s * .72}" fill="none" stroke="{col}" stroke-width="{s * .17:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'


# ================================================================== HERO
def hero():
    W, H = 1280, 440
    s = Svg(W, H, "Allen Wu: CS + Movement Science at the University of Michigan. AI agent tooling, LLM systems, robotics data, apps.")
    frame(s, 26)
    # aurora
    for i, (cx, cy, r, col, dx, dy, dur) in enumerate([(300, 120, 340, VIOLET, 160, 60, 17), (980, 330, 320, CYAN, -150, -50, 21), (720, 40, 260, PINK, 90, 70, 19)]):
        g = s.uid("au")
        s.defs.append(f'<radialGradient id="{g}"><stop offset="0" stop-color="{col}" stop-opacity=".30"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>')
        s.css.append(f"@keyframes drift{i}{{50%{{transform:translate({dx}px,{dy}px) scale(1.15)}}}}.au{i}{{animation:drift{i} {dur}s ease-in-out infinite;transform-box:fill-box;transform-origin:center}}")
        s.add(f'<circle class="au{i}" cx="{cx}" cy="{cy}" r="{r}" fill="url(#{g})"/>')
    dot_grid(s, 0.10)
    # scan line
    sg = s.uid("scan")
    s.defs.append(f'<linearGradient id="{sg}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset=".5" stop-color="{CYAN}" stop-opacity=".10"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>')
    s.add(f'<rect x="2" y="-60" width="{W - 4}" height="60" fill="url(#{sg})"><animate attributeName="y" values="-60;{H}" dur="7s" repeatCount="indefinite"/></rect>')

    # ---- right: orbit system
    cx, cy = 1040, 220
    s.css.append("@keyframes pulse{0%{r:34;opacity:.55}100%{r:96;opacity:0}}.pulse{animation:pulse 3s ease-out infinite}"
                 ".pulse2{animation-delay:1.5s}@keyframes spin{to{transform:rotate(360deg)}}"
                 f".spin{{animation:spin 18s linear infinite;transform-origin:{cx}px {cy}px}}.spinr{{animation:spin 26s linear infinite reverse;transform-origin:{cx}px {cy}px}}")
    core = s.uid("core")
    s.defs.append(f'<radialGradient id="{core}"><stop offset="0" stop-color="#fff"/><stop offset=".35" stop-color="{CYAN}"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>')
    for k in ("pulse", "pulse pulse2"):
        s.add(f'<circle class="{k}" cx="{cx}" cy="{cy}" r="34" fill="none" stroke="{CYAN}" stroke-width="1.5"/>')
    orbits = [(170, 64, -18, VIOLET, 7.5), (150, 52, 40, CYAN, 5.5), (182, 40, 95, PINK, 9.5)]
    for i, (rx, ry, rot, col, dur) in enumerate(orbits):
        pid = s.uid("orb")
        d = f"M{cx - rx},{cy} a{rx},{ry} 0 1,0 {2 * rx},0 a{rx},{ry} 0 1,0 {-2 * rx},0"
        s.defs.append(f'<path id="{pid}" d="{d}"/>')
        s.add(f'<g transform="rotate({rot} {cx} {cy})">'
              f'<use href="#{pid}" fill="none" stroke="{col}" stroke-opacity=".22" stroke-width="1.3"/>'
              f'<use href="#{pid}" fill="none" stroke="{col}" stroke-width="2.4" stroke-linecap="round" stroke-dasharray="60 {int(2 * math.pi * rx)}" opacity=".9">'
              f'<animate attributeName="stroke-dashoffset" values="0;-{int(2 * math.pi * (rx + ry) / 2 * 1.02)}" dur="{dur}s" repeatCount="indefinite"/></use>'
              f'<circle r="6.5" fill="{col}"><animateMotion dur="{dur}s" repeatCount="indefinite" rotate="auto"><mpath href="#{pid}"/></animateMotion></circle>'
              f'<circle r="15" fill="{col}" opacity=".18"><animateMotion dur="{dur}s" repeatCount="indefinite"><mpath href="#{pid}"/></animateMotion></circle>'
              f"</g>")
    s.add(f'<circle cx="{cx}" cy="{cy}" r="58" fill="url(#{core})" opacity=".55"/>')
    s.add(f'<circle cx="{cx}" cy="{cy}" r="31" fill="{BG0}" stroke="{CYAN}" stroke-width="2"/>')
    s.add(f'<g class="spin"><circle cx="{cx}" cy="{cy}" r="42" fill="none" stroke="{VIOLET}" stroke-width="2" stroke-dasharray="6 10"/></g>')
    s.add(s.text(cx, cy + 9, "AW", "display", 26, TEXT, anchor="middle"))
    # tiny labels riding an outer ring (they stay upright)
    labels = [("agents", VIOLET), ("serving", CYAN), ("robotics", LIME), ("apps", PINK)]
    ring = s.uid("ring")
    s.defs.append(f'<path id="{ring}" d="M{cx + 200},{cy} a200,158 0 1,1 -400,0 a200,158 0 1,1 400,0"/>')
    for i, (lab, col) in enumerate(labels):
        wv = width(lab, "mono", 14) + 18
        s.add(f'<g><rect x="{-wv / 2:.1f}" y="-13" width="{wv:.1f}" height="26" rx="13" fill="{BG0}" stroke="{col}" stroke-opacity=".7"/>'
              + s.text(0, 5, lab, "mono", 14, col, anchor="middle")
              + f'<animateMotion dur="32s" begin="{-i * 8}s" repeatCount="indefinite"><mpath href="#{ring}"/></animateMotion></g>')

    # ---- left: text
    X = 72
    s.css.append("@keyframes blink{50%{opacity:0}}.blink{animation:blink 1.1s steps(1) infinite}"
                 "@keyframes live{0%,100%{opacity:1}50%{opacity:.35}}.live{animation:live 2s ease-in-out infinite}")
    s.add(f'<circle class="live" cx="{X + 6}" cy="96" r="6" fill="{LIME}"/><circle cx="{X + 6}" cy="96" r="11" fill="{LIME}" opacity=".18" class="live"/>')
    s.add(s.tspans(X + 22, 101, [("~/", DIM), ("allen-wu", MUTED), ("  ·  ", DIM), ("shipping from Ann Arbor, MI", MUTED)], "mono", 17))
    ng = s.uid("name")
    s.defs.append(f'<linearGradient id="{ng}" x1="0" y1="0" x2="600" y2="0" gradientUnits="userSpaceOnUse" spreadMethod="reflect">'
                  f'<stop offset="0" stop-color="#ffffff"/><stop offset=".35" stop-color="#c4b5fd"/><stop offset=".7" stop-color="{CYAN}"/><stop offset="1" stop-color="#f9a8d4"/>'
                  f'<animateTransform attributeName="gradientTransform" type="translate" values="0 0;600 0" dur="6s" repeatCount="indefinite"/></linearGradient>')
    glow = s.uid("glow")
    s.defs.append(f'<filter id="{glow}" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>')
    s.add(f'<g opacity=".55" filter="url(#{glow})">' + s.text(X - 4, 205, "Allen Wu", "display", 104, VIOLET) + "</g>")
    s.add(s.text(X - 4, 205, "Allen Wu", "display", 104, f"url(#{ng})"))

    # typed, rotating focus lines
    phrases = ["building safety rails for AI coding agents", "benchmarking LLM inference and KV-cache serving",
               "converting robotics datasets at scale", "shipping apps kids actually want to open"]
    size, y = 25, 262
    px = X + width("> ", "mono", size)
    s.add(s.text(X, y, ">", "monob", size, CYAN))
    cps, hold, ecps, gap = 26, 2.6, 70, 0.35
    slots, t = [], 0.4
    for p in phrases:
        n = len(p)
        slots.append((t, n))
        t += n / cps + hold + n / ecps + gap
    T = round(t, 2)
    cur_t, cur_x = [0.0], [px]
    cw = width("a", "mono", size)
    for (start, n), p in zip(slots, phrases):
        cid = s.uid("clip")
        times, vals = [0.0], [0.0]
        for k in range(1, n + 1):
            times.append(start + k / cps)
            vals.append(k * cw)
        e0 = start + n / cps + hold
        for k in range(1, n + 1):
            times.append(e0 + k / ecps)
            vals.append((n - k) * cw)
        for tt, vv in zip(times[1:], vals[1:]):
            cur_t.append(tt)
            cur_x.append(px + vv)
        s.defs.append(f'<clipPath id="{cid}"><rect x="{px:.1f}" y="{y - size}" width="0" height="{size * 1.5}">{discrete("width", times, vals, T)}</rect></clipPath>')
        s.add(f'<g clip-path="url(#{cid})">' + s.text(px, y, p, "mono", size, TEXT) + "</g>")
    s.add(f'<rect class="blink" x="{px:.1f}" y="{y - size + 3}" width="{cw * .55:.1f}" height="{size + 2}" fill="{CYAN}">{discrete("x", cur_t, cur_x, T)}</rect>')

    # chips
    chips = [("CS + Movement Science", TEXT), ("University of Michigan", AMBER), ("AI agent tooling", VIOLET), ("LLM systems", CYAN), ("robotics data", LIME), ("iOS + web apps", PINK)]
    cx0, cy0, size = X, 318, 16
    for i, (c, col) in enumerate(chips):
        w = width(c, "mono", size) + 30
        if cx0 + w > 820:
            cx0, cy0 = X, cy0 + 46
        s.add(f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{0.3 + i * 0.12:.2f}s" dur=".6s" fill="freeze"/>'
              f'<rect x="{cx0}" y="{cy0}" width="{w:.1f}" height="34" rx="17" fill="{col}" fill-opacity=".08" stroke="{col}" stroke-opacity=".45"/>'
              + s.text(cx0 + 15, cy0 + 22.5, c, "mono", size, col) + "</g>")
        cx0 += w + 10
    s.save("hero.svg")


# ================================================================== TERMINAL
def terminal():
    W, H = 1280, 470
    s = Svg(W, H, "Terminal: whoami, now, focus areas, and an mcpaudit scan")
    frame(s, 18, CYAN)
    s.add(f'<rect x="1" y="1" width="{W - 2}" height="48" rx="18" fill="#0e1528"/><rect x="1" y="30" width="{W - 2}" height="20" fill="#0e1528"/>'
          f'<line x1="1" y1="49" x2="{W - 1}" y2="49" stroke="{LINE}"/>')
    for i, col in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        s.add(f'<circle cx="{30 + i * 24}" cy="25" r="7" fill="{col}"/>')
    s.add(s.text(W / 2, 31, "allen@umich: ~ (zsh)", "mono", 16, DIM, anchor="middle"))
    size, lh, X, Y0 = 22, 40, 40, 100
    cw = width("a", "mono", size)
    prompt = [("allen", LIME), ("@umich ", MUTED), ("~ ", CYAN), ("❯ ", VIOLET)]
    pw = width("".join(p for p, _ in prompt), "mono", size)
    script = [
        ("whoami", [[("Allen Wu", TEXT), (" · CS + Movement Science @ University of Michigan", MUTED)]]),
        ("cat now.md", [[("shipping ", MUTED), ("Sparkle", PINK), (" for Tech Jam 2026: a 3D toothbrushing buddy for kids", MUTED)]]),
        ("ls ~/work", [[("agent-safety/   ", VIOLET), ("llm-serving/   ", CYAN), ("robotics-data/   ", LIME), ("apps/", PINK)]]),
        ("npx mcpaudit ./my-mcp-server", [[("  command injection   ", MUTED), ("  env exfiltration   ", MUTED), ("  fs scope   ", MUTED), ("  dynamic eval", MUTED)]]),
    ]
    T, t, line = 0.0, 0.8, 0
    cps = 17
    events = []  # (time, x, y) for the cursor
    content = []
    for cmd, outs in script:
        y = Y0 + line * lh
        content.append(("prompt", y, 0.0 if line == 0 else t - 0.05))
        events.append((t - 0.4 if line else 0.0, X + pw, y))
        start = t + 0.5
        cid = s.uid("tc")
        times, vals = [0.0], [0.0]
        for k in range(1, len(cmd) + 1):
            times.append(start + k / cps)
            vals.append(k * cw)
            events.append((start + k / cps, X + pw + k * cw, y))
        content.append(("cmd", y, cmd, cid, times, vals))
        t = start + len(cmd) / cps + 0.35
        line += 1
        for o in outs:
            content.append(("out", Y0 + line * lh, o, t))
            line += 1
        t += 0.55
    yl = Y0 + line * lh
    content.append(("prompt", yl, t - 0.05))
    events.append((t, X + pw, yl))
    T = round(t + 6.0, 2)
    end = T - 0.7
    for item in content:
        if item[0] == "prompt":
            _, y, at = item
            g = s.tspans(X, y, prompt, "mono", size)
            s.add(f'<g opacity="{1 if at <= 0 else 0}">{discrete("opacity", [0.0, max(0.0, at), end], [1 if at <= 0 else 0, 1, 0], T)}{g}</g>')
        elif item[0] == "cmd":
            _, y, cmd, cid, times, vals = item
            times, vals = times + [end], vals + [0.0]
            s.defs.append(f'<clipPath id="{cid}"><rect x="{X + pw:.1f}" y="{y - size}" width="0" height="{size * 1.6}">{discrete("width", times, vals, T)}</rect></clipPath>')
            s.add(f'<g clip-path="url(#{cid})">' + s.text(X + pw, y, cmd, "mono", size, TEXT) + "</g>")
        else:
            _, y, parts, at = item
            inner = s.tspans(X, y, parts, "mono", size)
            if parts[0][0].startswith("  command"):  # draw the mcpaudit check marks
                xx = X
                marks = []
                for p, _ in parts:
                    marks.append(check(xx + 4, y - 7, 15))
                    xx += width(p, "mono", size)
                inner += "".join(marks)
            s.add(f'<g opacity="0">{discrete("opacity", [0.0, at, end], [0, 1, 0], T)}{inner}</g>')
    ts = [e[0] for e in events] + [end]
    xs = [e[1] for e in events] + [X + pw]
    ys = [e[2] - size + 4 for e in events] + [Y0 - size + 4]
    s.css.append("@keyframes blink{50%{opacity:0}}.blink{animation:blink 1s steps(1) infinite}")
    s.add(f'<rect class="blink" x="{X + pw:.1f}" y="{Y0 - size + 4}" width="{cw * .6:.1f}" height="{size + 3}" fill="{CYAN}">'
          f'{discrete("x", ts, xs, T)}{discrete("y", ts, ys, T)}</rect>')
    s.save("terminal.svg")


# ================================================================== SECTION HEADERS
def header(name, num, title, sub, col):
    W, H = 1280, 112
    s = Svg(W, H, title)
    b = s.uid("hb")  # its own dark panel, so it reads on GitHub's light theme too
    s.defs.append(f'<linearGradient id="{b}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BG1}"/><stop offset="1" stop-color="{BG0}"/></linearGradient>')
    s.add(f'<rect x="0" y="6" width="{W}" height="{H - 12}" rx="18" fill="url(#{b})"/>')
    g = s.uid("hg")
    s.defs.append(f'<linearGradient id="{g}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{col}"/><stop offset=".5" stop-color="{col}" stop-opacity=".25"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient>')
    sh = s.uid("sh")
    s.defs.append(f'<linearGradient id="{sh}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    s.add(s.text(30, 52, num, "monob", 18, col))
    s.add(s.text(76, 62, title, "display", 42, TEXT))
    tw = width(title, "display", 42)
    s.add(s.text(90 + tw, 61, sub, "mono", 18, MUTED))
    s.add(f'<rect x="30" y="80" width="{W - 60}" height="2.5" rx="1.2" fill="url(#{g})"/>')
    s.add(f'<rect x="-200" y="79" width="200" height="4.5" rx="2" fill="url(#{sh})" opacity=".8"><animate attributeName="x" values="-200;{W}" dur="3.6s" repeatCount="indefinite"/></rect>')
    s.save(name)


# ================================================================== SPARKLE STRIP
def sparkle_strip():
    W, H = 1280, 300
    s = Svg(W, H, "Sparkle: a 3D toothbrushing buddy for kids. Try the live demo.")
    frame(s, 22, PINK)
    s.add(s.text(48, 64, "FEATURED · TECH JAM 2026", "monob", 16, AMBER, 'letter-spacing="2"'))
    pg = s.uid("pg")
    s.defs.append(f'<linearGradient id="{pg}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f9a8d4"/><stop offset="1" stop-color="#c4b5fd"/></linearGradient>')
    s.add(s.text(46, 128, "Sparkle", "display", 64, f"url(#{pg})"))
    sw = width("Sparkle", "display", 64)
    star = "M0 -10 C1.2 -3 3 -1.2 10 0 C3 1.2 1.2 3 0 10 C-1.2 3 -3 1.2 -10 0 C-3 -1.2 -1.2 -3 0 -10Z"
    s.css.append("@keyframes tw{0%,100%{opacity:.2;transform:scale(.6)}50%{opacity:1;transform:scale(1)}}.tw{animation:tw 2.4s ease-in-out infinite;transform-box:fill-box;transform-origin:center}")
    for i, (dx, dy, k, col) in enumerate([(14, -46, 1.1, AMBER), (38, -20, .7, "#f9a8d4"), (24, 2, .5, "#c4b5fd")]):
        s.add(f'<g transform="translate({46 + sw + dx:.0f} {128 + dy}) scale({k})"><path class="tw" style="animation-delay:{-i * .8:.1f}s" d="{star}" fill="{col}"/></g>')
    s.add(s.text(48, 172, "A fairy who brushes along with kids: five zones on live 3D teeth, sugar bugs that pop,", "body", 22, TEXT))
    s.add(s.text(48, 204, "a letter from Sparkle after every brush, and a parent view behind a PIN.", "body", 22, TEXT))
    tags = [("React + TypeScript PWA", CYAN), ("three.js 3D teeth", VIOLET), ("ElevenLabs voice + lip-sync", PINK), ("Suno theme song", AMBER), ("tsc → vitest → Playwright → Pages", LIME)]
    x, y = 48, 236
    for t, col in tags:
        w = width(t, "mono", 15) + 26
        s.add(f'<rect x="{x}" y="{y}" width="{w:.1f}" height="30" rx="15" fill="{col}" fill-opacity=".08" stroke="{col}" stroke-opacity=".45"/>' + s.text(x + 13, y + 20, t, "mono", 15, col))
        x += w + 10
    # play button
    bx, by, bw, bh = 1000, 100, 232, 64
    bg = s.uid("btn")
    s.defs.append(f'<linearGradient id="{bg}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PINK}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient>')
    s.css.append("@keyframes ring{0%{opacity:.6;transform:scale(1)}100%{opacity:0;transform:scale(1.25)}}.ring{animation:ring 2.2s ease-out infinite;transform-box:fill-box;transform-origin:center}")
    s.add(f'<rect class="ring" x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="32" fill="none" stroke="{PINK}" stroke-width="2"/>')
    s.add(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="32" fill="url(#{bg})"/>')
    s.add(f'<path d="M{bx + 34} {by + 20} l18 12 l-18 12z" fill="#fff"/>')
    s.add(s.text(bx + 64, by + 40, "Try the live demo", "display", 21, "#fff"))
    s.add(s.text(bx + bw / 2, by + bh + 32, "parent PIN 1234", "mono", 15, MUTED, anchor="middle"))
    s.save("sparkle.svg")


# ================================================================== PROJECT CARDS
CATS = {"tool": ("AGENT TOOLING", VIOLET), "research": ("RESEARCH", CYAN), "data": ("ML DATA INFRA", LIME), "app": ("APPS", PINK)}
LANG = {"JavaScript": "#f1e05a", "Python": "#3572A5", "Swift": "#F05138", "TypeScript": "#3178c6"}
PROJECTS = [
    ("mcpaudit", "tool", "JavaScript", "npx mcpaudit", "Pre-install security scanner for MCP servers: command injection, env exfiltration, over-broad scope, eval."),
    ("agentguard", "tool", "JavaScript", "CLI · ESLint · Action", "AST linter that flags unguarded shell, filesystem, network and eval sinks in AI-agent tool calls."),
    ("aclaim", "tool", "JavaScript", "CI oracle", "Re-runs an AI coding agent's claims (tests pass, build green, files touched) and emits a pass/fail receipt."),
    ("spendguard", "tool", "JavaScript", "local proxy", "Hard-caps an AI coding agent's token spend per project. Never logs keys or prompt bodies."),
    ("tokenstack", "tool", "JavaScript", "Claude Code", "Per-layer token attribution for Claude Code: by MCP server, subagent, skill and tool family."),
    ("slopguard", "tool", "Python", "web · CLI · skill", "Catch AI slop before it ships: in-browser detector and de-slopper, Python CLI, Claude Code skill."),
    ("agenttoolbench-code", "research", "Python", "benchmark", "Benchmarking silent security failures in AI coding agents, with prompt-sentry for config edits."),
    ("llm-inference-lab", "research", "Python", "Metal → CUDA", "Reproducible LLM inference benchmarking: quantization sweeps with honest per-process measurement."),
    ("agentic-serving-lab", "research", "Python", "KV cache", "Research harness: does agentic tool-pausing waste KV cache in LLM serving?"),
    ("ai-evaluator", "research", "Python", "private · 300+ tests", "LLM emits structured parameters into deterministic population and discrete-choice models."),
    ("embodied-data", "data", "Python", "on PyPI", "Converter and validator for embodied-AI datasets: AgiBot World ↔ LeRobot v3 and more."),
    ("agibridge", "data", "Python", "SaaS", "Multi-tenant ML data-infra SaaS on embodied-data: FastAPI, React, Postgres, R2, Stripe, Clerk."),
    ("matchday-passport", "app", "Swift", "iOS", "A pocket passport for football fans: stamp every match you attend. iOS app and site."),
    ("huidu", "app", "JavaScript", "browser-only","Brings back the lines you highlighted in WeChat Read, a few each day. Data stays in your browser."),
]


def wrap(text, key, size, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if width(t, key, size) > maxw and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur]


def card(i, name, cat, lang, tag, desc):
    W, H = 600, 210
    label, col = CATS[cat]
    s = Svg(W, H, f"{name}: {desc}")
    frame(s, 18, col)
    # glint
    gl = s.uid("gl")
    s.defs.append(f'<linearGradient id="{gl}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{col}" stop-opacity="0"/><stop offset=".5" stop-color="{col}" stop-opacity=".9"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient>')
    s.add(f'<rect x="-160" y="1" width="160" height="2" fill="url(#{gl})"><animate attributeName="x" values="-160;{W}" dur="4.5s" begin="{-i * 0.7:.1f}s" repeatCount="indefinite"/></rect>')
    s.add(f'<rect x="28" y="28" width="{width(label, "monob", 13) + 22:.1f}" height="24" rx="12" fill="{col}" fill-opacity=".12"/>' + s.text(39, 45, label, "monob", 13, col, 'letter-spacing="1.2"'))
    tagw = width(tag, "mono", 14)
    s.add(s.text(W - 28, 45, tag, "mono", 14, MUTED, anchor="end"))
    s.add(s.text(28, 96, name, "display", 32, TEXT))
    s.add(s.text(28 + width(name, "display", 32) + 12, 94, "↗", "display", 24, col))
    for k, ln in enumerate(wrap(desc, "body", 18.5, W - 56)[:2]):
        s.add(s.text(28, 132 + k * 26, ln, "body", 18.5, "#b8c3dc"))
    s.add(f'<circle cx="36" cy="{H - 26}" r="6" fill="{LANG.get(lang, MUTED)}"/>' + s.text(50, H - 21, lang, "mono", 14, MUTED))
    s.save(f"card-{name}.svg")
    return tagw


# ================================================================== STACK MARQUEE
STACK = [
    [("python", "Python"), ("typescript", "TypeScript"), ("javascript", "JavaScript"), ("swift", "Swift"), ("cplusplus", "C++"), ("react", "React"),
     ("threedotjs", "three.js"), ("nodedotjs", "Node.js"), ("vite", "Vite"), ("vitest", "Vitest"), ("fastapi", "FastAPI"), ("postgresql", "Postgres"), ("apple", "iOS")],
    [("pytorch", "PyTorch"), ("huggingface", "Hugging Face"), ("nvidia", "CUDA"), ("anthropic", "Anthropic"), ("claude", "Claude Code"), ("docker", "Docker"),
     ("githubactions", "GitHub Actions"), ("cloudflare", "Cloudflare R2"), ("stripe", "Stripe"), ("clerk", "Clerk"), ("linux", "Linux / Slurm"), ("blender", "Blender"),
     ("unity", "Unity"), ("godotengine", "Godot"), ("ffmpeg", "FFmpeg")],
]


def brand():
    p = os.path.join(TOOLS, "icons", "colors.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def lum(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def stack():
    W, H = 1280, 236
    s = Svg(W, H, "Toolbox: " + ", ".join(n for row in STACK for _, n in row))
    frame(s, 22, VIOLET)
    colors = brand()
    fm, fg = s.uid("edge"), s.uid("eg")
    s.defs.append(f'<linearGradient id="{fg}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".08" stop-color="#fff"/><stop offset=".92" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
                  f'<mask id="{fm}"><rect width="{W}" height="{H}" fill="url(#{fg})"/></mask>')
    s.add(f'<g mask="url(#{fm})">')
    for r, row in enumerate(STACK):
        y = 40 + r * 92
        chips, x = [], 0
        for slug, label in row:
            svg = open(os.path.join(TOOLS, "icons", slug + ".svg"), encoding="utf-8").read()
            path = re.search(r'<path d="([^"]+)"', svg).group(1)
            c = "#" + colors.get(slug, "ffffff")
            if lum(c[1:]) < 0.2:
                c = "#e8edf8"
            elif lum(c[1:]) < 0.5:  # lift dark brand colours so they read on the dark chip
                rgb = [int(c[k:k + 2], 16) for k in (1, 3, 5)]
                c = "#" + "".join(f"{int(v + (255 - v) * .38):02x}" for v in rgb)
            w = width(label, "body", 19) + 76
            chips.append(f'<g transform="translate({x:.1f} 0)"><rect width="{w:.1f}" height="60" rx="16" fill="#0e1629" stroke="{LINE}"/>'
                         f'<g transform="translate(18 18) scale(1)"><path d="{path}" fill="{c}"/></g>' + s.text(54, 37, label, "body", 19, TEXT) + "</g>")
            x += w + 14
        total = x
        dur = total / 38
        name = f"mq{r}"
        dirn = "" if r == 0 else " reverse"
        s.css.append(f"@keyframes {name}{{to{{transform:translateX(-{total:.1f}px)}}}}.{name}{{animation:{name} {dur:.1f}s linear infinite{dirn}}}")
        s.add(f'<g transform="translate(0 {y})"><g class="{name}">{"".join(chips)}<g transform="translate({total:.1f} 0)">{"".join(chips)}</g></g></g>')
    s.add("</g>")
    s.save("stack.svg")


# ================================================================== FOOTER
def footer():
    W, H = 1280, 150
    s = Svg(W, H, "Thanks for stopping by")
    clip = s.uid("fc")
    s.defs.append(f'<clipPath id="{clip}"><rect width="{W}" height="{H}" rx="22"/></clipPath>')
    s.add(f'<g clip-path="url(#{clip})"><rect width="{W}" height="{H}" fill="{BG0}"/>')
    for i, (col, op, dur, amp, y0) in enumerate([(VIOLET, .30, 9, 16, 62), (CYAN, .20, 12, 12, 78), (PINK, .16, 15, 10, 92)]):
        pts = []
        for k in range(0, 2 * W + 41, 40):
            pts.append(f"{k},{y0 + amp * math.sin(k / W * 4 * math.pi + i):.1f}")
        d = f"M0,{H} L" + " L".join(pts) + f" L{2 * W + 40},{H} Z"
        s.css.append(f"@keyframes wv{i}{{to{{transform:translateX(-{W}px)}}}}.wv{i}{{animation:wv{i} {dur}s linear infinite}}")
        s.add(f'<path class="wv{i}" d="{d}" fill="{col}" fill-opacity="{op}"/>')
    s.add("</g>")
    s.add(s.text(W / 2, 40, "thanks for stopping by  ·  github.com/allenwu-blip", "mono", 18, TEXT, anchor="middle"))
    s.save("footer.svg")


# ================================================================== README
def readme():
    def row(names):
        cells = []
        for n in names:
            href = f"https://github.com/{USER}/{n}" if n != "ai-evaluator" else f"https://github.com/{USER}"
            cells.append(f'<a href="{href}"><img src="assets/card-{n}.svg" width="49%" alt="{n}"></a>')
        return "\n".join(cells)

    names = [p[0] for p in PROJECTS]
    rows = "\n<br>\n".join(row(names[i:i + 2]) for i in range(0, len(names), 2))
    md = f"""<div align="center">

<img src="assets/hero.svg" width="100%" alt="Allen Wu: CS + Movement Science at the University of Michigan">

<img src="assets/terminal.svg" width="100%" alt="whoami: Allen Wu, CS + Movement Science at UMich">

<img src="assets/h-now.svg" width="100%" alt="Now shipping">

<a href="{DEMO}"><img src="assets/sparkle-story.gif" width="100%" alt="Sparkle's opening story: the tooth fairy grows her magical garden"></a>

<a href="{DEMO}"><img src="assets/sparkle.svg" width="100%" alt="Sparkle: try the live demo (parent PIN 1234)"></a>

<img src="assets/h-build.svg" width="100%" alt="What I build">

{rows}

<img src="assets/h-stack.svg" width="100%" alt="Toolbox">

<img src="assets/stack.svg" width="100%" alt="Languages and tools">

<img src="assets/h-activity.svg" width="100%" alt="Activity">

<img src="profile-3d-contrib/profile-night-rainbow.svg" width="100%" alt="3D contribution graph">

<img src="profile-3d-contrib/snake.svg" width="100%" alt="Contribution snake">

<img src="assets/footer.svg" width="100%" alt="Thanks for stopping by">

<sub>Every image here is an animated SVG drawn by <a href="tools/build.py">tools/build.py</a>; the activity graphs refresh daily via GitHub Actions.</sub>

</div>
"""
    open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8").write(md)
    print("  README.md")


if __name__ == "__main__":
    print("building:")
    hero()
    terminal()
    header("h-now.svg", "01", "Now shipping", "// Tech Jam 2026 · live on any phone", PINK)
    header("h-build.svg", "02", "What I build", "// agent tooling · research · data infra · apps", VIOLET)
    header("h-stack.svg", "03", "Toolbox", "// what the projects above are made of", CYAN)
    header("h-activity.svg", "04", "Activity", "// refreshed daily by GitHub Actions", LIME)
    sparkle_strip()
    for i, p in enumerate(PROJECTS):
        card(i, *p)
    stack()
    footer()
    readme()

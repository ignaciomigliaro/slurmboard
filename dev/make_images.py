"""Render README illustrations for Slurm Board as PNGs (VSCode Dark Modern look).

Needs: pip install cairosvg fonttools; Inter fonts in INTER_FONT_DIR (or dev/fonts).
Run:   python dev/make_images.py [hero detail resubmit confirm geometry dismiss icon]
"""
import math
import os
import sys
import cairosvg

OUT = os.path.expanduser("~/slurmboard/images")
SCALE = 1.5

# Dark Modern palette
BG_EDITOR = "#1f1f1f"; BG_SIDE = "#181818"; BORDER = "#2b2b2b"; FG = "#cccccc"
MUTED = "#9d9d9d"; DIM = "#6e7681"; SEL = "#04395e"; HOVER = "#2a2d2e"; ACCENT = "#0078d4"
RED = "#f14c4c"; GREEN = "#89d185"; YELLOW = "#cca700"; PASS = "#73c991"; BLUE = "#3794ff"
UI = "Inter"; MONO = "DejaVu Sans Mono"

from fontTools.ttLib import TTFont
_FD = os.environ.get("INTER_FONT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"))  # Inter-*.ttf from rsms.me/inter
_FONTS = {}


def _font(family, weight):
    if family == MONO:
        path = "/usr/share/fonts/dejavu/DejaVuSansMono" + ("-Bold" if weight >= 600 else "") + ".ttf"
    else:
        path = os.path.join(_FD, {400: "Inter-Regular", 500: "Inter-Medium", 600: "Inter-SemiBold",
                                  700: "Inter-Bold"}[weight] + ".ttf")
    if path not in _FONTS:
        f = TTFont(path)
        _FONTS[path] = (f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm)
    return _FONTS[path]


def measure(t, size=13, weight=400, family=UI):
    cmap, hmtx, upm = _font(family, weight)
    return sum(hmtx[cmap.get(ord(ch), cmap[ord("?")])][0] for ch in str(t)) * size / upm


def fit(t, width, size=13, weight=400, family=UI):
    """Truncate with an ellipsis, like VSCode does for long descriptions."""
    if measure(t, size, weight, family) <= width:
        return t
    while t and measure(t + "…", size, weight, family) > width:
        t = t[:-1]
    return t + "…" if t else ""


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, t, size=13, fill=FG, weight=400, family=UI, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" {extra}>{esc(t)}</text>')


def rect(x, y, w, h, fill, rx=0, stroke=None, sw=1, extra=""):
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{s} {extra}/>'


# ---------------------------------------------------------------- icons ----
# each draws in a 16x16 box with top-left (x, y)

def ic(name, x, y, color=FG):
    c = color
    g = f'<g transform="translate({x},{y})" fill="none" stroke="{c}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">'
    body = {
        "error": f'<circle cx="8" cy="8" r="6.2"/><path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8"/>',
        "pass": f'<circle cx="8" cy="8" r="6.2"/><path d="M5.2 8.2l2 2 3.8-4"/>',
        "spin": f'<path d="M8 1.8a6.2 6.2 0 1 1-5.6 3.6"/><path d="M2.2 2.4v3.2h3.2"/>',
        "clock": f'<circle cx="8" cy="8" r="6.2"/><path d="M8 4.6V8l2.4 1.6"/>',
        "warning": f'<path d="M8 2.2l6.2 11H1.8z"/><path d="M8 6.4v3.2M8 11.4v.2"/>',
        "folder": f'<path d="M1.8 4.2h4.4l1.4 1.4h6.6v7.2H1.8z"/>',
        "file": f'<path d="M3.5 1.8h6l3 3v9.4h-9z"/><path d="M9.5 1.8v3h3"/>',
        "structure": f'<circle cx="4" cy="11.5" r="1.8"/><circle cx="12" cy="11.5" r="1.8"/><circle cx="8" cy="4" r="1.8"/><path d="M5 10l2-4.4M11 10L9 5.6M5.8 11.5h4.4"/>',
        "note": f'<path d="M3 2h10v12H3z"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3"/>',
        "history": f'<path d="M2.6 8a5.4 5.4 0 1 0 1.6-3.8"/><path d="M2.4 1.8v2.8h2.8"/><path d="M8 5v3.2l2.2 1.4"/>',
        "dot": f'<circle cx="8" cy="8" r="2" fill="{c}"/>',
        "restart": f'<path d="M12.8 8.6A5 5 0 1 1 11 4.2"/><path d="M11.4 1.6v3h-3"/>',
        "copy": f'<rect x="5" y="5" width="8.5" height="8.5" rx="1"/><path d="M3 10.6V3.2c0-.6.4-1 1-1h7"/>',
        "check": f'<path d="M3 8.4l3.2 3.2L13 4.8"/>',
        "checkall": f'<path d="M1.6 8.6l2.8 2.8L10 5.8M7 11.2l.4.2L14.4 4.4"/>',
        "checklist": f'<path d="M2 4l1.4 1.4L6 3M2 10l1.4 1.4L6 9M8.4 4.4h5.6M8.4 10.4h5.6"/>',
        "eye": f'<path d="M1.4 8s2.4-4.6 6.6-4.6S14.6 8 14.6 8s-2.4 4.6-6.6 4.6S1.4 8 1.4 8z"/><circle cx="8" cy="8" r="2"/>',
        "refresh": f'<path d="M13.2 7.4A5.2 5.2 0 1 0 12 11.2"/><path d="M13.4 2.6v4.8H8.6"/>',
        "collapse": f'<path d="M2 3h12v10H2z"/><path d="M5 8h6"/>',
        "edit": f'<path d="M10.6 2.6l2.8 2.8L5.6 13.2H2.8v-2.8z"/>',
        "output": f'<path d="M2 3h12v10H2z"/><path d="M4.6 6.2l2 1.8-2 1.8M8.4 10h3"/>',
        "chev_r": f'<path d="M6 3.8L10.2 8 6 12.2"/>',
        "chev_d": f'<path d="M3.8 6L8 10.2 12.2 6"/>',
        "files": f'<path d="M4 1.8h5.2l3 3v8.4H4z"/><path d="M2 4.4v9.8h7.6"/>',
        "search": f'<circle cx="7" cy="7" r="4.4"/><path d="M10.2 10.2l3.6 3.6"/>',
        "branch": f'<circle cx="4.6" cy="3.4" r="1.6"/><circle cx="4.6" cy="12.6" r="1.6"/><circle cx="11.4" cy="5.4" r="1.6"/><path d="M4.6 5v6M11.4 7c0 2.6-6.8 1.8-6.8 4"/>',
        "extensions": f'<rect x="2" y="7.6" width="6.4" height="6.4"/><rect x="7.6" y="7.6" width="6.4" height="6.4" transform="translate(0 0)"/><rect x="2" y="2" width="6.4" height="5.6"/><rect x="9.4" y="1.2" width="5.4" height="5.4" transform="rotate(10 12 4)"/>',
        "remote": f'<path d="M2 6l3.2 3.2L2 12.4M14 3.6l-3.2 3.2L14 10"/>',
        "board": f'<rect x="2" y="2" width="12" height="12" rx="2"/><path d="M4.6 5.6l1.1 1.1 1.9-1.9M9 6h3M4.8 9.6l2.2 2.2M7 9.6l-2.2 2.2M9 10.8h3"/>',
        "bell": f'<path d="M4 11V7a4 4 0 0 1 8 0v4l1.2 1.4H2.8z"/><path d="M6.6 13.8a1.6 1.6 0 0 0 2.8 0"/>',
        "close": f'<path d="M4 4l8 8M12 4l-8 8"/>',
        "gear": f'<circle cx="8" cy="8" r="2.2"/><path d="M8 1.6v2M8 12.4v2M1.6 8h2M12.4 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/>',
    }[name]
    return g + body + "</g>"


def checkbox(x, y, on):
    s = rect(x, y, 16, 16, ACCENT if on else "#313131", 3, None if on else "#6b6b6b")
    if on:
        s += f'<path d="M{x+3.6} {y+8.4}l3 3 6-6.6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    return s


# ----------------------------------------------------------- the tree ----

ROW = 22

def tree_row(x0, y, w, depth, label, desc="", icon=None, icon_color=FG, chevron=None,
             selected=False, hover=False, buttons=(), label_color=FG, bold=False, mono=False,
             desc_color=MUTED):
    s = ""
    if selected:
        s += rect(x0, y, w, ROW, SEL) + rect(x0, y, w, ROW, "none", 0, ACCENT)
    elif hover:
        s += rect(x0, y, w, ROW, HOVER)
    x = x0 + 8 + depth * 16
    if chevron:
        s += ic("chev_d" if chevron == "open" else "chev_r", x, y + 3, FG)
    x += 18
    if icon:
        s += ic(icon, x, y + 3, icon_color)
        x += 22
    fam = MONO if mono else UI
    size = 12 if mono else 13
    wt = 600 if bold else 400
    bx = x0 + w - 8 - 22 * len(buttons)
    limit = (bx - 6 if buttons else x0 + w - 10)
    label = fit(label, limit - x, size, wt, fam)
    s += text(x, y + 15.5, label, size, label_color, wt, fam)
    lw = measure(label, size, wt, fam)
    if desc and limit - (x + lw + 8) > 20:
        s += text(x + lw + 8, y + 15.5, fit(desc, limit - (x + lw + 8), 12), 12, desc_color)
    for b in buttons:
        s += ic(b, bx + 3, y + 3, FG)
        bx += 22
    return s


def sidebar(x, y, w, h, rows, title_desc="synced 14:32:05", badge=None):
    s = rect(x, y, w, h, BG_SIDE)
    s += text(x + 20, y + 23, "SLURM BOARD", 11, FG, 400, extra='letter-spacing="0.4"')
    for i, b in enumerate(["collapse", "eye", "refresh"]):
        s += ic(b, x + w - 30 - i * 26, y + 11, FG)
    s += rect(x, y + 36, w, 1, BORDER)
    s += ic("chev_d", x + 4, y + 42, FG)
    s += text(x + 22, y + 55, "CALCULATIONS", 11, FG, 700, extra='letter-spacing="0.3"')
    s += text(x + 22 + measure("CALCULATIONS", 11, 700) + 10, y + 55, title_desc, 11, MUTED)
    yy = y + 66
    for r in rows:
        s += tree_row(x, yy, w, **r)
        yy += ROW
    return s


def sample_rows(expanded=False, hover_idx=None):
    rows = [
        dict(depth=0, label="Needs attention", desc="3", chevron="open", bold=True),
        dict(depth=1, label="TS_sn2_ClMeBr", desc="ORCA error · #2481207 · try 2", icon="error",
             icon_color=RED, chevron="open" if expanded else "closed",
             selected=hover_idx == 1, buttons=("structure", "edit", "restart", "output", "copy", "check") if hover_idx == 1 else ()),
    ]
    if expanded:
        rows += [
            dict(depth=2, label="~/projects/sn2/ts", icon="folder", icon_color=MUTED),
            dict(depth=2, label="TS_sn2_ClMeBr.inp", desc="input", icon="file", icon_color=BLUE),
            dict(depth=2, label="TS_sn2_ClMeBr_trj.xyz", desc="optimization trajectory", icon="structure", icon_color=GREEN),
            dict(depth=2, label="input geometry", icon="structure", icon_color=GREEN),
            dict(depth=2, label="TS_sn2_ClMeBr.out", icon="file", icon_color=MUTED),
            dict(depth=2, label="TS_sn2_ClMeBr.err", icon="file", icon_color=MUTED),
            dict(depth=2, label="try a smaller trust radius, start from the scan maximum", icon="note", icon_color=YELLOW),
            dict(depth=2, label="SCF NOT CONVERGED AFTER 125 CYCLES", icon="dot", icon_color=RED, label_color="#e0a0a0"),
            dict(depth=2, label="ORCA finished by error termination in SCF", icon="dot", icon_color=RED, label_color="#e0a0a0"),
            dict(depth=2, label="attempts: 2481207 failed, 2479988 timeout", icon="history", icon_color=MUTED, label_color=MUTED),
        ]
    rows += [
        dict(depth=1, label="neb_proton_transfer", desc="timed out · #2480950", icon="error", icon_color=RED, chevron="closed"),
        dict(depth=1, label="md_water_box", desc="out of memory · #2480712", icon="error", icon_color=RED, chevron="closed"),
        dict(depth=0, label="Running", desc="2", chevron="open", bold=True),
        dict(depth=1, label="opt_benzene_dimer", desc="running · #2481301", icon="spin", icon_color=GREEN, chevron="closed"),
        dict(depth=1, label="lmp_melt", desc="running · #2481288", icon="spin", icon_color=GREEN, chevron="closed"),
        dict(depth=0, label="Pending", desc="2", chevron="open", bold=True),
        dict(depth=1, label="freq_benzene_dimer", desc="pending · #2481302", icon="clock", icon_color=YELLOW, chevron="closed"),
        dict(depth=1, label="scan_CO_stretch", desc="pending · #2481305", icon="clock", icon_color=YELLOW, chevron="closed"),
        dict(depth=0, label="Completed", desc="24", chevron="open", bold=True),
        dict(depth=1, label="opt_TMAO", desc="completed · #2479901", icon="pass", icon_color=PASS, chevron="closed"),
        dict(depth=1, label="opt_TS_guess", desc="completed · #2479870", icon="warning", icon_color=YELLOW, chevron="closed"),
        dict(depth=1, label="g16_irc_forward", desc="completed · #2479655", icon="pass", icon_color=PASS, chevron="closed"),
        dict(depth=1, label="gmx_npt_equil", desc="completed · #2479602", icon="pass", icon_color=PASS, chevron="closed"),
    ]
    return rows


# --------------------------------------------------------- window parts ----

def window(w, h, inner, title="lipid-project [SSH: cluster]", status_extra=True):
    s = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
    s += '<defs><filter id="sh" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.55"/></filter></defs>'
    s += rect(0, 0, w, h, BG_EDITOR, 10)
    s += f'<clipPath id="win"><rect width="{w}" height="{h}" rx="10"/></clipPath><g clip-path="url(#win)">'
    s += rect(0, 0, w, 34, BG_SIDE) + rect(0, 34, w, 1, BORDER)
    for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        s += f'<circle cx="{18 + i * 20}" cy="17" r="6" fill="{c}"/>'
    s += rect(w / 2 - 170, 7, 340, 21, "#242424", 6, BORDER)
    s += ic("search", w / 2 - 160, 9, MUTED) + text(w / 2, 22, title, 12, MUTED, anchor="middle")
    # activity bar
    s += rect(0, 35, 48, h - 35 - 22, BG_SIDE) + rect(48, 35, 1, h - 57, BORDER)
    for i, n in enumerate(["files", "search", "branch", "extensions", "board"]):
        yy = 47 + i * 48
        active = n == "board"
        s += ic(n, 12, yy, FG if active else "#868686").replace('stroke-width="1.3"', 'stroke-width="1.5"').replace(
            f'translate(12,{yy})', f'translate(12,{yy}) scale(1.5)')
        if active:
            s += rect(0, yy - 4, 2, 32, FG)
            s += f'<circle cx="35" cy="{yy + 22}" r="8" fill="{ACCENT}"/>' + text(35, yy + 26, "3", 10, "#fff", 600, anchor="middle")
    s += inner
    # status bar
    sy = h - 22
    s += rect(0, sy, w, 22, BG_SIDE) + rect(0, sy, w, 1, BORDER)
    rw = 36 + measure("SSH: cluster", 12)
    s += rect(0, sy, rw, 22, ACCENT) + ic("remote", 8, sy + 3, "#fff") + text(28, sy + 15, "SSH: cluster", 12, "#fff")
    if status_extra:
        sx = rw + 8
        s += rect(sx, sy, 116, 22, "#8a6d00")
        for k, (n, v) in enumerate([("spin", "2"), ("clock", "2"), ("error", "3")]):
            s += ic(n, sx + 8 + k * 36, sy + 3, "#fff") + text(sx + 27 + k * 36, sy + 15, v, 12, "#fff")
    s += text(w - 40, sy + 15, "Ln 214, Col 1    UTF-8", 12, MUTED, anchor="end")
    s += ic("bell", w - 26, sy + 3, MUTED)
    s += "</g></svg>"
    return s


def tabs(x, y, w, items):
    s = rect(x, y, w, 35, BG_SIDE) + rect(x, y + 35, w, 1, BORDER)
    xx = x
    for i, (label, icon, color) in enumerate(items):
        tw = 32 + measure(label, 13) + 34
        if i == 0:
            s += rect(xx, y, tw, 36, BG_EDITOR) + rect(xx, y, tw, 1.5, ACCENT)
        s += ic(icon, xx + 10, y + 10, color) + text(xx + 32, y + 22, label, 13, FG if i == 0 else MUTED)
        s += ic("close", xx + tw - 24, y + 10, MUTED if i == 0 else "none")
        s += rect(xx + tw, y, 1, 35, BORDER)
        xx += tw + 1
    return s


def code(x, y, lines, start=1, colors=None, lh=19):
    s = ""
    for i, ln in enumerate(lines):
        yy = y + i * lh
        s += text(x + 34, yy, str(start + i), 12, "#6e7681", family=MONO, anchor="end")
        col = (colors or {}).get(i, "#cccccc")
        if isinstance(ln, list):  # segments [(text, color)]
            xx = x + 56
            for seg, c in ln:
                s += text(xx, yy, seg, 12.5, c, family=MONO, extra='xml:space="preserve"')
                xx += measure(seg, 12.5, 400, MONO)
        else:
            s += text(x + 56, yy, ln, 12.5, col, family=MONO, extra='xml:space="preserve"')
    return s


def toast(x, y, w, icon, icon_color, msg, buttons, source="Slurm Board (Extension)"):
    h = 92
    s = f'<g filter="url(#sh)">{rect(x, y, w, h, "#202020", 6, "#3c3c3c")}</g>'
    s += ic(icon, x + 14, y + 16, icon_color) + text(x + 40, y + 29, msg, 13, FG)
    s += ic("gear", x + w - 52, y + 15, MUTED) + ic("close", x + w - 28, y + 15, MUTED)
    bx = x + w - 14
    widths = [measure(b, 12.5) + 24 for b in buttons]
    left = bx - sum(widths) - 8 * (len(buttons) - 1)
    s += text(x + 14, y + 74, fit("Source: " + source, left - x - 26, 11.5), 11.5, DIM)
    for i in reversed(range(len(buttons))):
        b, bw = buttons[i], widths[i]
        bx -= bw
        s += rect(bx, y + 56, bw, 26, ACCENT if i == 0 else "#313131", 3, None if i == 0 else "#454545")
        s += text(bx + bw / 2, y + 73, b, 12.5, "#fff", anchor="middle")
        bx -= 8
    return s


def quickpick(x, y, w, placeholder, items, filt="", multi=False, sel=0):
    h = 46 + len(items) * (44 if any(i.get("detail") for i in items) else 26) + 10
    s = f'<g filter="url(#sh)">{rect(x, y, w, h, "#222222", 8, "#3c3c3c")}</g>'
    if multi:
        s += checkbox(x + 12, y + 14, all(i.get("on") for i in items))
    ix = x + (40 if multi else 10)
    s += rect(ix, y + 8, w - (ix - x) - 10 - (60 if multi else 0), 28, "#313131", 4, ACCENT)
    s += text(ix + 8, y + 27, filt if filt else placeholder, 13, FG if filt else DIM)
    if filt:
        cx_ = ix + 9 + measure(filt, 13)
        s += f'<line x1="{cx_}" y1="{y + 14}" x2="{cx_}" y2="{y + 30}" stroke="{FG}"/>'
    if multi:
        n = sum(1 for i in items if i.get("on"))
        s += rect(x + w - 64, y + 12, 22, 20, "#4d4d4d", 10) + text(x + w - 53, y + 26, str(n), 11.5, FG, 600, anchor="middle")
        s += rect(x + w - 38, y + 10, 28, 24, ACCENT, 3) + text(x + w - 24, y + 26, "OK", 11, "#fff", 600, anchor="middle")
    yy = y + 44
    for k, it in enumerate(items):
        ih = 44 if it.get("detail") else 26
        if k == sel:
            s += rect(x + 4, yy, w - 8, ih, SEL, 4)
        xx = x + 14
        if multi:
            s += checkbox(xx, yy + 5, it.get("on"))
            xx += 26
        if it.get("icon"):
            s += ic(it["icon"], xx, yy + 5, it.get("icon_color", FG))
            xx += 24
        s += text(xx, yy + 17, it["label"], 13, FG, 600 if k == sel else 400)
        s += text(xx + measure(it["label"], 13, 600 if k == sel else 400) + 10, yy + 17, it.get("desc", ""), 12.5, MUTED)
        if it.get("detail"):
            s += text(xx, yy + 35, it["detail"], 12, DIM)
        yy += ih
    return s


def molecule(cx, cy, scale, atoms, bonds, rot=(0.35, -0.5)):
    """Ball-and-stick from xyz; rot = (about x, about y) radians."""
    ax, ay = rot
    pts = []
    for el, x, y, z in atoms:
        y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
        x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
        pts.append((el, cx + x * scale, cy - y * scale, z))
    colors = {"C": "#909090", "H": "#f2f2f2", "Cl": "#1ff01f", "Br": "#a62929", "O": "#ff3030", "N": "#3050f8"}
    radii = {"C": 0.34, "H": 0.22, "Cl": 0.45, "Br": 0.5, "O": 0.34, "N": 0.34}
    s = '<defs>'
    for el, c in colors.items():
        s += (f'<radialGradient id="g{el}" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#ffffff" stop-opacity="0.9"/>'
              f'<stop offset="0.25" stop-color="{c}"/><stop offset="1" stop-color="#000" stop-opacity="0.85"/></radialGradient>')
    s += '</defs>'
    items = []
    for i, j, partial in bonds:
        a, b = pts[i], pts[j]
        z = (a[3] + b[3]) / 2
        dash = ' stroke-dasharray="7 6"' if partial else ""
        items.append((z - 0.01, f'<line x1="{a[1]:.1f}" y1="{a[2]:.1f}" x2="{b[1]:.1f}" y2="{b[2]:.1f}" stroke="#b8b8b8" stroke-width="7" stroke-linecap="round"{dash}/>'))
    for el, x, y, z in pts:
        items.append((z, f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radii[el] * scale:.1f}" fill="url(#g{el})"/>'))
    for _, it in sorted(items, key=lambda t: t[0]):
        s += it
    return s


SN2_ATOMS = [("C", 0, 0, 0), ("H", 1.07, 0, 0.0), ("H", -0.535, 0.927, 0), ("H", -0.535, -0.927, 0),
             ("Cl", 0, 0, 2.35), ("Br", 0, 0, -2.5)]
SN2_BONDS = [(0, 1, False), (0, 2, False), (0, 3, False), (0, 4, True), (0, 5, True)]


# --------------------------------------------------------------- images ----

def hero():
    W, H = 1280, 760
    side_w = 400
    inner = sidebar(49, 35, side_w, H - 57, sample_rows(hover_idx=1))
    ex = 49 + side_w
    inner += rect(ex, 35, 1, H - 57, BORDER)
    inner += tabs(ex + 1, 35, W - ex - 1, [("TS_sn2_ClMeBr.out", "output", BLUE), ("TS_sn2_ClMeBr.inp", "file", MUTED)])
    out = [
        "                         *****************************",
        "                         * Geometry Optimization Run *",
        "                         *****************************",
        "",
        "--------------------------------------------------------",
        "                       SCF ITERATIONS",
        "--------------------------------------------------------",
        [("  ITER       Energy         Delta-E        Max-DP", MUTED)],
        "   121  -3112.40213912   2.13e-03   8.41e-02",
        "   122  -3112.39874106   3.40e-03   9.02e-02",
        "   123  -3112.40518275  -6.44e-03   7.77e-02",
        "   124  -3112.40011920   5.06e-03   8.95e-02",
        "   125  -3112.40347733  -3.36e-03   8.12e-02",
        "",
        [("               *****************************************************", "#e0a0a0")],
        [("               *                     ", "#e0a0a0"), ("SCF NOT CONVERGED AFTER 125 CYCLES", RED), ("   *", "#e0a0a0")],
        [("               *****************************************************", "#e0a0a0")],
        "",
        [("ORCA finished by error termination in SCF", RED)],
        "Calling Command: mpirun -np 8  /opt/orca/orca_scf_mpi TS_sn2_ClMeBr.gbw",
        "[file orca_tools/qcmsg.cpp, line 394]:",
        "  .... aborting the run",
    ]
    inner += code(ex + 1, 35 + 36 + 26, out, start=193)
    inner += toast(W - 470, H - 22 - 112, 455, "error", RED, "Slurm: TS_sn2_ClMeBr ORCA error (#2481207)",
                   ["Open .out", "Edit input", "Resubmit"])
    return window(W, H, inner)


def detail():
    W, H = 1100, 620
    side_w = 520
    inner = sidebar(49, 35, side_w, H - 57, sample_rows(expanded=True)[:14], title_desc="synced 14:32:05")
    # hover tooltip
    tx, ty, tw = 49 + side_w - 60, 120, 470
    tip = f'<g filter="url(#sh)">{rect(tx, ty, tw, 228, "#202020", 6, "#454545")}</g>'
    tip += text(tx + 14, ty + 26, "TS_sn2_ClMeBr", 13, FG, 700)
    tip += text(tx + 14 + measure("TS_sn2_ClMeBr", 13, 700) + 5, ty + 26, "— ORCA error (#2481207) · ORCA", 13, FG)
    tip += rect(tx + 14, ty + 40, tw - 28, 28, "#2b2b2b", 4)
    tip += text(tx + 24, ty + 59, "/home/user/projects/sn2/ts", 12, "#ce9178", family=MONO)
    tip += text(tx + 14, ty + 90, "ended 2026-10-06 13:12:40 · ran 04:12:09 · exit 1:0", 12.5, FG)
    tip += ic("note", tx + 12, ty + 103, YELLOW) + text(tx + 34, ty + 116, "try a smaller trust radius, start from the scan maximum", 12.5, FG)
    tip += rect(tx + 14, ty + 130, tw - 28, 50, "#2b2b2b", 4)
    tip += text(tx + 24, ty + 150, "SCF NOT CONVERGED AFTER 125 CYCLES", 12, "#d4d4d4", family=MONO)
    tip += text(tx + 24, ty + 168, "ORCA finished by error termination in SCF", 12, "#d4d4d4", family=MONO)
    tip += text(tx + 14, ty + 206, "Click to copy the directory.", 12.5, MUTED, extra='font-style="italic"')
    inner += rect(49 + side_w, 35, W - 49 - side_w, H - 57, BG_EDITOR) + rect(49 + side_w, 35, 1, H - 57, BORDER)
    inner += tip
    return window(W, H, inner)


def resubmit():
    W, H = 1180, 600
    side_w = 300
    rows = [r for r in sample_rows(hover_idx=1)][:6]
    inner = sidebar(49, 35, side_w, H - 57, rows)
    ex = 49 + side_w
    inner += rect(ex, 35, 1, H - 57, BORDER)
    inner += tabs(ex + 1, 35, W - ex - 1, [("TS_sn2_ClMeBr.inp", "file", BLUE)])
    K, V, N, S = "#569cd6", "#9cdcfe", "#b5cea8", "#ce9178"
    inp = [
        [("! ", FG), ("wB97X-D4 def2-TZVP OptTS Freq TightSCF", K)],
        "",
        [("%maxcore ", K), ("4000", N)],
        [("%pal ", K), ("nprocs ", V), ("8", N), (" end", K)],
        "",
        [("%scf", K)],
        [("  MaxIter ", V), ("300", N), ("        ", FG), ("# was 125", "#6a9955")],
        [("  SOSCFStart ", V), ("0.00033", N)],
        [("end", K)],
        "",
        [("%geom", K)],
        [("  Calc_Hess ", V), ("true", K)],
        [("  Trust ", V), ("-0.1", N), ("         ", FG), ("# smaller trust radius", "#6a9955")],
        [("end", K)],
        "",
        [("* xyzfile ", K), ("-1 1 ", N), ("TS_guess.xyz", S)],
    ]
    inner += code(ex + 1, 35 + 36 + 26, inp)
    inner += toast(W - 520, H - 22 - 112, 505, "bell", BLUE, "Saved input for TS_sn2_ClMeBr. Resubmit now?",
                   ["Resubmit", "Resubmit with options…", "Not yet"])
    return window(W, H, inner)


def confirm():
    W, H = 760, 270
    s = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
    s += '<defs><filter id="sh" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="6" stdDeviation="12" flood-color="#000" flood-opacity="0.6"/></filter></defs>'
    s += rect(0, 0, W, H, "#141414", 10)
    x, y, w, h = 60, 30, W - 120, H - 60
    s += f'<g filter="url(#sh)">{rect(x, y, w, h, "#252526", 8, "#3c3c3c")}</g>'
    s += f'<g transform="translate({x + 22},{y + 26}) scale(2.2)" fill="none" stroke="{YELLOW}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.2l6.2 11H1.8z"/><path d="M8 6.4v3.2M8 11.4v.2"/></g>'
    s += text(x + 76, y + 44, "Resubmit TS_sn2_ClMeBr?", 15, FG, 600)
    s += text(x + 76, y + 80, "cd /home/user/projects/sn2/ts", 13, MUTED, family=MONO)
    s += text(x + 76, y + 102, "sbatch --time=2-00:00:00 TS_sn2_ClMeBr.slurm", 13, MUTED, family=MONO)
    s += text(x + 76, y + 142, "The exact command is always shown before anything is submitted.", 12.5, DIM)
    s += rect(x + w - 222, y + h - 50, 104, 30, ACCENT, 4) + text(x + w - 170, y + h - 30, "Resubmit", 13, "#fff", anchor="middle")
    s += rect(x + w - 108, y + h - 50, 88, 30, "#313131", 4, "#454545") + text(x + w - 64, y + h - 30, "Cancel", 13, FG, anchor="middle")
    return s + "</svg>"


def geometry():
    W, H = 1180, 640
    side_w = 300
    inner = sidebar(49, 35, side_w, H - 57, sample_rows(hover_idx=1)[:8])
    ex = 49 + side_w
    inner += rect(ex, 35, 1, H - 57, BORDER)
    inner += tabs(ex + 1, 35, W - ex - 1, [("Protein Viewer - TS_sn2_ClMeBr_trj.xyz", "structure", GREEN)])
    vx, vy, vw, vh = ex + 1, 71, W - ex - 1, H - 71 - 22
    inner += rect(vx, vy, vw, vh, "#000000")
    # Mol*-style viewport controls
    for i, n in enumerate(["refresh", "eye", "gear", "collapse"]):
        inner += rect(vx + vw - 40, vy + 16 + i * 34, 28, 28, "#1b1b1b", 3) + ic(n, vx + vw - 34, vy + 22 + i * 34, "#9a9a9a")
    inner += molecule(vx + vw / 2 + 20, vy + vh / 2 + 120, 50, SN2_ATOMS, SN2_BONDS, rot=(0.95, 1.05))
    inner += quickpick(vx + vw / 2 - 300, vy + 6, 600, "Geometry for TS_sn2_ClMeBr (opens in Protein Viewer)", [
        dict(label="TS_sn2_ClMeBr_trj.xyz", desc="optimization trajectory", icon="structure", icon_color=GREEN,
             detail="modified 10/6/2026, 1:12:38 PM"),
        dict(label="TS_sn2_ClMeBr_input.xyz", desc="input geometry", icon="structure", icon_color=GREEN,
             detail="from TS_sn2_ClMeBr.inp"),
        dict(label="TS_guess.xyz", desc="xyz file", icon="structure", icon_color=GREEN, detail="modified 10/5/2026, 9:40:02 AM"),
    ])
    return window(W, H, inner)


def dismiss():
    W, H = 1000, 470
    side_w = 300
    rows = sample_rows()[10:]
    rows[0].update(hover=True, buttons=("checklist", "checkall"))
    rows[2].update(selected=True)
    inner = sidebar(49, 35, side_w, H - 57, rows)
    ex = 49 + side_w
    inner += rect(ex, 35, 1, H - 57, BORDER)
    inner += quickpick(ex + 40, 50, 580, "Tick the completed calculations to dismiss", [
        dict(label="opt_TMAO", desc="completed · #2479901 · 2026-10-05 22:41", detail="~/projects/tmao/opt", on=True),
        dict(label="opt_TS_guess", desc="completed · #2479870 · 2026-10-05 21:03", detail="~/projects/sn2/guess", on=True),
        dict(label="opt_water_dimer", desc="completed · #2479111 · 2026-10-04 08:15", detail="~/projects/benchmarks", on=True),
        dict(label="opt_benzene", desc="completed · #2478720 · 2026-10-03 17:52", detail="~/projects/benchmarks", on=False),
    ], filt="opt_", multi=True, sel=2)
    return window(W, H, inner)


def icon():
    s = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">'
    s += '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1f6feb"/><stop offset="1" stop-color="#0b3d91"/></linearGradient></defs>'
    s += '<rect x="4" y="4" width="120" height="120" rx="26" fill="url(#bg)"/>'
    rows = [(30, "#3fb950", "check"), (58, "#f0b429", "spin"), (86, "#ff6b6b", "x")]
    for y, c, kind in rows:
        s += f'<rect x="22" y="{y}" width="84" height="20" rx="6" fill="#ffffff" fill-opacity="0.12"/>'
        s += f'<circle cx="34" cy="{y + 10}" r="7" fill="{c}"/>'
        if kind == "check":
            s += f'<path d="M30.5 {y + 10.3}l2.6 2.6 4.6-5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        elif kind == "x":
            s += f'<path d="M31 {y + 7}l6 6M37 {y + 7}l-6 6" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>'
        else:
            s += f'<path d="M34 {y + 5.5}v4.5l3 2" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'
        s += f'<rect x="48" y="{y + 7}" width="{46 if kind != "spin" else 36}" height="6" rx="3" fill="#ffffff" fill-opacity="0.85"/>'
    return s + "</svg>"


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    jobs = {"hero": hero, "detail": detail, "resubmit": resubmit, "confirm": confirm,
            "geometry": geometry, "dismiss": dismiss}
    only = sys.argv[1:] or list(jobs) + ["icon"]
    for name in only:
        if name == "icon":
            cairosvg.svg2png(bytestring=icon().encode(), write_to=os.path.join(OUT, "..", "media", "icon.png"),
                             output_width=256, output_height=256)
            continue
        svg = jobs[name]()
        cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(OUT, name + ".png"), scale=SCALE)
        print("wrote", name)

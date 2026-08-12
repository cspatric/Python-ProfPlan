"""Generate an .excalidraw scene from the Excalidraw-build mermaid file.

Why: Excalidraw's mermaid importer cannot do subgraphs, so importing the .mmd
lands 47 boxes with no grouping. This lays them out in the same layered shape as
the documentation diagram, wraps each layer in a named frame, and binds straight
arrows (Excalidraw re-routes them properly as soon as a box is moved).
"""

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "architecture-excalidraw.mmd"
OUT = HERE / "architecture.excalidraw"

rnd = random.Random(20260809)  # fixed seed: regenerating gives a stable file
FONT = 2  # Helvetica — predictable metrics for dense technical text
FS = 16  # font size
LH = 1.25  # line height
CHAR_W = 7.6  # avg advance at 16px Helvetica (text metrics)
# Box sizing runs wider than the text estimate: Excalidraw renders wider than this.
BOX_CHAR_W = 8.8
PAD_X, PAD_Y = 16, 12

# ---------------------------------------------------------------- parse .mmd
text = SRC.read_text()

nodes: dict[str, str] = {}
for nid, label in re.findall(r'^(\w+)\["`(.*?)`"\]', text, re.S | re.M):
    nodes[nid] = label

styles: dict[str, dict] = {}
for name, body in re.findall(r"^classDef\s+(\w+)\s+(.*)$", text, re.M):
    d = dict(kv.split(":", 1) for kv in body.split(","))
    styles[name] = {
        "fill": d.get("fill", "#ffffff"),
        "stroke": d.get("stroke", "#1e1e1e"),
    }

node_style: dict[str, str] = {}
for name, ids in re.findall(r"^class\s+([\w,]+)\s+(\w+)$", text, re.M):
    for nid in name.split(","):
        node_style[nid] = ids

EDGE_RE = re.compile(r"(\w+)\s*(-->|-\.->|==>)\s*(?:\|\"(.*?)\"\|\s*)?(?=(\w+))")
edges: list[tuple[str, str, str, str]] = []
for line in text.split("\n"):
    line = line.strip()
    if not line or line.startswith(("classDef", "class ", "flowchart")):
        continue
    parts = EDGE_RE.findall(line)
    if not parts:
        continue
    # chains: A --> B --> C  (findall gives each hop with its right-hand node)
    for src, kind, label, dst in parts:
        if src in nodes and dst in nodes:
            edges.append((src, dst, kind, label))

# ---------------------------------------------------------------- layout
LAYERS = [
    ("EDGE", ["CLI", "TRF"]),
    ("API · middleware", ["M1", "M2", "M3", "M4", "DISP"]),
    (
        "API · modules",
        ["A_AUTH", "A_CRUD", "A_DOC", "A_RAG", "A_AI", "A_GEN", "A_AUD", "A_OPS"],
    ),
    ("DATA & MODELS", ["PG", "RDS", "MIO", "OLL", "ADM"]),
    ("LLM GATEWAY", ["GW", "CB", "PC", "PO", "PGM", "PL"]),
]
ASYNC = ("ASYNC · Celery", ["WRK", "P1", "P2", "P3", "P4", "P5", "GENT", "FLW"])
OBS = ("OBSERVABILITY", ["OTC", "TMP", "PTL", "LOK", "NEX", "PRM", "GRF"])
LEGEND = ("LEGEND", ["LG1", "LG2", "LG3", "LG4", "LG5", "LG6"])

BOX_W = 320
COL_GAP = 200
ROW_GAP = 44
FRAME_PAD = 34
FRAME_TITLE = 40


def box_size(label: str) -> tuple[int, int]:
    lines = label.split("\n")
    w = max(BOX_W, int(max(len(line) for line in lines) * BOX_CHAR_W) + PAD_X * 2)
    h = int(len(lines) * FS * LH) + PAD_Y * 2
    return w, h


pos: dict[str, tuple[int, int, int, int]] = {}
frames: list[tuple[str, int, int, int, int]] = []

x = 0
band_bottom = 0
for title, ids in LAYERS:
    col_w = max(box_size(nodes[i])[0] for i in ids)
    y = FRAME_TITLE
    for nid in ids:
        w, h = box_size(nodes[nid])
        pos[nid] = (x + (col_w - w) // 2, y, w, h)
        y += h + ROW_GAP
    frames.append(
        (title, x - FRAME_PAD, 0, col_w + FRAME_PAD * 2, y - ROW_GAP + FRAME_PAD)
    )
    band_bottom = max(band_bottom, y - ROW_GAP + FRAME_PAD)
    x += col_w + COL_GAP

total_w = x - COL_GAP


def band(title, rows, top, trailing=None):
    """Lay explicit rows of nodes inside one frame; `trailing` sits to the right."""
    y = top + FRAME_TITLE
    right = 0
    for row in rows:
        cx, row_h = 0, 0
        for nid in row:
            w, h = box_size(nodes[nid])
            pos[nid] = (cx, y, w, h)
            cx += w + COL_GAP // 2
            right = max(right, cx - COL_GAP // 2)
            row_h = max(row_h, h)
        y += row_h + ROW_GAP
    bottom = y - ROW_GAP
    if trailing:
        w, h = box_size(nodes[trailing])
        top_y = (top + FRAME_TITLE + bottom - h) // 2
        pos[trailing] = (right + COL_GAP // 2, top_y, w, h)
        right += COL_GAP // 2 + w
    bottom += FRAME_PAD
    frames.append((title, -FRAME_PAD, top, right + FRAME_PAD * 2, bottom - top))
    return bottom


y_async = band_bottom + 140
y_obs = (
    band(ASYNC[0], [["WRK", "GENT", "FLW"], ["P1", "P2", "P3", "P4", "P5"]], y_async)
    + 140
)
y_leg = (
    band(
        OBS[0],
        [["OTC", "TMP"], ["PTL", "LOK"], ["NEX", "PRM"]],
        y_obs,
        trailing="GRF",
    )
    + 140
)
band(LEGEND[0], [["LG1", "LG2", "LG3", "LG4", "LG5", "LG6"]], y_leg)


# ---------------------------------------------------------------- elements
def nonce() -> int:
    return rnd.randint(1, 2**31 - 1)


elements: list[dict] = []
frame_ids: dict[str, str] = {}

for title, fx, fy, fw, fh in frames:
    fid = f"frame-{re.sub(r'[^a-z]+', '-', title.lower())}"
    frame_ids[title] = fid
    elements.append(
        {
            "type": "frame",
            "id": fid,
            "x": fx,
            "y": fy,
            "width": fw,
            "height": fh,
            "angle": 0,
            "strokeColor": "#bbb",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": None,
            "seed": nonce(),
            "version": 1,
            "versionNonce": nonce(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
            "name": title,
        }
    )


def frame_of(nid: str) -> str | None:
    for title, ids in [*LAYERS, ASYNC, OBS, LEGEND]:
        if nid in ids:
            return frame_ids[title]
    return None


bound: dict[str, list] = {nid: [] for nid in nodes}

for nid, label in nodes.items():
    if nid not in pos:
        continue
    x0, y0, w, h = pos[nid]
    style = styles.get(
        node_style.get(nid, ""), {"fill": "#ffffff", "stroke": "#1e1e1e"}
    )
    tid = f"text-{nid}"
    bound[nid].append({"type": "text", "id": tid})
    elements.append(
        {
            "type": "rectangle",
            "id": nid,
            "x": x0,
            "y": y0,
            "width": w,
            "height": h,
            "angle": 0,
            "strokeColor": style["stroke"],
            "backgroundColor": style["fill"],
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": frame_of(nid),
            "roundness": {"type": 3},
            "seed": nonce(),
            "version": 1,
            "versionNonce": nonce(),
            "isDeleted": False,
            "boundElements": bound[nid],
            "updated": 1,
            "link": None,
            "locked": False,
        }
    )
    lines = label.split("\n")
    tw = int(max(len(line) for line in lines) * CHAR_W)
    th = int(len(lines) * FS * LH)
    elements.append(
        {
            "type": "text",
            "id": tid,
            "x": x0 + (w - tw) / 2,
            "y": y0 + (h - th) / 2,
            "width": tw,
            "height": th,
            "angle": 0,
            "strokeColor": "#0b1220",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": frame_of(nid),
            "roundness": None,
            "seed": nonce(),
            "version": 1,
            "versionNonce": nonce(),
            "isDeleted": False,
            "boundElements": [],
            "updated": 1,
            "link": None,
            "locked": False,
            "text": label,
            "fontSize": FS,
            "fontFamily": FONT,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": nid,
            "originalText": label,
            "autoResize": True,
            "lineHeight": LH,
        }
    )


def anchor(a: tuple[int, int, int, int], b: tuple[int, int, int, int]):
    """Point on a's border facing b's centre, plus b's border point."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    acx, acy = ax + aw / 2, ay + ah / 2
    bcx, bcy = bx + bw / 2, by + bh / 2
    dx, dy = bcx - acx, bcy - acy

    def edge(cx, cy, w, h, dx, dy, gap=8):
        if dx == 0 and dy == 0:
            return cx, cy
        sx = (w / 2 + gap) / abs(dx) if dx else float("inf")
        sy = (h / 2 + gap) / abs(dy) if dy else float("inf")
        s = min(sx, sy)
        return cx + dx * s, cy + dy * s

    p1 = edge(acx, acy, aw, ah, dx, dy)
    p2 = edge(bcx, bcy, bw, bh, -dx, -dy)
    return p1, p2


STYLE_OF = {"-->": ("solid", 2), "-.->": ("dashed", 2), "==>": ("solid", 4)}

for i, (src, dst, kind, label) in enumerate(edges):
    if src not in pos or dst not in pos:
        continue
    (x1, y1), (x2, y2) = anchor(pos[src], pos[dst])
    aid = f"arrow-{i}-{src}-{dst}"
    stroke_style, stroke_w = STYLE_OF[kind]
    arrow_bound = []
    if label:
        lid = f"{aid}-label"
        arrow_bound.append({"type": "text", "id": lid})
    elements.append(
        {
            "type": "arrow",
            "id": aid,
            "x": x1,
            "y": y1,
            "width": abs(x2 - x1),
            "height": abs(y2 - y1),
            "angle": 0,
            "strokeColor": "#64748b",
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": stroke_w,
            "strokeStyle": stroke_style,
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "roundness": {"type": 2},
            "seed": nonce(),
            "version": 1,
            "versionNonce": nonce(),
            "isDeleted": False,
            "boundElements": arrow_bound,
            "updated": 1,
            "link": None,
            "locked": False,
            "points": [[0, 0], [x2 - x1, y2 - y1]],
            "lastCommittedPoint": None,
            "startBinding": {"elementId": src, "focus": 0, "gap": 8},
            "endBinding": {"elementId": dst, "focus": 0, "gap": 8},
            "startArrowhead": None,
            "endArrowhead": "arrow",
            "elbowed": False,
        }
    )
    bound[src].append({"type": "arrow", "id": aid})
    bound[dst].append({"type": "arrow", "id": aid})
    if label:
        lw, lh = len(label) * (CHAR_W - 1.4), FS * LH
        t = (0.32, 0.5, 0.68, 0.42, 0.58)[i % 5]
        mx, my = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        elements.append(
            {
                "type": "text",
                "id": f"{aid}-label",
                "x": mx - lw / 2,
                "y": my - lh / 2,
                "width": lw,
                "height": lh,
                "angle": 0,
                "strokeColor": "#475569",
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "strokeWidth": 2,
                "strokeStyle": "solid",
                "roughness": 0,
                "opacity": 100,
                "groupIds": [],
                "frameId": None,
                "roundness": None,
                "seed": nonce(),
                "version": 1,
                "versionNonce": nonce(),
                "isDeleted": False,
                "boundElements": [],
                "updated": 1,
                "link": None,
                "locked": False,
                "text": label,
                "fontSize": 14,
                "fontFamily": FONT,
                "textAlign": "center",
                "verticalAlign": "middle",
                "containerId": aid,
                "originalText": label,
                "autoResize": True,
                "lineHeight": LH,
            }
        )

scene = {
    "type": "excalidraw",
    "version": 2,
    "source": "ProfPlan docs",
    "elements": elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}

OUT.write_text(json.dumps(scene, ensure_ascii=False, indent=1))

ids = {e["id"] for e in elements}
dangling = [
    e["id"]
    for e in elements
    if e["type"] == "arrow"
    and not ({e["startBinding"]["elementId"], e["endBinding"]["elementId"]} <= ids)
]
print(
    f"nodes={len(nodes)} edges={len(edges)} "
    f"elements={len(elements)} frames={len(frames)}"
)
print(f"canvas≈{total_w}px wide · dangling bindings: {dangling}")

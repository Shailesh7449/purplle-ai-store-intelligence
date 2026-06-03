"""Zone definitions and geometry helpers.

Zones model the REAL Purplle store floor-plan (Brigade, Bangalore) from the
provided layout: a top wall of brand counters, a bottom wall of brand counters,
the central Front-of-House (FOH) with makeup/nail units, and the cash counter on
the right where conversion happens.

Coordinates are NORMALISED (0..1 of frame width/height) so the same config works
at any video resolution. A door counting-line near the entrance measures footfall.

NOTE: A single fixed CCTV view rarely sees the whole store. Treat these polygons
as a sensible default for an entrance-facing camera and tune per actual camera in
`load_layout()` / store_layout.json. This is documented in DESIGN.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Zone:
    name: str
    polygon: list[tuple[float, float]]   # (x, y) normalised [0,1]
    kind: str = "product"                # product | foh | counter | entrance

    def contains(self, x: float, y: float) -> bool:
        inside = False
        n = len(self.polygon)
        j = n - 1
        for i in range(n):
            xi, yi = self.polygon[i]
            xj, yj = self.polygon[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            ):
                inside = not inside
            j = i
        return inside


@dataclass
class CountingLine:
    name: str
    p1: tuple[float, float]
    p2: tuple[float, float]

    def side(self, x: float, y: float) -> float:
        (x1, y1), (x2, y2) = self.p1, self.p2
        return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)


@dataclass
class StoreLayout:
    zones: list[Zone] = field(default_factory=list)
    lines: list[CountingLine] = field(default_factory=list)

    def zone_for_point(self, x: float, y: float) -> str | None:
        # counter/entrance take priority if overlapping; product zones next
        for z in self.zones:
            if z.contains(x, y):
                return z.name
        return None


def default_layout() -> StoreLayout:
    """Default Purplle store layout (entrance-left, cash-counter-right).

    Maps the floor-plan into camera-friendly normalised bands:
      - entrance        : left edge (door + glass)
      - shelf_top       : top wall brand counters (Salm/TFS/GV/DermDoc/...)
      - foh             : central front-of-house (makeup & nail units)
      - shelf_bottom    : bottom wall counters (Maybelline/Faces/Lakme/...)
      - cash_counter    : right side where purchase happens (conversion!)
    """
    return StoreLayout(
        zones=[
            Zone("entrance", [(0.0, 0.0), (0.12, 0.0), (0.12, 1.0), (0.0, 1.0)],
                 kind="entrance"),
            Zone("shelf_top", [(0.12, 0.0), (0.85, 0.0), (0.85, 0.30), (0.12, 0.30)],
                 kind="product"),
            Zone("foh", [(0.12, 0.30), (0.85, 0.30), (0.85, 0.72), (0.12, 0.72)],
                 kind="foh"),
            Zone("shelf_bottom", [(0.12, 0.72), (0.85, 0.72), (0.85, 1.0), (0.12, 1.0)],
                 kind="product"),
            Zone("cash_counter", [(0.85, 0.0), (1.0, 0.0), (1.0, 1.0), (0.85, 1.0)],
                 kind="counter"),
        ],
        lines=[
            # vertical line just inside the door: crossing left->right = entering
            CountingLine("door", (0.10, 0.0), (0.10, 1.0)),
        ],
    )


def load_layout(path: str | Path = "data/store_layout.json") -> StoreLayout:
    """Load a custom layout if present, else fall back to the default.

    store_layout.json format:
        {"zones":[{"name":"...","kind":"product","polygon":[[x,y],...]}],
         "lines":[{"name":"door","p1":[x,y],"p2":[x,y]}]}
    """
    p = Path(path)
    if not p.exists():
        return default_layout()
    data = json.loads(p.read_text())
    zones = [Zone(z["name"], [tuple(pt) for pt in z["polygon"]],
                  z.get("kind", "product")) for z in data.get("zones", [])]
    lines = [CountingLine(l["name"], tuple(l["p1"]), tuple(l["p2"]))
             for l in data.get("lines", [])]
    return StoreLayout(zones=zones or default_layout().zones,
                       lines=lines or default_layout().lines)

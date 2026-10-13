"""Rutnätet: rutor om 50 × 50 m i SWEREF99 TM (EPSG:3006), indelat i block om 100 × 100 rutor (5 × 5 km).

Varje ruta lagras som 14 byte (0–254 är värden, 255 betyder att data saknas):
  0 poäng (0–250)          1–5 faktorerna tradslag, alder, jordart, fukt, hojd (0–250)
  6–8 gran, tall, björk (%) 9 trädhöjd (m)   10 år sedan avverkning   11 jordart   12 fuktklass   13 höjd över havet / 5
Webbappen läser blocket för en ruta när man trycker på den.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RUTA_M = 50
BLOCK = 100
SAKNAS = 255
FALT = ["poang", "f_tradslag", "f_alder", "f_jordart", "f_fukt", "f_hojd",
        "gran", "tall", "bjork", "tradhojd", "ar_sedan_avverkning", "jordart", "fukt", "hojd"]


@dataclass(frozen=True)
class Rutnat:
    x0: float   # västra kanten (m, EPSG:3006)
    y0: float   # norra kanten
    bredd: int  # antal rutor i x
    hojd: int   # antal rutor i y

    @staticmethod
    def kring(minx: float, miny: float, maxx: float, maxy: float) -> "Rutnat":
        """Rutnätet som täcker en bbox, med kanterna på jämna 50 m."""
        x0 = np.floor(minx / RUTA_M) * RUTA_M
        y0 = np.ceil(maxy / RUTA_M) * RUTA_M
        x1 = np.ceil(maxx / RUTA_M) * RUTA_M
        y1 = np.floor(miny / RUTA_M) * RUTA_M
        return Rutnat(float(x0), float(y0), int((x1 - x0) / RUTA_M), int((y0 - y1) / RUTA_M))

    @property
    def transform(self):
        from rasterio.transform import from_origin
        return from_origin(self.x0, self.y0, RUTA_M, RUTA_M)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0 - self.hojd * RUTA_M, self.x0 + self.bredd * RUTA_M, self.y0)

    def block(self):
        """Blocken som (bx, by, rad0, kol0, rader, kolumner)."""
        for by in range(0, self.hojd, BLOCK):
            for bx in range(0, self.bredd, BLOCK):
                yield bx // BLOCK, by // BLOCK, by, bx, min(BLOCK, self.hojd - by), min(BLOCK, self.bredd - bx)


def byte(v: np.ndarray, skala: float = 1.0, max_: int = 254) -> np.ndarray:
    """Värden till byte; NaN blir SAKNAS."""
    out = np.full(v.shape, SAKNAS, dtype=np.uint8)
    ok = ~np.isnan(v)
    out[ok] = np.clip(np.round(v[ok] * skala), 0, max_).astype(np.uint8)
    return out


def koda_block(falt: dict[str, np.ndarray]) -> bytes:
    """Ett block som byte, ruta för ruta (radvis), 14 byte per ruta."""
    skalor = {"poang": 250, "f_tradslag": 250, "f_alder": 250, "f_jordart": 250, "f_fukt": 250, "f_hojd": 250, "hojd": 0.2}
    lager = [byte(falt[f], skalor.get(f, 1.0)) for f in FALT]
    return np.stack(lager, axis=-1).tobytes()


def avkoda_ruta(data: bytes, index: int) -> dict[str, float | None]:
    """Omvändningen för en ruta (används i testerna; webbappen gör samma sak i JavaScript)."""
    b = data[index * len(FALT):(index + 1) * len(FALT)]
    ut: dict[str, float | None] = {}
    for f, v in zip(FALT, b):
        if v == SAKNAS:
            ut[f] = None
        elif f in ("poang",) or f.startswith("f_"):
            ut[f] = v / 250
        elif f == "hojd":
            ut[f] = v * 5
        else:
            ut[f] = float(v)
    return ut

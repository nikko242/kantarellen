"""Förberäkningen: källornas data på rutnätet → poäng per ruta → kartbild och block för webbappen.

  python -m kantarell.forberakna --demo        påhittade data för ett område kring Östersund (för att pröva appen)
  python -m kantarell.forberakna               riktiga källor för Jämtlands län (se kantarell/kallor.py)

Resultatet hamnar i web/data: tiles/<z>/<x>/<y>.png (kartbilden), block/<bx>_<by>.bin.gz och meta.json
(rutnätet, källorna med datum och licens, och statistik).
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np

from .poang import bedom_falt
from .rutnat import BLOCK, FALT, RUTA_M, Rutnat, koda_block

log = logging.getLogger("kantarell")
WEB = Path(__file__).resolve().parent.parent / "web" / "data"
KALLFALT = ["gran", "tall", "bjork", "tradhojd", "ar_sedan_avverkning", "jordart", "fukt", "hojd"]


def berakna(nat: Rutnat, data: dict[str, np.ndarray], innanfor: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Poäng och faktorer för varje ruta (reglerna i kantarell/poang.py, för hela rutnätet på en gång).
    data har källfälten som float-arrayer på rutnätet (NaN = saknas)."""
    shape = (nat.hojd, nat.bredd)
    kalla = {f: data.get(f, np.full(shape, np.nan)).astype(np.float32) for f in KALLFALT}
    ut = {**{k: v.astype(np.float32) for k, v in bedom_falt(kalla).items()}, **kalla}
    if innanfor is not None:
        for f in ut:
            ut[f][~innanfor] = np.nan
    return ut


# Färgen går efter rangordning bland områdets skogsrutor (beslut i Saida, KS-5): guld är de bästa 10 %.
# Poängen är densamma; skalan gör att kartan skiljer ut de bästa ställena även där nästan all skog får hög poäng.
FARGER = [(0.0, (120, 120, 120, 60)), (0.5, (165, 158, 120, 110)), (0.75, (215, 175, 70, 160)), (0.9, (240, 175, 20, 200)), (1.0, (255, 196, 0, 235))]
TROSKLAR = [50, 75, 90]   # percentiler som webbappen visar ("bland de 10 % bästa")


def rang(poang: np.ndarray) -> np.ndarray:
    """Varje rutas plats bland skogsrutorna, 0 (sämst) till 1 (bäst); NaN där det inte är skog."""
    ut = np.full(poang.shape, np.nan)
    ok = ~np.isnan(poang)
    if ok.any():
        sorterad = np.sort(poang[ok])
        ut[ok] = np.searchsorted(sorterad, poang[ok], side="right") / sorterad.size
    return ut


def farg(rang_: np.ndarray) -> np.ndarray:
    """Rang till RGBA: grått (sämst) till guld (de bästa 10 %); genomskinligt där det inte är skog."""
    rgba = np.zeros(rang_.shape + (4,), dtype=np.uint8)
    ok = ~np.isnan(rang_)
    xs = [p for p, _ in FARGER]
    for k in range(4):
        rgba[..., k][ok] = np.interp(rang_[ok], xs, [c[k] for _, c in FARGER]).astype(np.uint8)
    return rgba


MINZOOM, MAXZOOM = 5, 11   # på zoom 11 är en pixel ungefär 35 m i länet, alltså mindre än en ruta
TILE = 256
VARLDEN = 20037508.342789244   # halva Web Mercators bredd i meter


def _png(rgba: np.ndarray) -> bytes:
    """En RGBA-bild som PNG (utan bildbibliotek)."""
    import struct
    import zlib
    h, w, _ = rgba.shape
    rader = b"".join(b"\x00" + rgba[i].tobytes() for i in range(h))   # filtertyp 0 före varje rad
    def chunk(typ: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rader, 6)) + chunk(b"IEND", b""))


def _halvera(rgba: np.ndarray) -> np.ndarray:
    """Halva upplösningen: medelvärde av 2 × 2 pixlar, färgen viktad med genomskinligheten."""
    h, w = rgba.shape[0] // 2 * 2, rgba.shape[1] // 2 * 2
    a = rgba[:h, :w].astype(np.float32).reshape(h // 2, 2, w // 2, 2, 4)
    alfa = a[..., 3]
    vikt = alfa.sum(axis=(1, 3))
    ut = np.zeros((h // 2, w // 2, 4), dtype=np.float32)
    for k in range(3):
        ut[..., k] = np.where(vikt > 0, (a[..., k] * alfa).sum(axis=(1, 3)) / np.maximum(vikt, 1), 0)
    ut[..., 3] = alfa.mean(axis=(1, 3))
    return np.round(ut).astype(np.uint8)


def skriv_tiles(nat: Rutnat, rgba: np.ndarray, ut_dir: Path) -> tuple[int, list[float]]:
    """Kartbilden som tiles ({z}/{x}/{y}.png) för zoom MINZOOM–MAXZOOM. Bilden omprojiceras en gång till Web Mercator
    i MAXZOOM:s upplösning, med kanterna på tile-gränser; de lägre nivåerna är halveringar av den."""
    import shutil

    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject, transform_bounds

    lon0, lat0, lon1, lat1 = transform_bounds("EPSG:3006", "EPSG:4326", *nat.bounds)
    x0m, y0m, x1m, y1m = transform_bounds("EPSG:3006", "EPSG:3857", *nat.bounds)
    upp = 2 * VARLDEN / (TILE * 2 ** MAXZOOM)
    tx0, ty0 = int((x0m + VARLDEN) // (upp * TILE)), int((VARLDEN - y1m) // (upp * TILE))
    tx1, ty1 = int((x1m + VARLDEN) // (upp * TILE)), int((VARLDEN - y0m) // (upp * TILE))
    w, h = (tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE
    dst_t = from_origin(-VARLDEN + tx0 * TILE * upp, VARLDEN - ty0 * TILE * upp, upp, upp)
    bild = np.zeros((h, w, 4), dtype=np.uint8)
    for k in range(4):
        reproject(np.ascontiguousarray(rgba[..., k]), bild[..., k], src_transform=nat.transform, src_crs="EPSG:3006",
                  dst_transform=dst_t, dst_crs="EPSG:3857", resampling=Resampling.nearest, num_threads=8)
    tiles = ut_dir / "tiles"
    if tiles.exists():
        shutil.rmtree(tiles)
    antal = 0
    bx0, by0 = tx0, ty0
    for z in range(MAXZOOM, MINZOOM - 1, -1):
        for j in range(bild.shape[0] // TILE):
            for i in range(bild.shape[1] // TILE):
                t = bild[j * TILE:(j + 1) * TILE, i * TILE:(i + 1) * TILE]
                if not t[..., 3].any():
                    continue
                p = tiles / str(z) / str(bx0 + i) / f"{by0 + j}.png"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(_png(t))
                antal += 1
        if z > MINZOOM:
            # Fyll ut till jämna tile-nummer, så att varje tile på nivån under är exakt fyra tiles
            vanster, topp = (bx0 % 2) * TILE, (by0 % 2) * TILE
            hoger = (TILE * 2 - (bild.shape[1] + vanster) % (TILE * 2)) % (TILE * 2)
            botten = (TILE * 2 - (bild.shape[0] + topp) % (TILE * 2)) % (TILE * 2)
            bild = _halvera(np.pad(bild, ((topp, botten), (vanster, hoger), (0, 0))))
            bx0, by0 = bx0 // 2, by0 // 2
    return antal, [lon0, lat0, lon1, lat1]


def skriv(nat: Rutnat, ut: dict[str, np.ndarray], kallor: list[dict], ut_dir: Path = WEB, omrade: str = "området") -> dict:
    import gzip
    import shutil

    if (ut_dir / "block").exists():
        shutil.rmtree(ut_dir / "block")
    (ut_dir / "block").mkdir(parents=True)
    for gammal in ut_dir.glob("poang.png*"):
        gammal.unlink()
    antal = 0
    for bx, by, r0, k0, nr, nk in nat.block():
        falt = {f: ut[f][r0:r0 + nr, k0:k0 + nk] for f in ut if f in FALT}
        if np.all(np.isnan(falt["poang"])):
            continue
        # Kanterna fylls ut till hela block, så att webbappen alltid räknar med 100 × 100
        fullt = {f: np.pad(v, ((0, BLOCK - nr), (0, BLOCK - nk)), constant_values=np.nan) for f, v in falt.items()}
        (ut_dir / "block" / f"{bx}_{by}.bin.gz").write_bytes(gzip.compress(koda_block(fullt), 9, mtime=0))
        antal += 1

    tiles, bounds = skriv_tiles(nat, farg(rang(ut["poang"])), ut_dir)
    poang = ut["poang"][~np.isnan(ut["poang"])]
    meta = {
        "skapad": time.strftime("%Y-%m-%d %H:%M"),
        "omrade": omrade,
        "rutnat": {"crs": "EPSG:3006", "x0": nat.x0, "y0": nat.y0, "bredd": nat.bredd, "hojd": nat.hojd, "ruta_m": RUTA_M, "block": BLOCK},
        "tiles": {"url": "data/tiles/{z}/{x}/{y}.png", "minzoom": MINZOOM, "maxzoom": MAXZOOM, "bounds": bounds},
        "kallor": kallor,
        "skala": {"percentiler": TROSKLAR, "poang": [round(float(np.percentile(poang, q)), 3) for q in TROSKLAR] if poang.size else []},
        "statistik": {"skogsrutor": int(poang.size), "block": antal, "tiles": tiles,
                      "andel_hog": round(float((poang >= 0.7).mean()), 3) if poang.size else 0},
    }
    (ut_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def demodata(nat: Rutnat, seed: int = 7) -> dict[str, np.ndarray]:
    """Påhittade men sammanhängande data (mjuka fält), för att pröva appen utan riktiga källor."""
    rng = np.random.default_rng(seed)
    shape = (nat.hojd, nat.bredd)

    def falt(skala: int) -> np.ndarray:
        grov = rng.random((shape[0] // skala + 2, shape[1] // skala + 2))
        return np.kron(grov, np.ones((skala, skala)))[: shape[0], : shape[1]]

    barr = falt(8)
    gran = 40 + 50 * barr
    tall = 10 + 30 * (1 - barr)
    bjork = 30 * falt(6)
    tradhojd = 3 + 20 * falt(5)
    avverk = np.where(falt(10) < 0.12, np.round(25 * falt(3)), np.nan)
    tradhojd = np.where(~np.isnan(avverk) & (avverk < 10), 1 + 3 * falt(2), tradhojd)
    jord = np.select([falt(12) < 0.6, falt(12) < 0.75, falt(12) < 0.85], [1, 2, 6], 5).astype(float)
    fukt = np.clip(np.round(1 + 3 * falt(7)), 1, 4)
    hojd = 300 + 450 * falt(20)
    vatten = falt(15) < 0.08
    data = {"gran": gran, "tall": tall, "bjork": bjork, "tradhojd": tradhojd, "ar_sedan_avverkning": avverk,
            "jordart": jord, "fukt": fukt, "hojd": hojd}
    for f in ("gran", "tall", "bjork"):
        data[f] = np.where(vatten, np.nan, data[f])
    return data


DEMO_KALLOR = [{"namn": "Påhittade demodata", "vad": "alla faktorer", "datum": time.strftime("%Y-%m-%d"),
                "licens": "–", "url": "", "not": "Bara för att pröva appen; säger ingenting om verkliga kantareller."}]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Förberäkna sannolikhetskartan för kantareller")
    p.add_argument("--demo", action="store_true", help="påhittade data för ett område om 10 × 10 km kring Östersund")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.time()
    if a.demo:
        nat = Rutnat.kring(476000, 7002000, 486000, 7012000)
        log.info("Demo: %d × %d rutor om %d m", nat.bredd, nat.hojd, RUTA_M)
        data, kallor, innanfor = demodata(nat), DEMO_KALLOR, None
    else:
        from .kallor import hamta
        from .kallor import OMRADE
        nat, data, kallor, innanfor = hamta()
    for f in KALLFALT:
        if f == "ar_sedan_avverkning":   # saknas = ingen känd avverkning, inte en lucka
            continue
        saknas = float(np.isnan(data[f]).mean()) if f in data else 1.0
        (log.warning if saknas > 0.5 else log.info)("%s: data saknas för %.0f %% av rutorna", f, 100 * saknas)
    ut = berakna(nat, data, innanfor)
    meta = skriv(nat, ut, kallor, omrade="området runt Östersund (demo)" if a.demo else OMRADE)
    log.info("Klart på %.1f s: %d skogsrutor, %d block, %.0f %% med hög sannolikhet", time.time() - t0,
             meta["statistik"]["skogsrutor"], meta["statistik"]["block"], 100 * meta["statistik"]["andel_hog"])


if __name__ == "__main__":
    main()

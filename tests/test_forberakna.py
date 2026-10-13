"""Rutnätet, kodningen av block och förberäkningen från början till slut med demodata."""
import gzip
import json

import numpy as np

from kantarell.forberakna import berakna, demodata, skriv
from kantarell.rutnat import BLOCK, FALT, Rutnat, avkoda_ruta, koda_block


def test_rutnatet_ligger_pa_jamna_50_m():
    n = Rutnat.kring(476012, 7002031, 476490, 7002470)
    assert n.x0 == 476000 and n.y0 == 7002500
    assert n.bredd == 10 and n.hojd == 10


def test_kodning_och_avkodning_av_en_ruta():
    falt = {f: np.full((BLOCK, BLOCK), np.nan) for f in FALT}
    falt["poang"][3, 7] = 0.84
    falt["gran"][3, 7] = 70
    falt["hojd"][3, 7] = 425
    ruta = avkoda_ruta(koda_block(falt), 3 * BLOCK + 7)
    assert abs(ruta["poang"] - 0.84) < 0.005
    assert ruta["gran"] == 70 and ruta["hojd"] == 425
    assert ruta["tall"] is None


def test_forberakningen_med_demodata(tmp_path):
    n = Rutnat.kring(476000, 7002000, 481000, 7007000)
    ut = berakna(n, demodata(n))
    meta = skriv(n, ut, [{"namn": "test", "vad": "", "datum": "", "licens": "", "url": ""}], tmp_path)
    assert meta["statistik"]["skogsrutor"] > 0
    assert len(list((tmp_path / "block").glob("*.bin.gz"))) == meta["statistik"]["block"]
    assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))["rutnat"]["ruta_m"] == 50
    # Varje block är fullt: 100 × 100 rutor × 14 byte
    for b in (tmp_path / "block").glob("*.bin.gz"):
        assert len(gzip.decompress(b.read_bytes())) == BLOCK * BLOCK * len(FALT)
    # Tiles finns på alla zoomnivåer och är giltiga PNG-filer
    tiles = meta["tiles"]
    for z in range(tiles["minzoom"], tiles["maxzoom"] + 1):
        filer = list((tmp_path / "tiles" / str(z)).rglob("*.png"))
        assert filer and all(f.read_bytes()[:8] == bytes.fromhex("89504e470d0a1a0a") for f in filer)
    assert sum(1 for _ in (tmp_path / "tiles").rglob("*.png")) == meta["statistik"]["tiles"]


def test_skog_kraver_trad_eller_avverkning_och_inte_vatten():
    from kantarell.kallor import arSkog
    nan = np.nan
    data = {"tradhojd": np.array([[15, 1.5, 1.5, 15]]), "ar_sedan_avverkning": np.array([[nan, 5, nan, nan]]),
            "fukt": np.array([[2, 2, 2, nan]])}
    assert arSkog(data).tolist() == [[True, True, False, False]]   # hög skog, färskt hygge, kalmark, vatten


def test_rangen_gor_guld_av_de_basta_tio_procenten():
    from kantarell.forberakna import farg, rang
    poang = np.array([[0.9] * 90 + [0.95] * 10 + [np.nan]])
    r = rang(poang)
    assert np.isnan(r[0, -1])
    assert r[0, 0] == 0.9 and r[0, 95] == 1.0
    rgba = farg(r)
    assert rgba[0, 95, 0] == 255 and rgba[0, -1, 3] == 0


def test_tatort_raknas_inte_som_skog():
    from kantarell.kallor import arSkog, tatort
    bebyggd = np.zeros((20, 20))
    bebyggd[2:7, 2:7] = 0.6          # ett villaområde: hälften av marken är hus, vägar och tomter
    bebyggd[15, 15] = 1.0            # ett ensamt hus i skogen
    bebyggd[:, 10] = 0.2             # en skogsbilväg (10 m bred) genom rutorna
    t = tatort(bebyggd)
    assert t[4, 4] and t[2, 2]       # mitt i och i kanten av villaområdet
    assert not t[15, 15]             # ett hus gör ingen tätort
    assert not t[12, 4]              # skogen intill
    assert not t[12, 10]             # vägen
    data = {"tradhojd": np.full((20, 20), 15.0), "ar_sedan_avverkning": np.full((20, 20), np.nan),
            "fukt": np.full((20, 20), 2.0), "tatort": t}
    skog = arSkog(data)
    assert not skog[4, 4] and skog[15, 15] and skog[12, 4]

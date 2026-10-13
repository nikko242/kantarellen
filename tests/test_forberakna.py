"""Rutnätet, kodningen av block och förberäkningen från början till slut med demodata."""
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
    assert (tmp_path / "poang.png").exists()
    assert meta["statistik"]["skogsrutor"] > 0
    assert len(list((tmp_path / "block").glob("*.bin"))) == meta["statistik"]["block"]
    assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))["rutnat"]["ruta_m"] == 50
    # Varje block är fullt: 100 × 100 rutor × 14 byte
    for b in (tmp_path / "block").glob("*.bin"):
        assert b.stat().st_size == BLOCK * BLOCK * len(FALT)


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

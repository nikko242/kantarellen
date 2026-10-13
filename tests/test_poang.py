"""Poängreglerna prövade med påhittade rutor där svaret är känt (Saida: kvalitetskravet "Poängreglerna testas med pytest")."""
import pytest

from kantarell.poang import Ruta, bedom, ramp

GAMMAL_GRANSKOG = Ruta(gran=75, tall=10, bjork=10, tradhojd=18, jordart=1, fukt=2, hojd=420)


def test_gammal_granskog_pa_moran_ger_hog_poang():
    b = bedom(GAMMAL_GRANSKOG)
    assert b.poang is not None and b.poang > 0.9
    assert b.begransas_av is None and b.saknas == []


def test_farskt_hygge_ger_lag_poang_och_begransar():
    b = bedom(Ruta(gran=75, tall=10, bjork=10, tradhojd=2, ar_sedan_avverkning=4, jordart=1, fukt=2, hojd=420))
    assert b.poang == 0.0
    assert b.begransas_av == "alder"


def test_aldre_hygge_ger_lag_men_inte_noll():
    b = bedom(Ruta(gran=75, tall=10, tradhojd=8, ar_sedan_avverkning=20, jordart=1, fukt=2, hojd=420))
    assert b.faktorer["alder"] == 0.3
    assert b.poang < bedom(GAMMAL_GRANSKOG).poang


def test_torv_begransar_rutan():
    b = bedom(Ruta(gran=75, tall=10, tradhojd=18, jordart=6, fukt=4, hojd=420))
    assert b.poang == 0.0
    assert b.begransas_av in ("jordart", "fukt")


def test_lovskog_ger_lagre_poang_an_barrskog():
    lov = bedom(Ruta(gran=5, tall=5, bjork=90, tradhojd=18, jordart=1, fukt=2, hojd=420))
    assert lov.poang < bedom(GAMMAL_GRANSKOG).poang
    assert lov.faktorer["tradslag"] == 0.0


def test_bjorkinslag_hojer_tradslaget():
    utan = bedom(Ruta(gran=50, tall=0, bjork=0, tradhojd=18))
    med = bedom(Ruta(gran=50, tall=0, bjork=15, tradhojd=18))
    assert med.faktorer["tradslag"] == pytest.approx(utan.faktorer["tradslag"] + 0.1)


def test_ovan_tradgransen_ger_ingen_kantarell():
    b = bedom(Ruta(gran=60, tall=20, tradhojd=6, jordart=1, fukt=2, hojd=950))
    assert b.faktorer["hojd"] == 0.0
    assert b.poang == 0.0


def test_saknad_data_raknas_bort_och_markeras():
    b = bedom(Ruta(gran=75, tall=10, tradhojd=18))
    assert b.saknas == ["jordart", "fukt", "hojd"]
    assert b.poang is not None and b.poang > 0.9


def test_utan_tradslag_ar_rutan_inte_skog():
    b = bedom(Ruta(tradhojd=18, jordart=1, fukt=2, hojd=420))
    assert b.poang is None


def test_ramp_at_bada_hallen():
    assert ramp(10, 5, 15) == 0.5
    assert ramp(800, 900, 700) == 0.5
    assert ramp(0, 5, 15) == 0.0 and ramp(20, 5, 15) == 1.0


def test_falten_ger_samma_svar_som_bedom():
    import numpy as np

    from kantarell.poang import bedom_falt
    rng = np.random.default_rng(1)
    n = 5000
    def med_luckor(v, andel=0.15):
        return np.where(rng.random(n) < andel, np.nan, v)
    d = {"gran": med_luckor(rng.integers(0, 100, n).astype(float)), "tall": med_luckor(rng.integers(0, 60, n).astype(float)),
         "bjork": med_luckor(rng.integers(0, 50, n).astype(float)), "tradhojd": med_luckor(rng.integers(0, 30, n).astype(float)),
         "ar_sedan_avverkning": med_luckor(rng.integers(0, 60, n).astype(float), 0.7),
         "jordart": med_luckor(rng.integers(1, 10, n).astype(float)), "fukt": med_luckor(rng.integers(1, 6, n).astype(float)),
         "hojd": med_luckor(rng.integers(200, 1100, n).astype(float))}
    ut = bedom_falt(d)
    for i in range(n):
        v = {k: (None if np.isnan(a[i]) else a[i]) for k, a in d.items()}
        for k in ("ar_sedan_avverkning", "jordart", "fukt"):
            v[k] = None if v[k] is None else int(v[k])
        b = bedom(Ruta(**v))
        assert (b.poang is None) == np.isnan(ut["poang"][i])
        if b.poang is not None:
            # avrundningen till tre decimaler kan slå åt olika håll när summan räknas i en annan ordning
            assert b.poang == pytest.approx(ut["poang"][i], abs=0.0011)
        for k, x in b.faktorer.items():
            assert (x is None) == np.isnan(ut[f"f_{k}"][i])
            if x is not None:
                assert x == pytest.approx(ut[f"f_{k}"][i])

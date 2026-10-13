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

# -*- coding: utf-8 -*-
"""O <select> nativo nao deixava DIGITAR: os_busca.js poe uma busca por cima (21/09)."""
import io
import os

_ST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "os_creator", "os_web", "static")


def _ler(nome):
    return io.open(os.path.join(_ST, nome), encoding="utf-8").read()


def test_a_busca_e_carregada_em_todas_as_telas():
    """No base.html: uma tela nova ja nasce com a busca, sem ninguem lembrar de ligar."""
    base = io.open(os.path.join(os.path.dirname(_ST), "templates", "base.html"),
                   encoding="utf-8").read()
    assert "os_busca.js" in base


def test_o_select_original_continua_mandando():
    """A decisao que evitou reescrever as telas: o <select> fica na pagina, escondido, guardando
    o valor — `cbCli.value` e o `onchange` de sempre continuam valendo."""
    js = _ler("os_busca.js")
    assert "sel.selectedIndex = idx" in js
    assert "new Event('change'" in js
    css = _ler("os.css")
    assert ".osb select{position:absolute;opacity:0" in css


def test_filtra_pelo_meio_e_sem_acento():
    """O nativo so pula para a inicial. A busca casa no MEIO e ignora acento — com 60 usinas
    'taguai' tem de achar 'Thopen - Taguaí 1 e 2 - SP'."""
    js = _ler("os_busca.js")
    assert "normalize('NFD')" in js and "includes(f)" in js


def test_le_as_opcoes_na_hora_de_abrir():
    """Usinas e responsaveis chegam por fetch DEPOIS da tela pronta; lista congelada na montagem
    mostraria o vazio para sempre."""
    js = _ler("os_busca.js")
    assert "opcoes()" in js and "function pintar" in js


def test_selects_curtos_ficam_como_estao():
    js = _ler("os_busca.js")
    assert "MIN_OPC" in js and ">= MIN_OPC" in js

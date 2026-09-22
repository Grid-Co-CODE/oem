# tests/test_os_web_engenharia.py
"""Área Engenharia na web (card "Engenharia"): a MESMA moldura do desktop (steps/engenharia/tela.py) — título, o aviso de
área em construção e o Voltar. Nasce vazia de propósito: o conteúdo é da Engenharia (docs/ambiente-compartilhado-engenharia.md)."""
import pytest

import api
from os_web import criar_app
from steps import engenharia as area

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"})
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


def test_a_area_abre_com_a_moldura_do_desktop(cli):
    r = cli.get("/os/engenharia")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert area.TITULO in html and area.DESCRICAO in html                      # descritor da área: título e descrição do card
    assert "Área em construção pela Engenharia. O primeiro fluxo será OS de ETM." in html   # o texto da tela do desktop
    assert "Voltar" in html


def test_sem_sessao_vai_para_o_login(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    r = app.test_client().get("/os/engenharia")
    assert r.status_code == 302 and "/os/login" in r.headers["Location"]

# tests/test_os_web_engenharia_supervisorio.py
"""O supervisório da Engenharia ligado na área Engenharia da web (Levi, 27/09/2026) — só a ligação: o endereço mora no
.env do servidor, nunca no código, e sem ele a área fica como sempre foi. Os endereços aqui são inventados."""
import pytest

import api
from os_web import criar_app, engenharia_web as ew, rotas

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"


@pytest.fixture
def cli(monkeypatch):
    rotas._MEMO.clear()
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 0)
    monkeypatch.setattr(api, "assets_cache_info", lambda: {"ts": 0, "n": 0, "idade_h": 0.0, "expirado": True})
    monkeypatch.setattr(api, "_read_asset_cache", lambda: None)
    monkeypatch.delenv("OS_WEB_SUPERVISORIO_URL", raising=False)
    monkeypatch.delenv("OS_WEB_SUPERVISORIO_NOME", raising=False)
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "pessoa@teste.invalid", "perfil": "ADMINISTRATOR"}
    return c


def test_sem_endereco_a_area_fica_como_era(cli):
    h = cli.get("/os/engenharia").get_data(as_text=True)
    assert "<iframe" not in h and "entra aqui assim que tiver o endereço" in h
    inicio = cli.get("/os/").get_data(as_text=True)
    eng = inicio[inicio.index('data-chave="eng"'):]
    assert "em construção" in eng[:600]


def test_com_endereco_a_area_mostra_o_supervisorio(cli, monkeypatch):
    monkeypatch.setenv("OS_WEB_SUPERVISORIO_URL", "https://supervisorio.exemplo.invalid/painel")
    monkeypatch.setenv("OS_WEB_SUPERVISORIO_NOME", "Supervisório de teste")
    h = cli.get("/os/engenharia").get_data(as_text=True)
    assert '<iframe src="https://supervisorio.exemplo.invalid/painel"' in h and "Supervisório de teste" in h
    assert 'target="_blank" rel="noopener noreferrer"' in h                    # o "abrir em outra aba"
    inicio = cli.get("/os/").get_data(as_text=True)
    eng = inicio[inicio.index('data-chave="eng"'):]
    assert '<a href="/os/engenharia">Supervisório</a>' in eng[:900] and "em construção" not in eng[:600]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://x", "https://a b", "", 'https://x" onload="y'])
def test_endereco_que_nao_e_http_nao_vira_quadro(monkeypatch, url):
    monkeypatch.setenv("OS_WEB_SUPERVISORIO_URL", url)
    assert ew.supervisorio() == {}


def test_o_nome_padrao(monkeypatch):
    monkeypatch.setenv("OS_WEB_SUPERVISORIO_URL", "http://127.0.0.1:5099/")
    monkeypatch.delenv("OS_WEB_SUPERVISORIO_NOME", raising=False)
    assert ew.supervisorio() == {"url": "http://127.0.0.1:5099/", "nome": ew.NOME_PADRAO}

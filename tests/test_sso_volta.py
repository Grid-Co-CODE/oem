# tests/test_sso_volta.py
"""SSO da web pelo app instalado (Levi, 12/09/2026: "nao tem como abrir uma aba para a pessoa logar, que nem o OS
Creator faz?"). Um navegador comum nao le a sessao de outro site; o app le, porque leva o proprio navegador embutido
(steps/sso_login.py). Entao a pagina de login da web chama `gridos://sso?volta=<url do /os/login>`: o app abre a janela
de login que a equipe ja conhece, a pessoa entra pela Microsoft, e ele devolve o navegador em `volta#sso=<jwt>` — a
pagina entra sozinha. Qt-free aqui: a janela e um parametro, para o teste nao precisar do WebEngine."""
import pytest

import api
import sso_volta

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.c2lnbmF0dXJlLWZha2UtcGFyYS10ZXN0ZQ"


def test_volta_so_para_a_plataforma():
    assert sso_volta.volta_valida("https://clusters-interim-weapon-plays.trycloudflare.com/os/login")
    assert sso_volta.volta_valida("http://127.0.0.1:5050/os/login") and sso_volta.volta_valida("http://localhost:5050/os/login")
    assert sso_volta.volta_valida("https://plataforma.gridco.com.br/os/login")
    assert not sso_volta.volta_valida("https://malicioso.com/os/login")            # o token so volta para a nossa casa
    assert not sso_volta.volta_valida("https://x.trycloudflare.com/outra")        # e so para a pagina de login
    assert not sso_volta.volta_valida("javascript:alert(1)") and not sso_volta.volta_valida("")


def test_url_de_volta_leva_o_token_no_fragmento():
    """Fragmento, nunca query: o navegador nao manda o `#...` ao servidor, entao o JWT nao passa por log nenhum."""
    u = sso_volta.url_de_volta("http://127.0.0.1:5050/os/login", JWT)
    assert u == "http://127.0.0.1:5050/os/login#sso=" + JWT
    assert "?" not in u


class _Janela:
    """Duble da SsoLoginDialog: exec() aceita e .token traz o JWT (ou cancela)."""
    def __init__(self, token=JWT, aceita=True):
        self.token, self._aceita = token, aceita
    def exec(self):
        return 1 if self._aceita else 0


def test_tratar_abre_a_janela_salva_a_sessao_do_app_e_volta_ao_navegador(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "LOGIN_JWT_FILE", str(tmp_path / "fracttal_login.txt"))
    abertos = []
    res = sso_volta.tratar({"_acao": "sso", "volta": "http://127.0.0.1:5050/os/login"},
                           dialogo_cls=lambda: _Janela(), abrir=lambda u: abertos.append(u))
    assert res["ok"] is True
    assert abertos == ["http://127.0.0.1:5050/os/login#sso=" + JWT]
    assert api._read_jwt() == JWT                                                   # o app fica logado tambem


def test_cancelar_nao_abre_nada_e_volta_invalida_nem_abre_a_janela(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "LOGIN_JWT_FILE", str(tmp_path / "fracttal_login.txt"))
    abertos, janelas = [], []
    def _cls():
        janelas.append(1); return _Janela(aceita=False)
    res = sso_volta.tratar({"_acao": "sso", "volta": "http://127.0.0.1:5050/os/login"}, dialogo_cls=_cls, abrir=abertos.append)
    assert res["ok"] is False and abertos == [] and janelas == [1]
    res = sso_volta.tratar({"_acao": "sso", "volta": "https://malicioso.com/os/login"}, dialogo_cls=_cls, abrir=abertos.append)
    assert res["ok"] is False and "volta" in res["motivo"] and janelas == [1]      # janela nao abriu de novo


def test_parse_do_deep_link_traz_a_acao_sso_e_a_volta():
    from urllib.parse import quote
    import main
    d = main._parse_gridos(["gridos://sso?volta=" + quote("http://127.0.0.1:5050/os/login", safe="")])
    assert d["_acao"] == "sso" and d["volta"] == "http://127.0.0.1:5050/os/login"

# tests/test_os_web_oauth_volta_fixa.py
"""O callback do OAuth do Fracttal tem de ser IGUAL ao registrado no consumidor ("Integração mal configurada: 'callback_url'
inválido", 12/09/2026, quando o Levi testou pelo túnel). O túnel muda de endereço a cada queda, e o consumidor nao pode mudar
junto. Saida: um endereco FIXO de volta (uma pagina estatica, o "relay") registrado no Fracttal; o `state` leva, alem do
nonce, o endereco real de volta desta sessao (o tunel de hoje), e o relay so faz o navegador seguir para la — apenas para
hosts da nossa casa. Sem FRACTTAL_OAUTH_VOLTA no .env tudo fica como antes (o callback e o proprio tunel)."""
import pytest

import api
from os_web import criar_app, oauth_fracttal

VOLTA = "https://x.trycloudflare.com/os/login/fracttal/volta"
RELAY = "https://grid-co-code.github.io/os-volta/"


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "CLIENT_ID", "cid"); monkeypatch.setattr(api, "CLIENT_SECRET", "segredo")
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 0)
    return app.test_client()


def test_state_leva_a_volta_real_e_o_relay_a_recupera_so_para_a_nossa_casa():
    s = oauth_fracttal.novo_state(VOLTA)
    assert s.count(".") == 1 and oauth_fracttal.volta_do_state(s) == VOLTA
    assert oauth_fracttal.destino_do_relay({"code": "c1", "state": s}) == VOLTA + "?code=c1&state=" + s
    forjado = oauth_fracttal.novo_state("https://malicioso.com/os/login/fracttal/volta")
    assert oauth_fracttal.destino_do_relay({"code": "c1", "state": forjado}) is None       # host fora da casa: nao segue
    assert oauth_fracttal.destino_do_relay({"state": s}) is None                          # sem code nao ha o que entregar
    assert oauth_fracttal.destino_do_relay({"code": "c1", "state": "semponto"}) is None
    assert oauth_fracttal.volta_do_state("nonce.@@@") == ""
    # o Fracttal negou: o relay repassa o erro para a volta real, que sabe mostrar
    assert oauth_fracttal.destino_do_relay({"error": "access_denied", "error_description": "nao", "state": s}) == VOLTA + "?error=access_denied&error_description=nao&state=" + s


def test_com_volta_fixa_o_fracttal_recebe_o_relay_e_a_troca_do_codigo_usa_o_mesmo_endereco(cli, monkeypatch):
    monkeypatch.setenv("FRACTTAL_OAUTH_VOLTA", RELAY)
    r = cli.get("/os/login/fracttal?volta=" + VOLTA + "&next=/os/")
    assert r.status_code == 302 and "redirect_uri=https%3A%2F%2Fgrid-co-code.github.io%2Fos-volta%2F" in r.headers["Location"]
    with cli.session_transaction(path="/os/") as s:
        state = s["oauth_state"]
        assert s["oauth_redirect"] == RELAY and s["oauth_volta"] == VOLTA and oauth_fracttal.volta_do_state(state) == VOLTA
    usados = {}
    monkeypatch.setattr(oauth_fracttal, "trocar_codigo", lambda code, redirect: usados.update(code=code, redirect=redirect) or {"access_token": "tok", "expires_in": 3600})
    monkeypatch.setattr(oauth_fracttal, "diagnosticar", lambda tok: {"rpc_ok": True, "rest_ok": True, "nome": "Levi Maia", "perfil": "ADMINISTRATOR", "email": "levi@gridco.com.br", "rpc_erro": "", "jwt": False})
    r = cli.get("/os/login/fracttal/volta?code=c0d3&state=" + state)
    assert r.status_code == 302 and usados == {"code": "c0d3", "redirect": RELAY}          # a troca repete o redirect_uri do authorize, como o RFC exige


def test_sem_volta_fixa_o_callback_continua_sendo_o_proprio_tunel(cli, monkeypatch):
    monkeypatch.delenv("FRACTTAL_OAUTH_VOLTA", raising=False)
    r = cli.get("/os/login/fracttal?volta=" + VOLTA)
    assert "redirect_uri=https%3A%2F%2Fx.trycloudflare.com%2Fos%2Flogin%2Ffracttal%2Fvolta" in r.headers["Location"]
    with cli.session_transaction(path="/os/") as s:
        assert s["oauth_redirect"] == VOLTA


def test_pagina_do_relay_segue_a_mesma_regra_do_python():
    """A pagina e estatica (GitHub Pages, Cloudflare Pages, qualquer host fixo): le code/state, decodifica a volta e so segue
    para a nossa casa. O teste garante que ela existe, le os mesmos campos e carrega a mesma lista de hosts."""
    html = oauth_fracttal.pagina_relay()
    assert "state" in html and "code" in html and "error_description" in html and oauth_fracttal.CAMINHO_VOLTA in html
    assert oauth_fracttal._HOSTS_OK.pattern in html                    # a MESMA expressao de hosts, caractere por caractere
    assert "malicioso" not in html and "<script" in html

# tests/test_os_web_sso.py
"""Entrar com Microsoft / SSO na web (Levi, 12/09/2026: "Não tem a opção de entrar com SSO"). O app captura o token
num navegador embutido; um navegador comum não deixa nossa página ler nada de app.fracttal.com. O caminho na web é o
mesmo truque, só que quem lê a sessão é um FAVORITO (bookmarklet) que a pessoa clica na aba do Fracttal depois de entrar
pela Microsoft: ele varre localStorage/sessionStorage/cookies (igual ao _POLL_JS do app), copia o JWT e a pessoa cola
no login da web. Aqui se testa a costura: extrair o JWT do que foi colado, validar ao vivo e abrir a sessão."""
import pytest

import api
from os_web import criar_app, sessao, sso

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.c2lnbmF0dXJlLWZha2UtcGFyYS10ZXN0ZQ"


def test_extrai_o_jwt_do_que_a_pessoa_colou():
    assert sso.extrair_jwt(JWT) == JWT
    assert sso.extrair_jwt("Bearer " + JWT) == JWT
    assert sso.extrair_jwt("curl 'https://app.fracttal.com/rpc/proxy' -H 'authorization: Bearer " + JWT + "' -H 'x-version: web'") == JWT
    assert sso.extrair_jwt('{"token":"' + JWT + '","user":1}') == JWT
    assert sso.extrair_jwt("") == "" and sso.extrair_jwt("nada aqui") == "" and sso.extrair_jwt(None) == ""


def test_bookmarklet_e_um_link_javascript_com_a_varredura_do_app():
    href = sso.bookmarklet_href()
    assert href.startswith("javascript:") and "\n" not in href
    for trecho in ("fracttal.com", "localStorage", "sessionStorage", "document.cookie", "clipboard", "eyJ"):
        assert trecho in href, trecho


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"})
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 0)
    return app.test_client()


def test_a_tela_de_login_nao_tem_mais_nada_de_sso(cli):
    """Levi, 21/09: so e-mail e senha. Saiu o botao, saiu o favorito, saiu o `gridos://sso`.

    Eram tres formas de fazer a mesma coisa — a tela do proprio Fracttal, o app instalado e o
    favorito que copiava a sessao de uma aba aberta — e a que todo mundo usava era o formulario.
    A rota que ACEITA um token colado continua existindo (o teste abaixo ainda a exercita); o que
    sumiu foi a porta de entrada na tela."""
    html = cli.get("/os/login").get_data(as_text=True)
    for sumido in ("Entrar com Microsoft / SSO", 'href="javascript:', 'name="token"',
                   "gridos://sso", "Aguardando o login no Fracttal", "Copiar sessão do Fracttal"):
        assert sumido not in html, "sobrou na tela: %s" % sumido
    assert 'name="email"' in html and 'name="senha"' in html


def test_colar_uma_sessao_viva_entra_sem_senha(cli, monkeypatch):
    visto = {}
    def _viva():
        visto["jwt"] = api._read_jwt()                                  # a validacao ao vivo roda com o token colado
        return True
    monkeypatch.setattr(api, "is_logged_in", _viva)
    monkeypatch.setattr(api, "fracttal_login", lambda *a, **k: pytest.fail("senha nao entra no caminho do SSO"))
    r = cli.post("/os/login", data={"token": "Bearer " + JWT, "next": "/os/"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/") and visto["jwt"] == JWT
    assert "os_sessao=" in r.headers.get("Set-Cookie", "")
    with cli.session_transaction(path="/os/") as s:
        assert s.get("jwt") == JWT and s.get("conta", {}).get("nome") == "Levi Maia"


def test_sessao_morta_ou_lixo_volta_com_a_explicacao(cli, monkeypatch):
    monkeypatch.setattr(api, "is_logged_in", lambda: False)
    r = cli.post("/os/login", data={"token": JWT})
    html = r.get_data(as_text=True)
    assert r.status_code == 401 and "Feche a aba do Fracttal" in html and "os_sessao=" not in r.headers.get("Set-Cookie", "")
    r = cli.post("/os/login", data={"token": "isso nao e um token"})
    assert r.status_code == 401 and "Não achei um token" in r.get_data(as_text=True)


def test_a_tela_de_login_nao_roda_mais_script_nenhum(cli):
    """O script que lia `location.hash` para pescar o token do favorito foi junto com o resto.
    Tela de login sem JavaScript e uma tela a menos para dar errado."""
    html = cli.get("/os/login").get_data(as_text=True)
    assert "location.hash" not in html and "#sso=" not in html
    assert "<script" not in html.split("os-login")[1]

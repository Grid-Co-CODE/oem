# tests/test_os_web_sessao.py
"""OS Creator na web (12/09/2026, Levi: "traga toda a estrutura do OS Creator para a plataforma"): a sessao do
Fracttal deixa de ser um arquivo unico da maquina e passa a ser UMA POR PESSOA, presa a requisicao. O `api.py`
continua o mesmo do desktop — o que muda e de onde `_read_jwt`/`_save_jwt`/`_clear_jwt` leem e gravam quando ha
uma requisicao web em curso. Fora de requisicao, nada muda: o desktop segue no arquivo/keyring."""
import os

import pytest

import api
from os_web import sessao
from os_web import criar_app

JWT_A = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # {"email":"levi@gridco.com.br","exp":9999999999}
JWT_B = "bbb.eyJlbWFpbCI6ImFuYUBncmlkY28uY29tLmJyIiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"     # {"email":"ana@gridco.com.br","exp":9999999999}


@pytest.fixture(autouse=True)
def _arquivo_de_jwt_em_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "LOGIN_JWT_FILE", str(tmp_path / "fracttal_login.txt"))
    monkeypatch.delenv("FRACTTAL_LOGIN_JWT", raising=False)
    sessao.instalar(api)
    yield


def test_fora_de_requisicao_o_api_continua_lendo_o_arquivo(tmp_path):
    with open(api.LOGIN_JWT_FILE, "w", encoding="utf-8") as f:
        f.write(JWT_A)
    assert api._read_jwt() == JWT_A
    assert sessao.jwt_atual() == ""                                 # nenhuma requisicao em curso


def test_dentro_do_contexto_le_o_jwt_da_pessoa_e_nao_o_arquivo(tmp_path):
    with open(api.LOGIN_JWT_FILE, "w", encoding="utf-8") as f:
        f.write(JWT_A)
    with sessao.contexto(JWT_B):
        assert api._read_jwt() == JWT_B
        assert api.current_user() == "ana@gridco.com.br"
    assert api._read_jwt() == JWT_A                                 # saiu do contexto: arquivo de novo


def test_save_e_clear_dentro_do_contexto_nao_tocam_o_arquivo(tmp_path):
    with sessao.contexto(""):
        api._save_jwt(JWT_A)                                        # o que o fracttal_login faz ao logar
        assert sessao.jwt_atual() == JWT_A and sessao.jwt_novo() == JWT_A
        assert not os.path.exists(api.LOGIN_JWT_FILE)
        api._clear_jwt()                                            # o que o _rpc_call faz em USER_NOT_LOGIN
        assert sessao.morta() is True and sessao.jwt_atual() == ""


def test_refresh_do_token_atualiza_a_sessao_da_pessoa(monkeypatch):
    """_rpc_try_refresh grava o token renovado direto no arquivo; na web ele tem de cair na sessao — o Fracttal
    mata o JWT anterior a cada renovacao, entao a proxima requisicao com o velho daria USER_NOT_LOGIN."""
    class R:
        status_code = 200
        def json(self): return {"token": JWT_B}
    monkeypatch.setattr(api.requests, "post", lambda *a, **k: R())
    with sessao.contexto(JWT_A):
        assert api._rpc_try_refresh(JWT_A) == JWT_B
        assert sessao.jwt_atual() == JWT_B and sessao.jwt_novo() == JWT_B
    assert not os.path.exists(api.LOGIN_JWT_FILE)


def test_instalar_e_idempotente():
    antes = api._read_jwt
    sessao.instalar(api)
    sessao.instalar(api)
    assert api._read_jwt is antes


# ── integracao com o Flask ────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"})
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 3)
    return app.test_client()


def _login_ok(email, senha):
    assert (email, senha) == ("levi@gridco.com.br", "s3nh4")
    api._save_jwt(JWT_A)                                            # igual ao fracttal_login real
    return {"email": email, "jwt_exp": 9999999999}


def test_sem_sessao_a_area_redireciona_para_o_login(cli):
    r = cli.get("/os/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/login?next=%2Fos%2F")


def test_login_guarda_o_jwt_no_cookie_e_a_proxima_requisicao_usa_ele(cli, monkeypatch):
    monkeypatch.setattr(api, "fracttal_login", _login_ok)
    r = cli.post("/os/login", data={"email": "levi@gridco.com.br", "senha": "s3nh4", "next": "/os/"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/")
    cookie = r.headers.get("Set-Cookie", "")
    assert "os_sessao=" in cookie and "Path=/os" in cookie and "HttpOnly" in cookie
    visto = {}
    # o perfil fica guardado na sessao desde o login (como o app, que o busca no boot); o selo do card Performance
    # e buscado a cada abertura da tela — e ele tem de sair com o JWT da pessoa
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: visto.setdefault("jwt", api._read_jwt()) and 0)
    r = cli.get("/os/")
    assert r.status_code == 200 and visto["jwt"] == JWT_A


def test_senha_errada_volta_para_o_formulario_com_a_mensagem_do_api(cli, monkeypatch):
    def _falha(email, senha):
        raise api.FracttalError("E-mail ou senha incorretos.")
    monkeypatch.setattr(api, "fracttal_login", _falha)
    r = cli.post("/os/login", data={"email": "x@gridco.com.br", "senha": "errada"})
    assert r.status_code == 401 and "E-mail ou senha incorretos." in r.get_data(as_text=True)
    assert "os_sessao=" not in r.headers.get("Set-Cookie", "")


def test_sessao_derrubada_no_fracttal_manda_de_volta_ao_login_com_aviso(cli, monkeypatch):
    monkeypatch.setattr(api, "fracttal_login", _login_ok)
    cli.post("/os/login", data={"email": "levi@gridco.com.br", "senha": "s3nh4"})

    def _morreu():
        api._clear_jwt()                                            # o _rpc_call faz isto ao ver USER_NOT_LOGIN
        raise api.SessionExpired("USER_NOT_LOGIN")
    monkeypatch.setattr(api, "contar_minhas_analises", _morreu)     # a primeira chamada ao Fracttal da tela inicial
    r = cli.get("/os/")
    assert r.status_code == 302 and "/os/login" in r.headers["Location"]
    r = cli.get(r.headers["Location"])
    assert "sessão do fracttal caiu" in r.get_data(as_text=True).lower()
    assert cli.get("/os/").status_code == 302                       # o cookie foi limpo


def test_logout_limpa_o_cookie(cli, monkeypatch):
    monkeypatch.setattr(api, "fracttal_login", _login_ok)
    cli.post("/os/login", data={"email": "levi@gridco.com.br", "senha": "s3nh4"})
    assert cli.get("/os/").status_code == 200
    r = cli.get("/os/logout")
    assert r.status_code == 302 and cli.get("/os/").status_code == 302


def test_a_senha_nao_fica_em_lugar_nenhum(cli, monkeypatch):
    """A senha so serve para obter o JWT (mesma regra do desktop): nem cookie, nem sessao, nem log."""
    monkeypatch.setattr(api, "fracttal_login", _login_ok)
    r = cli.post("/os/login", data={"email": "levi@gridco.com.br", "senha": "s3nh4"})
    with cli.session_transaction(path="/os/") as s:                 # o cookie e Path=/os: fora dele a sessao e vazia
        assert "s3nh4" not in repr(dict(s)) and s.get("jwt") == JWT_A
    assert "s3nh4" not in r.headers.get("Set-Cookie", "")

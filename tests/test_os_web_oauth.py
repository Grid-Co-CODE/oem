# tests/test_os_web_oauth.py
"""Entrar com o Fracttal (OAuth authorization_code) — a "ponte com o app do Fracttal para logar" que o Levi pediu em
12/09/2026. A doc oficial lista `https://one.fracttal.com/oauth/authorize` e o grant `authorization_code`; sondado ao
vivo, o authorize redireciona para a tela `accessgrant` do Fracttal One levando o nosso callback. Fluxo: a pessoa loga
na tela DELES (Microsoft incluida), autoriza, volta com `code`; trocamos pelo token e diagnosticamos ao vivo o que ele
pode fazer (RPC = criar OS como o app; REST = so leitura). HTTP e um duble: o que se testa e a costura."""
import pytest

import api
from os_web import criar_app, oauth_fracttal

VOLTA = "https://x.trycloudflare.com/os/login/fracttal/volta"


def test_url_de_autorizacao_vai_para_o_fracttal_one_com_state_e_callback():
    u = oauth_fracttal.url_autorizacao("cid", VOLTA, "estado123")
    assert u.startswith("https://one.fracttal.com/oauth/authorize?")
    assert "response_type=code" in u and "client_id=cid" in u and "state=estado123" in u
    assert "redirect_uri=https%3A%2F%2Fx.trycloudflare.com%2Fos%2Flogin%2Ffracttal%2Fvolta" in u


def test_callback_so_para_a_plataforma():
    assert oauth_fracttal.callback_valido(VOLTA)
    assert oauth_fracttal.callback_valido("http://127.0.0.1:5050/os/login/fracttal/volta")
    assert not oauth_fracttal.callback_valido("https://malicioso.com/os/login/fracttal/volta")
    assert not oauth_fracttal.callback_valido("https://x.trycloudflare.com/os/login")


def test_troca_do_codigo_posta_o_formulario_e_cai_para_o_app_fracttal(monkeypatch):
    visto = []

    class R:
        def __init__(self, status, j): self.status_code, self._j = status, j
        def json(self): return self._j
    def _post(url, data=None, timeout=None, headers=None):
        visto.append((url, dict(data or {})))
        if "one.fracttal" in url:
            return R(404, {})                                             # o host da doc nao respondeu: tenta o app.
        return R(200, {"access_token": "tok-do-usuario", "expires_in": 3600, "refresh_token": "r1", "token_type": "Bearer"})
    monkeypatch.setattr(api.requests, "post", _post)
    monkeypatch.setattr(api, "CLIENT_ID", "cid"); monkeypatch.setattr(api, "CLIENT_SECRET", "segredo")
    t = oauth_fracttal.trocar_codigo("c0d3", VOLTA)
    assert t["access_token"] == "tok-do-usuario" and t["refresh_token"] == "r1"
    assert [u for u, _ in visto] == ["https://one.fracttal.com/oauth/token", "https://app.fracttal.com/oauth/token"]
    assert visto[0][1] == {"grant_type": "authorization_code", "code": "c0d3", "redirect_uri": VOLTA, "client_id": "cid", "client_secret": "segredo"}


def test_diagnostico_diz_o_que_o_token_pode_fazer(monkeypatch):
    def _rpc(method, params, timeout=45):
        assert api._read_jwt() == "tok-do-usuario"                        # a chamada roda com o token do OAuth
        return {"data": [{"name": "Levi Maia", "profiles_description": "ADMINISTRATOR", "email": "levi@gridco.com.br"}]}
    monkeypatch.setattr(api, "_rpc_call", _rpc)
    from os_web import sessao
    with sessao.contexto(""):
        d = oauth_fracttal.diagnosticar("tok-do-usuario")
    assert d["rpc_ok"] is True and d["nome"] == "Levi Maia" and d["perfil"] == "ADMINISTRATOR" and d["email"] == "levi@gridco.com.br"

    def _rpc_nao(method, params, timeout=45):
        raise api.FracttalError("INVALID_TOKEN")
    monkeypatch.setattr(api, "_rpc_call", _rpc_nao)
    with sessao.contexto(""):
        d = oauth_fracttal.diagnosticar("tok-do-usuario")
    assert d["rpc_ok"] is False and "INVALID_TOKEN" in d["rpc_erro"]


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "CLIENT_ID", "cid"); monkeypatch.setattr(api, "CLIENT_SECRET", "segredo")
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 0)
    return app.test_client()


def test_inicio_redireciona_ao_fracttal_e_guarda_state_e_callback(cli):
    r = cli.get("/os/login/fracttal?volta=" + VOLTA + "&next=/os/")
    assert r.status_code == 302 and r.headers["Location"].startswith("https://one.fracttal.com/oauth/authorize?")
    with cli.session_transaction(path="/os/") as s:
        assert s["oauth_state"] and s["oauth_state"] in r.headers["Location"] and s["oauth_volta"] == VOLTA and s["oauth_next"] == "/os/"
    assert cli.get("/os/login/fracttal?volta=https://malicioso.com/os/login/fracttal/volta").status_code == 400


def test_volta_com_state_errado_e_recusada(cli):
    with cli.session_transaction(path="/os/") as s:
        s["oauth_state"], s["oauth_volta"] = "bom", VOLTA
    r = cli.get("/os/login/fracttal/volta?code=c&state=ruim")
    assert r.status_code == 401 and "state" in r.get_data(as_text=True).lower()


def test_volta_boa_troca_o_codigo_e_abre_a_sessao_quando_o_rpc_aceita(cli, monkeypatch):
    with cli.session_transaction(path="/os/") as s:
        s["oauth_state"], s["oauth_volta"], s["oauth_next"] = "bom", VOLTA, "/os/"
    monkeypatch.setattr(oauth_fracttal, "trocar_codigo", lambda code, volta: {"access_token": "tok-do-usuario", "expires_in": 3600})
    monkeypatch.setattr(oauth_fracttal, "diagnosticar", lambda tok: {"rpc_ok": True, "rest_ok": True, "nome": "Levi Maia", "perfil": "ADMINISTRATOR", "email": "levi@gridco.com.br", "rpc_erro": "", "jwt": False})
    r = cli.get("/os/login/fracttal/volta?code=c0d3&state=bom")
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/")
    with cli.session_transaction(path="/os/") as s:
        assert s["jwt"] == "tok-do-usuario" and s["conta"]["nome"] == "Levi Maia" and "oauth_state" not in s


def test_volta_boa_mas_token_sem_rpc_mostra_o_diagnostico(cli, monkeypatch):
    with cli.session_transaction(path="/os/") as s:
        s["oauth_state"], s["oauth_volta"] = "bom", VOLTA
    monkeypatch.setattr(oauth_fracttal, "trocar_codigo", lambda code, volta: {"access_token": "tok", "expires_in": 3600})
    monkeypatch.setattr(oauth_fracttal, "diagnosticar", lambda tok: {"rpc_ok": False, "rest_ok": True, "nome": "", "perfil": "", "email": "", "rpc_erro": "INVALID_TOKEN", "jwt": False})
    r = cli.get("/os/login/fracttal/volta?code=c0d3&state=bom")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "não serve para criar OS" in html and "INVALID_TOKEN" in html and "REST" in html
    with cli.session_transaction(path="/os/") as s:
        assert "jwt" not in s


def test_a_tela_de_login_nao_oferece_mais_o_caminho_do_oauth(cli):
    """Levi, 21/09: so e-mail e senha. As ROTAS do OAuth continuam de pe (os testes acima
    seguem valendo) — o que sumiu foi a porta de entrada na tela."""
    html = cli.get("/os/login").get_data(as_text=True)
    assert "Entrar pela tela do Fracttal" not in html
    assert 'href="/os/login/fracttal' not in html


def test_email_da_sessao_vale_quando_o_token_nao_e_um_jwt_com_email():
    """`api.current_user()` le o e-mail do payload do JWT; um access_token OAuth pode ser opaco. Sem e-mail o
    `_current_user_info` nao acha a pessoa no personnel e o historico 'criadas por mim' morre. A sessao web guarda o
    e-mail (do diagnostico) e a costura responde por ele quando o token nao diz."""
    from os_web import sessao
    sessao.instalar(api)
    with sessao.contexto("tok-opaco-sem-payload", email="levi@gridco.com.br"):
        assert api.current_user() == "levi@gridco.com.br"
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImFuYUBncmlkY28uY29tLmJyIiwiZXhwIjo5OTk5OTk5OTk5fQ.c2lnbmF0dXJlLWZha2UtcGFyYS10ZXN0ZQ"
    with sessao.contexto(jwt, email="outro@gridco.com.br"):
        assert api.current_user() == "ana@gridco.com.br"                   # o JWT, quando diz, manda


def test_diagnostico_acha_o_nome_pelo_personnel_quando_o_token_nao_traz_email_no_load_account_info(monkeypatch):
    """13/09/2026: o Levi logou por SSO e o app o mostrou como 'Usuario' generico. O token do OAuth NAO traz e-mail como o
    de senha, e o companies.load_account_info nao devolveu o nome com esse token. A resolucao passa a: (1) tirar o e-mail dos
    claims do token (varios nomes de campo); (2) se o load_account_info nao trouxer o nome, procurar no personnel pelo e-mail."""
    import base64 as _b64, json as _json
    from os_web import sessao
    def _jwt_com(**claims):
        h = _b64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
        p = _b64.urlsafe_b64encode(_json.dumps(claims).encode()).decode().rstrip("=")
        return f"{h}.{p}.sig"
    def fake_rpc(method, params, timeout=45):
        if method == "companies.load_account_info":
            return {"data": [{"profiles_description": "TECNICO"}]}          # tem perfil, mas SEM name/email
        if method == "personnel.personnel_list":
            return {"data": [{"account_email": "levi.maia@gridco.com.br", "full_name": "Levi Maia", "id": 1414413}]}
        return {}
    monkeypatch.setattr(api, "_rpc_call", fake_rpc)
    monkeypatch.setattr(api, "_save_jwt", lambda t: None)
    with sessao.contexto(""):
        d = oauth_fracttal.diagnosticar(_jwt_com(preferred_username="levi.maia@gridco.com.br", id_company=4987))
    assert d["rpc_ok"] and d["email"] == "levi.maia@gridco.com.br" and d["nome"] == "Levi Maia" and d["perfil"] == "TECNICO"


def test_o_login_abre_no_formulario_e_nao_redireciona_mais(cli):
    """O oposto do que valia de 13/09 a 21/09.

    Ate aqui a pagina se redirecionava sozinha para a tela do Fracttal (`location.replace` no
    <head>) e o formulario so aparecia com `?manual=1`. Agora o formulario E a tela, e o
    `?manual=1` deixou de significar coisa alguma — o que ele mostrava virou o padrao."""
    html = cli.get("/os/login").get_data(as_text=True)
    assert "location.replace" not in html
    assert 'name="email"' in html and 'name="senha"' in html
    assert 'class="os-topo-voltar"' in html and 'href="/"' in html       # o Voltar continua
    assert cli.get("/os/login?manual=1").get_data(as_text=True) == html  # nao ha mais dois modos

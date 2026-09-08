# -*- coding: utf-8 -*-
"""O lado do app do relay de escrita (tickets_escrita): por onde a gravação sai.

Levi, 07/09: "quando a pessoa faz uma alteração para o BD manda uma mensagem para um canto seguro
onde tem o token, e aí faz essa mudança". O canto seguro é a plataforma; aqui se tranca que o app
manda para ela por padrão, com o JWT do Fracttal, que acha a URL dela no banco, e que traduz as
respostas em erros que a tela sabe explicar.
"""
import os

import pytest

import tickets_escrita as esc


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    monkeypatch.delenv(esc.RELAY_DIRETO_ENV, raising=False)
    monkeypatch.setattr(esc, "_jwt", lambda: "a.b.c")
    esc._relay.update(url="", quando=0.0, sheet=None)
    yield
    esc._relay.update(url="", quando=0.0, sheet=None)


class _R:
    def __init__(self, status=200, corpo=None, texto=""):
        self.status_code = status
        self._corpo = corpo
        self.text = texto if texto else ("" if corpo is None else __import__("json").dumps(corpo))
        self.content = self.text.encode()

    def json(self):
        if self._corpo is None:
            raise ValueError("sem json")
        return self._corpo


# ── quem grava ────────────────────────────────────────────────────────────────────────────
def test_por_padrao_a_escrita_sai_pelo_relay(monkeypatch):
    monkeypatch.setattr(esc, "_token", lambda: "tem-token-local")
    assert esc._transporte() is esc._via_plataforma, "com token local e sem a variável, foi direto"


def test_direto_so_com_a_variavel_E_token(monkeypatch):
    monkeypatch.setenv(esc.RELAY_DIRETO_ENV, "1")
    monkeypatch.setattr(esc, "_token", lambda: "")
    assert esc._transporte() is esc._via_plataforma, "sem token não existe caminho direto"
    monkeypatch.setattr(esc, "_token", lambda: "tok")
    assert esc._transporte() is None


def test_gravar_apagar_e_criar_usam_o_transporte_quando_ninguem_injeta(monkeypatch):
    vistos = []
    monkeypatch.setattr(esc, "_transporte",
                        lambda: (lambda m, s, r, c: vistos.append((m, s, r)) or {}))
    # 374 e não 387: a aba do diário só entra na lista de escrita quando `tickets_diario` a
    # libera em tempo de execução — aqui interessa o transporte, não a trava.
    esc.gravar_linha(128, 154, {"Usina": "X"}, ["Usina"])
    esc.apagar_linha(128, 154)
    esc.criar_linha(374, {"Usina": "y"}, ["Usina"])
    assert vistos == [("PUT", 128, 154), ("DELETE", 128, 154), ("POST", 374, None)]


def test_o_enviar_injetado_continua_valendo_mais_que_o_transporte(monkeypatch):
    monkeypatch.setattr(esc, "_transporte", lambda: (lambda *a: pytest.fail("usou o transporte")))
    assert esc.gravar_linha(128, 1, {"Usina": "X"}, ["Usina"], enviar=lambda *a: {"ok": 1}) == {"ok": 1}


# ── a URL da plataforma vem do banco ─────────────────────────────────────────────────────
def _banco(url="https://abc.trycloudflare.com"):
    def buscar(caminho):
        if caminho == "/api/sheets":
            return [{"id": 415, "workbook_key": "os_creator", "sheet_name": "temas"},
                    {"id": 500, "workbook_key": "os_creator", "sheet_name": "plataforma"}]
        assert caminho.startswith("/api/sheets/500/rows")
        return {"rows": [{"row_number": 1, "values": ["tunnel_url", url]},
                         {"row_number": 2, "values": ["quando", "2026-09-07 23:00:00"]}]}
    return buscar


def test_url_do_relay_e_lida_da_aba_plataforma_do_banco():
    assert esc.url_relay(buscar=_banco("https://abc.trycloudflare.com/")) == "https://abc.trycloudflare.com"


def test_url_fica_em_cache_e_forcar_rele(monkeypatch):
    vezes = []
    b = _banco()

    def buscar(c):
        vezes.append(c)
        return b(c)
    esc.url_relay(buscar=buscar, agora=1000.0)
    n = len(vezes)
    esc.url_relay(buscar=buscar, agora=1000.0 + 10)
    assert len(vezes) == n
    esc.url_relay(buscar=buscar, agora=1000.0 + 10, forcar=True)
    assert len(vezes) > n


def test_sem_url_publicada_cai_na_config_da_tela_e_depois_avisa(monkeypatch):
    vazio = lambda c: [] if c == "/api/sheets" else {"rows": []}
    import types
    falso_api = types.SimpleNamespace(load_dash_config=lambda: {"url": "https://manual.x"},
                                      _dash_url=lambda cfg: cfg["url"])
    monkeypatch.setitem(__import__("sys").modules, "api", falso_api)
    assert esc.url_relay(buscar=vazio) == "https://manual.x"
    esc._relay.update(url="", quando=0.0, sheet=None)
    falso_api._dash_url = lambda cfg: ""
    with pytest.raises(esc.RelayIndisponivel):
        esc.url_relay(buscar=vazio, forcar=True)


# ── a conversa com a plataforma ──────────────────────────────────────────────────────────
@pytest.fixture
def plataforma(monkeypatch):
    """Dublê da plataforma: guarda o que recebeu e responde o que o teste mandar."""
    box = {"resp": _R(200, {"row_number": 154}), "vistos": []}
    esc._relay.update(url="https://abc.trycloudflare.com", quando=__import__("time").time(), sheet=500)

    def request(metodo, url, headers=None, json=None, timeout=None):
        box["vistos"].append((metodo, url, headers, json))
        r = box["resp"]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(esc.requests, "request", request)
    return box


def test_manda_para_a_rota_certa_com_o_jwt_no_header(plataforma):
    out = esc._via_plataforma("PUT", 128, 154, {"headers": ["Usina"], "values": ["PTL200"]})
    assert out == {"row_number": 154}
    metodo, url, cab, corpo = plataforma["vistos"][0]
    assert (metodo, url) == ("PUT", "https://abc.trycloudflare.com/api/tickets/128/rows/154")
    assert cab["X-Fracttal-JWT"] == "a.b.c"
    assert corpo["values"] == ["PTL200"]


def test_post_sem_linha_e_delete_sem_corpo(plataforma):
    esc._via_plataforma("POST", 387, None, {"headers": ["quem"], "values": ["x"]})
    esc._via_plataforma("DELETE", 128, 7, None)
    assert plataforma["vistos"][0][1].endswith("/api/tickets/387/rows")
    assert plataforma["vistos"][1][1].endswith("/api/tickets/128/rows/7")
    assert plataforma["vistos"][1][3] is None


def test_401_vira_login_recusado_com_o_motivo(plataforma):
    plataforma["resp"] = _R(401, {"error": "o login do Fracttal expirou"})
    with pytest.raises(esc.RelayRecusou) as e:
        esc._via_plataforma("PUT", 128, 1, {})
    assert "expirou" in str(e.value)
    assert isinstance(e.value, esc.EscritaBloqueada), "a tela trata EscritaBloqueada; precisa continuar pegando"


def test_403_e_aba_fora_da_lista(plataforma):
    plataforma["resp"] = _R(403, {"error": "a aba 999 não está na lista"})
    with pytest.raises(esc.EscritaBloqueada):
        esc._via_plataforma("PUT", 999, 1, {})


def test_503_e_plataforma_indisponivel(plataforma):
    plataforma["resp"] = _R(503, {"error": "banco fora do ar"})
    with pytest.raises(esc.RelayIndisponivel):
        esc._via_plataforma("PUT", 128, 1, {})


def test_ligacao_recusada_rele_a_url_e_tenta_de_novo(plataforma, monkeypatch):
    """O túnel troca de endereço a cada subida. Falhou a ligação: relê a URL do banco UMA vez."""
    urls = ["https://velha.trycloudflare.com", "https://nova.trycloudflare.com"]
    monkeypatch.setattr(esc, "url_relay", lambda forcar=False, **k: urls[1] if forcar else urls[0])
    chamadas = []

    def request(metodo, url, **k):
        chamadas.append(url)
        if "velha" in url:
            raise esc.requests.ConnectionError("recusada")
        return _R(200, {})
    monkeypatch.setattr(esc.requests, "request", request)
    esc._via_plataforma("PUT", 128, 1, {})
    assert [u.split("/")[2] for u in chamadas] == ["velha.trycloudflare.com", "nova.trycloudflare.com"]


def test_resposta_vazia_do_banco_vira_dicionario_vazio(plataforma):
    plataforma["resp"] = _R(200, None, texto="")
    assert esc._via_plataforma("DELETE", 128, 7, None) == {}


def test_criar_aba_pelo_relay_vai_para_a_rota_de_workbook(plataforma):
    plataforma["resp"] = _R(201, {"id": 900})
    assert esc.criar_aba("tickets_performance", {"sheet_name": "v4"}) == {"id": 900}
    assert plataforma["vistos"][0][1].endswith("/api/tickets/workbooks/tickets_performance/sheets")


def test_o_diario_cria_a_aba_pelo_mesmo_caminho(monkeypatch):
    import tickets_diario as d
    monkeypatch.setattr(d, "_SHEET_ID", {})
    monkeypatch.setattr(esc, "criar_aba", lambda wb, corpo: {"id": 901, "wb": wb, "nome": corpo["sheet_name"]})
    sid = d.garantir_aba(listar=lambda: [])
    assert sid == 901

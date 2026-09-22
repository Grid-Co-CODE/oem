# tests/test_os_web_ativos.py
"""Ativos na web (card "Ativos"): o catálogo do Fracttal para CONSULTA, como a `steps/ativos.py` — árvore cliente→usina,
visão Lista/Hierarquia, chips de tipo, tabela Código/Ativo/Tipo/Usina, painel do ativo com as últimas 4 OS e o menu
"Criar OS neste ativo" que leva às telas que já existem. O filtro é todo local (no navegador), como no app."""
import ast
import os

import pytest

import api
import chamado_insp_spec as ci
from os_web import ativos_web, criar_app

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator")

CATALOGO = [
    {"id": 1, "code": "TAN2", "description": "Tanabi 2", "tipo": "Usina", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": None},
    {"id": 11, "code": "TAN2-INV-2.18", "description": "Inversor 2.18 {SMA Sunny}", "tipo": "Inversor", "cliente": "Thopen",
     "usina": "Thopen - Tanabi 2 - SP", "id_parent": 1, "id_type_item": 5, "id_group_task": 9},
    {"id": 12, "code": "TAN2-INV-2.19", "description": "Inversor 2.19", "tipo": "Inversor", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 1},
    {"id": 33, "code": "ARA-TRK-5", "description": "Tracker 5", "tipo": "Estrutura Trackers", "cliente": "2C", "usina": "2C - Araputanga 1 - MT", "id_parent": None},
]
OS_DO_ATIVO = [
    {"folio": 9700, "id": 500, "descricao": "a", "event_date": "2026-09-01T12:00:00Z", "status": "Concluída", "tipo_tarefa": "Corretiva"},
    {"folio": 9812, "id": 501, "descricao": "b", "event_date": "2026-09-12T11:00:00Z", "status": "Em Processo", "tipo_tarefa": "Corretiva / Religamento Remoto"},
]


def _literal(nome):
    with open(os.path.join(_APP, "steps", "ativos.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == nome for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(nome)


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"})
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: CATALOGO)
    monkeypatch.setattr(api, "assets_cache_info", lambda: {"ts": 1757800000, "n": 4, "idade_h": 30.0, "expirado": True})
    monkeypatch.setattr(api, "ultimas_os_do_ativo", lambda id_item, limite=10, com_tipo=True: OS_DO_ATIVO if id_item == 11 else [])
    monkeypatch.setattr(api, "codigos_os_recentes", lambda dias=30: ["TAN2-INV-2.18"])
    monkeypatch.setattr(ci, "descobrir_marca", lambda a, todos: "SMA" if a.get("id") == 11 else "")
    monkeypatch.setattr(ci, "aceita", lambda tipo: tipo == "Inversor")
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


def test_a_tela_tem_os_tres_paineis_e_os_textos_do_app(cli):
    html = cli.get("/os/ativos").get_data(as_text=True)
    for txt in ("Ativos", "CLIENTE / USINA", "buscar usina…", "VISÃO", "Lista", "Hierarquia", "TIPO", "Todos", "Inversor", "Trackers",
                "Cabine", "Estação Met.", "Skid", "Código", "Ativo", "Tipo", "Usina", "ATIVO SELECIONADO", "Marca", "Cliente",
                "ÚLTIMAS 4 OS", "selecione um ativo", "Criar OS neste ativo", "Atualizar", "código, nome, usina…", "Voltar"):
        assert txt in html, txt
    assert "[Ctrl+F]" in html


def test_constantes_iguais_as_do_app():
    assert ativos_web.TIPOS_CHIP == tuple(tuple(x) for x in _literal("TIPOS_CHIP"))
    assert ativos_web.LIMITE_TABELA == _literal("LIMITE_TABELA")
    assert ativos_web.DESTINOS_OS == tuple(tuple(x) for x in _literal("DESTINOS_OS"))
    assert ativos_web.COR_STATUS == _literal("COR_STATUS")
    assert all(t in api._PERF_PLANOS for _, t in ativos_web.DESTINOS_OS)        # as frases dos planos, não um plano fixo (item 17)


def test_catalogo_enxuto_e_info_da_lista(cli):
    d = cli.get("/os/api/ativos/catalogo").get_json()
    assert len(d["ativos"]) == 4 and d["info"]["expirado"] is True and d["info"]["n"] == 4
    a = next(x for x in d["ativos"] if x["id"] == 11)
    assert a == {"id": 11, "code": "TAN2-INV-2.18", "nome": "Inversor 2.18", "tipo": "Inversor", "cliente": "Thopen",
                 "usina": "Thopen - Tanabi 2 - SP", "usina_curta": "Tanabi 2 - SP", "id_parent": 1}       # nome sem o "{…}", usina sem o cliente
    assert cli.get("/os/api/ativos/recentes").get_json()["codes"] == ["TAN2-INV-2.18"]


def test_detalhe_do_ativo_traz_marca_ultimas_4_os_e_os_destinos(cli):
    d = cli.get("/os/api/ativos/11").get_json()
    assert d["ativo"]["nome"] == "Inversor 2.18" and d["marca"] == "SMA" and d["inspecao"] is True
    assert [o["folio"] for o in d["os"]] == [9812, 9700]                          # da maior para a menor (item 5)
    assert d["os"][0]["data"] == "12/09" and d["os"][0]["cor"] == "#4a9eff"        # data curta e a cor do status do app
    rotulos = [x["rotulo"] for x in d["destinos"]]
    assert rotulos[:4] == [r for r, _ in ativos_web.DESTINOS_OS] and rotulos[-1] == "Inspeção de chamado (garantia)"
    assert d["destinos"][2]["href"].startswith("/os/performance/criar?frase=recomposicao%20de%20string&usina=")
    assert "ativo=Inversor%202.18" in d["destinos"][2]["href"]
    assert d["destinos"][-1]["href"] == "/os/inspecao?ativo=11"
    d2 = cli.get("/os/api/ativos/33").get_json()
    assert d2["inspecao"] is False and d2["destinos"][-1]["rotulo"] != "Inspeção de chamado (garantia)" and d2["os"] == []
    assert cli.get("/os/api/ativos/999").status_code == 404


def test_atualizar_recarrega_o_catalogo_ignorando_o_cache(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: visto.update(force=force) or CATALOGO + [dict(CATALOGO[0], id=2, code="X")])
    r = cli.post("/os/api/ativos/atualizar")
    assert r.status_code == 200 and visto["force"] is True and r.get_json()["n"] == 5


def test_usina_exibe_tira_o_cliente_da_frente():
    assert ativos_web.usina_exibe("2C - Araputanga 1 - MT", "2C") == "Araputanga 1 - MT"
    assert ativos_web.usina_exibe("Thopen - Tanabi 2 - SP", "Athon") == "Thopen - Tanabi 2 - SP"
    assert ativos_web.nome_curto("Inversor 2.18 {SMA Sunny}") == "Inversor 2.18"

# tests/test_os_web_performance.py
"""Fluxo Performance na web, com a MESMA logica do `steps/performance.py`: quatro planos, cascata Cliente -> Usina
pela carteira real, ativos com o plano (api.get_performance_alvos), nome '[Ativo] - base', responsavel e criacao de
UMA OS POR ATIVO (api.create_performance_os). A API do Fracttal e um duble: o que se testa e o contrato da tela."""
import datetime as dt
import json

import pytest

import api
from os_web import criar_app, perf_web

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"

# registros como o catálogo (`api._build_records`) devolve: description e o nome que a API mostra, label e 'code — description'
ASSETS = [
    {"id": 11, "code": "TNB200-INVR2.18", "description": "Inversor 2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "tipo": "Inversor", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP"},
    {"id": 12, "code": "TNB200-INVR2.17", "description": "Inversor 2.17", "label": "TNB200-INVR2.17 — Inversor 2.17", "tipo": "Inversor", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP"},
    {"id": 13, "code": "TNB200-ESTM1", "description": "Estação Meteorológica", "label": "TNB200-ESTM1 — Estação Meteorológica", "tipo": "Estação Meteorológica", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP"},
    {"id": 14, "code": "TNB200", "description": "Thopen - Tanabi 2 - SP", "label": "TNB200 — Thopen - Tanabi 2 - SP", "tipo": "Usina", "tipo_code": "USINA", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP"},
    {"id": 21, "code": "IBR100-INVR1.1", "description": "Inversor 1.1", "label": "IBR100-INVR1.1 — Inversor 1.1", "tipo": "Inversor", "cliente": "Ultragaz", "usina": "Utragaz - Ibirapuã 1 e 2 - BA"},
    {"id": 31, "code": "ALM-DJ1", "description": "Disjuntor", "label": "ALM-DJ1 — Disjuntor", "tipo": "Disjuntor", "cliente": "Almoxarifado", "usina": "Depósito"},
]


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: ASSETS)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


# ── regras puras da cascata (espelham performance.py) ─────────────────────────
def test_clientes_reais_so_de_quem_tem_equipamento_de_planta():
    assert perf_web.clientes_reais(ASSETS) == {"Thopen", "Ultragaz"}      # o Almoxarifado (Disjuntor) fica fora


def test_usinas_livres_e_filtradas_pela_carteira():
    assert perf_web.usinas_para(ASSETS, None) == ["Thopen - Tanabi 2 - SP", "Utragaz - Ibirapuã 1 e 2 - BA"]
    # "Utragaz" no nome da usina (typo do cadastro) e "Ultragaz" no campo cliente: a carteira casa pelos DOIS
    assert perf_web.usinas_para(ASSETS, "Ultragaz") == ["Utragaz - Ibirapuã 1 e 2 - BA"]
    assert perf_web.usinas_para(ASSETS, "Thopen") == ["Thopen - Tanabi 2 - SP"]


def test_cliente_da_usina_vem_do_campo_cliente_e_nao_do_prefixo():
    assert perf_web.cliente_da_usina(ASSETS, "Utragaz - Ibirapuã 1 e 2 - BA") == "Ultragaz"
    assert perf_web.cliente_da_usina(ASSETS, "Thopen - Tanabi 2 - SP") == "Thopen"


def test_ativos_da_usina_para_o_plano():
    ids = lambda frase: [a["id"] for a in perf_web.ativos_da_usina(ASSETS, "Thopen - Tanabi 2 - SP", frase)]
    assert ids("recomposicao de string") == [11, 12, 13]              # PERF_TIPOS: inversor, trackers, estacao
    assert ids("coleta de dados de geracao") == [11, 12, 13, 14]     # so o card de coleta traz o item-usina (modo Usina)


def test_planos_sao_os_quatro_do_app():
    assert [p["titulo"] for p in perf_web.PLANOS] == ["Geração e ETM", "Inspeção Geral do Inversor",
                                                      "Recomposição de String", "Verificação de Tracker Parado"]
    assert perf_web.plano_por_frase("recomposicao de string")["badge"] == "Inversor"


# ── telas ─────────────────────────────────────────────────────────────────────
def test_tela_dos_planos_igual_a_do_app(cli):
    html = cli.get("/os/performance").get_data(as_text=True)
    for titulo, sub in (("Geração e ETM", "Geração por inversor • ou coleta e análise da estação meteorológica"),
                        ("Inspeção Geral do Inversor", "Checklist completo • conexões • alarmes • temperatura • strings"),
                        ("Recomposição de String", "Diagnóstico e normalização de string sem corrente"),
                        ("Verificação de Tracker Parado", "Tracker travado • fim de curso • alinhamento")):
        assert titulo in html and sub in html
    assert "Escolha o tipo de atendimento" in html and "Alocação de análises" in html
    assert 'href="/os/performance/criar?frase=recomposicao+de+string"' in html or "frase=recomposicao%20de%20string" in html


def test_tela_de_criacao_tem_cascata_tabela_e_nome(cli):
    html = cli.get("/os/performance/criar?frase=recomposicao de string").get_data(as_text=True)
    assert "Recomposição de String" in html
    assert "— Selecione o cliente —" in html and "— Selecione a usina —" in html
    assert "Thopen" in html and "Ultragaz" in html and "Almoxarifado" not in html
    for col in ("Ativo", "Strings", "OS Pai", "Observação"):
        assert col in html
    assert "[Ativo]" in html and "Nome da tarefa" in html and "Responsável" in html
    assert 'name="agendamento"' not in html                          # nada inventado alem do app


def test_tela_de_tracker_mostra_a_coluna_trackers(cli):
    html = cli.get("/os/performance/criar?frase=verificacao de tracker parado").get_data(as_text=True)
    assert "Trackers" in html and "Verificação de Tracker Parado" in html


def test_api_usinas_filtra_pela_carteira(cli):
    j = cli.get("/os/api/performance/usinas?cliente=Ultragaz").get_json()
    assert j == {"usinas": ["Utragaz - Ibirapuã 1 e 2 - BA"], "cliente": "Ultragaz"}
    j = cli.get("/os/api/performance/usinas").get_json()
    assert j["usinas"] == ["Thopen - Tanabi 2 - SP", "Utragaz - Ibirapuã 1 e 2 - BA"]


def test_api_alvos_manda_so_os_ativos_da_usina_ao_api(cli, monkeypatch):
    visto = {}
    def _alvos(ativos_usina, frase):
        visto["ids"] = [a["id"] for a in ativos_usina]; visto["frase"] = frase
        return {"is_tracker": False, "base": "Recomposição de String",
                "ativos": [{"asset": ASSETS[0], "plano_id_task": 900, "plano_id_item": 11, "linkar": True}]}
    monkeypatch.setattr(api, "get_performance_alvos", _alvos)
    j = cli.get("/os/api/performance/alvos?usina=Thopen - Tanabi 2 - SP&frase=recomposicao de string").get_json()
    assert visto == {"ids": [11, 12, 13], "frase": "recomposicao de string"}
    assert j["base"] == "Recomposição de String" and j["is_tracker"] is False
    assert j["ativos"] == [{"id": 11, "label": "Inversor 2.18", "code": "TNB200-INVR2.18", "tipo": "Inversor",
                            "plano_id_task": 900, "plano_id_item": 11, "linkar": True, "titulo": "[Inversor 2.18] - Recomposição de String"}]
    assert j["cliente"] == "Thopen"                                   # a usina escolhida preenche o cliente


def test_api_resumo_do_plano(cli, monkeypatch):
    monkeypatch.setattr(api, "get_plan_details", lambda it, ii: {"tasks_types_main_description": "Corretiva",
                        "tasks_types_description": "Elétrica", "tasks_types_2_description": "", "id_priorities": 2, "duration": 5400})
    j = cli.get("/os/api/performance/plano?id_task=900&id_item=11").get_json()
    assert j["resumo"] == "Tipo: Corretiva  ·  Classif. 1: Elétrica  ·  Criticidade: Alto  ·  Duração: 90 min"


def test_api_responsaveis(cli, monkeypatch):
    monkeypatch.setattr(api, "get_responsaveis", lambda: [{"code": "L1", "name": "Levi Maia", "id_personnel": 1414413},
                                                          {"code": "A1", "name": "Ana Patrícia", "id_personnel": 77}])
    j = cli.get("/os/api/responsaveis").get_json()
    assert [p["name"] for p in j["pessoas"]] == ["Ana Patrícia", "Levi Maia"]


def test_criar_uma_os_por_ativo_com_o_payload_do_app(cli, monkeypatch):
    visto = {}
    def _criar(itens, id_responsible=None, responsible_name="", event_date=None, id_parent=None, progresso=None,
               prog_date=None, etiquetas_extra=None):
        visto.update(itens=itens, idr=id_responsible, nome=responsible_name, evt=event_date, prog=prog_date, extra=etiquetas_extra)
        return [{"ok": True, "asset": "Inversor 2.18", "folio": 9812, "n_img_ok": 0, "img_erro": []},
                {"ok": False, "asset": "Inversor 2.17", "erro": "plano sem subtarefa"}]
    monkeypatch.setattr(api, "create_performance_os", _criar)
    corpo = {"frase": "recomposicao de string", "base": "Recomposição de String", "modo": "geracao",
             "evento": "2026-09-12T01:10", "programada": "2026-09-12T08:00",
             "responsavel": {"id_personnel": 1414413, "name": "Levi Maia"},
             "itens": [{"asset": ASSETS[0], "plano_id_task": 900, "plano_id_item": 11, "linkar": True,
                        "note": "Strings Ipv10 e Ipv17 com corrente nula", "os_pai": "9786"},
                       {"asset": ASSETS[1], "plano_id_task": 900, "plano_id_item": 12, "linkar": True, "note": "", "os_pai": ""}]}
    r = cli.post("/os/api/performance/criar", data=json.dumps(corpo), content_type="application/json")
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] == 1 and j["falhas"] == 1
    assert "1 OS criada(s) — Nº 9812" in j["mensagem"] and "Inversor 2.17: plano sem subtarefa" in j["mensagem"]
    it = visto["itens"][0]
    assert it["asset"] == ASSETS[0] and it["plano_id_task"] == 900 and it["plano_id_item"] == 11 and it["linkar"] is True
    assert it["base"] == "Recomposição de String" and it["note"] == "Strings Ipv10 e Ipv17 com corrente nula"
    # `gerar_ticket` era False fixo ("só no app por ora"); desde 21/09 a web gera a ocorrência,
    # com a caixa marcada por padrão — a mesma regra do app.
    assert it["os_pai"] == "9786" and it["titulo"] == "" and it["imagens"] == [] and it["gerar_ticket"] is True
    assert (visto["idr"], visto["nome"], visto["extra"]) == (1414413, "Levi Maia", None)
    brt = dt.timezone(dt.timedelta(hours=-3))
    assert visto["evt"] == dt.datetime(2026, 9, 12, 1, 10, tzinfo=brt) and visto["prog"] == dt.datetime(2026, 9, 12, 8, 0, tzinfo=brt)


def test_modo_etm_usa_titulo_literal_e_etiqueta_engenharia(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_performance_os", lambda itens, *a, **k: visto.update(itens=itens, k=k) or
                        [{"ok": True, "asset": "Estação", "folio": 1}])
    corpo = {"frase": "coleta de dados de geracao", "base": "Coleta e análise de dados", "modo": "etm",
             "evento": "2026-09-12T01:10", "programada": "2026-09-12T01:20",
             "responsavel": {"id_personnel": 1, "name": "X"},
             "itens": [{"asset": ASSETS[2], "plano_id_task": 1, "plano_id_item": 13, "linkar": True, "note": "", "os_pai": ""}]}
    cli.post("/os/api/performance/criar", data=json.dumps(corpo), content_type="application/json")
    assert visto["itens"][0]["titulo"] == "[ETM] - Coleta e análise de dados" and visto["k"]["etiquetas_extra"] == ["ENGENHARIA"]


def test_criar_sem_ativo_ou_sem_responsavel_e_400(cli):
    r = cli.post("/os/api/performance/criar", data=json.dumps({"frase": "x", "itens": [], "responsavel": {}}), content_type="application/json")
    assert r.status_code == 400 and "Marque ao menos um ativo." in r.get_json()["erro"]
    r = cli.post("/os/api/performance/criar", data=json.dumps({"frase": "x", "itens": [{"asset": ASSETS[0]}], "responsavel": {}}), content_type="application/json")
    assert r.status_code == 400 and "Escolha o responsável." in r.get_json()["erro"]

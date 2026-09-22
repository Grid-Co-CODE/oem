# tests/test_os_web_clonar.py
"""Clonar OS na web (card "Clonar OS"): a mesma tela do `steps/clonar.py` — OS de referência com TODAS as tarefas,
data/hora por tarefa e os atalhos de data, tarefa selecionada com troca de ativo/descrição e subtarefas editáveis,
observação única, etiquetas e responsável; a escrita é `api.clonar_os` com os mesmos argumentos do desktop."""
import datetime as dt

import pytest

import api
from os_web import clonar_web, criar_app

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
BRT = dt.timezone(dt.timedelta(hours=-3))

CATALOGO = [
    {"id": 11, "code": "INV-2.18", "label": "Inversor 2.18", "description": "Inversor 2.18", "tipo": "Inversor",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_type_item": 5, "id_group_task": 9},
    {"id": 12, "code": "INV-2.19", "label": "Inversor 2.19", "description": "Inversor 2.19", "tipo": "Inversor",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_type_item": 5, "id_group_task": 9},
    {"id": 33, "code": "TRK-5", "label": "Tracker 5", "description": "Tracker 5", "tipo": "Tracker",
     "cliente": "2C", "usina": "2C - Araputanga 1 - MT", "id_type_item": 6, "id_group_task": 9},
]
DADOS = {
    "folio": 9812, "notas": "Observação da OS de origem", "etiqueta_ids": [4660, 12], "n_sem_ativo": 1,
    "tarefas": [
        {"code": "INV-2.18", "asset": CATALOGO[0], "tipo": "Corretiva", "descricao": "Recomposição de String",
         "classif_1": "Programada", "classif_2": "Elétrica", "event_date_orig": "2026-09-12T11:00:00Z", "notas": "",
         "subtarefas": [{"description": "Medir corrente", "id_task_form_item_type": 1},
                        {"description": "Foto do painel", "id_task_form_item_type": 1}]},
        {"code": "SEM-ATIVO", "asset": None, "tipo": "Corretiva", "descricao": "Tarefa sem ativo", "subtarefas": []},
    ],
}
PESSOAS = [{"code": "LM", "name": "Levi Maia", "id_personnel": 77}, {"code": "LS", "name": "Luiz Silva", "id_personnel": 88}]


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"})
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: CATALOGO)
    monkeypatch.setattr(api, "get_responsaveis", lambda: PESSOAS)
    monkeypatch.setattr(api, "_wo_id_por_folio", lambda folio: 501 if str(folio) == "9812" else None)
    monkeypatch.setattr(api, "get_os_para_clonar", lambda wid: DADOS if wid == 501 else {})
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


def test_a_tela_tem_a_estrutura_do_dialogo_do_app(cli):
    html = cli.get("/os/clonar?folio=9812").get_data(as_text=True)
    for txt in ("Clonar OS nº", "OS de referência", "Tarefas / ativos que serão clonados", "Clonar ativo", "Tarefa", "Subt.",
                "Data/hora programada", "Aplicar data", "Manhã (07:00)", "Tarde (13:00)", "Avançar 1 mês", "Tarefa selecionada",
                "Atualizar do modelo", "Atualizar todas do modelo", "Detalhes", "Observação", "Clonar etiquetas", "Responsável",
                "Cancelar", "Criar clone"):
        assert txt in html, txt
    assert 'data-folio="9812"' in html                                          # ?folio= já carrega a OS, como o app.py:448
    assert "Luiz Silva" in html                                                 # responsáveis do Fracttal, ordenados


def test_le_a_os_de_referencia_pelo_numero_com_todas_as_tarefas(cli):
    d = cli.get("/os/api/clonar/os?folio=9812").get_json()
    assert d["folio"] == 9812 and len(d["tarefas"]) == 2 and d["etiqueta_ids"] == [4660, 12]
    assert d["tarefas"][0]["asset"]["id"] == 11 and d["tarefas"][1]["asset"] is None
    # candidatos para trocar o ativo: mesmo cliente e usina, como o combo do app
    assert [a["id"] for a in d["tarefas"][0]["candidatos"]] == [11, 12]
    r = cli.get("/os/api/clonar/os?folio=1")
    assert r.status_code == 404 and "não achei" in r.get_json()["erro"].lower()


def test_criar_clone_chama_clonar_os_como_o_app(cli, monkeypatch):
    visto = {}
    def _clonar(tarefas, id_responsible, responsible_name="", etiqueta_ids=None, note="", scheduled_date=None, id_parent=None, id_request=None):
        visto.update(tarefas=tarefas, idp=id_responsible, nome=responsible_name, eids=etiqueta_ids, note=note)
        return {"ok": True, "os": {"id_work_order": 900, "wo_folio": 9999}, "n_criadas": 1, "aviso": ""}
    monkeypatch.setattr(api, "clonar_os", _clonar)
    tarefas = [dict(DADOS["tarefas"][0], event_date="2026-09-15T08:00",
                    subtarefas=[{"description": "Medir corrente (editada)", "id_task_form_item_type": 1, "_keep": True},
                                {"description": "Foto do painel", "id_task_form_item_type": 1, "_keep": False}]),
               dict(DADOS["tarefas"][1], _skip=False)]
    r = cli.post("/os/api/clonar/criar", json={"tarefas": tarefas, "id_responsible": 88, "responsible_name": "Luiz Silva",
                                              "clonar_etiquetas": True, "etiqueta_ids": [4660, 12], "note": "  obs geral  "})
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j["ok"] and "OS clonada com sucesso — Nº 9999." in j["mensagem"] and "1 tarefa(s) recriada(s)." in j["mensagem"]
    assert visto["idp"] == 88 and visto["nome"] == "Luiz Silva" and visto["eids"] == [4660, 12] and visto["note"] == "obs geral"
    t0 = visto["tarefas"][0]
    assert t0["asset"] is CATALOGO[0] or t0["asset"]["id"] == 11                 # ativo completado pelo catálogo, não pelo que veio da tela
    assert t0["classif_1"] == "Programada" and t0["classif_2"] == "Elétrica"     # a classificação da origem segue junto (caso 10893/10895)
    assert [s["description"] for s in t0["subtarefas"]] == ["Medir corrente (editada)"]   # só as marcadas, com o texto editado
    assert t0["event_date"] == dt.datetime(2026, 9, 15, 8, 0, tzinfo=BRT)         # horário de Brasília, como o app
    assert len(visto["tarefas"]) == 2                                             # a sem ativo vai junto: o api.clonar_os é quem a ignora


def test_desmarcar_todos_ou_faltar_responsavel_nao_chega_na_api(cli, monkeypatch):
    monkeypatch.setattr(api, "clonar_os", lambda *a, **k: pytest.fail("não podia chamar a API"))
    base = {"tarefas": [dict(DADOS["tarefas"][0], _skip=True)], "id_responsible": 88, "responsible_name": "Luiz Silva"}
    r = cli.post("/os/api/clonar/criar", json=base)
    assert r.status_code == 400 and r.get_json()["erro"] == "Nenhum ativo marcado para clonar."
    r = cli.post("/os/api/clonar/criar", json={"tarefas": [dict(DADOS["tarefas"][0])], "id_responsible": None})
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o responsável."


def test_atualizar_do_modelo_e_todas(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "get_template_subtarefas", lambda asset, desc: visto.update(asset=asset, desc=desc) or
                        {"achou": True, "subtarefas": [{"description": "Nova do modelo", "id_task_form_item_type": 1}], "nome": desc, "id_task": 5})
    r = cli.post("/os/api/clonar/modelo", json={"asset_id": 11, "descricao": "Recomposição de String"})
    assert r.status_code == 200 and r.get_json()["achou"] and visto["asset"]["id"] == 11 and visto["desc"] == "Recomposição de String"
    assert r.get_json()["subtarefas"][0]["_keep"] is True                       # o app marca _keep=True no que vem do modelo
    monkeypatch.setattr(api, "atualizar_modelos_subtarefas", lambda tarefas: [{"achou": True, "subtarefas": [{"description": "X"}], "erro": None}, None])
    r = cli.post("/os/api/clonar/modelo-todas", json={"tarefas": DADOS["tarefas"]})
    assert r.status_code == 200 and r.get_json()["resultados"][1] is None and r.get_json()["resultados"][0]["achou"]


def test_helper_puro_prepara_as_tarefas_como_o_criar_do_app():
    tarefas = [dict(DADOS["tarefas"][0], event_date="2026-09-15T08:30", _skip=False,
                    subtarefas=[{"description": "a", "_keep": True}, {"description": "b", "_keep": False}]),
               dict(DADOS["tarefas"][0], asset={"id": 12}, _skip=True)]
    prontas, erro = clonar_web.preparar_tarefas(tarefas, {a["id"]: a for a in CATALOGO})
    assert erro == "" and len(prontas) == 1 and prontas[0]["asset"]["code"] == "INV-2.18"
    assert prontas[0]["event_date"].hour == 8 and prontas[0]["event_date"].tzinfo == BRT
    assert [s["description"] for s in prontas[0]["subtarefas"]] == ["a"]
    assert clonar_web.mensagem_resultado({"ok": False, "erro": "boom"})["mensagem"] == "boom"

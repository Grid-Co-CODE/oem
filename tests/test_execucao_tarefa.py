# tests/test_execucao_tarefa.py
"""Executar a tarefa da OS: preencher o checklist, salvar e registrar início/fim.

O QUE ESTES TESTES SÃO. O protocolo foi colhido do Fracttal web em 21/09/2026 — Levi capturou as
chamadas de verdade na OS 38299179 / tarefa 59150414. Aqui o `_rpc_call` é um dublê e o que se
compara é o CORPO QUE SAIRIA, campo a campo, contra o corpo capturado. Não é teste de "não
quebrou": é a única forma de saber que o payload está certo sem escrever numa OS de produção.

Os payloads abaixo são os da captura, com o token fora (ele é de sessão e já expirou).
"""
import datetime as dt

import pytest

import api

TAREFA = 59150414
OS = 38299179
UTC = dt.timezone.utc
BRT = dt.timezone(dt.timedelta(hours=-3))


@pytest.fixture
def espiao(monkeypatch):
    """Troca o `_rpc_call` por um que só anota (method, params) e devolve sucesso."""
    chamadas = []

    def falso(method, params, timeout=45):
        chamadas.append((method, params))
        if method == api.RPC_WO_EXEC_LIST:
            return {"data": [{"id": _ultimo_uuid(chamadas), "name": "Levi Maia",
                              "initial_date": "2026-09-21T05:58:00.000Z",
                              "final_date": "2026-09-21T17:08:05.000Z", "note": "", "done": True}]}
        return {"success": True}

    monkeypatch.setattr(api, "_rpc_call", falso)
    monkeypatch.setattr(api, "current_user_name", lambda: "Levi Maia")
    return chamadas


def _ultimo_uuid(chamadas):
    for m, p in reversed(chamadas):
        if m == api.RPC_WO_EXEC_INSERT and isinstance(p, dict):
            return p.get("id")
    return None


# ── o checklist ──────────────────────────────────────────────────────────────────────────────
def test_salvar_subtarefas_monta_o_payload_da_captura(espiao):
    """O corpo tem de sair IGUAL ao capturado: mesmos nove campos, mesmos nomes, mesma ordem."""
    valores = [{"id_form_item": 478247999, "valor": "1", "tipo": 4},
               {"id_form_item": 478248004, "valor": "TESTETESTETESTETESTE", "tipo": 1},
               {"id_form_item": 478248005, "valor": "1", "tipo": 3}]
    r = api.salvar_subtarefas(OS, TAREFA, valores)
    assert r["ok"] and r["n"] == 3

    metodo, params = espiao[0]
    assert metodo == "tasks.work_orders_task_form_items_values_insert"
    assert isinstance(params, list)                      # params é LISTA aqui, não dict
    assert params[0] == {"id_work_orders_tasks_form_items": 478247999, "id_work_order": OS,
                         "id_meter": None, "id_unit": None, "id_work_order_task": TAREFA,
                         "value": "1", "attachments": [], "is_offline": None,
                         "id_task_form_item_type": 4}
    assert set(params[0]) == {"id_work_orders_tasks_form_items", "id_work_order", "id_meter",
                              "id_unit", "id_work_order_task", "value", "attachments",
                              "is_offline", "id_task_form_item_type"}


def test_campo_vazio_nao_e_enviado(espiao):
    """Na captura, o campo que a pessoa esvaziou (478248006) SUMIU da segunda gravação — não foi
    com value:"". Mandar string vazia seria inventar um contrato que a tela deles não usa."""
    r = api.salvar_subtarefas(OS, TAREFA, [
        {"id_form_item": 478248004, "valor": "TESTETESTE", "tipo": 1},
        {"id_form_item": 478248006, "valor": "", "tipo": 1},
        {"id_form_item": 478248007, "valor": None, "tipo": 1}])
    assert r["n"] == 1
    _m, params = espiao[0]
    assert [p["id_work_orders_tasks_form_items"] for p in params] == [478248004]


def test_salvar_sem_nada_preenchido_nao_chama_a_api(espiao):
    r = api.salvar_subtarefas(OS, TAREFA, [{"id_form_item": 1, "valor": "  ", "tipo": 1}])
    assert r["ok"] is False and r["n"] == 0
    assert espiao == []                                  # nada saiu para o Fracttal


def test_salvar_sem_id_da_os_recusa(espiao):
    with pytest.raises(api.FracttalError):
        api.salvar_subtarefas(None, TAREFA, [{"id_form_item": 1, "valor": "x", "tipo": 1}])


# ── o registro de execução ───────────────────────────────────────────────────────────────────
def test_registrar_execucao_monta_o_payload_da_captura(espiao):
    ini = dt.datetime(2026, 9, 21, 2, 58, tzinfo=BRT)      # 05:58Z, como na captura
    fim = dt.datetime(2026, 9, 21, 14, 8, 5, tzinfo=BRT)   # 17:08:05Z
    r = api.registrar_execucao(TAREFA, ini, fim)
    assert r["ok"]

    metodos = [m for m, _ in espiao]
    # a ORDEM da tela: valida a segurança ANTES de inserir, e relê DEPOIS
    assert metodos[0] == "tasks.wo_tasks_security_validations_validate"
    assert metodos[1] == "tasks.wo_tasks_execution_insert"
    assert "tasks.wo_task_get_execution" in metodos

    _m, p = espiao[1]
    assert p["id_work_order_task"] == TAREFA
    assert p["initial_date"].startswith("2026-09-21T05:58:00")     # convertido para UTC
    assert p["final_date"].startswith("2026-09-21T17:08:05")
    assert p["done"] is True and p["to_pause"] is False and p["to_stop"] is False
    assert p["id_wo_tasks_stop_reasons"] == 1
    assert p["id_accounts_log"] == 0 and p["id_account"] is None
    assert p["name"] == "Levi Maia"
    assert p["id"] == p["idInternal"]                              # o mesmo uuid nos dois campos
    assert set(p) == {"id", "id_work_order_task", "id_accounts_log", "id_account",
                      "id_wo_tasks_execution_types", "note", "name", "initial_date", "final_date",
                      "done", "to_pause", "to_stop", "id_wo_tasks_stop_reasons",
                      "id_wo_tasks_execution_categorizations", "categorization_description",
                      "security_validations", "actions", "idInternal"}


def test_registro_e_reconferido(espiao):
    """"Registrado" só pode ser dito depois de reler: o insert pode voltar 200 sem ter gravado, e
    a própria tela deles relê. É o mesmo cuidado do `concluir_os_checado`."""
    ini = dt.datetime(2026, 9, 21, 2, 58, tzinfo=BRT)
    r = api.registrar_execucao(TAREFA, ini, dt.datetime(2026, 9, 21, 14, 8, 5, tzinfo=BRT))
    assert r["confirmado"] is True and r["n_registros"] == 1


def test_fim_antes_do_inicio_recusa(espiao):
    ini = dt.datetime(2026, 9, 21, 14, 0, tzinfo=BRT)
    with pytest.raises(api.FracttalError):
        api.registrar_execucao(TAREFA, ini, dt.datetime(2026, 9, 21, 8, 0, tzinfo=BRT))
    assert espiao == []                                   # recusa ANTES de tocar no Fracttal


def test_sem_inicio_recusa(espiao):
    with pytest.raises(api.FracttalError):
        api.registrar_execucao(TAREFA, None)
    assert espiao == []


def test_sem_fim_usa_agora(espiao):
    ini = dt.datetime.now(UTC) - dt.timedelta(hours=2)
    r = api.registrar_execucao(TAREFA, ini)
    assert r["fim"].endswith("Z") and r["fim"] > r["inicio"]


# ── a leitura do checklist ───────────────────────────────────────────────────────────────────
def test_subtarefas_da_tarefa_traduz_os_tipos(monkeypatch):
    def falso(method, params, timeout=45):
        assert method == "tasks.work_orders_task_form_items_list"
        assert params["id_work_order_task"] == TAREFA and params["limit"] == 2500
        return {"data": [
            {"id_work_orders_tasks_form_items": 478247999, "id_work_order": OS,
             "description": "Inspeção visual", "id_task_form_item_type": 4, "value": "1",
             "is_required": True, "attachments_required": True, "num_attachments": 2},
            {"id_work_orders_tasks_form_items": 478248004, "id_work_order": OS,
             "description": "Descreva a atividade", "id_task_form_item_type": 1, "value": None,
             "is_required": True, "attachments_required": False, "num_attachments": 0},
            {"id_work_orders_tasks_form_items": 478248005, "id_work_order": OS,
             "description": "Corrente (A)", "id_task_form_item_type": 3, "value": "12.4",
             "is_required": False, "attachments_required": False, "num_attachments": 0}]}
    monkeypatch.setattr(api, "_rpc_call", falso)
    itens = api.subtarefas_da_tarefa(TAREFA)
    assert [i["tipo_nome"] for i in itens] == ["verif", "texto", "num"]
    assert itens[0]["opcoes"] == [{"valor": "1", "rotulo": "Aprovado"},
                                  {"valor": "2", "rotulo": "Alerta"},
                                  {"valor": "3", "rotulo": "Falhou"}]
    assert itens[0]["anexo_obrigatorio"] is True and itens[0]["n_anexos"] == 2
    assert itens[1]["valor"] == ""                    # None vira string vazia, não "None"
    assert itens[2]["valor"] == "12.4"


def test_subtarefas_sem_tarefa_devolve_vazio():
    assert api.subtarefas_da_tarefa(None) == []

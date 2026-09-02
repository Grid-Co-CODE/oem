"""A aprovação tem de aguentar ser chamada duas vezes.

O caso real (02/09): a solicitação 3536 foi aprovada, a criação da TAREFA deu certo e a OS não
nasceu — faltava responsável. Na segunda tentativa o Fracttal recusou com `unique_violation`,
porque ele só aceita UMA tarefa por solicitação. Resultado: a solicitação ficou presa para
sempre, com uma tarefa órfã invisível no kanban. Aconteceu duas vezes (3534 e 3536) antes de
alguém entender o motivo, e o sintoma na tela era "erro estranho ao aprovar".

A régua que estes testes prendem: com tarefa já existente, a aprovação NÃO cria outra — ela
retoma pela fase 2.
"""
import api


class _Espiao:
    def __init__(self):
        self.clonou = False
        self.recs = None

    def clonar_os(self, *a, **k):
        self.clonou = True
        return {"ok": True, "os": {"wo_folio": "NOVA", "id_work_order": 1, "id_tasks": [9]},
                "n_tarefas": 1, "n_criadas": 1}

    def wo_insert(self, recs, idr, nome, **k):
        self.recs = recs
        return {"id_work_order": 777, "wo_folio": "12777"}


def _montar(monkeypatch, tarefa, row=None):
    e = _Espiao()
    monkeypatch.setattr(api, "_solicitacao_row", lambda idc: row)
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda idr: tarefa)
    monkeypatch.setattr(api, "clonar_os", e.clonar_os)
    monkeypatch.setattr(api, "_work_order_insert", e.wo_insert)
    return e


ATIVO = {"id": 43128243, "code": "TESTE100-CHSC1"}
SUBS = [{"description": "x", "id_task_form_item_type": 1, "attachments_required": False}]


def test_sem_tarefa_previa_cria_pelo_caminho_normal(monkeypatch):
    e = _montar(monkeypatch, None)
    r = api.aprovar_solicitacao(ATIVO, "titulo", SUBS, 3600, 1414413, "Levi Maia")
    assert e.clonou and r["ok"] and r["os"]["wo_folio"] == "NOVA"


def test_com_tarefa_orfa_retoma_e_NAO_cria_outra(monkeypatch):
    """O coração da correção: a segunda chamada aproveita a tarefa que existe.

    Se ela chamasse `clonar_os` de novo, o Fracttal devolveria `unique_violation` e a
    solicitação continuaria sem OS — exatamente o estado em que a 3534 e a 3536 ficaram."""
    orfa = {"id_task": 21544130, "id_request": 3536, "description": "Inspeção de nobreak"}
    e = _montar(monkeypatch, orfa)
    r = api.aprovar_solicitacao(ATIVO, "titulo", SUBS, 3536, 1414413, "Levi Maia")
    assert not e.clonou, "não pode tentar criar uma segunda tarefa"
    assert e.recs == [orfa]
    assert r["ok"] and r["os"]["wo_folio"] == "12777"
    assert "já existia" in r["aviso"] or "ja existia" in r["aviso"]


def test_retomada_sem_responsavel_recusa_em_vez_de_falhar_calada(monkeypatch):
    """Sem responsável a fase 2 não gera OS numerada. Recusar aqui é melhor que devolver ok e a
    OS não aparecer em lugar nenhum — que foi o sintoma original."""
    e = _montar(monkeypatch, {"id_task": 1, "id_request": 3536})
    r = api.aprovar_solicitacao(ATIVO, "titulo", SUBS, 3536, None, "")
    assert r["ok"] is False and e.recs is None
    assert "respons" in r["erro"].lower()


def test_kanban_fora_do_ar_nao_impede_a_aprovacao(monkeypatch):
    """A checagem é uma proteção, não um pré-requisito: se a listagem do kanban falhar, seguimos
    pelo caminho normal — o pior caso volta a ser o erro de antes, não uma aprovação bloqueada."""
    e = _Espiao()

    def _explode(_):
        raise api.FracttalError("kanban fora do ar")

    monkeypatch.setattr(api, "_solicitacao_row", lambda idc: None)
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", _explode)
    monkeypatch.setattr(api, "clonar_os", e.clonar_os)
    r = api.aprovar_solicitacao(ATIVO, "titulo", SUBS, 3600, 1414413, "Levi Maia")
    assert e.clonou and r["ok"]


def test_solicitacao_que_JA_virou_OS_e_recusada_com_o_numero(monkeypatch):
    """O que a segunda aprovação da 3537 devolvia: só "unique_violation", sem dizer que a OS
    12778 já existia. Recusar citando o número evita que alguém insista e crie OS duplicada."""
    e = _montar(monkeypatch, None, row={"id_work_order": 37636151, "wo_folio": "12778"})
    r = api.aprovar_solicitacao(ATIVO, "titulo", SUBS, 3537, 1414413, "Levi Maia")
    assert r["ok"] is False and not e.clonou
    assert "12778" in r["erro"]

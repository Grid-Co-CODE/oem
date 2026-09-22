# tests/test_os_web_executar.py
"""Fazer a tarefa na hora de concluir a OS (Levi, 21/09/2026).

O pedido, nas palavras dele: "se tiver tarefa pendente tem que dar a opção de fazer a tarefa —
OS → TAREFA DA OS → SUBTAREFA DA OS → PREENCHE SUBTAREFA → SALVA → VOU EM REGISTRO → APERTO EM
ADICIONAR → TEM A DATA E HORA DO INÍCIO".

O que estes testes seguram é a parte que escreve em produção: a ORDEM (checklist e só então o
registro), a recusa ANTES de tocar no Fracttal quando falta campo obrigatório ou data, e o fato de
o servidor não aceitar da tela nada além de valores — os ids e os tipos ele relê sozinho.
"""
import datetime as dt

import pytest

import api
from os_web import criar_app, os_acoes_web as regra

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
TAREFA = 59150414
OS = 501

CAMPOS = [
    {"id_form_item": 478247999, "id_work_order": OS, "descricao": "Inspeção visual", "tipo": 4,
     "tipo_nome": "verif", "valor": "", "obrigatorio": True, "anexo_obrigatorio": False,
     "n_anexos": 0, "opcoes": [{"valor": "1", "rotulo": "Aprovado"}]},
    {"id_form_item": 478248004, "id_work_order": OS, "descricao": "Descreva a atividade", "tipo": 1,
     "tipo_nome": "texto", "valor": "", "obrigatorio": True, "anexo_obrigatorio": False,
     "n_anexos": 0, "opcoes": []},
    {"id_form_item": 478248005, "id_work_order": OS, "descricao": "Corrente (A)", "tipo": 3,
     "tipo_nome": "num", "valor": "", "obrigatorio": False, "anexo_obrigatorio": False,
     "n_anexos": 0, "opcoes": []},
]


@pytest.fixture
def cli(monkeypatch):
    """Cliente logado, com a API do Fracttal dublada — e um diário do que foi chamado, em ordem."""
    app = criar_app(segredo="teste", testing=True)
    diario = []
    monkeypatch.setattr(api, "subtarefas_da_tarefa", lambda tid: [dict(c) for c in CAMPOS])

    def salvar(wid, tid, valores):
        diario.append(("salvar", wid, tid, valores))
        return {"ok": True, "n": len(valores)}

    def registrar(tid, ini, fim=None, note="", nome="", validar=True):
        diario.append(("registrar", tid, ini, fim, note))
        return {"ok": True, "id": "x", "confirmado": True, "n_registros": 1,
                "inicio": api._iso_z(ini), "fim": api._iso_z(fim or ini)}

    monkeypatch.setattr(api, "salvar_subtarefas", salvar)
    monkeypatch.setattr(api, "registrar_execucao", registrar)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    c.diario = diario
    return c


def _corpo(**muda):
    d = {"valores": {"478247999": "1", "478248004": "trocada a string"},
         "inicio": "2026-09-21T02:58", "fim": "2026-09-21T14:08", "nota": ""}
    d.update(muda)
    return d


# ── o checklist ──────────────────────────────────────────────────────────────────────────────
def test_checklist_devolve_os_campos(cli):
    r = cli.get("/os/api/os/%d/tarefa/%d/checklist" % (OS, TAREFA))
    assert r.status_code == 200
    j = r.get_json()
    assert j["id_tarefa"] == TAREFA and len(j["campos"]) == 3
    assert j["pendentes"] == 3                      # os três estão em branco
    assert j["campos"][0]["opcoes"][0]["rotulo"] == "Aprovado"


# ── a escrita ────────────────────────────────────────────────────────────────────────────────
def test_executar_grava_checklist_ANTES_do_registro(cli):
    """A ordem não é indiferente: registro primeiro + checklist falhando deixaria horas lançadas
    para um serviço não registrado. O contrário se conserta lançando o registro de novo."""
    r = cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA), json=_corpo())
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert [x[0] for x in cli.diario] == ["salvar", "registrar"]


def test_executar_manda_o_tipo_que_o_SERVIDOR_leu(cli):
    """A tela manda só {id: valor}. O tipo de cada campo vem do `subtarefas_da_tarefa`, no servidor:
    se viesse do navegador, um campo de Verificação podia chegar como texto e gravar lixo."""
    cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA), json=_corpo())
    _m, _w, _t, valores = cli.diario[0]
    por = {v["id_form_item"]: v for v in valores}
    assert por[478247999]["tipo"] == 4              # Verificação
    assert por[478248004]["tipo"] == 1              # Texto
    assert set(por) == {478247999, 478248004}       # o que não foi preenchido não vai


def test_campo_de_id_desconhecido_e_ignorado(cli):
    """Id que não está no checklist da tarefa não passa: é o único jeito de a tela não conseguir
    escrever numa subtarefa de OUTRA OS mandando o id na mão."""
    cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA),
             json=_corpo(valores={"478247999": "1", "478248004": "x", "999999999": "invasor"}))
    _m, _w, _t, valores = cli.diario[0]
    assert 999999999 not in [v["id_form_item"] for v in valores]


def test_data_vai_em_brasilia(cli):
    cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA), json=_corpo())
    _m, _t, ini, fim, _n = cli.diario[1]
    assert (ini.hour, ini.minute) == (2, 58)
    assert ini.utcoffset() == dt.timedelta(hours=-3)
    assert (fim.hour, fim.minute) == (14, 8)


def test_sem_fim_deixa_o_api_decidir(cli):
    cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA), json=_corpo(fim=""))
    _m, _t, _i, fim, _n = cli.diario[1]
    assert fim is None                              # o `registrar_execucao` usa agora


# ── as recusas, todas ANTES de tocar no Fracttal ─────────────────────────────────────────────
def test_obrigatoria_em_branco_recusa(cli):
    r = cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA),
                 json=_corpo(valores={"478248005": "12"}))     # só a opcional
    assert r.status_code == 400
    assert "Inspeção visual" in r.get_json()["erro"]
    assert cli.diario == []                                     # nada saiu


def test_sem_inicio_recusa(cli):
    r = cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA), json=_corpo(inicio=""))
    assert r.status_code == 400 and "início" in r.get_json()["erro"]
    assert cli.diario == []


def test_fim_antes_do_inicio_recusa(cli):
    r = cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA),
                 json=_corpo(inicio="2026-09-21T14:00", fim="2026-09-21T08:00"))
    assert r.status_code == 400 and "anterior" in r.get_json()["erro"]
    assert cli.diario == []


def test_obrigatoria_ja_respondida_nao_precisa_repetir(cli, monkeypatch):
    """Se a subtarefa obrigatória JÁ tem valor gravado, não é pendência — exigir de novo obrigaria
    a redigitar o que o técnico respondeu no celular."""
    campos = [dict(c) for c in CAMPOS]
    campos[0]["valor"] = "1"
    campos[1]["valor"] = "feito ontem"
    monkeypatch.setattr(api, "subtarefas_da_tarefa", lambda tid: campos)
    r = cli.post("/os/api/os/%d/tarefa/%d/executar" % (OS, TAREFA), json=_corpo(valores={}))
    assert r.status_code == 200
    assert [x[0] for x in cli.diario] == ["registrar"]   # sem nada novo, não chama o salvar


# ── as regras puras ──────────────────────────────────────────────────────────────────────────
def test_tarefas_pendentes_agrupa_por_tarefa():
    """Uma OS de preventiva pode ter treze tarefas: oferecer "fazer a tarefa" sem dizer QUAL faria
    a pessoa preencher o checklist da errada."""
    d = {"tarefas": [{"id": 1, "titulo": "Inversor 1.1"}, {"id": 2, "titulo": "Inversor 1.2"}],
         "subtarefas": [{"id_tarefa": 1, "feito": False}, {"id_tarefa": 1, "feito": False},
                        {"id_tarefa": 1, "feito": True}, {"id_tarefa": 2, "feito": False}]}
    tp = regra.tarefas_pendentes(d)
    assert [t["id_tarefa"] for t in tp] == [1, 2]            # a de mais pendências primeiro
    assert tp[0]["n_pendentes"] == 2 and tp[0]["titulo"] == "Inversor 1.1"


def test_tarefas_pendentes_vazio_quando_tudo_feito():
    assert regra.tarefas_pendentes({"subtarefas": [{"id_tarefa": 1, "feito": True}]}) == []
    assert regra.tarefas_pendentes({}) == []


def test_mensagem_avisa_quando_nao_deu_para_confirmar():
    txt, aviso = regra.mensagem_execucao(3, {"confirmado": False}, lambda x: "—")
    assert aviso is True and "NÃO consegui confirmar" in txt
    txt, aviso = regra.mensagem_execucao(3, {"confirmado": True, "inicio": "a", "fim": "b"}, lambda x: x)
    assert aviso is False and "3 subtarefa" in txt

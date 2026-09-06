"""Editar a observação da OS pelo próprio card (Levi, 02/09).

Antes, corrigir uma linha da observação exigia sair do app e abrir o Fracttal.

As DUAS recusas testadas aqui não são conservadorismo — cada uma saiu de um teste contra a API
real em 02/09:

· OS CONCLUÍDA — o `work_orders_update` responde ERROR_WO_FINISHED_BY_OTHER_USER (medido na OS
  10575). Apesar do nome, não é conflito entre usuários: é a OS estar fechada. Deixar a pessoa
  digitar para só então descobrir seria cruel, então o botão já nasce apagado com o motivo.
· OS com VÁRIAS TAREFAS — a nota é presa à TAREFA, mas o endpoint grava no nível da OS. Com uma
  tarefa só o teste provou que cai onde deve (OS 12728, marcador escrito e desfeito); com várias,
  não sei qual receberia, e sobrescrever a observação da tarefa errada é pior que não editar.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import steps.os_detalhe as od


@pytest.fixture
def card(qapp, monkeypatch):
    """O card real, sem rede. `ApiWorker` vira no-op: o construtor dispara threads de verdade e,
    num teste, elas ou batem na API ou morrem junto com o objeto e abortam o processo."""
    monkeypatch.setattr(od, "ApiWorker", lambda *a, **k: type(
        "W", (), {"ok": type("S", (), {"connect": lambda *_: None})(),
                  "erro": type("S", (), {"connect": lambda *_: None})(),
                  "start": lambda self: None})())
    d = od.OsDetalheDialog(None, 999, "9999")
    yield d
    d.deleteLater()


def _estado(card, status, n_tarefas):
    card._status_id = status
    card._tarefas = [{"id": i} for i in range(n_tarefas)]


def test_os_aberta_de_uma_tarefa_pode_editar(card):
    _estado(card, 1, 1)
    pode, _ = card._nota_pode_editar()
    assert pode


def test_os_em_verificacao_tambem_pode(card):
    # status 2 ainda não é fechamento — o Fracttal aceita a escrita.
    _estado(card, 2, 1)
    assert card._nota_pode_editar()[0]


def test_os_concluida_recusa_e_diz_por_que(card):
    _estado(card, 3, 1)
    pode, motivo = card._nota_pode_editar()
    assert not pode
    assert "conclu" in motivo.lower()


def test_os_cancelada_recusa(card):
    _estado(card, 4, 1)
    pode, motivo = card._nota_pode_editar()
    assert not pode
    assert "cancelada" in motivo.lower()


def test_os_de_varias_tarefas_recusa_e_manda_para_o_fracttal(card):
    _estado(card, 1, 3)
    pode, motivo = card._nota_pode_editar()
    assert not pode
    assert "3 tarefas" in motivo and "Fracttal" in motivo


# ── a troca leitura ↔ edição ──────────────────────────────────────────────────────────────────
def test_em_repouso_so_aparece_a_leitura(card):
    card._nota_modo(False)
    assert card.notas_blk.isVisibleTo(card) and not card.notas_ed.isVisibleTo(card)
    assert card.b_nota_edit.isVisibleTo(card)
    assert not card.b_nota_ok.isVisibleTo(card) and not card.b_nota_no.isVisibleTo(card)


def test_editando_so_aparece_o_editor(card):
    # os dois visíveis ao mesmo tempo empurrariam as subtarefas para fora do card.
    card._nota_modo(True)
    assert card.notas_ed.isVisibleTo(card) and not card.notas_blk.isVisibleTo(card)
    assert card.b_nota_ok.isVisibleTo(card) and card.b_nota_no.isVisibleTo(card)
    assert not card.b_nota_edit.isVisibleTo(card)


def test_editar_carrega_a_nota_atual_no_editor(card):
    _estado(card, 1, 1)
    card._notas_todas = "observação que já estava lá"
    card._nota_editar()
    assert card.notas_ed.toPlainText() == "observação que já estava lá"


def test_cancelar_volta_para_leitura_sem_gravar(card):
    _estado(card, 1, 1)
    card._notas_todas = "original"
    card._nota_editar()
    card.notas_ed.setPlainText("rascunho descartado")
    card._nota_cancelar()
    assert not card.notas_ed.isVisibleTo(card)
    assert card._notas_todas == "original"


def test_o_card_guarda_o_que_a_API_gravou_e_nao_o_digitado(card):
    # a API apara os espaços das pontas. Guardar o texto digitado deixaria o card mostrando uma
    # coisa e o Fracttal tendo outra.
    card._nota_modo(True)
    card._nota_gravou({"ok": True, "nota": "sem espaços"}, "  sem espaços  ")
    assert card._notas_todas == "sem espaços"
    assert not card.notas_ed.isVisibleTo(card)

# -*- coding: utf-8 -*-
"""O card de quantidade e o marcador de ocorrência na tela de Performance (Levi, 10/09/2026).

A régua em si está em `test_tickets_nasce.py`. Aqui o que se guarda é a TELA: que o card aparece
só onde deve, que o número dele é o que vai para a criação, e que a correção à mão não é
atropelada pelo recálculo — foi esse o pedido ("o card pode ser editado").
"""
import pytest

import steps.performance as P


def _ativo(i, nome, tipo, usina="Thopen - Tanabi 2 - SP", cliente="Thopen"):
    return {"id": i, "code": "THPN-TNB200-%d" % i, "description": nome, "tipo": tipo,
            "tipo_code": "", "usina": usina, "cliente": cliente, "id_parent": None,
            "label": nome}


def _tela(qapp, plano="strings", obs=None, marcar=(1, 2), assets=None, grupo=None):
    """PerfCriar montada com os alvos na mão — sem rede, como o `_set_alvos` deixaria."""
    if plano == "strings":
        assets = assets or [_ativo(1, "Inversor 2.18", "Inversor"),
                            _ativo(2, "Inversor 1.1", "Inversor")]
        titulo, frase, icone = "Recomposição de String", "recomposicao de string", "zap"
    elif plano == "trackers":
        assets = assets or [_ativo(1, "Tracker 1.101", "Estrutura Trackers"),
                            _ativo(2, "Tracker 1.102", "Estrutura Trackers")]
        titulo, frase, icone = "Verificação de Tracker Parado", "verificacao de tracker parado", "alert"
    else:                                  # um plano que NÃO gera ocorrência
        assets = [_ativo(1, "Inversor 2.18", "Inversor"), _ativo(2, "Inversor 1.1", "Inversor")]
        titulo, frase, icone = ("Inspeção Geral do Inversor", "inspecao geral do inversor",
                                "searchcheck")
    w = P.PerfCriar(assets, titulo, frase, icone, on_voltar=lambda: None)
    w._alvos = [{"asset": a, "plano_id_task": 1, "plano_id_item": a["id"], "linkar": True}
                for a in assets]
    w._alvo_by_id = {a["id"]: al for a, al in zip(assets, w._alvos)}
    w._montar_grupos()
    if grupo:
        i = w.cb_grupo.findData(grupo)
        assert i >= 0, "o grupo %s não está no seletor" % grupo
        w.cb_grupo.setCurrentIndex(i)      # dispara _on_grupo, que limpa a marcação
    w._obs = dict(obs or {})
    w._checked = set(marcar)               # por isso a marcação vem DEPOIS da troca de grupo
    w._repop()
    return w


# ── onde o card aparece ────────────────────────────────────────────────────────────────────
def test_o_card_so_existe_nos_planos_que_geram_ocorrencia(qapp):
    assert _tela(qapp, "strings")._aba_ticket == "Strings"
    assert _tela(qapp, "trackers")._aba_ticket == "Trackers"
    w = _tela(qapp, "inspecao")
    assert w._aba_ticket == ""
    assert w.tbl.isColumnHidden(1), "sem ocorrência, a coluna do card não ocupa espaço"
    assert w.ck_ticket is None, "e não há marcador para desmarcar"


def test_o_rotulo_da_coluna_segue_o_plano(qapp):
    assert _tela(qapp, "strings").tbl.horizontalHeaderItem(1).text() == "Strings"
    assert _tela(qapp, "trackers").tbl.horizontalHeaderItem(1).text() == "Trackers"


def test_ativo_desmarcado_nao_tem_card(qapp):
    w = _tela(qapp, "strings", marcar=(1,))
    assert 1 in w._chips and 2 not in w._chips


# ── o número ───────────────────────────────────────────────────────────────────────────────
def test_o_card_nasce_contado_da_observacao(qapp):
    w = _tela(qapp, "strings", obs={1: "Strings Ipv10, Ipv11 e Ipv12 com corrente nula",
                                    2: "String Ipv4 com corrente nula"})
    assert w._chips[1].valor() == 3
    assert w._chips[2].valor() == 1
    assert w._total_qtd() == 4


def test_tracker_INDIVIDUAL_nao_tem_card(qapp):
    """Levi, 11/09: o +/- só vale para ativo que agrupa trackers. Num tracker sozinho a resposta
    é sempre 1, e o botão só convidava ao erro."""
    w = _tela(qapp, "trackers")
    assert w._chips == {}, "tracker individual não ganha card"
    assert w.tbl.isColumnHidden(1), "e a coluna some, em vez de ficar vazia roubando largura"
    assert w._total_qtd() == 2, "mas a quantidade continua valendo 1 por tracker"


_CONJUNTO = [_ativo(1, "Estrutura de Trackers", "Estrutura Trackers"),
             _ativo(2, "NCU 1", "NCU"),
             _ativo(3, "Tracker 1.101", "Estrutura Trackers"),
             _ativo(4, "Tracker 1.102", "Estrutura Trackers")]


@pytest.mark.parametrize("grupo,aid", [("ESTRUTURA", 1), ("NCU", 2)])
def test_o_GENERALIZADO_e_a_NCU_tem_card(qapp, grupo, aid):
    # a Estrutura de Trackers e a NCU representam um conjunto: ali o número varia
    w = _tela(qapp, "trackers", marcar=(aid,), assets=_CONJUNTO, grupo=grupo)
    assert list(w._chips) == [aid]
    assert not w.tbl.isColumnHidden(1)


def test_o_card_do_tracker_nao_le_a_observacao(qapp):
    # "Ipv10" numa observação de tracker não pode virar contagem de tracker
    w = _tela(qapp, "trackers", obs={1: "Strings Ipv10 e Ipv11 sem corrente"},
              marcar=(1,), assets=_CONJUNTO, grupo="ESTRUTURA")
    assert w._chips[1].valor() == 1


# ── o seletor de grupo (Levi, 11/09) ───────────────────────────────────────────────────────
def test_a_lista_abre_nos_trackers_individuais(qapp):
    """"fica como standard tracker": é o ativo do dia a dia, e quem quer o conjunto troca."""
    w = _tela(qapp, "trackers", marcar=(), assets=_CONJUNTO)
    assert w._grupo_atual() == P.GRUPO_TRACKER
    nomes = [w.tbl.item(r, 0).text() for r in range(w.tbl.rowCount())]
    assert nomes == ["Tracker 1.101", "Tracker 1.102"]


def test_o_seletor_mostra_os_grupos_da_usina_com_a_contagem(qapp):
    w = _tela(qapp, "trackers", marcar=(), assets=_CONJUNTO)
    assert [w.cb_grupo.itemText(i) for i in range(w.cb_grupo.count())] == \
        ["Trackers (2)", "Estrutura (1)", "NCU (1)"]


def test_usina_so_com_trackers_nao_mostra_seletor(qapp):
    # com um grupo só o seletor não decide nada e vira ruído na barra
    w = _tela(qapp, "trackers", marcar=())
    assert not w._campo_grupo.isVisible()


def test_trocar_de_grupo_limpa_a_marcacao(qapp):
    """Criar OS num ativo que a pessoa não está mais vendo é surpresa que não se desfaz depois."""
    w = _tela(qapp, "trackers", marcar=(3, 4), assets=_CONJUNTO)
    assert len(w._checked) == 2
    w.cb_grupo.setCurrentIndex(w.cb_grupo.findData("NCU"))
    assert w._checked == set()
    assert [w.tbl.item(r, 0).text() for r in range(w.tbl.rowCount())] == ["NCU 1"]


def test_mudar_a_observacao_reconta(qapp):
    w = _tela(qapp, "strings", obs={1: "String Ipv4 sem corrente"}, marcar=(1,))
    assert w._chips[1].valor() == 1
    w._obs_mudou(1, "Strings Ipv4, Ipv5 e Ipv9 sem corrente")
    assert w._chips[1].valor() == 3


def test_a_correcao_a_mao_vence_e_nao_e_atropelada(qapp):
    """O caso que motiva o card ser editável: faixa ('Strings 1 a 12') a régua não entende."""
    w = _tela(qapp, "strings", obs={1: "Strings 1 a 12 sem corrente"}, marcar=(1,))
    chip = w._chips[1]
    assert chip.valor() == 1 and chip._estado == "presumido"
    chip.ed.setText("12"); chip._virar_manual()
    assert chip.manual() and w._qtd_de(1) == 12
    w._obs_mudou(1, "Strings Ipv1 e Ipv2 sem corrente")     # recálculo não pode desfazer
    assert w._qtd_de(1) == 12


def test_o_numero_escolhido_sobrevive_ao_redesenho_da_tabela(qapp):
    # a tabela é redesenhada a cada filtro e a cada marcar/desmarcar; sem a memória em _qtd a
    # correção da pessoa sumiria sem ela perceber
    w = _tela(qapp, "strings", obs={1: "String Ipv4 sem corrente"}, marcar=(1,))
    w._chips[1].ed.setText("7"); w._chips[1]._virar_manual()
    w._repop()
    assert w._qtd_de(1) == 7 and w._chips[1].manual()


def test_voltar_ao_numero_do_app_devolve_o_verde(qapp):
    """Levi, 11/09: "se eu volto para 1 não fica verde novamente". Manual não é caminho sem volta:
    o âmbar diz que há divergência, e sem divergência não há o que sinalizar."""
    w = _tela(qapp, "trackers", marcar=(1,), assets=_CONJUNTO, grupo="ESTRUTURA")
    chip = w._chips[1]
    assert chip._estado == "auto"
    chip._passo(1); chip._passo(1)
    assert chip.valor() == 3 and chip.manual(), "subiu: é correção, fica âmbar"
    chip._passo(-1); chip._passo(-1)
    assert chip.valor() == 1
    assert not chip.manual(), "voltou ao número do app: verde de novo"
    assert 1 not in w._qtd, "e não sobra escolha manual guardada"


def test_voltar_a_contagem_da_observacao_tambem_devolve_o_verde(qapp):
    w = _tela(qapp, "strings", obs={1: "Strings Ipv10 e Ipv11 sem corrente"}, marcar=(1,))
    chip = w._chips[1]
    assert chip.valor() == 2 and not chip.manual()
    chip.ed.setText("5"); chip._virar_manual()
    assert chip.manual() and w._qtd_de(1) == 5
    chip.ed.setText("2"); chip._virar_manual()
    assert not chip.manual(), "igual à contagem = sem divergência"


def test_o_card_nunca_desce_abaixo_de_1(qapp):
    # zero na planilha seria uma ocorrência que não afetou nada — e ela existe, senão não há OS
    w = _tela(qapp, "strings", obs={1: "String Ipv4 sem corrente"}, marcar=(1,))
    for _ in range(5):
        w._chips[1]._passo(-1)
    assert w._chips[1].valor() == 1


# ── o marcador ─────────────────────────────────────────────────────────────────────────────
def test_o_marcador_nasce_marcado(qapp):
    # é o comportamento que já estava no ar desde 31/08 — o que muda é ficar visível
    assert _tela(qapp, "strings")._gerar_ticket() is True


def test_o_resumo_conta_ocorrencias_e_strings(qapp):
    w = _tela(qapp, "strings", obs={1: "Strings Ipv10 e Ipv11 sem corrente",
                                    2: "String Ipv4 sem corrente"})
    txt = w.lb_ticket.text()
    assert "2 ocorrências" in txt and "Strings indisp" in txt and "3 strings" in txt


def test_desmarcado_o_resumo_diz_que_nao_registra(qapp):
    w = _tela(qapp, "strings")
    w.ck_ticket.setChecked(False)
    w._upd_ticket_resumo()
    assert "sem ocorrência" in w.lb_ticket.text().lower()


# ── o que a criação recebe ─────────────────────────────────────────────────────────────────
def test_a_frase_do_fim_conta_os_tickets(qapp):
    w = _tela(qapp, "strings")
    frase, erros = w._frase_tickets([{"aba": "Strings", "ok": True, "quantidade": 3},
                                     {"aba": "Strings", "ok": True, "quantidade": 2}])
    assert "2 tickets criados" in frase and "5 strings" in frase
    assert not erros


def test_a_frase_do_fim_denuncia_a_linha_que_nao_entrou(qapp):
    w = _tela(qapp, "strings")
    frase, erros = w._frase_tickets([{"aba": "Strings", "ok": True, "quantidade": 3},
                                     {"aba": "Strings", "ok": False, "erro": "relay fora"}])
    assert "1 ocorrência NÃO foi registrada" in frase
    assert erros == ["relay fora"]


def test_sem_marcador_a_frase_do_fim_diz_isso_com_todas_as_letras(qapp):
    w = _tela(qapp, "strings")
    w.ck_ticket.setChecked(False)
    frase, _ = w._frase_tickets([])
    assert "Sem ticket" in frase


def test_plano_sem_ocorrencia_nao_fala_de_ticket(qapp):
    frase, erros = _tela(qapp, "inspecao")._frase_tickets([])
    assert frase == "" and erros == []

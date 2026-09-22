# -*- coding: utf-8 -*-
"""Visão de Tickets na Performance web (21/09).

A tela já tinha a coluna de quantidade preparada, mas o `montar_itens` mandava `gerar_ticket:
False` fixo, com um comentário dizendo "só no app por ora". Ligar isso é gravar em PLANILHA DE
PRODUÇÃO a partir da web — por isso veio junto o que o app já fazia: caixa marcada por padrão,
confirmação dizendo quantas ocorrências vão (e o aviso quando NÃO vão), e a contagem no fim."""
import io
import os

from os_web import perf_web

FRASE_STR = "recomposicao de string"
FRASE_TRK = "verificacao de tracker parado"
_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "os_creator", "os_web", "static", "perf.js")


def _corpo(**kw):
    base = {"itens": [{"asset": {"id": 1, "code": "INV1", "label": "INV1"},
                       "plano_id_task": 9, "plano_id_item": 1, "note": "PV1 e PV2 sem corrente"}],
            "responsavel": {"id_personnel": 7, "name": "F"}, "evento": "2026-09-21T08:00"}
    base.update(kw)
    return base


def test_a_caixa_marcada_manda_gerar_ticket():
    itens, _kw, erro = perf_web.montar_itens(_corpo())
    assert not erro and itens[0]["gerar_ticket"] is True


def test_desmarcar_a_caixa_desliga_a_ocorrencia():
    itens, _kw, erro = perf_web.montar_itens(_corpo(gerar_ticket=False))
    assert not erro and itens[0]["gerar_ticket"] is False


def test_quantidade_em_branco_deixa_o_servidor_contar():
    """`qtd_ticket=None` faz o `nascer_ticket` aplicar a regra medida; zero ou lixo idem."""
    itens, _kw, _e = perf_web.montar_itens(_corpo())
    assert itens[0]["qtd_ticket"] is None
    for ruim in ("", "abc", 0, -3, None):
        c = _corpo()
        c["itens"][0]["qtd_ticket"] = ruim
        assert perf_web.montar_itens(c)[0][0]["qtd_ticket"] is None, ruim


def test_quantidade_escrita_a_mao_vence():
    c = _corpo()
    c["itens"][0]["qtd_ticket"] = 6
    itens, _kw, _e = perf_web.montar_itens(c)
    assert itens[0]["qtd_ticket"] == 6


def test_a_contagem_de_strings_sai_da_regra_do_app():
    """Sem porte para o JavaScript: a regra vive em `tickets_nasce.contar_strings`."""
    assert perf_web.qtd_sugerida(FRASE_STR, "PV1, PV2 e PV3 com corrente nula")["qtd"] == 3
    assert perf_web.qtd_sugerida(FRASE_STR, "sem marcador nenhum")["qtd"] == 1
    assert perf_web.qtd_sugerida(FRASE_TRK, "qualquer coisa")["qtd"] == 1   # tracker é sempre 1


def test_o_resultado_conta_os_tickets_criados():
    res = [{"ok": True, "folio": 101, "ticket": {"ok": True, "quantidade": 3}},
           {"ok": True, "folio": 102, "ticket": {"ok": True, "quantidade": 2}}]
    m = perf_web.mensagem_resultado(res, FRASE_STR, True)
    assert "2 tickets criados" in m["mensagem"] and "5 strings no total" in m["mensagem"]


def test_o_resultado_diz_alto_quando_a_linha_falhou():
    """A OS existe e a linha não — foi o caso da 13785, e é o que não pode passar batido."""
    res = [{"ok": True, "folio": 101, "ticket": {"ok": False, "erro": "não li o cabeçalho"}}]
    m = perf_web.mensagem_resultado(res, FRASE_STR, True)
    assert "NÃO foi registrada" in m["mensagem"] and "a OS existe, a linha não" in m["mensagem"]
    assert "não li o cabeçalho" in " ".join(m["detalhes"])


def test_com_a_caixa_desmarcada_o_resultado_avisa():
    m = perf_web.mensagem_resultado([{"ok": True, "folio": 1}], FRASE_STR, False)
    assert "Sem ticket" in m["mensagem"]


def test_plano_sem_aba_nao_fala_de_ticket():
    m = perf_web.mensagem_resultado([{"ok": True, "folio": 1}], "inspecao geral do inversor", True)
    assert "ticket" not in m["mensagem"].lower()


def test_a_tela_pergunta_a_quantidade_ao_servidor():
    js = io.open(_JS, encoding="utf-8").read()
    assert "/os/api/performance/qtd" in js
    assert "gerar_ticket: ger" in js and "qtd_ticket: qtd[a.id]" in js

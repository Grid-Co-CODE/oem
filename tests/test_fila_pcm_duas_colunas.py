# -*- coding: utf-8 -*-
"""Fila do PCM em duas colunas + faixa das subtarefas (16/09).

O que motivou, medido na solicitação 3620 — a que trazia 20 linhas de procedimento da Huawei:
o botão Aprovar nascia a 1413 px do topo numa janela de 844, e o último parágrafo do relato era
CORTADO sem aviso (o texto pedia 404 px, o campo dava 400). A tela era uma coluna só, então o
material de leitura ficava na frente do material de decisão — e metade da largura, vazia.

A segunda rodada veio do "ficaram espaços abertos na página": as subtarefas desceram para uma
faixa de largura inteira (com 13 delas a coluna da decisão tinha o dobro da altura da outra) e a
caixa da observação passou a ser dimensionada para EMPATAR as duas colunas."""
import pytest
from PyQt6.QtWidgets import QFrame

import solic_spec as sp

LONGO = "\n\n".join(
    "Parágrafo %d do procedimento que o fabricante mandou, com detalhe suficiente para ocupar "
    "mais de uma linha na coluna da esquerda e obrigar a caixa a rolar." % i for i in range(1, 9))
CURTO = "Piranômetro 1 sem leitura desde ontem à tarde."


def _solicitacao(relato):
    return {"id_code": 3620, "usina": "Santa Maria do Pará 1", "ativo": "Inversor 5.2 Huawei",
            "criado_por": "Laura Aguiar", "data": "2026-09-12 10:00:00", "status": "Pendente",
            "cor_status": "#01C0DD", "descricao_full": "Ventoinhas inoperantes",
            "observacao": relato + "\n\n" + sp.bloco({"tema": "inversor_inspecao"})}


def _monta(qapp, relato):
    from steps.solic_pcm import _Fila
    f = _Fila(lambda: None)
    f.resize(1600, 950)
    f.show()
    qapp.processEvents()
    f.set_itens([_solicitacao(relato)], [])
    for _ in range(4):          # a altura se assenta em duas passadas; folga para o layout
        qapp.processEvents()
    return f


@pytest.fixture
def fila(qapp):
    return _monta(qapp, LONGO)


def _cartao(fila, widget):
    """O cartão (boxLado) que contém este widget."""
    return next(w for w in fila.findChildren(QFrame)
                if w.objectName() == "boxLado" and w.isAncestorOf(widget))


def test_a_ficha_tem_pedido_decisao_e_a_faixa_das_subtarefas(fila):
    """Três caixas: o que se lê, o que se decide e — de ponta a ponta — as subtarefas."""
    caixas = [w for w in fila.findChildren(QFrame) if w.objectName() == "boxLado"]
    assert len(caixas) == 3
    pedido, decisao = _cartao(fila, fila.ed_obs), _cartao(fila, fila.cb_tema)
    subs = _cartao(fila, fila.editor_subs)
    assert pedido is not decisao and subs not in (pedido, decisao)
    px = pedido.mapTo(fila, pedido.rect().topLeft()).x()
    dx = decisao.mapTo(fila, decisao.rect().topLeft()).x()
    assert px < dx, "o pedido fica à esquerda da decisão"
    assert subs.width() > decisao.width(), "a faixa das subtarefas ocupa a largura inteira"
    assert subs.mapTo(fila, subs.rect().topLeft()).y() > pedido.mapTo(
        fila, pedido.rect().topLeft()).y(), "a faixa vem depois das duas colunas"


def test_as_colunas_ficam_parecidas_quando_o_relato_e_curto(qapp):
    """O vazio que o Levi viu: a coluna do pedido terminava muito antes da outra. Com a caixa
    da observação dimensionada para empatar, a diferença tem de ser pequena."""
    f = _monta(qapp, CURTO)
    pedido, decisao = _cartao(f, f.ed_obs), _cartao(f, f.cb_tema)
    assert abs(pedido.height() - decisao.height()) < 60, (
        "cartões desencontrados: %d x %d" % (pedido.height(), decisao.height()))


def test_relato_longo_rola_em_vez_de_cortar(fila):
    """A caixa para de crescer e passa a rolar. Antes o rótulo simplesmente cortava o que não
    coubesse — e ninguém via que havia mais texto."""
    assert fila.ed_obs.verticalScrollBar().maximum() > 0, "sem rolagem o texto estaria cortado"


def test_o_cartao_nao_cresce_com_o_tamanho_do_relato(qapp):
    """A regra que o Levi pediu em 16/09: "caso o texto da observação aumente o card não
    aumenta, será limitado por um scrol". Relato de uma linha ou de trinta, o cartão do pedido
    tem a mesma altura — quem passa disso fica atrás da rolagem."""
    curta = _monta(qapp, CURTO)
    longa = _monta(qapp, LONGO)
    assert _cartao(curta, curta.ed_obs).height() == _cartao(longa, longa.ed_obs).height()
    # A caixa em si pode variar uns poucos pixels: no relato longo o link "ver inteira" aparece
    # e ocupa a sua linha no cabecalho. O que nao pode mudar e o CARTAO, que e o que se ve.
    assert abs(curta.ed_obs.height() - longa.ed_obs.height()) <= 12
    assert longa.ed_obs.verticalScrollBar().maximum() > 0
    assert curta.ed_obs.verticalScrollBar().maximum() == 0, "relato curto não deveria rolar"


def test_ver_inteira_so_aparece_quando_ha_texto_escondido(fila, qapp):
    alt = fila.ed_obs.height()
    assert fila.b_ver_obs.isVisible(), "relato longo: o botão tem de aparecer"
    fila.b_ver_obs.click()
    qapp.processEvents()
    assert fila.ed_obs.height() > alt, "'ver inteira' tem de mostrar o resto"
    assert fila.ed_obs.verticalScrollBar().maximum() == 0, "expandida, não sobra texto"
    assert fila.b_ver_obs.text() == "ver menos"
    fila.b_ver_obs.click()
    qapp.processEvents()
    # tolerancia: expandida, a pagina fica mais alta e ganha barra de rolagem, o que estreita as
    # colunas em ~15 px; ao voltar, o texto quebra em outro ponto e a conta da altura muda junto
    assert abs(fila.ed_obs.height() - alt) <= 20


def test_relato_curto_nao_oferece_ver_inteira(qapp):
    """Num relato de uma linha o botão seria um convite para nada."""
    f = _monta(qapp, CURTO)
    assert not f.b_ver_obs.isVisible()


def test_modo_leitura_trava_sem_apagar_o_texto(fila):
    """`setEnabled(False)` pintaria o QTextEdit inteiro de cinza — justamente o relato que a
    pessoa abriu a ficha para ler. O campo trava editável, não visível."""
    fila.set_somente_leitura(True)
    fila.ed_obs.abrir()
    assert fila.ed_obs.isReadOnly(), "em consulta a observação não pode virar editor"
    assert fila.ed_obs.isEnabled(), "desabilitar cinzaria o texto"


def test_o_texto_da_subtarefa_comeca_no_inicio(fila):
    """O QLineEdit rola para o FIM do texto quando ele não cabe: com a coluna mais estreita, a
    lista aparecia começando no meio da palavra."""
    linhas = getattr(fila.editor_subs, "_linhas", None) or []
    assert linhas, "o corpo de teste precisa de subtarefas"
    for ln in linhas:
        assert ln.ed.cursorPosition() == 0

# -*- coding: utf-8 -*-
"""QUEM CEDE LARGURA quando a tabela de tickets não cabe na tela.

Levi, 06/09: "a coluna Período está cortada". Ela estava, e não era um descuido de uma coluna só:
o encaixe encolhia TODAS proporcionalmente, então faltando 45px a tela inteira elidia um pouco —
a data virava `24/05/2025 08:0`, o período `1 ano e 3 me…`. Medido em janela de 1536: cinco
colunas cortadas ao mesmo tempo.

A régua nova separa dois tipos de coluna. As de VALOR ATÔMICO (data, período, OS, ativo, usina)
não suportam corte: meia data não diz nada, e nenhuma delas tem painel ou hover com o resto. As
duas ELÁSTICAS — Resumo e Status — suportam, e são as mesmas que levam a folga quando sobra
espaço. Então a dívida vai toda para elas primeiro.

Os testes de `_encolher` valem offscreen porque a função é aritmética pura: nenhum deles depende
de métrica de fonte, que é justamente o que o offscreen não tem.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import steps.tickets as tk
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem


# ── a aritmética do encolhimento ──────────────────────────────────────────────────────────
def test_encolher_tira_proporcional_a_folga():
    """Quem tem mais folga sobre o piso cede mais. 100 de dívida entre folgas de 100 e 50 sai
    2 para 1 — sem isso, a coluna já apertada perderia tanto quanto a larga."""
    largs = [200, 150]
    assert tk._encolher(largs, [0, 1], -90, 100) == 0
    assert largs == [140, 120]          # perdeu 60 e 30


def test_encolher_nunca_passa_do_piso():
    largs = [120, 120]
    tk._encolher(largs, [0, 1], -400, 100)
    assert largs == [100, 100]


def test_encolher_devolve_o_que_nao_coube():
    """É o que permite cobrar primeiro de quem tem folga e só depois passar o chapéu."""
    largs = [120, 120]                  # 40 de folga sobre o piso 100
    assert tk._encolher(largs, [0, 1], -100, 100) == -60


def test_encolher_sem_folga_nenhuma_devolve_a_divida_inteira():
    """Divisão por zero era o caminho fácil aqui; o antigo `or 1` mascarava o caso em vez de
    responder que não há de onde tirar."""
    largs = [100, 100]
    assert tk._encolher(largs, [0, 1], -80, 100) == -80
    assert largs == [100, 100]


def test_encolher_ignora_quem_esta_fora_da_lista():
    largs = [500, 120, 500]
    tk._encolher(largs, [1], -20, 100)
    assert largs[0] == 500 and largs[2] == 500


# ── a política: quem cede é quem ganha ────────────────────────────────────────────────────
class _Fingida:
    """O bastante de `TicketsTab` para rodar o encaixe: ele só usa `tab` e `_preciso_por_coluna`.

    Instanciar a tela inteira aqui puxaria a rede (ocorrências e catálogo de ativos) e, offscreen,
    mediria fonte que não existe — o que se quer trancar é a REGRA de repartição, e ela é
    aritmética."""

    def __init__(self, precisos, ncols):
        self.tab = QTableWidget(0, ncols)
        self.tab.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tab.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._precisos = precisos

    def _preciso_por_coluna(self, nomes):
        return list(self._precisos)

    _ajustar_larguras_por_conteudo = tk.TicketsTab._ajustar_larguras_por_conteudo
    _hover_do_que_nao_coube = tk.TicketsTab._hover_do_que_nao_coube


def _encaixar(qapp, deficit, atomica=70):
    """Monta a aba Trackers com um déficit conhecido e devolve {coluna: largura}.

    `deficit` é a `sobra` que o encaixe vai encontrar: negativo, falta espaço. A primeira versão
    deste ajudante trocou o sinal — as elásticas passavam a pedir MENOS e o teste media o caminho
    da folga achando que media o do aperto."""
    nomes = tk.colunas_da_aba("Trackers")
    t = _Fingida([0] * len(nomes), len(nomes))
    t.tab.resize(900, 300)
    qapp.processEvents()
    vp = t.tab.viewport().width()
    assert vp > 400, "viewport pequeno demais para o teste ser significativo: %d" % vp
    atom = {n: atomica for n in nomes if n not in (tk._ROTULO_CAUSA, tk._COL_STATUS)}
    resto = vp - deficit - sum(atom.values())
    if deficit < 0:
        assert resto > 2 * tk._LARG_ELASTICA, "o cenário não deixa as elásticas acima do piso"
    precisos = [atom.get(n, resto // 2) for n in nomes]
    t._precisos = precisos
    t._ajustar_larguras_por_conteudo(nomes)
    pedido = dict(zip(nomes, precisos))
    return nomes, {n: t.tab.columnWidth(i) for i, n in enumerate(nomes)}, vp, pedido


def test_faltando_espaco_a_coluna_periodo_nao_encolhe(qapp):
    """O pedido do Levi, trancado. Com a régua antiga ela perdia largura junto com as outras."""
    nomes, larg, _, _ = _encaixar(qapp, deficit=-120)
    for n in nomes:
        if n not in (tk._ROTULO_CAUSA, tk._COL_STATUS):
            assert larg[n] == 70, "%s cedeu largura e não deveria (%d)" % (n, larg[n])


def test_faltando_espaco_quem_cede_sao_as_duas_elasticas(qapp):
    """As duas, e não uma: drenar o Resumo inteiro antes de encostar no Status deixaria uma
    coluna no piso ao lado de outra intacta."""
    _, larg, _, pedido = _encaixar(qapp, deficit=-120)
    for n in (tk._ROTULO_CAUSA, tk._COL_STATUS):
        assert larg[n] < pedido[n], "%s não cedeu nada" % n
        assert larg[n] >= tk._LARG_ELASTICA


def test_a_soma_das_colunas_fecha_exatamente_no_viewport(qapp):
    """Sem isto a tabela transborda alguns pixels e a última coluna sai cortada pela borda — as
    duas barras de rolagem estão desligadas, então não há nada que denuncie a sobra."""
    for deficit in (-300, -120, -1, 0, 40, 300):
        nomes, larg, vp, _ = _encaixar(qapp, deficit)
        assert sum(larg.values()) == vp, "déficit %d fechou em %d, viewport %d" % (
            deficit, sum(larg.values()), vp)


def test_deficit_grande_demais_transborda_para_as_outras(qapp):
    """As elásticas têm piso. Passando dele, as atômicas voltam a ceder — é a saída honesta:
    numa janela impossível alguma coisa TEM de encolher, e o que não pode é encolher antes da
    hora."""
    # atômicas largas de propósito: só assim o piso das elásticas não dá conta sozinho.
    nomes, larg, _, _ = _encaixar(qapp, deficit=-400, atomica=110)
    assert larg[tk._ROTULO_CAUSA] == tk._LARG_ELASTICA
    assert larg[tk._COL_STATUS] == tk._LARG_ELASTICA
    assert larg["Período"] < 110


def test_o_piso_das_elasticas_e_maior_que_o_das_outras():
    """Elas são as únicas colunas de texto corrido: em 58px não sobra palavra nenhuma."""
    assert tk._LARG_ELASTICA > tk._LARG_MINIMA


# ── o hover de quem foi cortado ───────────────────────────────────────────────────────────
def test_celula_cortada_ganha_o_texto_inteiro_no_hover(qapp):
    nomes = tk.colunas_da_aba("Trackers")
    t = _Fingida([0] * len(nomes), len(nomes))
    t.tab.setRowCount(1)
    for i in range(len(nomes)):
        t.tab.setItem(0, i, QTableWidgetItem("x" * 300))
    t._hover_do_que_nao_coube([tk._LARG_MINIMA] * len(nomes))
    assert t.tab.item(0, 0).toolTip() == "x" * 300


def test_o_hover_que_ja_existe_nao_e_sobrescrito(qapp):
    """A primeira célula da linha explica a COR do estado e o Inversor conta as strings afetadas.
    Sobrescrever trocaria dado por formatação."""
    nomes = tk.colunas_da_aba("Trackers")
    t = _Fingida([0] * len(nomes), len(nomes))
    t.tab.setRowCount(1)
    it = QTableWidgetItem("y" * 300)
    it.setToolTip("ocorrência aberta há 12 dias")
    t.tab.setItem(0, 0, it)
    t._hover_do_que_nao_coube([tk._LARG_MINIMA] * len(nomes))
    assert it.toolTip() == "ocorrência aberta há 12 dias"


def test_celula_que_cabe_nao_ganha_hover(qapp):
    """Hover em célula inteira é ruído: some e aparece sem motivo enquanto se lê a lista."""
    nomes = tk.colunas_da_aba("Trackers")
    t = _Fingida([0] * len(nomes), len(nomes))
    t.tab.setRowCount(1)
    t.tab.setItem(0, 0, QTableWidgetItem("a"))
    t._hover_do_que_nao_coube([400] * len(nomes))
    assert t.tab.item(0, 0).toolTip() == ""


def test_o_encaixe_nao_dispara_o_sinal_de_edicao(qapp):
    """`itemChanged` é o mesmo sinal da edição da causa raiz. Sem bloquear, encaixar coluna
    pareceria digitação e acenderia o Salvar sozinho — o `_pintar_selecao` já tinha aprendido
    isso ao mudar cor de célula."""
    nomes = tk.colunas_da_aba("Trackers")
    t = _Fingida([0] * len(nomes), len(nomes))
    t.tab.setRowCount(1)
    t.tab.setItem(0, 0, QTableWidgetItem("z" * 300))
    vistos = []
    t.tab.itemChanged.connect(lambda it: vistos.append(it))
    t._hover_do_que_nao_coube([tk._LARG_MINIMA] * len(nomes))
    assert vistos == []

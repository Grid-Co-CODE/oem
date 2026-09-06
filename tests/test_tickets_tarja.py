"""A cor de estado: de coluna, para tarja ao lado, para BORDA — em dois passos, no mesmo dia.

06/09, de manhã: "ao invés dessas cores ao lado funcionarem como uma coluna, pode deixar do lado
de fora da linha para que em strings tenha mais espaço para a coluna período". Medido antes de
mexer: o `ResizeToContents` inflava a coluna da tarja até o glifo "▐" e ela ocupava 34px.

06/09, à tarde, sobre o protótipo do estilo novo: "faltou a borda, pode inserir as cores laterais
nas bordas". A cor deixou de ser um objeto solto ao lado e virou a própria aresta esquerda.

Estes testes trancam o que os dois passos não podem perder: a cor continua dizendo o estado, o
hover continua explicando a cor, e a borda não pode roubar o clique da tabela.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import steps.tickets as tk
import tickets_spec


def test_a_tarja_nao_e_mais_uma_coluna():
    # se voltar a ser, volta junto o custo de 34px e o caso especial da largura.
    for aba in ("Trackers", "Strings"):
        assert "" not in tk.colunas_da_aba(aba)
        assert tk.colunas_da_aba(aba)[0] == "Usina"


def test_a_borda_recebe_a_tabela_e_a_fonte_de_cor(qapp):
    """Sem os dois, a fita não tem como saber ONDE cada linha começa nem DE QUE COR ela é — e a
    borda voltaria a ser um contorno neutro, sem dizer estado nenhum."""
    m = tk._MolduraTabela("#121A2B", tk._LINHA, 10, tab="tabela-falsa",
                          cor_da_linha=lambda r: "#e05454")
    assert m.borda._tab == "tabela-falsa"
    assert m.borda._cor_da_linha(0) == "#e05454"
    m.deleteLater()


def test_a_fita_nao_desenha_quando_nao_ha_o_que_pintar(qapp):
    """Chamada sem tabela, a pintura tem de sair calada. Ela roda a cada repintura da tela, e um
    erro dentro de paintEvent no PyQt6 vira exceção engolida com a tela pela metade."""
    m = tk._MolduraTabela("#121A2B", tk._LINHA, 10)      # sem tab nem cor_da_linha
    m.resize(200, 120)
    # `grab()` e não `show()`: o show dispara o mesmo paintEvent, mas põe a janela no gerenciador
    # e, com a suíte inteira rodando na MESMA QApplication, aborta o interpretador sem traceback
    # (saída 127) — o teste "some" em vez de falhar. O grab pinta no pixmap e não abre nada.
    m.grab()
    m.deleteLater()


def test_a_borda_nao_rouba_o_clique(qapp):
    from PyQt6.QtCore import Qt
    m = tk._MolduraTabela("#121A2B", tk._LINHA, 10)
    # ela cobre a tabela inteira: sem isto nenhuma linha responderia a clique.
    assert m.borda.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    m.deleteLater()


def test_a_cor_vem_do_estado_da_ocorrencia(qapp):
    tela = tk.TicketsTab.__new__(tk.TicketsTab)
    tela._visiveis = [{"_estado": "aberta"}, {"_estado": "encerrada"}]
    assert tela._cor_da_linha(0) == tickets_spec.COR_ESTADO["aberta"]
    assert tela._cor_da_linha(1) == tickets_spec.COR_ESTADO["encerrada"]
    assert tela._cor_da_linha(9) == ""         # fora da lista não pinta nada


def test_o_hover_continua_explicando_a_cor(qapp):
    """Levi, 31/08: "ao passar o mouse nessas cores apareça o detalhamento".

    A explicação já mudou de casa duas vezes — era o tooltip do item da coluna 0, virou o
    `event()` da tarja lateral, e agora é o tooltip da PRIMEIRA célula, porque a borda não recebe
    hover. O texto é o mesmo desde o começo; o que muda é quem o carrega."""
    tela = tk.TicketsTab.__new__(tk.TicketsTab)
    tela._visiveis = [{"_estado": "aberta"}]
    dica = tela._dica_da_linha(0)
    assert tickets_spec.NOME_ESTADO["aberta"] in dica
    assert len(dica) > len(tickets_spec.NOME_ESTADO["aberta"])   # traz a explicação junto
    assert tela._dica_da_linha(5) == ""

"""O acabamento da tabela de tickets: a borda arredondada por cima das células.

Levi, 06/09: "a ponta ainda está sendo comida um pouquinho, como se o fundo do cabeçalho estivesse
passando por cima da linha — a linha deve estar na frente das células e cabeçalhos para não termos
esses erros toscos."

O diagnóstico dele é o certo, e é ordem de PINTURA, não folha de estilo: o Qt pinta o pai e só
depois os filhos, o fundo do cabeçalho é opaco, e num canto arredondado o arco entra bem mais do
que 1px para dentro. Enquanto a borda era do pai, o cabeçalho sempre comia um naco da curva.

Estes testes trancam as três propriedades de que o conserto depende. Todas já quebraram uma vez:
a borda ficou no tamanho de nascença porque o `resizeEvent` não chega em widget escondido, e a
primeira versão da moldura tinha borda no QSS — que reintroduz a linha dupla ao lado da rolagem.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import steps.tickets as tk
from PyQt6.QtCore import Qt


@pytest.fixture
def moldura(qapp):
    m = tk._MolduraTabela("#121A2B", "#818487", 10)
    yield m
    m.deleteLater()


def test_a_borda_nao_rouba_o_clique_da_tabela(moldura):
    # ela cobre a tabela inteira: sem este atributo, nenhuma linha responderia a clique — a tela
    # ficaria bonita e morta.
    assert moldura.borda.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_a_borda_nao_pinta_fundo(moldura):
    # se pintasse, cobriria as células que ela deveria apenas contornar.
    assert moldura.borda.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
    assert moldura.borda.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_a_borda_cobre_a_moldura_inteira_ao_aparecer(moldura):
    # o Qt SEGURA o resizeEvent enquanto o widget está escondido. Sem o showEvent, a borda
    # aparecia no tamanho de nascença (100x30) num canto e o resto da tabela ficava sem contorno.
    moldura.resize(420, 260)
    moldura.show()
    assert moldura.borda.geometry().size() == moldura.size()


def test_a_borda_acompanha_o_redimensionamento(moldura):
    moldura.show()
    moldura.resize(900, 500)
    assert moldura.borda.geometry().size() == moldura.size()


def test_a_moldura_nao_desenha_borda_propria(moldura):
    # a borda do QSS ficava DEBAIXO dos filhos e reaparecia como segunda linha ao lado da barra de
    # rolagem — que foi a reclamação anterior ("essa linha dupla não é aceitável").
    folha = moldura.styleSheet()
    assert "border:none" in folha.replace(" ", "")
    assert "1pxsolid" not in folha.replace(" ", "")

# -*- coding: utf-8 -*-
"""A coluna Período dos tickets: a unidade acompanha a grandeza (Levi, 06/09).

Até 31/08 era `"%d dias"` seco, e funcionava porque as ocorrências eram recentes. Com a base
inteira na tela apareceram **470 e 462 dias** na aba Trackers — ninguém converte isso de cabeça,
e o número deixava de dizer o que a coluna existe para dizer: se é coisa de ontem ou de um ano.
"""
import pytest
from steps.tickets import _periodo_txt as p


@pytest.mark.parametrize("dias,esperado", [
    (None, "—"),
    (-1, "—"),          # `_dias_desde` já devolve None nesse caso; aqui é cinto
    (0, "0 dias"),
    (1, "1 dia"),       # singular
    (2, "2 dias"),
    (30, "30 dias"),
    (59, "59 dias"),
    (60, "2 meses"),
    (90, "3 meses"),
    (181, "6 meses"),
    (359, "11 meses"),
    (360, "1 ano"),
    (400, "1 ano e 1 mês"),   # singular do mês no resto
    (462, "1 ano e 3 meses"),
    (470, "1 ano e 3 meses"),
    (730, "2 anos"),
])
def test_a_unidade_acompanha_a_grandeza(dias, esperado):
    assert p(dias) == esperado


def test_o_dia_sobrevive_ate_60_e_nao_ate_30():
    """30 é o limiar do alarme vermelho e do filtro "Abertas há +30 dias". Se a unidade virasse
    mês exatamente ali, "31 dias" viraria "1 mês" no mesmo ponto em que a linha fica vermelha, e
    quem varre a lista perderia a noção de quanto passou do limite."""
    for d in range(28, 60):
        assert p(d).endswith("dias"), "%d já virou mês antes da hora" % d
    assert p(60).endswith("meses")


def test_nao_existe_o_degrau_de_12_meses():
    """A primeira versão contava o ano à parte (`dias // 365`) e produzia "12 meses" com 364 dias
    e "1 ano" com 365 — os dois na mesma tela. A escada agora é uma só, em meses."""
    todos = {p(d) for d in range(1, 1200)}
    assert "12 meses" not in todos
    assert "0 meses" not in todos
    assert "0 anos" not in todos


def test_nunca_promete_precisao_que_a_origem_nao_tem():
    """`_dias_desde` conta dias corridos entre datas que muitas vezes vêm sem hora. Arredondar
    para baixo é o que mantém o número honesto."""
    assert p(89) == "2 meses"      # e não "3 meses"
    assert p(719) == "1 ano e 11 meses"

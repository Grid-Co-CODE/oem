"""Portão de aceite: o cálculo do app tem de bater com o que já está na planilha.

Gabarito são as 232 linhas de `Strings indisp`, a única das duas abas cuja fórmula de
indisponibilidade resolve (a de Trackers aponta para arquivo externo e está vazia, 1.516 linhas
encerradas sem número).

Divergência que não seja arredondamento REPROVA: é conta que vai para relatório de cliente."""
import io
import json
import os

from tickets_calc import indisponibilidade_gridco, indisponibilidade_horas

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "tickets_strings.json")
TOLERANCIA = 0.02          # ~1 minuto; cobre arredondamento, não cobre régua errada


def _linhas():
    with io.open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _num(v):
    return v if isinstance(v, (int, float)) else None


def test_a_fixture_tem_gabarito_suficiente():
    com_valor = [l for l in _linhas() if _num(l.get("Indisponibilidade (horas)")) is not None]
    assert len(com_valor) >= 200, "gabarito pequeno demais para o portão significar algo"


def test_indisponibilidade_bate_com_a_planilha():
    ruins = []
    for l in _linhas():
        esperado = _num(l.get("Indisponibilidade (horas)"))
        if esperado is None:
            continue
        obtido = indisponibilidade_horas(l.get("Início da ocorrência"),
                                         l.get("Fim da ocorrência"))
        if obtido is None or abs(obtido - esperado) > TOLERANCIA:
            ruins.append((l.get("_row"), l.get("Início da ocorrência"),
                          l.get("Fim da ocorrência"), esperado, obtido))
    assert not ruins, "linhas divergentes (linha, ini, fim, planilha, app): %s" % ruins[:10]


def test_gridco_bate_com_a_planilha():
    ruins = []
    for l in _linhas():
        esperado = _num(l.get("Indisponibilidade da Grid Co. (horas)"))
        base = _num(l.get("Indisponibilidade (horas)"))
        if esperado is None or base is None:
            continue
        obtido = indisponibilidade_gridco(base, l.get("Responsabilidade da Grid Co.?"))
        # o piso em zero é desvio DELIBERADO do Excel: onde a planilha ficou negativa, o app
        # devolve 0 e isso não conta como divergência.
        if esperado < 0 and obtido == 0.0:
            continue
        if obtido is None or abs(obtido - esperado) > TOLERANCIA:
            ruins.append((l.get("_row"), l.get("Responsabilidade da Grid Co.?"), esperado, obtido))
    assert not ruins, "linhas divergentes (linha, responsabilidade, planilha, app): %s" % ruins[:10]

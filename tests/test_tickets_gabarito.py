"""Portão de aceite: o cálculo do app tem de bater com o que já está na planilha.

Gabarito são as 233 linhas de `Strings indisp`, a única das duas abas cuja fórmula de
indisponibilidade resolve (a de Trackers aponta para arquivo externo e está vazia, 1.516 linhas
encerradas sem número).

O portão original misturava duas perguntas diferentes: "a fórmula está certa?" e "o que o app faz
com dado quebrado?". Comparar contra uma linha sem Início ou com Fim anterior ao Início não testa
a fórmula — testa o comportamento do Excel diante de célula vazia, que ele lê como data zero de
1900 e produz até 554 mil "horas" de indisponibilidade. Por isso o gabarito é dividido em dois
grupos por `_conferivel`:

  - CONFERÍVEL (217 linhas): as duas datas presentes e em ordem. Aqui a fórmula É testada, e
    divergência que não seja arredondamento REPROVA — é conta que vai para relatório de cliente.
  - INSERVÍVEL (16 linhas): falta data ou o Fim vem antes do Início. Aqui não existe "valor certo"
    para comparar — o que se testa é que o app se RECUSA a calcular (devolve None) em vez de
    repetir o número plausível-e-errado que a planilha mostra."""
import io
import json
import os

from tickets_calc import _para_dt, indisponibilidade_gridco, indisponibilidade_horas

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "tickets_strings.json")
TOLERANCIA = 0.02          # ~1 minuto; cobre arredondamento, não cobre régua errada


def _linhas():
    with io.open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _conferivel(l):
    """A linha permite conferir a fórmula? Exige as duas datas presentes e em ordem.

    Sem isso o portão compararia maçã com laranja: onde falta data, a planilha guarda o que o
    Excel produz tratando célula vazia como data zero (1900) — foi assim que apareceram 553.548 h
    e 554.206,5 h, ou seja 63 anos de indisponibilidade."""
    ini = _para_dt(l.get("Início da ocorrência"))
    fim = _para_dt(l.get("Fim da ocorrência"))
    return ini is not None and fim is not None and fim >= ini


def test_a_fixture_tem_gabarito_suficiente():
    conferiveis = [l for l in _linhas() if _conferivel(l)
                   and _num(l.get("Indisponibilidade (horas)")) is not None]
    assert len(conferiveis) >= 200, "gabarito pequeno demais para o portão significar algo"


def test_indisponibilidade_bate_com_a_planilha():
    """O PORTÃO. Toda linha em que a fórmula é conferível tem de bater."""
    ruins = []
    for l in _linhas():
        if not _conferivel(l):
            continue
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


def test_linhas_inservivéis_o_app_recusa_calcular():
    """Caracterização das 16 linhas em que a PLANILHA está errada e o app se recusa a chutar.

    Medido em 28/08 sobre as 233 linhas de Strings indisp:
      - 12 linhas com Fim vazio guardam número: a fórmula do Excel não recalculou depois de
        alguém apagar o fim, e a ocorrência segue ABERTA
      - 2 linhas sem Início dão 553.548 h e 554.206,5 h, porque o Excel lê célula vazia como 1900
      - 1 linha sem nenhuma das datas mostra 0, que é a afirmação falsa "ficou zero hora parado"
      - 1 linha tem Fim 19 dias ANTES do Início, provável erro de digitação

    O número 16 é proposital: se a planilha for consertada, ou se piorar, este teste avisa em vez
    de deixar a mudança passar em silêncio."""
    inserviveis = [l for l in _linhas() if not _conferivel(l)]
    assert len(inserviveis) == 16, (
        "a planilha mudou: %d linhas inservíveis, esperadas 16" % len(inserviveis))
    for l in inserviveis:
        obtido = indisponibilidade_horas(l.get("Início da ocorrência"),
                                         l.get("Fim da ocorrência"))
        assert obtido is None, (
            "linha %s deveria recusar cálculo e devolveu %s" % (l.get("_row"), obtido))

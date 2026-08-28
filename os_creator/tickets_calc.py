"""Indisponibilidade das ocorrências — a conta que hoje é fórmula do Excel.

A régua é JANELA SOLAR 06:00–18:00: hora fora dela não conta, e dia inteiro vale 12 horas.
Transcrita da fórmula LET da coluna U da aba Trackers, lida do `.xlsx` vivo em 28/08. Não é
`fim − início`, e essa diferença é grande: uma parada da noite de sexta à manhã de segunda dá
12 h nesta régua e 60 h na subtração ingênua.

A aba Trackers NÃO tem esses valores hoje (1.516 linhas encerradas, zero números): a fórmula de lá
aponta para `[1]!Tracker`, tabela em arquivo externo cujo vínculo não resolve. O gabarito para
conferir esta implementação são as 232 linhas de Strings indisp, onde a fórmula é local e
funciona."""
from datetime import datetime

INICIO_SOLAR = 6
FIM_SOLAR = 18
HORAS_DIA_INTEIRO = FIM_SOLAR - INICIO_SOLAR      # 12


def _para_dt(v):
    """Aceita o que a API devolve (ISO, com ou sem T, com ou sem fuso). Lixo vira None.

    Lixo acontece de verdade: a coluna Inversor da aba tem 'A ser verificado' e
    'Mapeamento agendado para 04/05' no lugar do valor."""
    if v in (None, "", " "):
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip().replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _hora_decimal(d):
    return d.hour + d.minute / 60.0 + d.second / 3600.0


def _grampeia(h):
    return min(max(h, INICIO_SOLAR), FIM_SOLAR)


def indisponibilidade_horas(ini, fim):
    """Horas solares entre início e fim. None quando não dá para calcular.

    None, nunca zero: o IFERROR do Excel devolve vazio, e vazio significa "não sei", enquanto
    zero significaria "ficou zero hora parado" — afirmação falsa sobre uma ocorrência aberta."""
    a, b = _para_dt(ini), _para_dt(fim)
    if a is None or b is None:
        return None

    h_ini, h_fim = _hora_decimal(a), _hora_decimal(b)

    if a.date() == b.date():
        return round(max(0.0, _grampeia(h_fim) - _grampeia(h_ini)), 6)

    # dias distintos: as duas pontas + os dias inteiros do meio
    ponta_ini = max(0.0, FIM_SOLAR - max(h_ini, INICIO_SOLAR))
    ponta_fim = max(0.0, min(h_fim, FIM_SOLAR) - INICIO_SOLAR)
    dias_meio = max(0, (b.date() - a.date()).days - 1)
    return round(dias_meio * HORAS_DIA_INTEIRO + ponta_ini + ponta_fim, 6)


def indisponibilidade_gridco(indisp, responsabilidade):
    """Parcela da indisponibilidade que é responsabilidade da Grid Co.

    Três casos, medidos na fórmula: Sim = valor cheio, Parcial = valor − 6, resto = 0.
    `Parcial` é o caso DOMINANTE (173 de 264 linhas de Trackers), então errar aqui erraria a
    maioria das linhas.

    DESVIO DELIBERADO: o Excel não põe piso no `− 6`, então uma ocorrência Parcial curta daria
    negativo. Aqui o piso é zero."""
    if indisp is None:
        return None
    r = str(responsabilidade or "").strip().lower()
    if r == "sim":
        return indisp
    if r == "parcial":
        return round(max(0.0, indisp - 6.0), 6)
    return 0.0

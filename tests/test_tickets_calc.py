"""Régua da indisponibilidade — janela solar 06:00–18:00.

Os casos saem da fórmula LET lida no `.xlsx` (aba Trackers, coluna U) em 28/08. O que o Excel
faz, o app tem de fazer igual: fora da janela solar não conta, e dia inteiro vale 12 horas."""
from tickets_calc import indisponibilidade_gridco, indisponibilidade_horas


def test_mesmo_dia_dentro_da_janela():
    # 08:00 → 12:00 = 4 h
    assert indisponibilidade_horas("2026-08-01T08:00:00", "2026-08-01T12:00:00") == 4.0


def test_mesmo_dia_comecando_antes_das_6():
    # 03:00 é grampeado para 06:00 → 06:00–10:00 = 4 h
    assert indisponibilidade_horas("2026-08-01T03:00:00", "2026-08-01T10:00:00") == 4.0


def test_mesmo_dia_terminando_depois_das_18():
    # 22:00 é grampeado para 18:00 → 14:00–18:00 = 4 h
    assert indisponibilidade_horas("2026-08-01T14:00:00", "2026-08-01T22:00:00") == 4.0


def test_mesmo_dia_inteiramente_fora_da_janela():
    # 19:00 → 23:00: os dois grampeiam para 18:00 → zero
    assert indisponibilidade_horas("2026-08-01T19:00:00", "2026-08-01T23:00:00") == 0.0


def test_dias_seguidos_sem_dia_inteiro_no_meio():
    # ponta do dia 1: 18 − 10 = 8 h ; ponta do dia 2: 14 − 6 = 8 h ; nenhum dia inteiro
    assert indisponibilidade_horas("2026-08-01T10:00:00", "2026-08-02T14:00:00") == 16.0


def test_com_dois_dias_inteiros_no_meio():
    # 8 + 8 + 2 dias inteiros × 12 = 40 h
    assert indisponibilidade_horas("2026-08-01T10:00:00", "2026-08-04T14:00:00") == 40.0


def test_fim_vazio_devolve_none():
    # o IFERROR do Excel devolve "" — aqui é None, e a tela mostra vazio, NÃO zero.
    # Zero significaria "ficou zero hora parado", que é uma afirmação falsa.
    assert indisponibilidade_horas("2026-08-01T10:00:00", None) is None
    assert indisponibilidade_horas("2026-08-01T10:00:00", "") is None


def test_data_invalida_devolve_none():
    assert indisponibilidade_horas("A ser verificado", "2026-08-01T10:00:00") is None


def test_gridco_sim_repassa_o_valor_cheio():
    assert indisponibilidade_gridco(10.0, "Sim") == 10.0


def test_gridco_parcial_desconta_seis():
    assert indisponibilidade_gridco(10.0, "Parcial") == 4.0


def test_gridco_parcial_curto_nao_fica_negativo():
    # DESVIO DELIBERADO do Excel: a fórmula original não tem piso, então uma ocorrência Parcial
    # de 2 h daria −4. Indisponibilidade negativa não significa nada num relatório de cliente.
    assert indisponibilidade_gridco(2.0, "Parcial") == 0.0


def test_gridco_nao_e_vazio_dao_zero():
    assert indisponibilidade_gridco(10.0, "Não") == 0.0
    assert indisponibilidade_gridco(10.0, None) == 0.0


def test_gridco_sem_indisponibilidade_devolve_none():
    assert indisponibilidade_gridco(None, "Sim") is None


def test_fim_antes_do_inicio_devolve_none():
    # devolvia 16.0, um número plausível, sem sinalizar nada. Neste projeto número plausível e
    # errado é pior que erro que quebra: ninguém vai conferir.
    assert indisponibilidade_horas("2026-08-05T10:00:00", "2026-08-01T14:00:00") is None

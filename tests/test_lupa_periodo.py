"""O filtro de período da lupa: OS que ESTEVE ABERTA na janela, não OS aberta na janela.

Levi foi explícito em 31/08: "se eu selecionar dia 5 e a OS foi aberta dia 1 e fechada dia 10
então pegará esse período". Filtrar pela data de abertura deixaria de fora justamente a OS que
estava em curso no dia que interessa — que é a que se quer vincular a uma ocorrência daquele dia.
"""
from datetime import datetime

from steps.lupa_os import esteve_aberta_no_periodo as passa


def _os(aberta, fechada=None):
    return {"aberta": aberta, "fechada": fechada}


DIA5 = datetime(2026, 8, 5)
DIA5_FIM = datetime(2026, 8, 5, 23, 59, 59)


def test_o_caso_que_o_levi_descreveu():
    # aberta dia 1, fechada dia 10, janela = dia 5
    assert passa(_os("2026-08-01 08:00:00", "2026-08-10 17:00:00"), DIA5, DIA5_FIM)


def test_fechada_antes_da_janela_fica_de_fora():
    assert not passa(_os("2026-07-01 08:00:00", "2026-07-20 17:00:00"), DIA5, DIA5_FIM)


def test_aberta_depois_da_janela_fica_de_fora():
    assert not passa(_os("2026-09-01 08:00:00", "2026-09-02 17:00:00"), DIA5, DIA5_FIM)


def test_ainda_em_aberto_entra_se_comecou_antes_do_fim_da_janela():
    # OS sem fechamento não tem fim: basta ter começado antes do fim da janela.
    assert passa(_os("2026-01-15 08:00:00", ""), DIA5, DIA5_FIM)
    assert passa(_os("2026-08-05 22:00:00", None), DIA5, DIA5_FIM)


def test_ainda_em_aberto_mas_comecou_depois_fica_de_fora():
    assert not passa(_os("2026-12-01 08:00:00", ""), DIA5, DIA5_FIM)


def test_encosta_na_borda_e_entra():
    # fechou exatamente no primeiro instante da janela: esteve aberta nela.
    assert passa(_os("2026-08-01 08:00:00", "2026-08-05 00:00:00"), DIA5, DIA5_FIM)
    # abriu no último instante da janela
    assert passa(_os("2026-08-05 23:59:59", None), DIA5, DIA5_FIM)


def test_sem_data_de_abertura_a_os_passa():
    # falta de cadastro não é resposta à pergunta do filtro; sumir da lista esconderia a OS de
    # quem está procurando, sem dizer por quê.
    assert passa(_os("", "2026-08-10 17:00:00"), DIA5, DIA5_FIM)
    assert passa(_os(None, None), DIA5, DIA5_FIM)


def test_janela_aberta_dos_dois_lados_aceita_tudo():
    assert passa(_os("2020-01-01 00:00:00", "2020-01-02 00:00:00"), None, None)


def test_data_em_formato_curto_tambem_e_lida():
    assert passa(_os("2026-08-01", "2026-08-10"), DIA5, DIA5_FIM)
    assert not passa(_os("2026-09-01", "2026-09-02"), DIA5, DIA5_FIM)

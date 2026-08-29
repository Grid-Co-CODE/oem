"""Paginação do cliente da Gridco Performance API.

A rota tem TETO DE 1000 linhas por chamada, e a aba Trackers tem 2.781. Sem paginar, o app
mostraria dois terços da realidade e ninguém perceberia — que é a pior classe de erro aqui."""
import tickets_api


def _falsa(paginas):
    """Devolve uma função de busca que serve as páginas dadas, na ordem."""
    chamadas = []

    def buscar(sheet_id, limit, offset):
        chamadas.append((limit, offset))
        i = offset // limit
        return paginas[i] if i < len(paginas) else []

    buscar.chamadas = chamadas
    return buscar


def test_uma_pagina_so():
    linhas = [{"row_number": n} for n in range(10)]
    r = tickets_api._paginar(123, _falsa([linhas]))
    assert len(r) == 10


def test_pagina_ate_o_fim():
    cheia = [{"row_number": n} for n in range(1000)]
    resto = [{"row_number": n} for n in range(200)]
    r = tickets_api._paginar(123, _falsa([cheia, resto]))
    assert len(r) == 1200


def test_para_quando_a_pagina_vem_vazia():
    cheia = [{"row_number": n} for n in range(1000)]
    b = _falsa([cheia, []])
    r = tickets_api._paginar(123, b)
    assert len(r) == 1000
    assert len(b.chamadas) == 2


def test_nunca_pede_mais_que_o_teto():
    b = _falsa([[{"row_number": 1}]])
    tickets_api._paginar(123, b)
    assert all(limit <= 1000 for limit, _ in b.chamadas)


def test_listar_linhas_nao_perde_a_primeira_ocorrencia():
    # o [1:] anterior descartava uma ocorrência REAL: verificado contra a amostra de produção,
    # o índice 0 é row_number=5 da usina Linhares, e todas as linhas trazem headers idênticos.
    pagina = [
        {"row_number": 5, "headers": ["Usina", "Status"], "values": ["Linhares", "Parado"]},
        {"row_number": 6, "headers": ["Usina", "Status"], "values": ["Araputanga", "Parado"]},
    ]
    r = tickets_api.listar_linhas(123, _falsa([pagina]))
    assert len(r) == 2
    assert r[0]["Usina"] == "Linhares"
    assert r[1]["Usina"] == "Araputanga"


def test_listar_linhas_carrega_o_numero_da_linha():
    pagina = [{"row_number": 5, "headers": ["Usina"], "values": ["Linhares"]}]
    r = tickets_api.listar_linhas(123, _falsa([pagina]))
    assert r[0]["_row"] == 5


def test_listar_linhas_com_aba_de_uma_linha_so():
    # antes devolvia [] — zero ocorrências onde existe uma
    pagina = [{"row_number": 5, "headers": ["Usina"], "values": ["Linhares"]}]
    assert len(tickets_api.listar_linhas(123, _falsa([pagina]))) == 1


def test_listar_linhas_com_aba_vazia():
    assert tickets_api.listar_linhas(123, _falsa([[]])) == []

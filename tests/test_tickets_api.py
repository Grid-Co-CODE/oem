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

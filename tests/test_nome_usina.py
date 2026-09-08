# -*- coding: utf-8 -*-
"""O que vai para a coluna Usina: o NOME, e não o código (Levi, 08/09).

Era o código ('PTL300') desde 31/08, porque o casamento com o ativo acontece por segmento de
código e porque a maioria das linhas já usava esse formato. Ele mandou trocar: "eu não quero que
fique o código da usina, eu quero o nome da usina".

Trocar de chave de casamento é o risco desta mudança, e é o que estes testes vigiam: o nome curto
tem de continuar achando os ativos DA SUA usina, e não pode alcançar os de outra. Medido no
catálogo de 08/09: "Linhares 1" existe na Axis e na Thopen, e por isso existe o desempate.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from steps.lupa_usinas import nome_curto, usinas_do_catalogo


# ── nome_curto ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("cliente,nome,esperado", [
    ("Axis", "Axis - Petrolina 3 - PE", "Petrolina 3"),
    ("Thopen", "Thopen - Santarém 1 e 2 - PA", "Santarém 1 e 2"),
    ("2C", "2C - Ipixuna do Pará 1 - PA", "Ipixuna do Pará 1"),
    ("Greenyellow", "Greenyellow - Irecê 1 - BA", "Irecê 1"),
    # o nome da usina tem hífen no meio: só o cliente e a UF saem
    ("Thopen", "Thopen - São Bento do Una 1 - PE", "São Bento do Una 1"),
])
def test_tira_o_cliente_e_a_uf(cliente, nome, esperado):
    assert nome_curto(cliente, nome) == esperado


def test_nome_fora_do_padrao_volta_inteiro():
    """Encurtar errado é pior que não encurtar: o nome casa o ativo por substring, e um pedaço
    solto acharia a usina do vizinho."""
    assert nome_curto("Solier Qair", "Solier - Cascavel") == "Solier - Cascavel"
    assert nome_curto("Thopen", "Cabine 1") == "Cabine 1"
    assert nome_curto("", "") == ""


def test_nao_tira_o_que_so_PARECE_cliente_ou_uf():
    # o começo não é o cliente; a última parte não é sigla de estado
    assert nome_curto("Axis", "Thopen - Linhares 1 - ES") == "Thopen - Linhares 1"
    assert nome_curto("Thopen", "Thopen - Usina - Bloco") == "Usina - Bloco"


# ── o desempate ───────────────────────────────────────────────────────────────────────────
def _ativo(cliente, usina, code):
    return {"cliente": cliente, "usina": usina, "code": code}


def test_nome_repetido_em_dois_clientes_volta_a_ser_o_nome_completo():
    """O caso real: "Linhares 1" na Axis e na Thopen. Gravar só "Linhares 1" deixaria a linha
    apontando para duas usinas, e o casamento escolheria pela ordem do catálogo."""
    cat = usinas_do_catalogo([
        _ativo("Axis", "Axis - Linhares 1 - ES", "LNH100-INVR1.1"),
        _ativo("Thopen", "Thopen - Linhares 1 - ES", "THPN-LNH200-INVR1.1"),
        _ativo("Axis", "Axis - Petrolina 3 - PE", "PTL300-INVR1.1"),
    ])
    por_cod = {u["codigo"]: u["curto"] for u in cat}
    assert por_cod["LNH100"] == "Axis - Linhares 1 - ES"
    assert por_cod["LNH200"] == "Thopen - Linhares 1 - ES"
    assert por_cod["PTL300"] == "Petrolina 3", "usina sem xará não devia ganhar o nome longo"


def test_o_desempate_e_o_nome_do_CADASTRO_e_por_isso_casa_o_ativo():
    """Colar "cliente + curto" parecia mais bonito e quebrou três usinas cujo nome não tem a
    forma "Cliente - Nome - UF" — o resultado não existia em ativo nenhum."""
    from steps.tickets import _ativos_da_usina
    ativos = [_ativo("Solier Qair", "Solier - Cascavel", "SLC100-INVR1.1"),
              _ativo("TESTE - PA", "Solier - Cascavel", "TST100-INVR1.1")]
    for u in usinas_do_catalogo(ativos):
        assert _ativos_da_usina(u["curto"], ativos), "%r não acha ativo nenhum" % u["curto"]


def test_nome_contido_em_outro_tambem_desempata():
    """O casamento por nome é substring: "Cabine 1" alcança "Cabine 1 TESTE" do mesmo jeito."""
    cat = usinas_do_catalogo([_ativo("X", "Cabine 1", "CB1-INVR1.1"),
                              _ativo("X", "Cabine 1 TESTE", "CB2-INVR1.1")])
    assert all(u["curto"] == u["nome"] for u in cat)

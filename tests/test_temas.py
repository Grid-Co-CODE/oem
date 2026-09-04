# -*- coding: utf-8 -*-
"""A tela de Temas e o filtro de ativos que ela liga.

Nenhum teste aqui vai à rede: o `temas_store` recebe a busca por injeção, que é como o
`tickets_api` já faz. Ir ao banco num teste o deixaria vermelho quando a API cair, e aí ninguém
mais confia nele."""
import json

import pytest
import temas_store as ts


def _linha(chave, **kw):
    d = {"nome": chave.title(), "motivo": "", "classif1": "", "tipo_os": "",
         "tipo_equipamento": "", "solicitacoes": 0, "arquivado": False, "subtarefas": []}
    d.update(kw)
    return {"row_number": 2, "headers": ["chave", "valor"],
            "values": [chave, json.dumps(d, ensure_ascii=False)]}


def test_linha_quebrada_nao_derruba_as_outras():
    """JSON estragado num tema não pode tirar os outros treze da tela — o PCM ficaria sem
    nenhum tema para escolher por causa de um registro ruim."""
    linhas = [_linha("bom", nome="Bom"),
              {"row_number": 3, "headers": ["chave", "valor"], "values": ["ruim", "{isto nao e json"]},
              {"row_number": 4, "headers": ["chave", "valor"], "values": ["", "{}"]},
              _linha("outro", nome="Outro")]
    itens = ts.carregar(buscar=lambda: linhas)
    assert [x["chave"] for x in itens] == ["bom", "outro"]


def test_banco_fora_do_ar_cai_na_semente_do_codigo():
    """Sem isto, uma queda da API deixaria a Solicitação sem tema nenhum — pior do que temas
    desatualizados."""
    def explode():
        raise ConnectionError("sem rede")
    ts._cache = None
    itens = ts.carregar(buscar=explode)
    assert itens, "caiu para lista vazia em vez da semente"
    assert all("chave" in x for x in itens)


def test_arquivado_some_da_escolha_mas_nao_do_historico():
    """Arquivar tira o tema da lista de escolha; a OS que já nasceu com ele guarda as
    subtarefas copiadas e não muda."""
    import solic_spec as sp
    guarda_t, guarda_p = dict(sp.TEMAS), dict(sp.POR_TEMA)
    try:
        ts.aplicar_no_spec([
            _de(ts, "vivo", nome="Vivo"),
            _de(ts, "morto", nome="Morto", arquivado=True),
        ])
        assert "vivo" in sp.TEMAS
        assert "morto" not in sp.TEMAS
    finally:
        sp.TEMAS.clear(); sp.TEMAS.update(guarda_t)
        sp.POR_TEMA.clear(); sp.POR_TEMA.update(guarda_p)


def _de(_ts, chave, **kw):
    d = {"chave": chave, "nome": chave, "motivo": "", "classif1": "", "tipo_os": "",
         "tipo_equipamento": "", "solicitacoes": 0, "arquivado": False, "subtarefas": []}
    d.update(kw)
    return d


def test_gravar_sem_token_avisa_em_vez_de_falhar_calado(monkeypatch):
    monkeypatch.setattr(ts, "_tok", lambda: "")
    with pytest.raises(PermissionError):
        ts.salvar({"chave": "x", "nome": "X"})


def test_o_tipo_do_tema_e_o_do_CADASTRO_e_nao_um_apelido():
    """A regra que o Levi pediu depende de igualdade EXATA com o campo `tipo` do ativo.

    O primeiro rascunho casava por pedaço de texto no nome ("inv-", "tracker"). O cadastro real
    tem "Inversor" (2.247 ativos) e "DINV" (2.237): qualquer heurística de "inv" pegaria os dois.
    Por isso o valor guardado no tema tem de ser o mesmo string do cadastro."""
    import solic_spec as sp
    guarda = dict(sp.TEMAS)
    try:
        sp.TEMAS["t"] = {"nome": "T", "tipo_equipamento": "Estrutura Trackers"}
        assert ts.tipo_equipamento("t") == "Estrutura Trackers"
        assert ts.tipo_equipamento("nao_existe") == ""
    finally:
        sp.TEMAS.clear(); sp.TEMAS.update(guarda)

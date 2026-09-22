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


# ── as etiquetas passaram do código para o tema (04/09) ──────────────────────
def _card(qapp, catalogo=None):
    from steps.solic_pcm import _CardEtiquetas
    c = _CardEtiquetas()
    c.set_catalogo(catalogo or [{"id": 1, "description": "PERFORMANCE"},
                                {"id": 2, "description": "GARANTIA"},
                                {"id": 3, "description": "URGENTE"}])
    return c


def _chips(c):
    from PyQt6.QtWidgets import QPushButton
    return [w.text() for w in c.findChildren(QPushButton)]


def test_etiqueta_do_tema_aparece_como_tema_e_nao_como_regra(qapp):
    """Pedido do Levi (04/09). A palavra mudou porque a coisa mudou: até então quem decidia era
    `sp.exige_performance()`, uma regra do sistema que ninguém conseguia mudar sem release.
    Agora é campo do tema, editável na aba Temas."""
    import solic_spec as sp
    guarda = dict(sp.TEMAS)
    try:
        sp.TEMAS["t1"] = {"nome": "T1", "etiquetas": ["PERFORMANCE"]}
        c = _card(qapp)
        c.aplicar_regra("t1", "INV-03")
        assert _chips(c) == ["PERFORMANCE  ×  (tema)"]
        assert "(regra)" not in " ".join(_chips(c))
    finally:
        sp.TEMAS.clear(); sp.TEMAS.update(guarda)


def test_tema_sem_lista_ainda_cai_na_regra_antiga(qapp):
    """Os temas gravados ANTES de 04/09 não têm o campo `etiquetas`. Sem esta queda, a
    PERFORMANCE deixaria de entrar em tracker/ETM/garantia no dia da atualização, sem ninguém
    ter pedido — o pior tipo de mudança, a que ninguém escolheu."""
    import solic_spec as sp
    guarda = dict(sp.TEMAS)
    try:
        sp.TEMAS["tracker_x"] = {"nome": "TX"}          # sem a chave `etiquetas`
        c = _card(qapp)
        c.aplicar_regra("tracker_x", "Estrutura Trackers")
        assert _chips(c) == ["PERFORMANCE  ×  (tema)"]
    finally:
        sp.TEMAS.clear(); sp.TEMAS.update(guarda)


def test_trocar_de_tema_nao_apaga_a_etiqueta_posta_a_mao(qapp):
    """Desfazer escolha de gente sem avisar é o pior tipo de automação. Sai o que o TEMA
    ANTERIOR pôs; o que o PCM acrescentou fica, e continua removível pelo ×."""
    import solic_spec as sp
    guarda = dict(sp.TEMAS)
    try:
        sp.TEMAS["t1"] = {"nome": "T1", "etiquetas": ["PERFORMANCE"]}
        sp.TEMAS["t2"] = {"nome": "T2", "etiquetas": ["GARANTIA"]}
        c = _card(qapp)
        c.aplicar_regra("t1", "x")
        c._sel.append({"id": 3, "description": "URGENTE"})   # o PCM pôs à mão
        c._pintar()
        c.aplicar_regra("t2", "x")
        chips = _chips(c)
        assert "GARANTIA  ×  (tema)" in chips
        assert not any(x.startswith("PERFORMANCE") for x in chips), "sobrou o tema anterior"
        assert any(x.startswith("URGENTE") for x in chips), "apagou a escolha do PCM"
        assert sorted(c.ids()) == [2, 3]
    finally:
        sp.TEMAS.clear(); sp.TEMAS.update(guarda)


def test_tema_com_lista_VAZIA_nao_poe_etiqueta_nenhuma(qapp):
    """Lista vazia é escolha explícita do PCM, e tem de valer — se caísse na regra antiga,
    tirar a PERFORMANCE de um tema de tracker seria impossível."""
    import solic_spec as sp
    guarda = dict(sp.TEMAS)
    try:
        sp.TEMAS["tracker_y"] = {"nome": "TY", "etiquetas": []}
        c = _card(qapp)
        c.aplicar_regra("tracker_y", "Estrutura Trackers")
        assert _chips(c) == []
    finally:
        sp.TEMAS.clear(); sp.TEMAS.update(guarda)

# tests/test_os_web_imagens_e_pagina.py
"""A janela de imagens na Performance e os ativos de 10 em 10 no Tradicional e na Solicitação
(Levi, 22/09/2026: itens 1 e 2 do lote).

Conferido no navegador com dado real: a janela abre, mostra as miniaturas, renomeia e remove; o
Tradicional e a Solicitação abrem com 10 dos 353 ativos da Timon 1, o marcado sobrevive à
paginação e ao filtro. Estes testes seguram as decisões que não aparecem na tela.
"""
import os
import re

import pytest

from os_web import perf_web

_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "os_web")


def _ler(rel):
    with open(os.path.join(_WEB, rel), encoding="utf-8") as f:
        return f.read()


# ── 1. a janela de imagens ───────────────────────────────────────────────────────────────────
def test_a_performance_tem_a_MESMA_janela_do_tradicional():
    """Uma janela só, com a mesma marcação: a do app (PerfAnexoDialog)."""
    perf, trad = _ler("templates/perf_criar.html"), _ler("templates/tradicional.html")
    for ident in ('id="modal_img"', 'id="img_grid"', 'id="b_img_add"', 'id="b_img_paste"',
                  'id="img_vazio"', 'id="img_erro"', 'class="os-modal-card os-form trad-modal trad-modal-img"'):
        assert ident in perf and ident in trad, ident


def test_o_css_da_janela_mora_no_os_css_e_nao_esta_duplicado():
    css, trad = _ler("static/os.css"), _ler("static/tradicional.css")
    for regra in (".trad-img-grid{", ".trad-img-cell{", ".trad-modal-img{", ".trad-img-btns{"):
        assert regra in css, regra
        assert regra not in trad, "%s ficou duplicado no tradicional.css" % regra


def test_o_payload_manda_so_nome_e_b64_e_nao_a_miniatura():
    """A `url` da miniatura é o MESMO base64 de novo: mandá-la dobraria o tamanho do envio."""
    js = _ler("static/perf.js")
    assert "imagens: (imgs[a.id] || []).map(x => ({nome: x.nome, b64: x.b64}))" in js


def test_o_nome_renomeado_mantem_a_extensao():
    """O servidor RECUSA anexo sem extensão de imagem, e a recusa derruba a criação inteira. Quem
    renomeia escreve o nome; a extensão volta sozinha (conferido: "inversor 1.1 queimado" virou
    "inversor 1.1 queimado.png" no navegador)."""
    js = _ler("static/perf.js")
    assert "function nomeSeguro(nome, tipo)" in js
    assert "if (!EXT.test(n)) n +=" in js


def test_o_ctrl_v_so_vale_com_a_janela_aberta():
    """Antes a imagem colada caía no último ativo clicado, com a janela fechada."""
    js = _ler("static/perf.js")
    trecho = js[js.index("document.addEventListener('paste'"):][:400]
    assert "if (!imgAberta) return;" in trecho


@pytest.mark.parametrize("nome, esperado", [
    ("foto.png", "foto.png"),
    ("../x/foto.png", ".._x_foto.png"),          # não sai da pasta da OS no S3
    ("a\\b\\foto.png", "a_b_foto.png"),
    ("pasta/sub/foto.jpg", "pasta_sub_foto.jpg"),
])
def test_o_servidor_nao_aceita_barra_no_nome(nome, esperado):
    """O nome entra na chave do S3 (".ot/<OS>/<nome>"): uma "/" abriria subpasta."""
    imgs, erro = perf_web.imagens_do_item({"imagens": [{"nome": nome, "b64": "aGVsbG8="}],
                                           "asset": {"label": "A"}})
    assert erro == "" and imgs[0]["nome"] == esperado


def test_nome_sem_extensao_continua_recusado_no_servidor():
    """A regra do servidor não muda — é a tela que passa a não violá-la."""
    _imgs, erro = perf_web.imagens_do_item({"imagens": [{"nome": "sem extensao", "b64": "aGVsbG8="}],
                                            "asset": {"label": "A"}})
    assert "não é imagem" in erro


# ── 2. 10 em 10 no Tradicional e na Solicitação ──────────────────────────────────────────────
@pytest.mark.parametrize("rel", ["static/tradicional.js", "templates/solic.html"])
def test_pagina_de_dez_com_o_rodape_e_os_marcados_fora(rel):
    s = _ler(rel)
    assert re.search(r"PAGINA = 10", s)
    assert "function rodapeMais(rows, vis, estaMarcado, colunas)" in s
    assert "marcado(s) fora da tela" in s
    assert '<td colspan="\' + colunas + \'"><div class="mais-in">' in s      # flex no DIV, não no td


def test_tradicional_volta_a_dez_quando_a_lista_muda():
    s = _ler("static/tradicional.js")
    assert "cbTipo.onchange = () => { limite = PAGINA; refreshAtivos(); };" in s
    assert "busca.oninput = () => { limite = PAGINA; refreshAtivos(); };" in s
    assert "assets = j.ativos || []; limite = PAGINA;" in s                  # usina nova


def test_fechar_a_janela_de_imagens_NAO_perde_a_pagina():
    """O `refreshAtivos()` depois da janela de imagens atualiza o rótulo do botão; zerar o limite
    ali jogaria a pessoa de volta para o topo a cada anexo."""
    s = _ler("static/tradicional.js")
    trecho = s[s.index("function fecharImagens()"):][:300]
    assert "limite = PAGINA" not in trecho


def test_solicitacao_volta_a_dez_quando_a_lista_muda():
    s = _ler("templates/solic.html")
    assert 'cbTipo.addEventListener("change", function () { limite = PAGINA; pintar(); });' in s
    assert 'busca.addEventListener("input", function () { limite = PAGINA; pintar(); });' in s
    assert "ativos = j.ativos || []; limite = PAGINA; pintar();" in s


def test_o_clique_do_rodape_vem_antes_do_da_linha_no_tradicional():
    """O rodapé é um <tr> sem data-id: se o `closest('tr')` viesse antes, o clique caía no ramo
    dos ativos."""
    s = _ler("static/tradicional.js")
    trecho = s[s.index("tbody.addEventListener('click'"):][:400]
    assert trecho.index("dataset.mais") < trecho.index("classList.contains('anx')")

# tests/test_os_web_pagina_ativos.py
"""A tabela de ativos abre de 10 em 10 (Levi, 22/09/2026: "quero que quando os ativos carregarem
carreguem de 10 em 10, está abrindo tudo atualmente").

Por que importa: a Timon 1 tem 50 inversores e a Recomposição de String os lista todos. A tela
virava duas telas de rolagem antes de o primeiro campo aparecer.

O LIMITE É SÓ DE EXIBIÇÃO. Selecionar, filtrar e criar continuam valendo sobre a lista inteira —
e é por isso que o rodapé diz quantos marcados estão fora da tela: cada um vira uma OS, e não
poder vê-los não pode significar não saber que existem. Estes testes seguram essa separação no
código-fonte; o comportamento na tela foi conferido no navegador com os 50 inversores reais.
"""
import os
import re

import pytest

_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "os_creator", "os_web", "static", "perf.js")


@pytest.fixture(scope="module")
def js():
    with open(_JS, encoding="utf-8") as f:
        return f.read()


def test_pagina_e_de_dez(js):
    assert re.search(r"const PAGINA = 10;", js), "o tamanho da página saiu de 10"


def test_o_limite_corta_a_EXIBICAO_e_nao_a_lista(js):
    """`rows` é a lista filtrada inteira; `vis` é o pedaço desenhado. Quem conta marcados, quem
    filtra e quem cria usa `rows` — trocar isso por `vis` faria "Selecionar todos" marcar 10 de 50
    em silêncio, criando menos OS do que a pessoa pediu."""
    assert "const vis = rows.slice(0, limite);" in js
    # "Selecionar todos" segue varrendo `alvos`, não o que está na tela
    assert "$('b_all').onclick = () => { alvos.filter(visivel).forEach(a => checked.add(a.id)); repop(); };" in js


def test_o_rodape_avisa_os_marcados_fora_da_tela(js):
    assert "escondidosMarcados" in js
    assert "marcado(s) fora da tela" in js
    assert "Mostrando ' + vis.length + ' de ' + rows.length" in js


def test_o_flex_do_rodape_vai_no_div_e_nao_no_td(js):
    """`display:flex` num <td> tira a célula do layout de tabela e o `colspan` para de valer — o
    rodapé ficava espremido na largura da primeira coluna (medido em 22/09)."""
    assert '<td colspan="6"><div class="mais-in">' in js
    css = os.path.join(os.path.dirname(_JS), "os.css")
    with open(css, encoding="utf-8") as f:
        c = f.read()
    assert ".os-tbl tr.mais .mais-in{display:flex" in c
    assert ".os-tbl tr.mais td{display:flex" not in c


@pytest.mark.parametrize("gatilho", [
    "busca.oninput = () => { limite = PAGINA; repop(); };",              # filtrar
    "qtd = {}; limite = PAGINA; repop();",                               # trocar de usina
    "checked = new Set(); limite = PAGINA; repop(); marcarUnico();",     # trocar de modo
])
def test_o_limite_volta_ao_inicio_quando_a_lista_muda(js, gatilho):
    """Sem isto, trocar de usina herdaria o "mostrar todos" da anterior — e o pedido era
    justamente não abrir tudo de uma vez."""
    assert gatilho in js


def test_os_botoes_do_rodape_sao_delegados(js):
    """O tbody é refeito inteiro a cada `repop`: um listener presso ao botão morreria no primeiro
    clique. A delegação tem de vir ANTES do `closest('tr')`, senão o clique no rodapé (que é um
    <tr> sem data-id) cairia no ramo dos ativos."""
    trecho = js[js.index("tbody.addEventListener('click'"):]
    trecho = trecho[:trecho.index("});")]
    assert trecho.index("dataset.mais") < trecho.index("closest('tr')")

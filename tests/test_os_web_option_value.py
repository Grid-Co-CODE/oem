# tests/test_os_web_option_value.py
"""`<option>` sem `value` perde espaço duplo do nome (Levi, 22/09/2026).

O CASO REAL: "Athon -  Timon 1 - MA" — dois espaços depois do tracinho — é o nome da usina no
catálogo do Fracttal. O `<option>` era gerado sem o atributo `value`, e nesse caso o navegador não
devolve o texto cru em `option.value`: devolve o texto com o espaço em branco COLAPSADO. Medido no
navegador, mesmo `<option>`, com e sem o atributo:

    sem value:  "Athon - Timon 1 - MA"     ← um espaço
    com value:  "Athon -  Timon 1 - MA"    ← dois, o certo

O servidor procura `a["usina"] == <o que veio>`, não acha, e a tela diz "Sem inversores/trackers/
estação nesta usina" numa usina com 70 inversores. Atinge 4 das 142 usinas.

NÃO SE CONSERTA LIMPANDO O NOME: ele é a chave de junção com o catálogo do Fracttal, não um rótulo
nosso. Normalizar de um lado só quebraria a busca do outro. O conserto é carregar o valor.
"""
import os
import re

import pytest

_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "os_creator", "os_web")

# nome real, do catálogo — não inventado
USINA_COM_ESPACO_DUPLO = "Athon -  Timon 1 - MA"


def _texto(rel):
    with open(os.path.join(_WEB, rel), encoding="utf-8") as f:
        return f.read()


def _templates():
    d = os.path.join(_WEB, "templates")
    return [os.path.join("templates", f) for f in sorted(os.listdir(d)) if f.endswith(".html")]


@pytest.mark.parametrize("rel", _templates())
def test_nenhum_option_do_jinja_sem_value(rel):
    """`<option>{{ x }}</option>` é o padrão proibido: o dado tem de ir no `value`.

    A varredura é do arquivo inteiro e vale para telas que ainda nem existem — é mais barato do
    que descobrir de novo, numa usina só, que a lista não casa."""
    txt = _texto(rel)
    ruins = re.findall(r"<option\s*>\s*\{\{", txt)
    assert not ruins, ("%s tem <option> sem `value` com dado do servidor. "
                       "Use <option value=\"{{ x }}\">{{ x }}</option>." % rel)


@pytest.mark.parametrize("rel", ["static/perf.js", "static/tradicional.js", "static/os_busca.js"])
def test_nenhum_option_montado_em_js_sem_value(rel):
    """O mesmo no JS: `'<option>' + esc(x) + '</option>'` tem o mesmo defeito."""
    txt = _texto(rel)
    assert "'<option>' + esc(" not in txt, "%s monta <option> sem `value`" % rel
    assert '"<option>" + esc(' not in txt, "%s monta <option> sem `value`" % rel


def test_as_usinas_com_espaco_duplo_continuam_existindo_no_catalogo():
    """A trava só faz sentido enquanto o catálogo tiver nome com espaço duplo. No dia em que o
    Fracttal for limpo, este teste avisa que a regra pode ser revista — em vez de ela virar
    superstição que ninguém sabe por que existe."""
    import api
    from os_web import perf_web
    try:
        assets = api.load_assets_cached()
    except Exception:                                   # noqa: BLE001 — sem catálogo, sem teste
        pytest.skip("catálogo de ativos indisponível nesta máquina")
    if not assets:
        pytest.skip("catálogo vazio")
    usinas = perf_web.usinas_para(assets, None)
    sujas = [u for u in usinas if u != re.sub(r"\s+", " ", u).strip()]
    assert USINA_COM_ESPACO_DUPLO in usinas, "o nome do caso real sumiu do catálogo"
    assert sujas, "nenhuma usina com espaço sobrando — a regra pode ser revista"


def test_lookup_do_servidor_e_por_igualdade_exata():
    """Mostra POR QUE o espaço importa: a busca do servidor é `==`, não uma comparação frouxa.

    Este teste é a outra metade do conserto. Se um dia alguém "resolver" o problema afrouxando a
    comparação aqui, vai casar duas usinas diferentes que só diferem por espaço — e criar OS no
    cliente errado, que é a classe de erro que este projeto não aceita."""
    from os_web import perf_web
    assets = [{"usina": USINA_COM_ESPACO_DUPLO, "tipo": "Inversor", "id": 1, "code": "A"},
              {"usina": "Athon -  Timon 2 - MA", "tipo": "Inversor", "id": 2, "code": "B"}]
    achou = perf_web.ativos_da_usina(assets, USINA_COM_ESPACO_DUPLO, "recomposicao de string")
    assert [a["id"] for a in achou] == [1]
    # o nome COLAPSADO — exatamente o que o navegador mandava — não acha nada
    colapsado = re.sub(r"\s+", " ", USINA_COM_ESPACO_DUPLO)
    assert perf_web.ativos_da_usina(assets, colapsado, "recomposicao de string") == []

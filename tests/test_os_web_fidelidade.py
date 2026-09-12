# tests/test_os_web_fidelidade.py
"""A web NAO redesenha o OS Creator (Levi, 12/09/2026: "segue o mesmo design e logica do OS Creator"). Os textos dos
cards do lancador e dos planos da Performance moram no `app.py` e no `steps/performance.py` — modulos Qt, que o
servidor web nao importa. Entao a web tem a sua copia, e ESTE teste le o codigo-fonte do app (ast, sem Qt) e falha
se alguem mudar um lado e esquecer o outro."""
import ast
import os

from os_web import perf_web, lancador

_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator")


def _modulo(rel):
    with open(os.path.join(_APP, rel), encoding="utf-8") as f:
        return ast.parse(f.read())


def _literal_de(tree, nome):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == nome for t in node.targets):
            return node.value
    raise AssertionError(f"{nome} nao encontrado")


def test_planos_da_performance_iguais_aos_do_app():
    planos = _literal_de(_modulo("steps/performance.py"), "_PLANOS")
    do_app = []
    for tup in planos.elts:
        vals = [e.value if isinstance(e, ast.Constant) else e.id for e in tup.elts]
        do_app.append(vals)
    # FRASE_COLETA e um Name no app: vale o valor da constante
    frase_coleta = _literal_de(_modulo("steps/performance.py"), "FRASE_COLETA").value
    do_app = [[frase_coleta if v == "FRASE_COLETA" else v for v in vals] for vals in do_app]
    da_web = [[p["titulo"], p["frase"], p["icone"], p["badge"], p["sub"]] for p in perf_web.PLANOS]
    assert da_web == do_app


def test_titulos_literais_etm_e_usina_iguais_aos_do_app():
    tree = _modulo("steps/performance.py")
    assert perf_web.ETM_TITULO == _literal_de(tree, "ETM_TITULO").value
    assert perf_web.USINA_TITULO == _literal_de(tree, "USINA_TITULO").value
    assert perf_web.ETM_ETIQUETAS == tuple(e.value for e in _literal_de(tree, "ETM_ETIQUETAS").elts)
    conj = _literal_de(tree, "_CARTEIRA_EQUIP")
    conj = conj.args[0] if isinstance(conj, ast.Call) else conj             # frozenset({...}) e uma chamada
    assert perf_web.CARTEIRA_EQUIP == frozenset(e.value for e in conj.elts)


def test_cards_do_lancador_iguais_aos_do_app():
    tree = _modulo("app.py")
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_build_launcher")
    cards = next(n.value for n in ast.walk(fn) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "cards" for t in n.targets))
    do_app = [tuple(e.value for e in tup.elts[:3]) for tup in cards.elts]
    # as AREAS entram depois dos cards do app (steps/engenharia e Qt-free e pode ser importado)
    from steps import engenharia
    do_app.append((engenharia.ICONE, engenharia.TITULO, engenharia.DESCRICAO))
    assert [(c["icone"], c["titulo"], c["sub"]) for c in lancador.CARDS] == do_app


def test_icones_do_lancador_existem_como_svg():
    tree = _modulo("app.py")
    ico = {k.value: v.value for k, v in zip(_literal_de(tree, "_ICO").keys, _literal_de(tree, "_ICO").values)}
    from steps import engenharia
    ico.update(engenharia.ICONES)
    for c in lancador.CARDS:
        assert lancador.svg(c["icone"]) == ico[c["icone"]], c["icone"]
    assert lancador.svg("arrow") == ico["arrow"]

# tests/test_os_web_blueprints.py
"""Cada tela nova do os_web vive no próprio `os_web/rotas_<tela>.py` com um `bp`. O `criar_app` registra todos sozinho,
varrendo o pacote — assim dez telas entram em paralelo sem disputar uma linha de `__init__.py` (porte de 13/09/2026)."""
import os

import os_web
from os_web import blueprints, criar_app


def test_varre_os_modulos_rotas_e_devolve_os_blueprints():
    bps = blueprints.TODOS()
    nomes = {b.name for b in bps}
    arquivos = [f[:-3] for f in os.listdir(os.path.dirname(os_web.__file__)) if f.startswith("rotas_") and f.endswith(".py")]
    assert len(bps) == len(arquivos), "todo rotas_<tela>.py precisa expor um `bp` — e só um por arquivo"
    assert "os_web" not in nomes                            # o blueprint principal continua registrado à parte


def test_criar_app_registra_o_principal_e_todos_os_das_telas(monkeypatch):
    from flask import Blueprint
    falso = Blueprint("os_web_teste", __name__, url_prefix="/os")
    monkeypatch.setattr(blueprints, "TODOS", lambda: [falso])
    app = criar_app(segredo="teste", testing=True)
    assert "os_web" in app.blueprints and "os_web_teste" in app.blueprints

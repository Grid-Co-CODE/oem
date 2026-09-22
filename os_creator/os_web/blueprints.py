# os_creator/os_web/blueprints.py
"""Registro automático das telas: todo `os_web/rotas_<tela>.py` que exponha um `bp` (flask.Blueprint) entra no app.

Por quê: o porte do OS Creator para a web (13/09/2026) traz uma dezena de telas ao mesmo tempo, cada uma no próprio
módulo. Se cada uma tivesse que acrescentar uma linha em `criar_app`, dez mãos disputariam o mesmo arquivo; aqui basta
criar o módulo. O `rotas.py` (porta, home, Performance, Históricos, detalhe) continua registrado à parte."""
from __future__ import annotations
import importlib
import os

from flask import Blueprint

_AQUI = os.path.dirname(os.path.abspath(__file__))


def modulos() -> list[str]:
    """Nomes dos módulos `rotas_*` do pacote, em ordem alfabética (ordem estável de registro)."""
    return sorted(f[:-3] for f in os.listdir(_AQUI) if f.startswith("rotas_") and f.endswith(".py"))


def TODOS() -> list[Blueprint]:
    out = []
    for nome in modulos():
        mod = importlib.import_module(f"{__package__}.{nome}")
        bp = getattr(mod, "bp", None)
        if not isinstance(bp, Blueprint):
            raise RuntimeError(f"os_web/{nome}.py precisa expor um `bp` (flask.Blueprint)")
        out.append(bp)
    return out

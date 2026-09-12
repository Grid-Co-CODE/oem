# os_creator/os_web/__init__.py
"""OS Creator na WEB: o mesmo app, dentro da Plataforma de Performance (Levi, 12/09/2026: "traga toda a estrutura
do OS Creator para a plataforma"). Um Flask pequeno, servido em 127.0.0.1:5090 e publicado pela plataforma sob
`/os/*` (proxy, como o Gêmeo Digital). Reaproveita o `api.py` do desktop — o motor — e refaz as telas em HTML com o
MESMO design (sem redesign, decisão dele). A sessão do Fracttal é por pessoa (`sessao.py`).

Uso: `from os_web import criar_app`; servidor: `python -m os_web.servir` (waitress)."""
from __future__ import annotations
import datetime as dt
import os
import secrets

from flask import Flask, g, session

import api
from . import lancador, sessao

_AQUI = os.path.dirname(os.path.abspath(__file__))


def _segredo() -> str:
    """Chave do cookie de sessão: variável OS_WEB_SEGREDO ou um arquivo na pasta de dados do app (gerado uma vez).
    Sem isso cada reinício invalidaria a sessão de todo mundo."""
    env = (os.environ.get("OS_WEB_SEGREDO") or "").strip()
    if env:
        return env
    caminho = os.path.join(api._data_dir(), "os_web_segredo.txt")
    try:
        with open(caminho, encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s
    except OSError:
        pass
    s = secrets.token_hex(32)
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(s)
    except OSError:
        pass
    return s


def criar_app(segredo: str | None = None, testing: bool = False) -> Flask:
    sessao.instalar(api)
    from .rotas import bp
    app = Flask("os_web", template_folder=os.path.join(_AQUI, "templates"), static_folder=None)
    app.config.update(
        SECRET_KEY=segredo or _segredo(), TESTING=testing,
        SESSION_COOKIE_NAME="os_sessao", SESSION_COOKIE_PATH="/os",
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        # a plataforma (https pelo túnel) é quem fala com o navegador; entre ela e este serviço é http local
        SESSION_COOKIE_SECURE=False,
        PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=12),        # o JWT do Fracttal dura ~12 h
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
    )
    app.json.ensure_ascii = False
    app.jinja_env.filters["iniciais"] = lancador.iniciais
    app.jinja_env.globals.update(icone=lancador.icone, abas=lancador.ABAS)
    app.register_blueprint(bp)

    @app.before_request
    def _abrir_sessao():
        g._os_web_tokens = sessao.abrir(session.get("jwt") or "")

    @app.after_request
    def _fechar_sessao(resp):
        if getattr(g, "_os_web_tokens", None) is not None:
            if sessao.morta():
                for k in ("jwt", "conta"):
                    session.pop(k, None)
                session["aviso"] = "A sessão do Fracttal caiu (outro login na sua conta ou o token venceu). Entre de novo."
            else:
                novo = sessao.jwt_novo()
                if novo and novo != session.get("jwt"):
                    session["jwt"] = novo
                    session.permanent = True
        return resp

    @app.teardown_request
    def _soltar_sessao(_exc):
        tokens = getattr(g, "_os_web_tokens", None)
        if tokens is not None:
            sessao.fechar(tokens)
            g._os_web_tokens = None

    return app

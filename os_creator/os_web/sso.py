# os_creator/os_web/sso.py
"""Entrar com Microsoft / SSO na web.

O app desktop abre o Fracttal num navegador embutido e um script injetado lê o `Authorization: Bearer` das requisições
da própria página (steps/sso_login.py). Num navegador comum isso é impossível: nossa página não lê nada de
app.fracttal.com (same-origin). O que dá para fazer é o MESMO truque com outro dono do script — um favorito
(bookmarklet) que a pessoa clica NA ABA DO FRACTTAL depois de entrar pela Microsoft. Ele varre localStorage,
sessionStorage e cookies (igual ao _POLL_JS do app), copia o JWT e a pessoa cola no login da web. A validação é ao vivo
(um RPC barato), como o `api.is_logged_in` do app. Fracttal com OAuth para integradores continua sendo a saída limpa."""
from __future__ import annotations
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


def extrair_jwt(texto) -> str:
    """O JWT dentro do que a pessoa colou: o token puro, 'Bearer …', uma linha de cURL ou um JSON. '' se não há."""
    m = _RE_JWT.search(str(texto or ""))
    return m.group(0) if m else ""


def bookmarklet_href() -> str:
    """O favorito: o JS de static/sso_bookmarklet.js numa linha só, sem os comentários, como URL javascript:."""
    with open(os.path.join(_AQUI, "static", "sso_bookmarklet.js"), encoding="utf-8") as f:
        linhas = [l.strip() for l in f.read().splitlines()]
    codigo = " ".join(l for l in linhas if l and not l.startswith("//"))
    return "javascript:" + codigo


ERRO_SEM_TOKEN = ("Não achei um token de sessão no que foi colado. Na aba do Fracttal, clique no favorito "
                  "\"Copiar sessão do Fracttal\" e cole aqui o que ele copiou.")
ERRO_SESSAO_MORTA = ("Sessão inválida ou já derrubada. O Fracttal aberto em outra aba renova a sessão e mata a cópia: "
                     "Feche a aba do Fracttal, clique no favorito de novo e cole aqui.")

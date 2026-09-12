# os_creator/sso_volta.py
"""SSO da web pelo app instalado: `gridos://sso?volta=<url do /os/login da plataforma>`.

Um navegador comum não lê a sessão de outro site; o app lê, porque leva o próprio navegador embutido
(steps/sso_login.py). Então a página de login da web chama este deep link: o app abre a janela de login que a equipe
já conhece, a pessoa entra pela Microsoft, e o app devolve o navegador em `volta#sso=<jwt>` — a página entra sozinha.
O token vai no FRAGMENTO (`#`), que o navegador nunca manda ao servidor nem a log nenhum.

Qt-free de propósito: a janela entra por parâmetro, e o teste roda sem o WebEngine."""
from __future__ import annotations
import re
import webbrowser
from urllib.parse import quote, urlsplit

import api

# Só a nossa casa recebe o token: o túnel da plataforma, a máquina local e o domínio fixo de amanhã.
_HOSTS_OK = re.compile(r"^(?:[a-z0-9-]+\.trycloudflare\.com|localhost|127\.0\.0\.1|(?:[a-z0-9-]+\.)*gridco\.com\.br)$", re.I)


def volta_valida(volta: str) -> bool:
    try:
        u = urlsplit(str(volta or ""))
    except ValueError:
        return False
    return (u.scheme in ("http", "https") and bool(u.hostname) and bool(_HOSTS_OK.match(u.hostname))
            and u.path.rstrip("/").endswith("/os/login"))


def url_de_volta(volta: str, token: str) -> str:
    return f"{volta}#sso={quote(token, safe='')}"


def _dialogo_padrao():
    from steps.sso_login import SsoLoginDialog      # WebEngine: carregado só quando a janela é pedida
    return SsoLoginDialog


def tratar(dados: dict, dialogo_cls=None, abrir=None) -> dict:
    """Abre a janela de login (Microsoft/SSO), guarda a sessão no app também e devolve o navegador logado.
    → {'ok': bool, 'motivo': str}. Nunca levanta: quem chama é o laço do deep link, best-effort."""
    volta = str((dados or {}).get("volta") or "").strip()
    if not volta_valida(volta):
        return {"ok": False, "motivo": "volta inválida: só o /os/login da plataforma recebe a sessão"}
    try:
        dlg = (dialogo_cls or _dialogo_padrao())()
        if int(dlg.exec()) != 1 or not getattr(dlg, "token", None):
            return {"ok": False, "motivo": "cancelado"}
        api._save_jwt(dlg.token)                        # a mesma sessão vale para o app aberto
        (abrir or webbrowser.open)(url_de_volta(volta, dlg.token))
        return {"ok": True, "motivo": ""}
    except Exception as e:                              # noqa: BLE001 — deep link é best-effort
        return {"ok": False, "motivo": f"{type(e).__name__}: {e}"}

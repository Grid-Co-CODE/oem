# os_creator/os_web/oauth_fracttal.py
"""Entrar com o Fracttal (OAuth 2.0, authorization_code) — a ponte com a tela de login DELES.

A doc oficial (`fracttal_api_reference.md`) lista `https://one.fracttal.com/oauth/authorize` e os grants
`client_credentials` e `authorization_code`. Sondado ao vivo em 12/09/2026: o authorize redireciona para
`one.fracttal.com/accessgrant?oauthredirect=<base64{client_id, callback_url, state}>`, a tela do Fracttal One — a
pessoa loga lá (Microsoft incluída), autoriza a plataforma e o Fracttal volta ao nosso callback com `code`.

O que ainda NÃO se sabe, e por isso o retorno diagnostica ao vivo: se o access_token do usuário vale no RPC
(`rpc/proxy`, o caminho que cria OS de verdade) ou só no REST (`/api/...`, leitura). O token de `client_credentials`
levava 401 no RPC; o de uma PESSOA pode ser diferente. Se o RPC aceitar, a ponte está completa e o token entra no lugar
do JWT de sessão em toda a área /os. Se não, a tela diz isso, com o erro, e os outros caminhos continuam.

O callback tem de ser IGUAL ao registrado no consumidor OAuth do Fracttal ("Integração mal configurada: 'callback_url'
inválido", quando o Levi testou pelo túnel em 12/09/2026) — e o túnel muda de endereço a cada queda. Saída: uma volta FIXA
(`FRACTTAL_OAUTH_VOLTA` no .env), uma página estática (`relay/volta.html`) que mora num endereço que não muda e é o callback
registrado; o `state` leva, depois do nonce, a volta real desta sessão (o túnel de hoje) em base64url, e a página só faz o
navegador seguir para lá — apenas para hosts da nossa casa. Sem a variável, o callback é o próprio túnel, como antes."""
from __future__ import annotations
import base64
import binascii
import json
import os
import re
import secrets
from urllib.parse import urlencode, urlsplit

import api

AUTORIZE = "https://one.fracttal.com/oauth/authorize"
TOKEN_URLS = ("https://one.fracttal.com/oauth/token", "https://app.fracttal.com/oauth/token")   # doc, depois o que funciona no coletor
_HOSTS_OK = re.compile(r"^(?:[a-z0-9-]+\.trycloudflare\.com|localhost|127\.0\.0\.1|(?:[a-z0-9-]+\.)*gridco\.com\.br)$", re.I)
CAMINHO_VOLTA = "/os/login/fracttal/volta"


def callback_valido(url: str) -> bool:
    try:
        u = urlsplit(str(url or ""))
    except ValueError:
        return False
    return (u.scheme in ("http", "https") and bool(u.hostname) and bool(_HOSTS_OK.match(u.hostname))
            and u.path.rstrip("/") == CAMINHO_VOLTA)


def volta_fixa() -> str:
    """Endereço fixo registrado no consumidor OAuth (a página `relay/volta.html` publicada), ou "" para usar o próprio túnel."""
    return (os.environ.get("FRACTTAL_OAUTH_VOLTA") or "").strip()


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def novo_state(volta: str) -> str:
    """nonce + '.' + volta real em base64url. A sessão confere o state INTEIRO (nonce incluído); o relay só lê a volta."""
    return secrets.token_urlsafe(18) + "." + _b64(volta)


def volta_do_state(state: str) -> str:
    """A volta real embutida no state — "" quando não há uma URL do nosso caminho de volta ali."""
    try:
        _, b = str(state or "").split(".", 1)
        b += "=" * (-len(b) % 4)
        volta = base64.urlsafe_b64decode(b.encode("ascii")).decode("utf-8")
        u = urlsplit(volta)
    except (ValueError, UnicodeDecodeError, UnicodeEncodeError, binascii.Error):
        return ""
    return volta if u.scheme in ("http", "https") and u.hostname and u.path.rstrip("/") == CAMINHO_VOLTA else ""


def destino_do_relay(args) -> str | None:
    """O que a página fixa faz, em Python (a página é a transliteração disto): a volta real com `code`+`state`, ou com
    `error`(+`error_description`)+`state` quando o Fracttal negou. None = não segue (state forjado, host de fora, sem code)."""
    state = str(args.get("state") or "")
    volta = volta_do_state(state)
    if not volta or not callback_valido(volta):
        return None
    if args.get("error"):
        q = {"error": str(args.get("error"))}
        if args.get("error_description"):
            q["error_description"] = str(args.get("error_description"))
        q["state"] = state
    elif args.get("code"):
        q = {"code": str(args.get("code")), "state": state}
    else:
        return None
    return volta + "?" + urlencode(q)


_RELAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relay", "volta.html")


def pagina_relay() -> str:
    with open(_RELAY, encoding="utf-8") as f:
        return f.read()


def url_autorizacao(client_id: str, redirect_uri: str, state: str) -> str:
    return AUTORIZE + "?" + urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state})


def trocar_codigo(code: str, redirect_uri: str) -> dict:
    """code → {access_token, expires_in, refresh_token?}. Tenta o host da doc e cai para o app.fracttal.com (o token de
    client_credentials do coletor só funcionou lá)."""
    corpo = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
             "client_id": api.CLIENT_ID, "client_secret": api.CLIENT_SECRET}
    ultimo = ""
    for url in TOKEN_URLS:
        try:
            r = api.requests.post(url, data=corpo, timeout=30, headers={"Accept": "application/json"})
        except api.requests.RequestException as e:
            ultimo = f"{type(e).__name__}"
            continue
        try:
            j = r.json()
        except ValueError:
            j = {}
        if r.status_code == 200 and isinstance(j, dict) and j.get("access_token"):
            return j
        ultimo = f"HTTP {r.status_code} em {url.split('/')[2]}: {str(j)[:120]}"
    raise api.FracttalError(f"O Fracttal não trocou o código pelo token ({ultimo}).")


_CAMPOS_EMAIL = ("email", "account_email", "user_email", "preferred_username", "upn", "unique_name", "mail")


def claims_do_token(token: str) -> dict:
    """Claims do payload do JWT, ou {} se o token for opaco/mal formado (o token do OAuth pode nao ser um JWT)."""
    try:
        pl = token.split(".")[1]
        pl += "=" * (-len(pl) % 4)
        c = json.loads(base64.urlsafe_b64decode(pl.encode()))
        return c if isinstance(c, dict) else {}
    except Exception:                                     # noqa: BLE001 - token opaco: sem claims
        return {}


def email_dos_claims(claims: dict) -> str:
    """E-mail dentro dos claims, sob qualquer um dos nomes usuais (o token de senha usa email; o do SSO pode variar)."""
    for k in _CAMPOS_EMAIL:
        v = claims.get(k)
        if isinstance(v, str) and "@" in v:
            return v.strip()
    return ""


def _pessoa_no_personnel(alvos: dict) -> tuple:
    """Acha (nome, email) da pessoa logada no personnel (Recursos Humanos), casando por qualquer identificador que o token
    traga: e-mail, id_account (a conta da pessoa), id_client ou id. O token do SSO nao traz e-mail e o
    companies.load_account_info devolve a EMPRESA (plano, limites) - o vinculo com a PESSOA e o id_account. Best-effort,
    100 por pagina, com teto."""
    email = str(alvos.get("email") or "").strip().lower()
    acc = str(alvos.get("id_account") or "").strip()
    cli = str(alvos.get("id_client") or "").strip()
    idt = str(alvos.get("id") or "").strip()
    if not (email or acc or cli or idt):
        return ("", "")
    start = 0
    for _ in range(50):                                   # teto de 5000 pessoas: nunca roda para sempre
        try:
            res = api._rpc_call("personnel.personnel_list", {"page": start // 100 + 1, "limit": 100,
                                                             "start": start, "append": True, "filter": [], "sort": []})
        except Exception:                                 # noqa: BLE001 - sem RH, nao da para resolver
            return ("", "")
        data = res.get("data") if isinstance(res, dict) else res
        data = data if isinstance(data, list) else []
        for pessoa in data:
            p_email = str(pessoa.get("account_email") or pessoa.get("email") or "").strip().lower()
            p_acc = str(pessoa.get("id_account") or "").strip()
            p_id = str(pessoa.get("id") or "").strip()
            if ((email and p_email == email) or (acc and p_acc == acc)
                    or (cli and p_acc == cli) or (idt and p_id == idt)):
                return (str(pessoa.get("full_name") or pessoa.get("name") or "").strip(),
                        str(pessoa.get("account_email") or pessoa.get("email") or "").strip())
        if len(data) < 100:
            break
        start += 100
    return ("", "")


def diagnosticar(token: str) -> dict:
    """Com o token no contexto da requisicao: o RPC aceita? Quem e a pessoa? -> {rpc_ok, rpc_erro, nome, perfil, email, jwt}.
    REST nao e verificado aqui: o que decide a ponte e o RPC (e ele que cria OS como o app).

    O token do SSO nao traz e-mail e o companies.load_account_info devolve a EMPRESA; por isso a identidade da pessoa vem
    do personnel, casada pelo id_account do token (13/09/2026)."""
    api._save_jwt(token)                                   # entra no contexto (sessao); quem chama decide se persiste
    claims = claims_do_token(token)
    d = {"rpc_ok": False, "rpc_erro": "", "nome": "", "perfil": "",
         "email": email_dos_claims(claims), "jwt": token.count(".") == 2, "rest_ok": None}
    try:
        r = api._rpc_call("companies.load_account_info", {"page": 1, "limit": 200, "start": 0, "append": True})
        data = r.get("data") if isinstance(r, dict) else r
        rec = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
        rec = rec if isinstance(rec, dict) else {}
        d["rpc_ok"] = True
        d["nome"] = str(rec.get("name") or (str(rec.get("first_name") or "") + " " + str(rec.get("last_name") or "")).strip()).strip()
        d["perfil"] = str(rec.get("profiles_description") or rec.get("profile_description") or rec.get("profile") or "").strip()
        d["email"] = d["email"] or str(rec.get("email") or rec.get("account_email") or "").strip()
    except api.FracttalError as e:
        d["rpc_erro"] = str(e)
    except Exception as e:                                 # noqa: BLE001 - diagnostico nunca derruba
        d["rpc_erro"] = "%s: %s" % (type(e).__name__, e)
    # o load_account_info deu a EMPRESA, nao a pessoa: acha a PESSOA no personnel pelo id_account do token (ou e-mail/id).
    # Dai vem o nome - e o e-mail, para a autoria "criadas por mim" / "atribuidas a voce" funcionar.
    if d["rpc_ok"] and not d["nome"]:
        nome, email = _pessoa_no_personnel({"email": d["email"], "id_account": claims.get("id_account"),
                                            "id_client": claims.get("id_client"), "id": claims.get("id")})
        if nome:
            d["nome"] = nome
        if email and not d["email"]:
            d["email"] = email
    return d

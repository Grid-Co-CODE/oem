# os_creator/os_web/sessao.py
"""A sessão do Fracttal por PESSOA, presa à requisição web.

No desktop o `api.py` guarda UM JWT por máquina (keyring ou `fracttal_login.txt`): quem abriu o app é quem está logado.
Na web o mesmo processo serve várias pessoas ao mesmo tempo, e cada uma tem a sua sessão no Fracttal — a OS nasce no
nome de quem a cria (decisão do Levi, 10/09/2026: "loga no Fracttal, faz parte!"). Este módulo é a costura:

- um `ContextVar` carrega o JWT da requisição em curso (cada thread do servidor tem o seu contexto);
- `instalar(api)` troca, no módulo `api`, as quatro funções que tocam o JWT — `_read_jwt`, `_save_jwt`, `_clear_jwt`
  e `_rpc_try_refresh` — por versões que, DENTRO de uma requisição, leem e gravam no contexto; FORA dela chamam as
  originais. O desktop continua exatamente igual: só a web entra no contexto.

O `api.py` não é editado. Ele muda todo dia com o app (hoje mesmo tem alteração não commitada) e um gancho lá dentro
seria mais uma coisa a manter em dois lugares; aqui a costura vive junto de quem precisa dela."""
from __future__ import annotations
import contextlib
import contextvars
import json

_JWT = contextvars.ContextVar("os_web_jwt", default=None)        # None = fora de requisição; "" = requisição sem sessão
_ESTADO = contextvars.ContextVar("os_web_estado", default=None)  # {"novo": jwt|None, "morta": bool}


def em_requisicao() -> bool:
    return _JWT.get() is not None


def jwt_atual() -> str:
    return _JWT.get() or ""


def jwt_novo():
    """JWT que entrou na sessão durante a requisição (login ou renovação) — quem fecha a requisição grava no cookie."""
    est = _ESTADO.get()
    return est.get("novo") if est else None


def morta() -> bool:
    """A requisição descobriu que a sessão do Fracttal morreu (USER_NOT_LOGIN): o cookie tem de ser limpo."""
    est = _ESTADO.get()
    return bool(est and est.get("morta"))


def abrir(jwt: str) -> tuple:
    """Entra no contexto com o JWT da pessoa. Devolve os tokens para `fechar`."""
    return _JWT.set(jwt or ""), _ESTADO.set({"novo": None, "morta": False})


def fechar(tokens) -> None:
    t1, t2 = tokens
    _JWT.reset(t1)
    _ESTADO.reset(t2)


@contextlib.contextmanager
def contexto(jwt: str):
    tokens = abrir(jwt)
    try:
        yield
    finally:
        fechar(tokens)


def _definir(jwt: str) -> None:
    _JWT.set(jwt or "")
    est = _ESTADO.get()
    if est is not None:
        est["novo"] = jwt or None
        est["morta"] = False


def _apagar() -> None:
    _JWT.set("")
    est = _ESTADO.get()
    if est is not None:
        est["novo"] = None
        est["morta"] = True


def descartar() -> None:
    """Esquece um JWT que entrou nesta requisição sem valer (token colado que não passou na validação): nem vai para
    o cookie, nem marca a sessão como morta — a pessoa simplesmente não entrou."""
    _JWT.set("")
    est = _ESTADO.get()
    if est is not None:
        est["novo"] = None


def _renovar_sem_arquivo(api, jwt: str) -> str:
    """O mesmo POST /rpc/token do `api._rpc_try_refresh`, sem gravar em arquivo: na web o token novo vai para a
    sessão da pessoa. Repetido aqui de propósito — o original grava em LOGIN_JWT_FILE no meio da função, e um
    arquivo compartilhado do servidor guardaria o token de UMA pessoa para todas."""
    try:
        r = api.requests.post(api.RPC_TOKEN_URL, timeout=20, headers={
            "Authorization": f"Bearer {jwt}", "Content-Type": "application/json", "Origin": "https://app.fracttal.com"})
        if r.status_code != 200:
            return ""
        novo = ""
        try:
            j = r.json()
            if isinstance(j, str):
                novo = j
            elif isinstance(j, dict):
                d = j.get("data") if isinstance(j.get("data"), dict) else {}
                novo = j.get("token") or j.get("access_token") or d.get("token") or d.get("access_token") or ""
        except ValueError:
            novo = (r.text or "").strip().strip('"')
        novo = (novo or "").strip()
        return novo if novo.count(".") == 2 else ""
    except api.requests.RequestException:
        return ""


def instalar(api) -> None:
    """Costura as quatro funções do `api`. Idempotente: instalar duas vezes não empilha embrulhos."""
    if getattr(api, "_os_web_sessao_instalada", False):
        return
    orig_read, orig_save = api._read_jwt, api._save_jwt
    orig_clear, orig_refresh = api._clear_jwt, api._rpc_try_refresh

    def _read_jwt() -> str:
        return jwt_atual() if em_requisicao() else orig_read()

    def _save_jwt(jwt: str):
        if em_requisicao():
            _definir(jwt)
        else:
            orig_save(jwt)

    def _clear_jwt():
        if em_requisicao():
            _apagar()
        else:
            orig_clear()

    def _rpc_try_refresh(jwt: str) -> str:
        if not em_requisicao():
            return orig_refresh(jwt)
        novo = _renovar_sem_arquivo(api, jwt)
        if novo:
            _definir(novo)
        return novo

    api._read_jwt, api._save_jwt = _read_jwt, _save_jwt
    api._clear_jwt, api._rpc_try_refresh = _clear_jwt, _rpc_try_refresh
    api._os_web_sessao_instalada = True


def email_do_jwt(jwt: str) -> str:
    """E-mail no payload do JWT (o mesmo que `api.current_user` lê), sem depender do contexto."""
    try:
        import base64
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return str(json.loads(base64.urlsafe_b64decode(p.encode())).get("email") or "")
    except Exception:                                   # noqa: BLE001 — JWT opaco: sem e-mail
        return ""

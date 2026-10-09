# os_creator/os_web/rotas.py
"""As rotas da área /os. Cada tela espelha uma do app; o motor é sempre o `api.py`, dentro da sessão da pessoa."""
from __future__ import annotations
import datetime as dt
import functools
import os
import threading
import time
from urllib.parse import quote, urlencode

from flask import (Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_from_directory, session,
                   url_for)

import api

from . import ativo_curto, engenharia_web, lancador, oauth_fracttal, perf_web, sessao, sso

_AQUI = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.join(os.path.dirname(_AQUI), "assets")           # os_creator/assets (logo e ícone do app)

bp = Blueprint("os_web", __name__, url_prefix="/os", template_folder="templates",
               static_folder=os.path.join(_AQUI, "static"), static_url_path="/static")

STATUS_COR = {"Em Processo": "#F5A623", "Em Verificação": "#4A9EF5", "Concluída": "#48D07A", "Cancelada": "#F5766B"}


def _api_path() -> bool:
    return request.path.startswith("/os/api/")


def _caminho_atual() -> str:
    """O caminho COM a consulta, para o login devolver a pessoa exatamente onde estava. Com o `request.path`, o
    "Abrir chamado" (/os/chamados/inspecao?pai=13926) voltava do login sem a OS de referência — e todo link com
    filtro (Tickets, Performance com o plano) perdia o filtro do mesmo jeito (27/09)."""
    return request.full_path.rstrip("?")


def _destino_local(n: str) -> str:
    n = (n or "").strip()
    return n if (n.startswith("/os") and not n.startswith("//")) else url_for("os_web.home")


def exige_sessao(f):
    @functools.wraps(f)
    def _w(*a, **k):
        if not session.get("jwt"):
            if _api_path():
                return jsonify({"erro": "Entre no Fracttal para continuar.", "login": True}), 401
            return redirect(url_for("os_web.login") + "?next=" + quote(_caminho_atual(), safe=""))
        return f(*a, **k)
    return _w


@bp.app_errorhandler(api.FracttalError)
def _erro_fracttal(e):
    """Sessão morta → volta ao login com o aviso; outro erro do Fracttal → mensagem, nunca 500."""
    if sessao.morta() or isinstance(e, api.SessionExpired):
        for k in ("jwt", "conta"):
            session.pop(k, None)
        session["aviso"] = "A sessão do Fracttal caiu (outro login na sua conta ou o token venceu). Entre de novo."
        if _api_path():
            return jsonify({"erro": str(e), "login": True}), 401
        return redirect(url_for("os_web.login") + "?next=" + quote(_caminho_atual(), safe=""))
    if _api_path():
        return jsonify({"erro": str(e)}), 502
    return render_template("erro.html", conta=session.get("conta") or {}, aba="", mensagem=str(e)), 200


def _conta() -> dict:
    """Nome + cargo do Fracttal, buscados uma vez por sessão (o app busca no boot)."""
    c = session.get("conta")
    if not c:
        try:
            c = api.get_conta_info()
        except api.FracttalError:
            raise
        except Exception:                               # noqa: BLE001 — sem perfil a tela ainda abre
            c = {"nome": sessao.email_do_jwt(session.get("jwt") or "") or "Usuário", "perfil": ""}
        session["conta"] = c
    return c


# ── porta ─────────────────────────────────────────────────────────────────────
def _tela_login(erro=None, email="", prox="", aviso=None, sso_aberto=False, status=200):
    # `sso_aberto` sobrevive porque as rotas do OAuth ainda o passam ao devolver erro; a tela
    # simplesmente nao o usa mais desde que o login virou so e-mail e senha (Levi, 21/09).
    return render_template("login.html", erro=erro, email=email, next=prox, aviso=aviso), status


def _abrir_sessao(jwt: str, email: str, prox: str, conta: dict | None = None):
    """Sessão aberta (por senha, SSO ou OAuth): o JWT vai para o cookie e o perfil é lido uma vez, como no boot do app."""
    session.clear()
    session["jwt"] = jwt
    session.permanent = True
    try:
        session["conta"] = conta or api.get_conta_info()
        if email and not session["conta"].get("email"):
            session["conta"]["email"] = email
    except Exception:                                   # noqa: BLE001 — perfil é enfeite; a porta não trava por ele
        session["conta"] = {"nome": email or sessao.email_do_jwt(jwt) or "Usuário", "email": email, "perfil": ""}
    return redirect(_destino_local(prox))


@bp.route("/login", methods=["GET", "POST"])
def login():
    aviso = session.pop("aviso", None)
    prox = request.values.get("next") or ""
    if request.method == "POST":
        colado = request.form.get("token") or ""
        if colado.strip():                              # Entrar com Microsoft / SSO: a sessão copiada pelo favorito
            jwt = sso.extrair_jwt(colado)
            if not jwt:
                return _tela_login(erro=sso.ERRO_SEM_TOKEN, prox=prox, sso_aberto=True, status=401)
            api._save_jwt(jwt)                          # entra no contexto da requisição (sessao)
            if not api.is_logged_in():                  # exp + 1 RPC barato: a sessão pode estar morta server-side
                sessao.descartar()
                return _tela_login(erro=sso.ERRO_SESSAO_MORTA, prox=prox, sso_aberto=True, status=401)
            return _abrir_sessao(jwt, sessao.email_do_jwt(jwt), prox)
        email = (request.form.get("email") or "").strip()
        senha = request.form.get("senha") or ""
        try:
            api.fracttal_login(email, senha)              # grava o JWT na sessão da requisição (sessao._save_jwt)
        except api.FracttalError as e:
            return _tela_login(erro=str(e), email=email, prox=prox, status=401)
        jwt = sessao.jwt_atual()
        if not jwt:
            return _tela_login(erro="Login sem token de sessão. Tente de novo.", email=email, prox=prox, status=401)
        return _abrir_sessao(jwt, email, prox)
    # A tela abre no FORMULARIO. Ate 21/09 ela redirecionava sozinha para a tela do Fracttal
    # (Levi, 13/09) e o formulario so aparecia com ?manual=1 — agora e o contrario: o caminho
    # unico e e-mail e senha, e o OAuth ficou sem porta de entrada.
    return _tela_login(prox=prox, aviso=aviso)


@bp.route("/login/fracttal")
def login_fracttal():
    """Entrar pela tela do Fracttal (OAuth authorization_code). A página manda o callback público (o serviço, atrás do
    proxy, não sabe o host que o navegador vê); só a nossa casa é aceita."""
    volta = (request.args.get("volta") or "").strip()
    if not oauth_fracttal.callback_valido(volta):
        return render_template("erro.html", conta={}, aba="", mensagem="Callback do OAuth fora da plataforma: recusado."), 400
    if not (api.CLIENT_ID and api.CLIENT_SECRET):
        return render_template("erro.html", conta={}, aba="", mensagem="Sem FRACTTAL_CLIENT_ID/FRACTTAL_CLIENT_SECRET no .env do os_creator."), 503
    # o callback que o Fracttal vê é o FIXO (relay) quando configurado — o consumidor deles só aceita um endereço e o túnel muda;
    # o state leva a volta real desta sessão para o relay devolver o navegador aqui
    state = oauth_fracttal.novo_state(volta)
    redirect_uri = oauth_fracttal.volta_fixa() or volta
    session["oauth_state"], session["oauth_volta"], session["oauth_redirect"] = state, volta, redirect_uri
    session["oauth_next"] = request.args.get("next") or ""
    return redirect(oauth_fracttal.url_autorizacao(api.CLIENT_ID, redirect_uri, state))


@bp.route("/login/fracttal/volta")
def login_fracttal_volta():
    """O Fracttal devolveu: confere o state, troca o code pelo token e diagnostica ao vivo o que ele pode fazer."""
    if request.args.get("error"):
        motivo = request.args.get("error_description") or request.args.get("error")
        return _tela_login(erro=f"O Fracttal não autorizou: {motivo}", sso_aberto=True, status=401)
    state, esperado = request.args.get("state") or "", session.get("oauth_state") or ""
    if not state or state != esperado:
        return render_template("erro.html", conta={}, aba="", mensagem="O state do OAuth não confere com o desta sessão. Comece de novo em /os/login."), 401
    volta, prox = session.get("oauth_volta") or "", session.get("oauth_next") or ""
    redirect_uri = session.get("oauth_redirect") or volta           # a troca repete o redirect_uri do authorize (RFC 6749 §4.1.3)
    for k in ("oauth_state", "oauth_volta", "oauth_redirect", "oauth_next"):
        session.pop(k, None)
    try:
        t = oauth_fracttal.trocar_codigo(request.args.get("code") or "", redirect_uri)
    except api.FracttalError as e:
        return _tela_login(erro=str(e), sso_aberto=True, status=502)
    token = str(t.get("access_token") or "")
    d = oauth_fracttal.diagnosticar(token)
    if not d.get("rpc_ok"):
        sessao.descartar()
        return render_template("oauth_diag.html", conta={}, aba="", d=d, expira=t.get("expires_in")), 200
    email = d.get("email") or sessao.email_do_jwt(token)
    conta = {"nome": d.get("nome") or email or "Usuário", "email": email, "perfil": d.get("perfil") or ""}
    return _abrir_sessao(token, email, prox, conta=conta)


@bp.route("/os/<int:wid>/anexos")
@exige_sessao
def os_anexos_contagem(wid):
    """Contagem dos anexos da OS para os dois cards do detalhe (verde = das subtarefas, azul = da OS), como a janela do app:
    o anexo que ja e de uma subtarefa nao conta de novo na OS (`_os_uniq` do steps/os_detalhe.py). Vem depois do detalhe,
    por fetch, porque sao duas chamadas RPC a mais e o card tem de abrir na hora; falha aqui vira '—', nunca erro.

    Para CONTAR não precisa da URL pré-assinada de cada arquivo (Levi, 08/10/2026: "a tela que abre quando clica na OS
    está demorando"): era um s3_object_get por foto, na cota da empresa, só para mostrar um número. A chave da conta é
    o caminho do arquivo, que vem sem a URL, então o número é o mesmo. As duas listas vão ao mesmo tempo."""
    from flask import jsonify
    def chave(a):
        return str(a.get("value") or a.get("url") or a.get("nome") or "").lower()
    def contar(ler):
        with api.enxuta("url"):
            return ler(wid) or []
    try:
        with api._ExecutorComContexto(max_workers=2) as ex:
            f_subs, f_oss = ex.submit(contar, api.get_os_subtarefa_anexos), ex.submit(contar, api.get_os_anexos)
            subs, oss = f_subs.result(), f_oss.result()
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        return jsonify({"sub": None, "os": None, "erro": str(e)[:160]})
    vistos = {chave(a) for a in subs if chave(a)}
    return jsonify({"sub": len(subs), "os": sum(1 for a in oss if chave(a) not in vistos)})


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("os_web.login"))


@bp.route("/assets/<nome>")
def assets(nome):
    if not nome.lower().endswith((".png", ".ico")):
        abort(404)
    return send_from_directory(_ASSETS, nome, max_age=86400)


# ── a tela inicial: consultar, os setores e as solicitações (Levi, 27/09/2026) ────────────────────────────
_BRT = dt.timezone(dt.timedelta(hours=-3))


def _rota_existe(rota: str) -> bool:
    """A tela já nasceu na web? É o que acende a porta que esperava por ela (`lancador.portas_vivas`)."""
    return any(r.rule == rota for r in current_app.url_map.iter_rules())


def _info_catalogo() -> dict:
    """De quando é o catálogo local e quantos ativos ele tem pela MESMA régua da tela de Ativos (só ativo com código):
    o arquivo tem registro sem código, e a tela inicial dizia 21.639 enquanto a de Ativos dizia 21.635 (27/09).
    Catálogo vencido (`_read_asset_cache` → None) fica com a conta do arquivo e a marca de desatualizado."""
    info = dict(api.assets_cache_info())
    ativos = api._read_asset_cache()
    if ativos is not None:
        info["n"] = sum(1 for a in ativos if isinstance(a, dict) and a.get("code"))
    return info


def _pilulas_ativos(agora) -> list:
    """'21.635 ativos' e de quando é o catálogo — do arquivo local, com memória de 5 min: ler os 21 mil ativos do disco a
    cada abertura da tela inicial custaria mais do que a própria tela."""
    info = _memo(("ativos_info",), 300, _info_catalogo)
    n = int(info.get("n") or 0)
    if not n:
        return []
    out = [f"{n:,} ativos".replace(",", ".")]
    ts = float(info.get("ts") or 0)
    if ts:
        quando = dt.datetime.fromtimestamp(ts, _BRT)
        dia = "hoje" if quando.date() == agora.date() else quando.strftime("%d/%m")
        out.append("catálogo de %s, %s%s" % (dia, quando.strftime("%H:%M"), " · desatualizado" if info.get("expirado") else ""))
    return out


@bp.route("/")
@exige_sessao
def home():
    conta = _conta()
    try:
        selo = lancador.texto_selo(api.contar_minhas_analises())
    except api.FracttalError:
        if sessao.morta():                              # a sessão morreu no Fracttal: melhor saber já na porta
            raise
        selo = ""                                       # o selo é informativo, nunca derruba a tela
    except Exception:                                   # noqa: BLE001
        selo = ""
    agora = dt.datetime.now(_BRT)
    try:
        pilulas = _pilulas_ativos(agora)
    except Exception:                                   # noqa: BLE001 — informativo, como o selo
        pilulas = []
    nome = ((conta or {}).get("nome") or "").split()
    ola = lancador.saudacao(agora.hour) + (", " + nome[0] if nome else "")
    setores = [dict(s, portas=lancador.portas_vivas(s.get("portas"), _rota_existe))
               for s in lancador.portas_vivas(lancador.SETORES, _rota_existe)]
    if engenharia_web.supervisorio():                   # 27/09: o supervisório da Engenharia ligado no .env
        setores = [dict(s, etiqueta="", portas=[{"rotulo": "Supervisório", "href": "/os/engenharia"}])
                   if s["chave"] == "eng" else s for s in setores]
    # casca=True: a tela inicial é a CASCA das abas abertas (28/09) — o Início mora nela, as outras telas em abas
    return render_template("home.html", conta=conta, aba="criar", selo=selo, ola=ola, consulta=lancador.CONSULTA,
                           pilulas_ativos=pilulas, setores=setores, tradicional=lancador.TRADICIONAL,
                           solicitacoes=lancador.SOLICITACOES, casca=True)


@bp.route("/buscar")
@exige_sessao
def buscar():
    """A busca da tela inicial: um NÚMERO abre a OS (o mesmo "Buscar OS" do Histórico); TEXTO procura no catálogo de
    ativos, com o campo da tela de Ativos já preenchido."""
    q = " ".join((request.args.get("q") or "").split())
    if not q:
        return redirect(url_for("os_web.home"))
    num = q.lstrip("#").strip()
    if num.isdigit():
        return redirect(url_for("os_web.os_detalhe_por_folio", folio=int(num)))
    return redirect("/os/ativos?" + urlencode({"busca": q}))


def render_setor(chave: str):
    """A página de um setor: as partes dele, cada uma uma porta (o molde nasceu no Chamados, 27/09)."""
    s = lancador.PORTAS_SETOR.get(chave)
    if not s:
        abort(404)
    return render_template("setor.html", conta=_conta(), aba="criar", chave=chave, s=s,
                           portas=lancador.portas_vivas(s["portas"], _rota_existe))


@bp.route("/setor/<chave>")
@exige_sessao
def setor(chave):
    if chave == "chamados":                             # o de Chamados já morava em /os/chamados
        return redirect(url_for("os_web_chamados.chamados"))
    return render_setor(chave)


@bp.route("/em-breve/<chave>")
@exige_sessao
def em_breve(chave):
    info = lancador.NO_APP.get(chave)
    if not info:
        abort(404)
    aba = "solic" if chave == "solic" else "criar"
    return render_template("em_breve.html", conta=_conta(), aba=aba, titulo=info[0], faz=info[1])


# ── Performance ───────────────────────────────────────────────────────────────
@bp.route("/performance")
@exige_sessao
def performance():
    return render_template("performance.html", conta=_conta(), aba="criar", planos=perf_web.PLANOS)


@bp.route("/performance/criar")
@exige_sessao
def performance_criar():
    frase = request.args.get("frase") or ""
    plano = perf_web.plano_por_frase(frase)
    if not plano:
        abort(404)
    assets = api.load_assets_cached()
    clientes = sorted(perf_web.clientes_reais(assets))
    usinas = perf_web.usinas_para(assets, None)
    return render_template("perf_criar.html", conta=_conta(), aba="criar", plano=plano, clientes=clientes, usinas=usinas,
                           tem_modos=perf_web.tem_modos(frase), modos=perf_web.MODOS, coluna_qtd=perf_web.coluna_qtd(frase),
                           aba_ticket=perf_web.aba_ticket(frase), eh_tracker=perf_web.eh_tracker(frase),
                           sugestao={k: request.args.get(k, "") for k in ("usina", "ativo", "obs", "os_pai", "resp", "modo")},
                           agora=dt.datetime.now(perf_web.BRT).strftime("%Y-%m-%dT%H:%M"),
                           programada=(dt.datetime.now(perf_web.BRT) + dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M"))


@bp.route("/api/performance/qtd")
@exige_sessao
def api_qtd_ticket():
    """Quantas ocorrências a observação daquele ativo vale, pela regra do app.

    A tela pergunta em vez de contar: a regra ("PV"/"STR"/"String", cada uma uma vez) foi medida
    no corpus e vive em `tickets_nasce.contar_strings`. Portá-la para o JavaScript criaria uma
    segunda verdade, e a primeira divergência apareceria numa planilha de produção."""
    return jsonify(perf_web.qtd_sugerida(request.args.get("frase") or "",
                                         request.args.get("texto") or ""))


@bp.route("/api/performance/usinas")
@exige_sessao
def api_usinas():
    cliente = (request.args.get("cliente") or "").strip() or None
    return jsonify({"usinas": perf_web.usinas_para(api.load_assets_cached(), cliente), "cliente": cliente})


@bp.route("/api/performance/alvos")
@exige_sessao
def api_alvos():
    usina, frase = (request.args.get("usina") or "").strip(), request.args.get("frase") or ""
    assets = api.load_assets_cached()
    ativos_usi = perf_web.ativos_da_usina(assets, usina, frase)
    if not ativos_usi:
        return jsonify({"ativos": [], "base": "", "is_tracker": perf_web.eh_tracker(frase), "cliente": perf_web.cliente_da_usina(assets, usina),
                        "erro": "Sem inversores/trackers/estação nesta usina."})
    res = api.get_performance_alvos(ativos_usi, frase) or {}
    base = res.get("base") or (perf_web.plano_por_frase(frase) or {}).get("titulo") or ""
    ativos = []
    for al in res.get("ativos") or []:
        a = al.get("asset") or {}
        ativos.append({"id": a.get("id"), "label": api._asset_short_name(a), "code": a.get("code"), "tipo": a.get("tipo"),
                       "plano_id_task": al.get("plano_id_task"), "plano_id_item": al.get("plano_id_item"),
                       "linkar": bool(al.get("linkar", True)), "titulo": api.perf_os_nome(a, base)})
    out = {"ativos": ativos, "base": base, "is_tracker": bool(res.get("is_tracker", perf_web.eh_tracker(frase))),
           "cliente": perf_web.cliente_da_usina(assets, usina)}
    if res.get("erro"):
        out["erro"] = res["erro"]
    return jsonify(out)


@bp.route("/api/performance/alvo/<int:aid>")
@exige_sessao
def api_alvo(aid):
    """O ativo inteiro (o app guarda o dict do catálogo e o manda na criação); a tela pede na hora de criar."""
    a = next((x for x in api.load_assets_cached() if x.get("id") == aid), None)
    if not a:
        abort(404)
    return jsonify(a)


@bp.route("/api/performance/plano")
@exige_sessao
def api_plano():
    plan = api.get_plan_details(request.args.get("id_task"), request.args.get("id_item"))
    return jsonify({"resumo": perf_web.resumo_plano(plan)})


@bp.route("/api/performance/contagens")
@exige_sessao
def api_contagens():
    try:
        d = perf_web.contar_subtarefas(api.load_assets_cached())
    except Exception as e:                              # noqa: BLE001 — a contagem é enfeite do card
        return jsonify({"contagens": {}, "erro": str(e)})
    return jsonify({"contagens": d})


@bp.route("/api/responsaveis")
@exige_sessao
def api_responsaveis():
    pessoas = sorted(api.get_responsaveis() or [], key=lambda x: (x.get("name") or "").lower())
    return jsonify({"pessoas": pessoas})


@bp.route("/api/performance/criar", methods=["POST"])
@exige_sessao
def api_performance_criar():
    corpo = request.get_json(silent=True) or {}
    itens, kwargs, erro = perf_web.montar_itens(corpo)
    if erro:
        return jsonify({"erro": erro}), 400
    # a tela manda o ativo enxuto (id, code, label); o `create_performance_os` quer o registro INTEIRO do catálogo
    # (description, tipo_code, id_group_task…) — é dele que sai o título e a estrutura da OS. Completa pelo id.
    catalogo = {x.get("id"): x for x in api.load_assets_cached()}
    for it in itens:
        cheio = catalogo.get(it["asset"].get("id"))
        if cheio:
            it["asset"] = cheio
    res = api.create_performance_os(itens, **kwargs)
    # a frase e a caixa vao junto: e delas que sai o "N tickets criados na aba X" (e o "sem ticket")
    return jsonify(perf_web.mensagem_resultado(res, corpo.get("frase") or "",
                                               bool(corpo.get("gerar_ticket", True))))


# ── Históricos de OS ──────────────────────────────────────────────────────────
# As três visões (Histórico Geral / Atribuídas a mim / Visão COS) são TRÊS BUSCAS diferentes no Fracttal — criadas por
# mim, atribuídas a mim, a equipe inteira —, não três filtros da mesma lista: a da equipe passa de 2.000 OS em 30 dias,
# então filtrar as outras duas a partir dela perderia OS. O que dá para fazer, e faz (Levi, 27/09: "está demorando demais,
# por que não funciona como um filtro?"), é não repetir a busca: cada visão fica guardada alguns minutos por pessoa, e
# voltar a ela é instantâneo. O botão de atualizar (e a atualização de 10 em 10 min) passam por cima da memória.
TTL_HISTORICO = 180          # s — a lista de uma visão; o botão ↻ busca de novo na hora
TTL_APOIO = 600              # s — etiquetas e pessoas, que quase não mudam
_MEMO: dict = {}
_MEMO_LOCK = threading.Lock()


def _memo(chave, ttl: float, fn, forcar: bool = False):
    """O resultado de `fn()` guardado por `ttl` segundos. Erro não é guardado (sobe como sempre)."""
    agora = time.monotonic()
    if not forcar:
        with _MEMO_LOCK:
            v = _MEMO.get(chave)
        if v and agora - v[0] < ttl:
            return v[1]
    r = fn()
    with _MEMO_LOCK:
        _MEMO[chave] = (agora, r)
        if len(_MEMO) > 300:                              # memória com teto: sai o que foi guardado há mais tempo
            for k in sorted(_MEMO, key=lambda k: _MEMO[k][0])[:len(_MEMO) - 300]:
                _MEMO.pop(k, None)
    return r


# ── o círculo de carga do Histórico (Levi, 27/09: "no período de carregamento poderia ter um círculo mostrando o
# progresso"). O navegador manda um `p=<token>` junto com a busca e pergunta em /historico/progresso quanto já veio;
# quem responde é o `api.list_minhas_os`, a cada página e a cada lote do meta das tarefas que termina. ──────────────
_PROGRESSO: dict = {}
_PROG_LOCK = threading.Lock()


def _token_ok(t) -> str:
    t = str(t or "").strip()
    return t if 6 <= len(t) <= 40 and all(c.isalnum() or c in "-_" for c in t) else ""


def _progresso_de(token):
    """O `progresso(feito, total)` que a busca chama, gravando no registro deste token. Sem token válido, None."""
    token = _token_ok(token)
    if not token:
        return None
    with _PROG_LOCK:
        _PROGRESSO[token] = {"feito": 0, "total": 0, "quando": time.time()}
        if len(_PROGRESSO) > 200:                       # teto: sai o mais velho
            for k in sorted(_PROGRESSO, key=lambda k: _PROGRESSO[k]["quando"])[:len(_PROGRESSO) - 200]:
                _PROGRESSO.pop(k, None)

    def _aviso(feito, total):
        with _PROG_LOCK:
            _PROGRESSO[token] = {"feito": int(feito), "total": int(total), "quando": time.time()}
    return _aviso


def _quem() -> str:
    """A pessoa, para a memória não servir a lista de um para outro ("criadas por MIM" depende de quem é o mim)."""
    return (session.get("conta") or {}).get("email") or sessao.email_do_jwt(session.get("jwt") or "") or "?"


COLS = [("Nº", "folio"), ("Cliente", "cliente"), ("Usina", "usina"), ("Ativo", "ativo"), ("Descrição", "descricao"),
        ("Data de Criação", "data"), ("Data do Evento", "event_date"), ("Data Fim", "data_fim"), ("Status", "status"),
        ("Etiqueta", "etiqueta")]
# Visão COS: espelha a do Power BI, na ordem do print do Levi (steps/historico.py::COLS_COS)
COLS_COS = [("Data da programação", "programada"), ("Tipo de tarefa", "tipo_tarefa"), ("Usina", "usina"), ("Cliente", "cliente"),
            ("Descrição", "descricao"), ("Equipe", "equipe"), ("Data Início da OS", "inicio"), ("Data Fim da OS", "data_fim"),
            ("Descrição gatilho", "gatilho"), ("Descrição EQP", "ativo"), ("Nº Da OS", "folio"), ("Criado por", "criado_por")]
DATAS = {"data", "event_date", "data_fim", "programada", "inicio"}


def _catalogo_clientes_usinas() -> dict:
    """{cliente: {usinas}} do catálogo de ativos — só pares de PLANTA (api.CARTEIRA_EQUIP), como o `_catalogo_loc` do app:
    sem o discriminador o combo listava o almoxarifado inteiro como se fosse usina (print do Levi, 28/07). Best-effort."""
    m: dict = {}
    try:
        for cli, usi, tipo in api._code_to_loc().values():
            if cli and usi and tipo in api.CARTEIRA_EQUIP:
                m.setdefault(cli, set()).add(usi)
    except Exception:                                   # noqa: BLE001 — sem catálogo, valem só as linhas carregadas
        pass
    return m


@bp.route("/historico")
@exige_sessao
def historico():
    """Históricos de OS com os filtros do app (steps/historico.py): três visões (Histórico Geral / Atribuídas a mim /
    Visão COS), Buscar OS pelo nº (direto, ignora filtros), Buscar (local), Limpar filtros, e a grade Criado por, Etiqueta,
    Status, Cliente, Usina, Tipo de ativo, Tipo de tarefa, Período. Como no app: Visão, Criado por, Etiqueta, Status e
    Período valem NO SERVIDOR (re-buscam); Cliente, Usina, Tipo de ativo, Tipo de tarefa e a busca são locais (JS sobre
    a lista carregada). O tipo de tarefa já vem na lista (`list_minhas_os` junta o meta da tarefa na mesma busca).

    "Pq não funciona como um filtro?" (Levi, 27/09): porque as três visões são três buscas DIFERENTES no Fracttal
    (criadas por mim, atribuídas a mim, a equipe inteira) e a da equipe passa do teto de 2.000 em 30 dias — filtrar as
    outras a partir dela perderia OS. O que dá para cortar, cortou-se: a lista fica 3 min na memória por pessoa e visão
    (voltar a uma visão não vai ao Fracttal; o ↻, o F5 e a atualização de 10 min vão, com `atualizar=1`), e a tela
    deixou de buscar de novo, em 34 lotes sequenciais de 60, o meta que o servidor já tinha mandado."""
    modo = request.args.get("modo") or "criadas"
    if modo not in ("criadas", "atribuidas", "cos"):
        modo = "criadas"
    modo_srv = "atribuidas" if modo == "atribuidas" else "criadas"      # a COS é a busca de 'criadas' com outras colunas
    hoje = dt.date.today()
    de = request.args.get("de") or (hoje - dt.timedelta(days=30)).isoformat()
    ate = request.args.get("ate") or hoje.isoformat()
    busca = (request.args.get("busca") or "").strip()
    # Criado por: o padrão do app é o usuário logado (None); a Visão COS é de EQUIPE (Todos); em Atribuídas não existe
    pessoa = (request.args.get("pessoa") or "").strip()
    if modo == "atribuidas":
        id_account = None
    elif pessoa == "TODOS" or (modo == "cos" and not pessoa):
        id_account = "TODOS"
    elif pessoa.isdigit():
        id_account = int(pessoa)
    else:
        id_account = None
    etq = (request.args.get("etiqueta") or "").strip()
    id_label = int(etq) if etq.isdigit() else None
    nome_para_id = {v: k for k, v in api.WO_STATUS.items()}
    status_sel = [x for x in request.args.getlist("status") if x in nome_para_id]
    status_ids = [nome_para_id[x] for x in status_sel] or None
    linhas, erro, info = [], None, {}
    forcar = request.args.get("atualizar") == "1"
    chave = ("hist", _quem(), modo_srv, id_account, id_label, de, ate, tuple(status_ids or ()))

    aviso = _progresso_de(request.args.get("p"))

    def _buscar():
        inf = {}
        return (api.list_minhas_os(modo=modo_srv, id_account=id_account, id_label=id_label, de=de, ate=ate,
                                   status_ids=status_ids, info=inf, progresso=aviso) or []), inf
    try:
        linhas, info = _memo(chave, TTL_HISTORICO, _buscar, forcar)
        linhas = list(linhas)
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        erro = str(e)
    # o teto de 2.000 corta as OS MAIS ANTIGAS do período em silêncio — dizer, com o total do servidor e o que CHEGOU (a
    # conta é total − carregadas, antes da busca local; o teto só entra para saber se houve corte)
    total_srv, teto = int(info.get("total") or 0), int(info.get("cap") or 0)
    cortadas = max(0, total_srv - len(linhas)) if teto and total_srv > teto else 0
    if busca:                                            # a busca é local (JS); aqui só para quem está sem JS
        b = busca.lower()
        linhas = [l for l in linhas if b in " ".join(str(l.get(k) or "") for k in ("folio", "usina", "ativo", "descricao", "cliente", "status")).lower()]
    labels, pessoas, eu = [], [], None
    try:
        labels = sorted(_memo(("etiquetas",), TTL_APOIO, lambda: api.get_labels() or [], forcar),
                        key=lambda x: (x.get("description") or "").lower())
    except Exception:                                    # noqa: BLE001 — sem etiquetas o filtro fica em 'Todas'
        pass
    try:
        r = _memo(("pessoas", _quem()), TTL_APOIO, lambda: api.get_pessoas_contas() or {}, forcar)
        pessoas, eu = (r.get("pessoas") or []), r.get("eu")
    except Exception:                                    # noqa: BLE001 — idem
        pass
    cat = _catalogo_clientes_usinas()
    clientes = sorted(set(cat) | {l.get("cliente") for l in linhas if l.get("cliente") and l.get("cliente") != "—"})
    usina_cli = {u: c for c, us in cat.items() for u in us}
    for l in linhas:
        if l.get("usina") and l.get("usina") != "—":
            usina_cli.setdefault(l["usina"], l.get("cliente") or "")
    tipos_ativo = sorted({l.get("tipo") for l in linhas if l.get("tipo") and l.get("tipo") != "—"})
    tarefa_sel = list(api.TIPOS_COS) if modo == "cos" else []        # a COS já vem com os tipos do COS marcados
    # o nome curto do ativo ("Inversor 1.10", "Tracker 35.100"): a frase de cada tipo sai do catálogo que já está no disco
    # — ler o do Fracttal aqui (quando o cache venceu) poria minutos na frente do Histórico por um detalhe de exibição
    frases = _memo(("frases_ativo",), 3600, lambda: ativo_curto.frases(api._read_asset_cache() or []))
    for l in linhas:
        l["_ativo_curto"] = ativo_curto.curto(l.get("ativo"), frases.get(l.get("tipo")))
        l["_status_cor"] = STATUS_COR.get(l.get("status") or "")
        l["_etiqueta"] = ", ".join(e.get("nome") or "" for e in (l.get("etiquetas") or []) if isinstance(e, dict))
        l["_texto"] = (" ".join(str(l.get(k) or "") for k in ("folio", "cliente", "usina", "ativo", "descricao", "status")) + " " + l["_etiqueta"]).lower()
    pessoa_sel = "TODOS" if id_account == "TODOS" else (str(id_account) if isinstance(id_account, int) else (str(eu) if eu is not None else ""))
    return render_template("historico.html", conta=_conta(), aba="hist", linhas=linhas, modo=modo, de=de, ate=ate, busca=busca, erro=erro,
                           cols=(COLS_COS if modo == "cos" else COLS), datas=DATAS, fmt=api.fmt_data_br,
                           labels=labels, pessoas=pessoas, pessoa_sel=pessoa_sel, etiqueta_sel=str(id_label or ""),
                           status_opts=list(api.WO_STATUS.values()), status_sel=status_sel, clientes=clientes,
                           usinas=sorted(usina_cli), usina_cli=usina_cli, tipos_ativo=tipos_ativo,
                           tipos_tarefa=sorted(set(tarefa_sel) | {t for l in linhas for t in str(l.get("tipo_tarefa") or "").split(" / ") if t}),
                           tarefa_sel=tarefa_sel, cortadas=cortadas, total_srv=total_srv, teto=teto)


@bp.route("/historico/progresso")
@exige_sessao
def historico_progresso():
    """Quanto da busca deste token já veio: {feito, total}. total=0 = ainda na 1ª página (o círculo gira sem número)."""
    token = _token_ok(request.args.get("p"))
    with _PROG_LOCK:
        p = dict(_PROGRESSO.get(token) or {})
    return jsonify({"feito": p.get("feito", 0), "total": p.get("total", 0), "conhecido": bool(p)})


@bp.route("/historico/meta")
@exige_sessao
def historico_meta():
    """Tipo de tarefa e datas da tarefa por OS, em lote. A tela nova não chama mais (desde 27/09 o tipo já vem na lista);
    fica para a página aberta antes da troca, cujo JS ainda pede o meta depois da lista."""
    from flask import jsonify
    ids = [int(x) for x in (request.args.get("ids") or "").split(",") if x.strip().isdigit()]
    if not ids:
        return jsonify({})
    try:
        meta = api.meta_tarefas_por_os(ids) or {}
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        return jsonify({})
    return jsonify({str(k): v for k, v in meta.items()})


# ── o card da OS começa a ser lido antes do clique (Levi, 09/10/2026: "teria como utilizarmos essas requisições de forma
# mais inteligente?") ───────────────────────────────────────────────────────────────────────────────────────────────
# O mouse que PARA em cima de um cartão (Quadro da equipe da Engenharia do Nexus, Acompanhamento de chamados) pede o
# detalhe da OS por trás (`/os/api/os/<id>/preparar`); o clique que vem depois pega essa leitura, ou espera a que já está
# em curso, em vez de começar do zero no Fracttal. As regras são pela confiabilidade e pela cota da empresa (200/min):
# - vale PREPARO_S e UMA vez: o clique seguinte lê de novo (o card mostra o que a pessoa acabou de mudar);
# - toda gravação numa OS (POST com o id dela) joga fora o que foi lido antes (`_gravou_esquece_preparo`);
# - teto por pessoa e no total, por minuto: passar o mouse pelo quadro inteiro não vira rajada no Fracttal (no pior caso,
#   12 leituras de ~5 pedidos por minuto, somando todo mundo);
# - com a sessão DA PESSOA no Fracttal (`sessao.contexto`): a thread nasce sem o contexto da requisição.
PREPARO_S = 30
PREPARO_PESSOA_MIN = 6
PREPARO_TOTAL_MIN = 12
_PREPARO: dict = {}                # (pessoa, wid, modo) -> (quando, Future)
_PREPARO_PEDIDOS: list = []        # (quando, pessoa) dos pedidos aceitos no último minuto, para o teto
_PREPARO_LOCK = threading.Lock()
_PREPARO_EXEC = None               # nasce no 1º pedido: teste e desktop não abrem threads à toa


def _executor_preparo():
    global _PREPARO_EXEC
    with _PREPARO_LOCK:
        if _PREPARO_EXEC is None:
            from concurrent.futures import ThreadPoolExecutor
            _PREPARO_EXEC = ThreadPoolExecutor(max_workers=3, thread_name_prefix="os-web-preparo")
        return _PREPARO_EXEC


def preparar(pessoa, wid, modo: str = "card") -> bool:
    """Começa a ler, por trás, o detalhe da OS `wid` para `pessoa`. O modo "chamado" lê enxuto (a tela de um chamado não
    mostra solicitação nem OS pai: 2 pedidos a menos). False se já está pronto ou lendo, ou se passou do teto."""
    agora = time.monotonic()
    chave = (pessoa, int(wid), modo)
    jwt, email = sessao.jwt_atual(), sessao.email_atual()

    def ler():
        with sessao.contexto(jwt, email):
            if modo == "chamado":
                with api.enxuta("vinculos"):
                    return api.get_os_detalhes(int(wid)) or {}
            return api.get_os_detalhes(int(wid)) or {}
    executor = _executor_preparo()
    with _PREPARO_LOCK:
        for k in [k for k, (t, _f) in _PREPARO.items() if agora - t > PREPARO_S]:
            _PREPARO.pop(k, None)
        if chave in _PREPARO:
            return False
        _PREPARO_PEDIDOS[:] = [(t, p) for t, p in _PREPARO_PEDIDOS if agora - t < 60]
        if (len(_PREPARO_PEDIDOS) >= PREPARO_TOTAL_MIN
                or sum(1 for _t, p in _PREPARO_PEDIDOS if p == pessoa) >= PREPARO_PESSOA_MIN):
            return False
        _PREPARO_PEDIDOS.append((agora, pessoa))
        _PREPARO[chave] = (agora, executor.submit(ler))
    return True


def preparado(wid, modo: str = "card", pessoa=None):
    """O detalhe que o mouse parado pediu, se ainda vale: espera a leitura em curso, em vez de pedir de novo, e entrega
    UMA vez. None se não há, se venceu ou se deu erro: quem chama lê na hora, como sempre, e o erro aparece ali."""
    chave = (pessoa or _quem(), int(wid), modo)
    with _PREPARO_LOCK:
        v = _PREPARO.pop(chave, None)
    if not v or time.monotonic() - v[0] > PREPARO_S:
        return None
    try:
        det = v[1].result(timeout=45)
    except Exception:                   # noqa: BLE001 — sessão caída, 429, rede
        return None
    return det if det and det.get("folio") else None


def _esquecer_preparo(wid) -> None:
    with _PREPARO_LOCK:
        for k in [k for k in _PREPARO if k[1] == int(wid)]:
            _PREPARO.pop(k, None)


@bp.after_app_request
def _gravou_esquece_preparo(resp):
    """Toda gravação numa OS (as rotas POST com o id dela: concluir, nota, responsável, etiquetas, tarefa, cancelar...)
    tira o que foi lido antes dela: o card aberto depois mostra a OS como ficou."""
    wid = (request.view_args or {}).get("wid") if request.method == "POST" else None
    if wid:
        _esquecer_preparo(wid)
    return resp


@bp.route("/api/os/<int:wid>/preparar")
@exige_sessao
def os_preparar(wid):
    modo = "chamado" if request.args.get("modo") == "chamado" else "card"
    return jsonify({"pedido": preparar(_quem(), wid, modo)}), 202


@bp.route("/os/folio/<int:folio>")
@exige_sessao
def os_detalhe_por_folio(folio):
    """Buscar OS pelo nº — direto, ignora filtros e período (a barra do app). Resolve o nº para o id e cai no detalhe."""
    wid = api._wo_id_por_folio(str(folio))
    if not wid:
        msg = f"Não achei nenhuma OS com o nº {folio}."
        if request.args.get("parcial") or request.headers.get("X-Requested-With") == "fetch":
            return f'<p class="os-erro" style="padding:24px">{msg}</p>', 404
        return render_template("erro.html", conta=_conta(), aba="hist", mensagem=msg), 404
    return os_detalhe(wid)


@bp.route("/os/<int:wid>")
@exige_sessao
def os_detalhe(wid):
    # o Historico abre a OS num card sobreposto (Levi, 13/09): ?parcial=1 (ou fetch) devolve so o fragmento do detalhe,
    # sem o cabecalho/abas, para injetar no card. Sem isso, e a pagina cheia de sempre (fallback quando o JS nao roda).
    parcial = bool(request.args.get("parcial")) or request.headers.get("X-Requested-With") == "fetch"
    det = preparado(wid) or api.get_os_detalhes(wid) or {}      # o que o mouse parado no cartão já pediu (09/10/2026)
    if not det.get("folio"):
        if parcial:
            return f'<p class="os-erro" style="padding:24px">Não achei a OS de id {wid} no Fracttal.</p>', 404
        return render_template("erro.html", conta=_conta(), aba="hist", mensagem=f"Não achei a OS de id {wid} no Fracttal."), 404
    status = request.args.get("status") or ""
    template = "os_detalhe_conteudo.html" if parcial else "os_detalhe.html"
    return render_template(template, conta=_conta(), aba="hist", d=det, wid=wid, status=status, parcial=parcial,
                           status_cor=STATUS_COR.get(status), fmt=api.fmt_data_br, duracao=api.duracao_os)

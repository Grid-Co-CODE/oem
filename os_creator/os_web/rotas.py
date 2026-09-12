# os_creator/os_web/rotas.py
"""As rotas da área /os. Cada tela espelha uma do app; o motor é sempre o `api.py`, dentro da sessão da pessoa."""
from __future__ import annotations
import datetime as dt
import functools
import os
from urllib.parse import quote

from flask import (Blueprint, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for)

import api
from . import lancador, perf_web, sessao

_AQUI = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.join(os.path.dirname(_AQUI), "assets")           # os_creator/assets (logo e ícone do app)

bp = Blueprint("os_web", __name__, url_prefix="/os", template_folder="templates",
               static_folder=os.path.join(_AQUI, "static"), static_url_path="/static")

STATUS_COR = {"Em Processo": "#F5A623", "Em Verificação": "#4A9EF5", "Concluída": "#48D07A", "Cancelada": "#F5766B"}


def _api_path() -> bool:
    return request.path.startswith("/os/api/")


def _destino_local(n: str) -> str:
    n = (n or "").strip()
    return n if (n.startswith("/os") and not n.startswith("//")) else url_for("os_web.home")


def exige_sessao(f):
    @functools.wraps(f)
    def _w(*a, **k):
        if not session.get("jwt"):
            if _api_path():
                return jsonify({"erro": "Entre no Fracttal para continuar.", "login": True}), 401
            return redirect(url_for("os_web.login") + "?next=" + quote(request.path, safe=""))
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
        return redirect(url_for("os_web.login") + "?next=" + quote(request.path, safe=""))
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
@bp.route("/login", methods=["GET", "POST"])
def login():
    aviso = session.pop("aviso", None)
    prox = request.values.get("next") or ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        senha = request.form.get("senha") or ""
        try:
            api.fracttal_login(email, senha)              # grava o JWT na sessão da requisição (sessao._save_jwt)
        except api.FracttalError as e:
            return render_template("login.html", erro=str(e), email=email, next=prox, aviso=None), 401
        jwt = sessao.jwt_atual()
        if not jwt:
            return render_template("login.html", erro="Login sem token de sessão. Tente de novo.", email=email, next=prox, aviso=None), 401
        session.clear()
        session["jwt"] = jwt
        session.permanent = True
        try:
            session["conta"] = api.get_conta_info()
        except Exception:                               # noqa: BLE001 — perfil é enfeite; a porta não trava por ele
            session["conta"] = {"nome": email, "email": email, "perfil": ""}
        return redirect(_destino_local(prox))
    return render_template("login.html", erro=None, email="", next=prox, aviso=aviso)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("os_web.login"))


@bp.route("/assets/<nome>")
def assets(nome):
    if not nome.lower().endswith((".png", ".ico")):
        abort(404)
    return send_from_directory(_ASSETS, nome, max_age=86400)


# ── a tela inicial: as abas e o lançador ─────────────────────────────────────
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
    return render_template("home.html", conta=conta, aba="criar", cards=lancador.CARDS, selo=selo)


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
    return jsonify(perf_web.mensagem_resultado(res))


# ── Históricos de OS ──────────────────────────────────────────────────────────
COLS = [("Nº", "folio"), ("Cliente", "cliente"), ("Usina", "usina"), ("Ativo", "ativo"), ("Descrição", "descricao"),
        ("Data de Criação", "data"), ("Data do Evento", "event_date"), ("Data Fim", "data_fim"), ("Status", "status"),
        ("Etiqueta", "etiqueta")]


@bp.route("/historico")
@exige_sessao
def historico():
    modo = "atribuidas" if request.args.get("modo") == "atribuidas" else "criadas"
    hoje = dt.date.today()
    de = request.args.get("de") or (hoje - dt.timedelta(days=30)).isoformat()
    ate = request.args.get("ate") or hoje.isoformat()
    busca = (request.args.get("busca") or "").strip().lower()
    linhas, erro = [], None
    try:
        linhas = api.list_minhas_os(modo=modo, id_account=None, id_label=None, de=de, ate=ate) or []
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        erro = str(e)
    if busca:
        linhas = [l for l in linhas if busca in " ".join(str(l.get(k) or "") for k in ("folio", "usina", "ativo", "descricao", "cliente")).lower()]
    for l in linhas:
        l["_status_cor"] = STATUS_COR.get(l.get("status") or "")
        l["_etiqueta"] = ", ".join(e.get("nome") or "" for e in (l.get("etiquetas") or []) if isinstance(e, dict))
    return render_template("historico.html", conta=_conta(), aba="hist", linhas=linhas, modo=modo, de=de, ate=ate,
                           busca=request.args.get("busca") or "", erro=erro, cols=COLS, fmt=api.fmt_data_br)


@bp.route("/os/<int:wid>")
@exige_sessao
def os_detalhe(wid):
    det = api.get_os_detalhes(wid) or {}
    if not det.get("folio"):
        return render_template("erro.html", conta=_conta(), aba="hist", mensagem=f"Não achei a OS de id {wid} no Fracttal."), 404
    status = request.args.get("status") or ""
    return render_template("os_detalhe.html", conta=_conta(), aba="hist", d=det, wid=wid, status=status,
                           status_cor=STATUS_COR.get(status), fmt=api.fmt_data_br, duracao=api.duracao_os)

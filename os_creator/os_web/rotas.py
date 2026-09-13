# os_creator/os_web/rotas.py
"""As rotas da área /os. Cada tela espelha uma do app; o motor é sempre o `api.py`, dentro da sessão da pessoa."""
from __future__ import annotations
import datetime as dt
import functools
import os
from urllib.parse import quote

from flask import (Blueprint, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for)

import api
import secrets

from . import lancador, oauth_fracttal, perf_web, sessao, sso

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
def _tela_login(erro=None, email="", prox="", aviso=None, sso_aberto=False, status=200, auto=False):
    return render_template("login.html", erro=erro, email=email, next=prox, aviso=aviso, sso_aberto=sso_aberto,
                           bookmarklet=sso.bookmarklet_href(), auto=auto), status


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
    # abre direto na tela do Fracttal (Levi, 13/09): sem erro/aviso, sem ?manual=1, e com OAuth configurado
    auto = not aviso and not request.args.get("manual") and bool(api.CLIENT_ID and api.CLIENT_SECRET)
    return _tela_login(prox=prox, aviso=aviso, auto=auto)


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
    por fetch, porque sao duas chamadas RPC a mais e o card tem de abrir na hora; falha aqui vira '—', nunca erro."""
    from flask import jsonify
    def chave(a):
        return str(a.get("value") or a.get("url") or a.get("nome") or "").lower()
    try:
        subs = api.get_os_subtarefa_anexos(wid) or []
        oss = api.get_os_anexos(wid) or []
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
    a lista carregada). O tipo de tarefa chega depois, por /historico/meta — 3,5 s por 60 OS no Fracttal."""
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
    linhas, erro = [], None
    try:
        linhas = api.list_minhas_os(modo=modo_srv, id_account=id_account, id_label=id_label, de=de, ate=ate, status_ids=status_ids) or []
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        erro = str(e)
    if busca:                                            # a busca é local (JS); aqui só para quem está sem JS
        b = busca.lower()
        linhas = [l for l in linhas if b in " ".join(str(l.get(k) or "") for k in ("folio", "usina", "ativo", "descricao", "cliente", "status")).lower()]
    labels, pessoas, eu = [], [], None
    try:
        labels = sorted(api.get_labels() or [], key=lambda x: (x.get("description") or "").lower())
    except Exception:                                    # noqa: BLE001 — sem etiquetas o filtro fica em 'Todas'
        pass
    try:
        r = api.get_pessoas_contas() or {}
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
    for l in linhas:
        l["_status_cor"] = STATUS_COR.get(l.get("status") or "")
        l["_etiqueta"] = ", ".join(e.get("nome") or "" for e in (l.get("etiquetas") or []) if isinstance(e, dict))
        l["_texto"] = (" ".join(str(l.get(k) or "") for k in ("folio", "cliente", "usina", "ativo", "descricao", "status")) + " " + l["_etiqueta"]).lower()
    pessoa_sel = "TODOS" if id_account == "TODOS" else (str(id_account) if isinstance(id_account, int) else (str(eu) if eu is not None else ""))
    return render_template("historico.html", conta=_conta(), aba="hist", linhas=linhas, modo=modo, de=de, ate=ate, busca=busca, erro=erro,
                           cols=(COLS_COS if modo == "cos" else COLS), datas=DATAS, fmt=api.fmt_data_br,
                           labels=labels, pessoas=pessoas, pessoa_sel=pessoa_sel, etiqueta_sel=str(id_label or ""),
                           status_opts=list(api.WO_STATUS.values()), status_sel=status_sel, clientes=clientes,
                           usinas=sorted(usina_cli), usina_cli=usina_cli, tipos_ativo=tipos_ativo,
                           tipos_tarefa=sorted(set(tarefa_sel)), tarefa_sel=tarefa_sel)


@bp.route("/historico/meta")
@exige_sessao
def historico_meta():
    """Tipo de tarefa e datas da tarefa por OS, DEPOIS da lista (como o app: 3,5 s por 60 ids contra 0,7 s da página)."""
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
    det = api.get_os_detalhes(wid) or {}
    if not det.get("folio"):
        if parcial:
            return f'<p class="os-erro" style="padding:24px">Não achei a OS de id {wid} no Fracttal.</p>', 404
        return render_template("erro.html", conta=_conta(), aba="hist", mensagem=f"Não achei a OS de id {wid} no Fracttal."), 404
    status = request.args.get("status") or ""
    template = "os_detalhe_conteudo.html" if parcial else "os_detalhe.html"
    return render_template(template, conta=_conta(), aba="hist", d=det, wid=wid, status=status, parcial=parcial,
                           status_cor=STATUS_COR.get(status), fmt=api.fmt_data_br, duracao=api.duracao_os)

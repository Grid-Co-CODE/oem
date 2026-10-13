# os_creator/os_web/rotas_solic.py
"""Aba Solicitação / PCM na web — a criação do pedido e as quatro páginas do PCM: Painel, Fila do PCM, Histórico e Temas.

Espelha `steps/solicitacao.py` (criar), `steps/solic_pcm.py` (painel + fila), `steps/historico_solic.py` (histórico) e
`steps/temas.py` (temas), com o MESMO motor: `api.create_solicitacoes_bulk`, `api.list_minhas_solicitacoes`,
`api.aprovar_solicitacao`, `api.mudar_status_solicitacao`, `api.editar_observacao_solicitacao`,
`api.cancelar_solicitacao` e o `temas_store`. As regras que não são de rede estão em `solic_web.py`.

AS PÁGINAS SÃO AS DO APP (Levi, 13/10/2026: "Fila do PCM não está levando para a fila do PCM, referência é a fila do app
desktop, nem painel do PCM nem histórico nem temas"). Desde 21/09 a web juntava o painel e a fila numa tabela com um
painel de aprovação ("com menos estilo de dinamicidade"), o histórico era uma tabela sem filtro e os temas não existiam.
Agora: Painel = o kanban das três colunas; Fila = a lista à esquerda e a ficha à direita, com a OS nascendo na aprovação
e a fila passando para a próxima; Histórico = os filtros, a ficha, os anexos e o cancelar; Temas = o cadastro do PCM. A
barra de cima é a da `SolicPcmTab` ("‹ PCM", Nova solicitação, Painel, Fila do PCM, Histórico, Temas).

A LISTA É UMA SÓ, E FICA NA MEMÓRIA (o mesmo pedido: "Também está demorando demais para carregar!"). Cada abertura da
Fila fazia de 7 a 10 pedidos ao Fracttal, um depois do outro e sem memória nenhuma — as 400 solicitações, o pessoal de
100 em 100, as etiquetas, o catálogo de status —, e o Histórico baixava as mesmas 400 de novo. Agora Painel, Fila e
Histórico leem a MESMA lista, guardada por LISTA_TTL; os catálogos, por CATALOGO_TTL; a carga fria pede tudo ao mesmo
tempo (`_ao_mesmo_tempo`); e quem grava (criar, aprovar, status, observação, cancelar) esquece a lista: a próxima página
já a lê do Fracttal. O "Atualizar" de cada página força a releitura. A página do setor PCM pede a lista ao abrir
(`api_aquecer`), e a porta escolhida abre com ela pronta.

O CATÁLOGO DE ATIVOS NÃO VEM DO NAVEGADOR. O ativo da OS é resolvido no servidor por id_item/código
(`solic_web.asset_da`), nunca por nome: "Chave Seccionadora 1" existe em várias usinas, e casar por
nome já escolheu o ativo de outro cliente uma vez (solicitação 3534, em 02/09).
"""
from __future__ import annotations
import contextvars
import datetime as dt
import json
import os
import threading
import time

import requests
from flask import Blueprint, jsonify, redirect, render_template, request, url_for

import api
import solic_spec as sp
import temas_store as ts

from . import ativo_curto, sessao
from . import solic_web as sw
from . import tradicional_web as trad
from .rotas import _MEMO, _MEMO_LOCK, _conta, _memo, exige_sessao

bp = Blueprint("os_web_solic", __name__, url_prefix="/os")

LIMITE = 400            # o mesmo do painel do app (steps/solic_pcm.py: list_minhas_solicitacoes("TODOS", 400))
LISTA_TTL = 120         # s: a lista vale isto entre Painel, Fila e Histórico; quem grava a esquece antes
CATALOGO_TTL = 1800     # s: pessoal, etiquetas, status e tipos de tarefa — mudam de mês em mês
_LISTA = "solic_lista"


@bp.before_request
def _temas_em_dia():
    """Os temas que o PCM salva na tela de Temas do app valem para a Solicitação deste servidor: relê o banco quando a
    última leitura passou do TTL (o store nunca levanta — sem banco, fica o que já estava, e o código por baixo).

    Até 27/09/2026 a web lia só o `solic_spec`: tema novo não aparecia, e na aprovação um tema que só o banco tinha
    "não existia" — a OS nascia com as 3 subtarefas da base, sem erro nenhum."""
    ts.garantir()


# ── quem pode a Área PCM (a Fila do PCM e os Temas) ──────────────────────────────────────────────────────────────────
# Quem serve esta web pode fechar a Área PCM pondo a decisão no pedido: `request.environ["os_web.area_pcm"]` =
# {"pode": bool, "aviso": str}. O Nexus põe (`ponte.area_pcm`: só o setor PCM ou administrador — Levi, 13/10/2026: "Só
# o setor PCM ou administrador! Quem não é nenhum dos dois recebe a notificação!"): no lugar da tela vem o aviso, e as
# gravações da Fila e dos Temas voltam 403 com ele. Sem a chave — o OS Creator servido sozinho, o 5090 — a área fica
# aberta como sempre foi (no app ela pede a senha do PCM, `pcm_acesso`). O Painel, o Histórico e a Nova solicitação são
# a Área do Solicitante do app: ficam abertos.
AREA_PCM = "os_web.area_pcm"
AVISO_PCM = "A Fila do PCM e os Temas são da área do PCM."


def _area_pcm() -> dict:
    v = request.environ.get(AREA_PCM)
    return v if isinstance(v, dict) else {"pode": True, "aviso": ""}


def _sem_area_pcm_api():
    """A gravação da Área PCM pedida por quem não pode: 403 com o aviso (a tela o mostra no aviso de canto)."""
    a = _area_pcm()
    if a.get("pode", True):
        return None
    return jsonify({"erro": a.get("aviso") or AVISO_PCM, "area_pcm": False}), 403


def _sem_area_pcm_pagina(titulo: str, nav: str):
    """A página da Área PCM aberta por quem não pode: o aviso, com a barra de sempre (o Painel e o Histórico seguem)."""
    a = _area_pcm()
    if a.get("pode", True):
        return None
    return render_template("solic_sem_acesso.html", conta=_conta(), aba="solic", nav=nav, nav_pcm=sw.NAV_PCM,
                           titulo=titulo, aviso=a.get("aviso") or AVISO_PCM), 403


# ── a lista e os catálogos, na memória ───────────────────────────────────────────────────────────────────────────────
def _lista(forcar: bool = False) -> list:
    """As 400 solicitações mais novas (de todo mundo, como no app), já lidas pela `sw.linha`. Guardadas POR PESSOA: a
    lista vem com a sessão de quem pediu, e o que cada um vê é a permissão dele no Fracttal."""
    return _memo((_LISTA, sessao.email_atual() or ""), LISTA_TTL,
                 lambda: [sw.linha(s) for s in (api.list_minhas_solicitacoes("TODOS", LIMITE) or [])], forcar)


def _esquecer_lista() -> None:
    """Alguém gravou: a lista de TODO MUNDO fica velha (a solicitação mudou para todos)."""
    with _MEMO_LOCK:
        for k in [k for k in _MEMO if isinstance(k, tuple) and k and k[0] == _LISTA]:
            _MEMO.pop(k, None)


def _catalogo(nome: str, fn, padrao):
    """Um catálogo do Fracttal, guardado por CATALOGO_TTL. O erro não derruba a página (a Fila abre sem a lista de
    etiquetas, como no app) e não é guardado: a próxima página tenta de novo. Sessão caída sobe — é o login."""
    try:
        return _memo(("solic_cat", nome), CATALOGO_TTL, fn)
    except api.SessionExpired:
        raise
    except Exception:                                       # noqa: BLE001
        return padrao


def _pessoas() -> list:
    return _catalogo("pessoas", lambda: sorted(api.get_responsaveis() or [],
                                               key=lambda x: (x.get("name") or "").lower()), [])


def _etiquetas() -> list:
    return _catalogo("etiquetas", lambda: api.get_labels() or [], [])


def _tipos() -> dict:
    return _catalogo("tipos", lambda: api.get_tipos_classif() or {}, {})


def _status_cat() -> list:
    """[(id, código, rótulo)] do que o Fracttal aceita — sem os dois que a fila não deve oferecer.

    "Aberta" e "Pendente" são o estado de quem ESTÁ na fila; oferecê-los como ação só produziria
    uma mudança de status que não muda nada."""
    cat = _catalogo("status", lambda: api.status_solicitacao_catalogo() or [], list(api.STATUS_SOLICITACAO))
    return [t for t in cat if t[1] not in ("OPEN_STATUS", "REQUEST_TODO")]


def _ao_mesmo_tempo(*fns) -> list:
    """As leituras de uma página ao mesmo tempo: a carga fria custa a mais lenta delas, não a soma. Cada uma passa pela
    memória (a quente, volta na hora). O executor do `api` leva a sessão do Fracttal de quem pediu para as threads."""
    with api._ExecutorComContexto(max_workers=len(fns)) as ex:
        futuros = [ex.submit(f) for f in fns]
    return [f.result() for f in futuros]


# ── o catálogo de ativos do disco, sem esperar ──────────────────────────────────────────────────────────────────────
_DISCO = {"mtime": None, "idx": None, "vence": 0.0}
_DISCO_LOCK = threading.Lock()
_RENOVANDO = threading.Lock()
_TENTOU = {"quando": 0.0}
_ESPERA_TENTATIVA = 600          # s entre duas renovações por trás que falharam (sessão caída, rede fora)


def _indice_ativos() -> dict:
    """O catálogo de ativos do DISCO como estiver — mesmo vencido (as 24 h do `api.ASSETS_TTL`) —, reduzido ao que as
    páginas do PCM precisam: o tipo de cada ativo por id e por código (a ficha da Fila: o ativo existe? as subtarefas do
    tema mudam com o tipo) e a contagem por tipo (o combo dos Temas). Ele também dá nome às solicitações (`api._code_loc`,
    que a lista usa) antes de a lista ser pedida.

    Por que não o `api.load_assets_cached()`: vencido, ele baixa os ~22 mil ativos de novo NA HORA, de 200 em 200 — mais
    de cem pedidos ao Fracttal, a página parada por minutos (a 1ª Fila do dia). Para nomear e contar, o de ontem serve;
    vencido, ele é renovado por trás (`_renovar_por_tras`). Quem RESOLVE o ativo da OS continua lendo o catálogo em dia
    (`_catalogo_para_aprovar`)."""
    vazio = {"por_id": {}, "por_code": {}, "tipos": []}
    try:
        mtime = os.path.getmtime(api.ASSETS_CACHE)
    except OSError:
        return vazio                 # nenhum catálogo nesta máquina: a lista segue o caminho normal (baixa uma vez)
    with _DISCO_LOCK:
        if _DISCO["mtime"] != mtime:
            try:
                with open(api.ASSETS_CACHE, encoding="utf-8") as f:
                    bruto = json.load(f) or {}
                ativos = api._corrigir_itens_usina_estrangeiros(bruto.get("assets") or [])
            except Exception:                               # noqa: BLE001 — arquivo pela metade (sendo gravado)
                return _DISCO["idx"] or vazio
            por_id, por_code = {}, {}
            for a in ativos:
                tipo = a.get("tipo") or ""
                if a.get("id") is not None:
                    por_id.setdefault(a["id"], tipo)
                code = str(a.get("code") or "").strip()
                if code:
                    por_code.setdefault(code, tipo)
                    if code not in api._code_loc:
                        api._code_loc[code] = (a.get("cliente") or "", api._usina_curta(a.get("usina") or ""), tipo)
            vence = float(bruto.get("ts") or 0) + api.ASSETS_TTL if bruto.get("ver") == api._CACHE_VER else 0.0
            _DISCO.update(mtime=mtime, vence=vence,
                          idx={"por_id": por_id, "por_code": por_code, "tipos": sw.tipos_de_ativo(ativos)})
        idx, vence = _DISCO["idx"], _DISCO["vence"]
    if time.time() > vence:
        _renovar_por_tras()
    return idx


def _renovar_por_tras() -> None:
    """Baixa o catálogo vencido numa thread, com a sessão de quem abriu a página (a cópia do contexto leva o JWT). Uma
    por vez, e a que falhou só tenta de novo depois de `_ESPERA_TENTATIVA`."""
    if time.time() - _TENTOU["quando"] < _ESPERA_TENTATIVA or not _RENOVANDO.acquire(blocking=False):
        return
    _TENTOU["quando"] = time.time()
    ctx = contextvars.copy_context()

    def rodar():
        try:
            ctx.run(api.load_assets_cached, True)
            _TENTOU["quando"] = 0.0
        except Exception:                                   # noqa: BLE001 — fica o do disco; a próxima página tenta
            pass
        finally:
            _RENOVANDO.release()
    threading.Thread(target=rodar, name="os_web-catalogo", daemon=True).start()


def _catalogo_para_aprovar() -> list:
    """O catálogo COMPLETO, para resolver o ativo da OS: em dia, do disco. Vencido e já sendo baixado por trás, espera
    esse download em vez de começar outro."""
    if _RENOVANDO.acquire(timeout=240):
        _RENOVANDO.release()
    return api.load_assets_cached()


def _tipo_do_ativo(s: dict, idx: dict):
    """O tipo do ativo da solicitação no catálogo — ou None quando não há certeza. Só id e código, como o `asset_da`."""
    if s.get("id_item") is not None and s["id_item"] in idx["por_id"]:
        return idx["por_id"][s["id_item"]]
    code = str(s.get("code") or "").strip()
    return idx["por_code"].get(code) if code else None


def _ficha(s: dict, idx: dict, agora) -> dict:
    tipo = _tipo_do_ativo(s, idx)
    return sw.ficha(s, {"tipo": tipo} if tipo is not None else None, agora)


# ── criar a solicitação ──────────────────────────────────────────────────────────────────────
@bp.route("/solicitacao")
@exige_sessao
def solicitacao():
    """O formulário. A cascata (cliente→usina→ativo) usa o catálogo cacheado, como o app."""
    assets = api.load_assets_cached()
    try:
        tipos = api.get_request_types() or {}
    except api.FracttalError:                       # a tela abre mesmo sem o catálogo de classificação:
        tipos = {}                                  # a pessoa recarrega, em vez de levar um erro na cara
    pessoas = _pessoas()                            # "técnico sugerido" é opcional: sem a lista, a tela abre
    agora = trad.agora_brt()
    return render_template(
        "solic.html", conta=_conta(), aba="solic", clientes=trad.clientes(assets),
        todos_cliente=trad.TODOS_CLIENTE, todos_usina=trad.TODOS_USINA, todos_tipo=trad.TODOS_TIPO,
        grupos=tipos.get("grupo") or [], c1=tipos.get("classif1") or [], c2=tipos.get("classif2") or [],
        temas=sw.temas_para_tela(), pessoas=pessoas,
        agora=agora.strftime("%Y-%m-%dT%H:%M"),
        # +2 dias: o mesmo default da data sugerida no app (`SolicitacaoTab.reset`)
        sugerida=(agora.replace(hour=8, minute=0) + dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"))


@bp.route("/api/solic/subtarefas")
@exige_sessao
def api_subtarefas():
    """As subtarefas que o tema traz — a lista que o supervisor (e o PCM, na Fila) pode editar antes de enviar."""
    tema = (request.args.get("tema") or "").strip()
    tipo_ativo = (request.args.get("tipo") or "").strip()
    subs = sw.subtarefas_do_tema(tema, tipo_ativo)
    return jsonify({"tema": tema, "subtarefas": sp.de_api(subs), "n": len(subs)})


@bp.route("/api/solic/criar", methods=["POST"])
@exige_sessao
def api_criar():
    corpo = request.get_json(silent=True) or {}
    erro = sw.validar_criar(corpo)
    if erro:
        return jsonify({"erro": erro}), 400
    assets = api.load_assets_cached()
    por_code = {str(a.get("code") or ""): a for a in assets}
    escolhidos = [por_code[c] for c in (corpo.get("ativos") or []) if c in por_code]
    if not escolhidos:
        return jsonify({"erro": sw.ERRO_SEM_ASSET}), 400
    obs = sw.observacao(corpo.get("observacao") or "", corpo.get("tema") or "",
                        corpo.get("tecnico") or "", corpo.get("data_sugerida") or "",
                        corpo.get("subtarefas") or [])
    desc = str(corpo.get("descricao") or "").strip()
    campos = dict(id_type=corpo.get("grupo") or None, id_type_2=corpo.get("classif2") or None,
                  observation=obs, date_incident=sw.data_brt(corpo.get("data")),
                  is_urgent=bool(corpo.get("urgente")),
                  desc_type_1=corpo.get("classif1_txt") or "", desc_type=corpo.get("grupo_txt") or "",
                  desc_type_2=corpo.get("classif2_txt") or "")
    if sw.MARCA_ATIVO in desc:
        # "[Ativo] - Motivo" (27/09): uma chamada por ativo, cada uma com o nome DELE no título — a de lote repete a
        # mesma descrição em todas. As frases do tipo são as do Histórico (mesma memória de 1 h).
        frases = _memo(("frases_ativo",), 3600, lambda: ativo_curto.frases(api._read_asset_cache() or []))
        res = []
        for a in escolhidos:
            res += api.create_solicitacoes_bulk([a], sw.titulo_do_ativo(desc, a, frases), corpo.get("classif1"), **campos)
    else:
        res = api.create_solicitacoes_bulk(escolhidos, desc, corpo.get("classif1"), **campos)
    _esquecer_lista()
    return jsonify(sw.mensagem_bulk(res))


# ── o painel ────────────────────────────────────────────────────────────────────────────────
@bp.route("/solicitacao/painel")
@exige_sessao
def painel():
    """O Painel (`_Painel`): o kanban das três colunas, até 40 cartões em cada uma (a contagem diz o total), com a busca
    na própria tela. O cartão inteiro abre a Fila nele: pendente para analisar, das outras colunas só para ler."""
    _indice_ativos()
    lista = _lista(request.args.get("atualizar") == "1")
    cartoes = {c: [] for c, _r, _a in sw.COLUNAS}
    fora = []
    for s in lista:
        c = s.get("_coluna")
        if c in cartoes:
            cartoes[c].append(sw.cartao(s))
        else:                     # devolvidas para refazer: fora do quadro, só a contagem (e a busca as conta também)
            fora.append(sw.cartao(s)["busca"])
    return render_template("solic_painel.html", conta=_conta(), aba="solic", nav="painel", nav_pcm=sw.NAV_PCM,
                           colunas=sw.COLUNAS, cartoes=cartoes, fora=fora, por_coluna=sw.POR_COLUNA,
                           # fora da Área PCM o cartão abre a ficha da solicitação no Histórico, e não a Fila
                           pode_pcm=bool(_area_pcm().get("pode", True)))


# ── a fila do PCM ───────────────────────────────────────────────────────────────────────────
@bp.route("/solicitacao/fila")
@exige_sessao
def fila():
    """A Fila do PCM (`_Fila`): as pendentes à esquerda, a ficha da escolhida à direita — o pedido, a decisão, o tema e as
    subtarefas —, e a OS nascendo na aprovação. `?sel=<nº>` abre nela; se ela já saiu da fila (o Painel abriu uma
    em andamento ou finalizada), ela entra no fim da lista SÓ PARA LER, como o `set_somente_leitura` do app."""
    negado = _sem_area_pcm_pagina("Fila do PCM", "fila")
    if negado:
        return negado
    idx = _indice_ativos()
    forcar = request.args.get("atualizar") == "1"
    lista, pessoas, etiquetas, tipos, status = _ao_mesmo_tempo(lambda: _lista(forcar), _pessoas, _etiquetas, _tipos,
                                                               _status_cat)
    pend = [s for s in lista if s.get("_coluna") == sw.PENDENTE]
    sel = (request.args.get("sel") or "").strip()
    leitura = ""
    if sel and not any(str(s.get("id_code")) == sel for s in pend):
        alvo = next((s for s in lista if str(s.get("id_code")) == sel), None)
        if alvo is not None:
            pend, leitura = pend + [alvo], sel
        else:
            sel = ""
    agora = dt.datetime.now(dt.timezone.utc)
    fichas = [_ficha(s, idx, agora) for s in pend]
    return render_template(
        "solic_fila.html", conta=_conta(), aba="solic", nav="fila", nav_pcm=sw.NAV_PCM,
        fichas=fichas, sel=sel, leitura=leitura,
        n_hoje=sum(1 for f in fichas if f["hoje"] and str(f["id"]) != leitura),
        # o id do responsável é o id_personnel do api.get_responsaveis (= id_responsible da OS, como no app)
        pessoas=[{"id": p.get("id_personnel"), "nome": p.get("name") or ""} for p in pessoas if p.get("id_personnel")],
        etiquetas=[{"id": e.get("id"), "nome": e.get("description") or ""} for e in etiquetas if e.get("id")],
        tipos=[t.get("description") for t in (tipos.get("tipos") or []) if t.get("description")],
        cl1=[t.get("description") for t in (tipos.get("c1") or []) if t.get("description")],
        cl2=[t.get("description") for t in (tipos.get("c2") or []) if t.get("description")],
        status=[{"id": i, "cod": cod, "rot": rot} for i, cod, rot in status],
        temas=sw.temas_da_fila(), tipos_sub=sw.TIPOS_SUB, tipo_padrao=sw.TIPO_PADRAO,
        classif1_padrao=sw.CLASSIF1_PADRAO, nenhuma=sw.SEM_CLASSIF, etiqueta_perf=sp.ETIQUETA_PERFORMANCE)


@bp.route("/api/solic/<id_code>")
@exige_sessao
def api_detalhe(id_code):
    """Uma solicitação lida do Fracttal NA HORA (a que não está na lista: o Histórico busca pelo nº)."""
    row = api._solicitacao_row(id_code)
    if not row:
        return jsonify({"erro": "Não achei a solicitação nº %s." % id_code}), 404
    s = sw.linha(api._req_row_to_d(row, api._code_to_loc()))
    tipo = _tipo_do_ativo(s, _indice_ativos())
    subs = s.get("_subs") or sp.de_api(sw.subtarefas_do_tema(s.get("_tema") or "", tipo or ""))
    return jsonify(dict(
        sw.linha_hist(s), id_code=s.get("id_code"), descricao=s.get("descricao_full") or s.get("descricao"),
        ativo_curto=s.get("_ativo"), relato=s.get("_relato"), tema=s.get("_tema"), tema_nome=s.get("_tema_nome"),
        tecnico=s.get("_tecnico"), data_sugerida=s.get("_data_sug"), coluna=s.get("_coluna"),
        subtarefas=subs, ativo_ok=tipo is not None, ativo_aviso="" if tipo is not None else sw.ERRO_SEM_ASSET))


@bp.route("/api/solic/<id_code>/aprovar", methods=["POST"])
@exige_sessao
def api_aprovar(id_code):
    """Vira OS numerada (`_Fila._aprovar`). O ativo é resolvido AQUI, e não enviado pela tela (ver o topo do módulo); o
    título, as subtarefas (com o anexo), o tipo, as classificações, as etiquetas e a OS pai são os da ficha."""
    negado = _sem_area_pcm_api()
    if negado:
        return negado
    corpo = request.get_json(silent=True) or {}
    if not corpo.get("id_responsible"):
        return jsonify({"erro": "Escolha o responsável pela OS. Sem responsável a tarefa é criada "
                                "mas NÃO vira OS numerada — ela fica pendente no kanban do "
                                "Fracttal e ninguém a vê."}), 400
    row = api._solicitacao_row(id_code)
    if not row:
        return jsonify({"erro": "Não achei a solicitação nº %s." % id_code}), 404
    s = sw.linha(api._req_row_to_d(row, api._code_to_loc()))
    asset = sw.asset_da(s, _catalogo_para_aprovar())
    if not asset:
        return jsonify({"erro": sw.ERRO_SEM_ASSET}), 400
    # a lista da TELA (o PCM pode ter editado); a tela que esvaziou a lista leva a base, como o app
    # (`editor_subs.para_api() or sp.subtarefas_base()`); sem a chave (quem chama sem a ficha), as do tema
    subs = corpo.get("subtarefas")
    if subs is None:
        subs = sw.subtarefas_do_tema(s.get("_tema") or "", asset.get("tipo") or "")
    else:
        subs = sw.subs_para_api(subs) or sp.subtarefas_base()
    titulo = str(corpo.get("titulo") or corpo.get("descricao") or s.get("descricao_full") or "").strip()
    try:
        id_parent = int(corpo.get("id_parent")) if corpo.get("id_parent") not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"erro": "OS pai inválida: escolha a OS na lista que aparece ao digitar o número."}), 400
    res = api.aprovar_solicitacao(
        asset, titulo, subs, s.get("id_code"), corpo.get("id_responsible"), corpo.get("responsavel") or "",
        tipo=corpo.get("tipo") or sw.TIPO_PADRAO, note=str(s.get("observacao") or ""),
        etiqueta_ids=corpo.get("etiquetas") or None, id_parent=id_parent,
        classif=(corpo.get("classif1") or "", corpo.get("classif2") or ""))
    out = sw.mensagem_aprovacao(res, id_code)
    if out.get("ok") or (res or {}).get("ok"):
        _esquecer_lista()              # nasceu OS (ou a tarefa): a solicitação saiu da fila para todo mundo
    return (jsonify(out), 200) if out.get("ok") else (jsonify({"erro": out["mensagem"]}), 400)


@bp.route("/api/solic/<id_code>/status", methods=["POST"])
@exige_sessao
def api_status(id_code):
    """Mudar o status / devolver ao supervisor. O MOTIVO é obrigatório aqui, e no Fracttal não é.

    É escolha, a mesma do app: status trocado sem motivo vira o tipo de registro que ninguém
    consegue explicar três meses depois."""
    negado = _sem_area_pcm_api()
    if negado:
        return negado
    corpo = request.get_json(silent=True) or {}
    motivo = str(corpo.get("motivo") or "").strip()
    if not motivo:
        return jsonify({"erro": "Escreva o motivo — ele fica no histórico da solicitação."}), 400
    codigo = str(corpo.get("codigo") or "").strip()
    alvo = next((t for t in api.STATUS_SOLICITACAO if t[1] == codigo), None)
    if not alvo:
        return jsonify({"erro": "Escolha um status da lista."}), 400
    api.mudar_status_solicitacao(id_code, alvo[0], alvo[1], motivo)
    _esquecer_lista()
    return jsonify({"ok": True, "status": alvo[2],
                    "mensagem": "A solicitação %s passou para “%s”." % (id_code, alvo[2])})


@bp.route("/api/solic/<id_code>/observacao", methods=["POST"])
@exige_sessao
def api_observacao(id_code):
    """Reescreve a observação MANTENDO o bloco [PCM] (`_Fila._gravar_obs`: relato + linha em branco + bloco).

    Gravar só o texto novo apagaria tema, técnico e subtarefas editadas — e a fila perderia a
    sugestão que justifica ela existir."""
    negado = _sem_area_pcm_api()
    if negado:
        return negado
    corpo = request.get_json(silent=True) or {}
    row = api._solicitacao_row(id_code)
    if not row:
        return jsonify({"erro": "Não achei a solicitação nº %s." % id_code}), 404
    bloco = sp.so_bloco(str(row.get("observation") or ""))
    relato = str(corpo.get("relato") or "").strip()
    api.editar_observacao_solicitacao(id_code, (relato + "\n\n" + bloco).strip() if bloco else relato)
    _esquecer_lista()
    return jsonify({"ok": True, "mensagem": "Observação da solicitação %s gravada no Fracttal." % id_code})


# ── histórico ────────────────────────────────────────────────────────────────────────────────
@bp.route("/solicitacao/historico")
@exige_sessao
def historico():
    """O Histórico (`HistoricoSolic`): tudo o que já passou pela fila — inclusive as "Reabertas (refazer)", que o painel
    esconde —, com os filtros do app (criado por, cliente, usina, tipo de ativo, status e período, que abre nos últimos
    30 dias), a busca, o exportar e a ficha de cada uma (`SolicitacaoDialog`). Os filtros rodam na tela."""
    _indice_ativos()
    lista = _lista(request.args.get("atualizar") == "1")
    hoje = dt.datetime.now(sw.BRT).date()
    return render_template("solic_hist.html", conta=_conta(), aba="solic", nav="hist", nav_pcm=sw.NAV_PCM,
                           linhas=[sw.linha_hist(s) for s in lista], busca=(request.args.get("busca") or "").strip(),
                           de=(hoje - dt.timedelta(days=30)).isoformat(), ate=hoje.isoformat())


@bp.route("/api/solic/historico")
@exige_sessao
def api_historico():
    """A lista do Histórico de novo do Fracttal, sem recarregar a página: o "↻" e a atualização de 15 em 15 minutos do
    app (`_auto_refresh`) mantêm os filtros que a pessoa marcou."""
    _indice_ativos()
    return jsonify({"linhas": [sw.linha_hist(s) for s in _lista(True)]})


@bp.route("/api/solic/<id_code>/anexos")
@exige_sessao
def api_anexos(id_code):
    """Os anexos da solicitação (a ficha do Histórico: Imagens × Documentos)."""
    return jsonify({"anexos": [{"nome": a.get("nome") or "arquivo", "url": a.get("url") or "", "imagem": bool(a.get("is_image"))}
                               for a in (api.get_solic_anexos(id_code) or [])]})


@bp.route("/api/solic/<id_code>/cancelar", methods=["POST"])
@exige_sessao
def api_cancelar(id_code):
    """"Cancelar solicitação" da ficha do Histórico (`cancelar_solic.py`): o status vai para Cancelada, com a nota
    (opcional). Quem autoriza é a conta da pessoa no Fracttal: sem permissão, ele recusa e a ficha mostra o motivo."""
    nota = str((request.get_json(silent=True) or {}).get("nota") or "").strip()
    api.cancelar_solicitacao(id_code, nota)
    _esquecer_lista()
    return jsonify({"ok": True, "mensagem": "Solicitação Nº %s cancelada." % id_code})


# ── temas ────────────────────────────────────────────────────────────────────────────────────
def _temas_da_tela(itens) -> list:
    return [sw.tema_para_tela(t) for t in (itens or [])]


@bp.route("/solicitacao/temas")
@exige_sessao
def temas():
    """Os Temas (`TemasTab`): a lista à esquerda, o cadastro à direita, salvar por tema e arquivar em vez de excluir. Lê o
    BANCO na hora, como o app ao entrar na tela; com o banco fora mostra os temas do código, avisando, e não grava."""
    negado = _sem_area_pcm_pagina("Temas", "temas")
    if negado:
        return negado
    idx = _indice_ativos()
    erro = ""
    try:
        itens = ts.do_banco()
        if not itens:
            itens, erro = ts.da_semente(), "O banco ainda não tem temas — mostrando os do app."
    except Exception as e:                                  # noqa: BLE001
        itens, erro = ts.da_semente(), "Erro ao carregar do banco: %s — mostrando os temas do app." % str(e)[:140]
    nomes = sorted({str(e.get("description") or "").strip() for e in _etiquetas()} - {""}, key=str.lower)
    return render_template("solic_temas.html", conta=_conta(), aba="solic", nav="temas", nav_pcm=sw.NAV_PCM,
                           temas=_temas_da_tela(itens), erro=erro, etiquetas=nomes, tipos=idx["tipos"],
                           tipos_os=sw.TIPOS_OS, classif1=sw.CLASSIF1_TEMA, tipos_sub=sw.TIPOS_SUB,
                           pode_gravar=ts.pode_gravar())


def _depois_de_gravar_tema():
    """O tema gravado vale NA HORA neste servidor (Nova solicitação e Fila), e a tela recebe a lista do banco. Relê do
    banco e aplica só o que veio dele: a semente por cima, por uma queda de rede logo depois de gravar, desfaria os temas
    do PCM em memória (o `garantir` acerta na próxima janela)."""
    try:
        itens = ts.do_banco()
    except Exception:                                       # noqa: BLE001
        return None
    if itens:
        ts.aplicar_no_spec(itens)
    _esquecer_lista()                                       # o nome do tema mora em cada linha da lista
    return _temas_da_tela(itens)


def _erro_banco(e):
    if isinstance(e, PermissionError):
        return jsonify({"erro": str(e)}), 403
    return jsonify({"erro": "O banco da Gridco não respondeu: %s" % str(e)[:160]}), 502


@bp.route("/api/solic/temas/salvar", methods=["POST"])
@exige_sessao
def api_tema_salvar():
    """"Salvar tema" (`TemasTab._salvar`): nome obrigatório, a chave nasce do nome e nunca muda depois, nome repetido
    não entra. RELÊ o banco antes (o `temas_store.salvar` acha a linha pela chave, nunca pelo número da linha)."""
    negado = _sem_area_pcm_api()
    if negado:
        return negado
    try:
        atuais = ts.do_banco()
    except Exception as e:                                  # noqa: BLE001
        return _erro_banco(e)
    novo, erro = sw.tema_para_salvar(request.get_json(silent=True) or {}, atuais)
    if erro:
        return jsonify({"erro": erro}), 400
    try:
        ts.salvar(novo)
    except (PermissionError, requests.RequestException) as e:
        return _erro_banco(e)
    return jsonify({"ok": True, "chave": novo["chave"], "temas": _depois_de_gravar_tema(),
                    "mensagem": "salvo — vale para as próximas OS"})


@bp.route("/api/solic/temas/<chave>/arquivar", methods=["POST"])
@exige_sessao
def api_tema_arquivar(chave):
    """Arquivar (ou desarquivar): o tema some da escolha na Solicitação e na Fila, e as OS que já nasceram com ele não
    mudam. Excluir não existe — um tema usado em 751 solicitações não pode sumir."""
    negado = _sem_area_pcm_api()
    if negado:
        return negado
    on = bool((request.get_json(silent=True) or {}).get("arquivar", True))
    try:
        ts.arquivar(chave, on)
    except KeyError:
        return jsonify({"erro": "Esse tema não está no banco."}), 404
    except (PermissionError, requests.RequestException) as e:
        return _erro_banco(e)
    return jsonify({"ok": True, "chave": chave, "temas": _depois_de_gravar_tema(),
                    "mensagem": "arquivado — some da escolha na Solicitação e na Fila" if on else "desarquivado"})


# ── atualizar e aquecer ──────────────────────────────────────────────────────────────────────
@bp.route("/solicitacao/atualizar")
@exige_sessao
def atualizar():
    """Recarrega o CATÁLOGO DE ATIVOS e volta à Fila (o aviso "não consegui identificar o ativo" da ficha leva aqui).
    Existe porque a causa mais comum desse aviso é catálogo velho — um ativo cadastrado hoje de manhã. Se o catálogo já
    está sendo baixado por trás, espera esse em vez de baixar duas vezes."""
    negado = _sem_area_pcm_pagina("Fila do PCM", "fila")
    if negado:
        return negado
    ja_baixando = _RENOVANDO.locked()
    if _RENOVANDO.acquire(timeout=300):
        try:
            if not ja_baixando:
                api.load_assets_cached(True)
        finally:
            _RENOVANDO.release()
    _esquecer_lista()
    return redirect(url_for("os_web_solic.fila", sel=request.args.get("sel") or "", atualizar=1))


@bp.route("/api/solic/aquecer", methods=["POST"])
@exige_sessao
def api_aquecer():
    """A página do setor PCM pede isto ao abrir: a lista e os catálogos chegam à memória enquanto a pessoa escolhe a
    porta, e o Painel, a Fila ou o Histórico abrem já com eles."""
    _indice_ativos()
    _ao_mesmo_tempo(_lista, _pessoas, _etiquetas, _tipos, _status_cat)
    return ("", 204)

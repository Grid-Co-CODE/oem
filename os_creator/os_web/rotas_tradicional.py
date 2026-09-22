# os_creator/os_web/rotas_tradicional.py
"""Card Tradicional na web — Criar OS do zero, passo a passo: o wizard do `app.py` (Step1 → Step2 → Step3 → ResponsavelDialog)
numa página só, com os quatro passos como cards numerados (o 4º é o diálogo do responsável, como no app).

O motor é o mesmo do desktop: `api.load_assets_cached` (catálogo), `api.get_tipos_classif` (tipo/classificações),
`api.get_labels` (etiquetas), `api.buscar_os_pai` (OS pai) e, na escrita, `api.create_work_orders_bulk` (uma OS por ativo)
ou `api.create_work_orders_agrupada` (uma OS com várias tarefas) — com o payload montado por `tradicional_web.montar_payload`
nos mesmos argumentos do `ResponsavelDialog._gerar`. O responsável vem de `/os/api/responsaveis` (rotas.py), a mesma lista
que a Performance já usa. As imagens por ativo chegam em multipart e são repassadas em bytes, como o app manda em
`imagens_por_ativo`."""
from __future__ import annotations
import datetime as dt
import json

from flask import Blueprint, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

import api

from . import tradicional_web as trad
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_tradicional", __name__, url_prefix="/os")

ERRO_TAMANHO = "As imagens somam mais de 4 MB — envie menos imagens por vez (ou reduza o tamanho delas)."


@bp.route("/tradicional")
@exige_sessao
def tradicional():
    assets = api.load_assets_cached()
    agora = trad.agora_brt()
    return render_template("tradicional.html", conta=_conta(), aba="criar", passos=trad.STEP_LABELS,
                           clientes=trad.clientes(assets), criticidades=api.CRITICIDADES, crit_default=api.CRITICIDADE_DEFAULT,
                           todos_cliente=trad.TODOS_CLIENTE, todos_usina=trad.TODOS_USINA, todos_tipo=trad.TODOS_TIPO, nenhuma=trad.NENHUMA,
                           agora=agora.strftime("%Y-%m-%dT%H:%M"),
                           programada=(agora + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))   # default do Step1: amanhã


@bp.route("/api/tradicional/catalogo")
@exige_sessao
def api_catalogo():
    """A cascata do Step 1 em três pedidos: sem parâmetro → clientes; ?cliente= → usinas; ?cliente=&usina= → tipos + ativos
    (o filtro por tipo e a busca são locais, em memória, como no app). ?recarregar=1 é o botão ↻ (load_assets_cached(force))."""
    force = request.args.get("recarregar") == "1"
    assets = api.load_assets_cached(True) if force else api.load_assets_cached()
    cliente = (request.args.get("cliente") or "").strip()
    usina = (request.args.get("usina") or "").strip()
    if usina:
        return jsonify({"cliente": cliente, "usina": usina, "tipos": trad.tipos_de(assets, cliente, usina),
                        "ativos": trad.ativos_de(assets, cliente, usina)})
    if cliente:
        return jsonify({"cliente": cliente, "usinas": trad.usinas_de(assets, cliente)})
    return jsonify({"clientes": trad.clientes(assets), "recarregado": force})


@bp.route("/api/tradicional/tipos")
@exige_sessao
def api_tipos():
    """Tipo de tarefa + Classificação 1/2 AO VIVO (TipoTarefaBox) e a criticidade fixa (5 níveis, default Médio)."""
    d = api.get_tipos_classif() or {}
    return jsonify({"tipos": d.get("tipos") or [], "c1": d.get("c1") or [], "c2": d.get("c2") or [],
                    "criticidades": [{"id": i, "description": n} for n, i in api.CRITICIDADES],
                    "crit_default": api.CRITICIDADE_DEFAULT, "nenhuma": trad.NENHUMA})


@bp.route("/api/tradicional/etiquetas")
@exige_sessao
def api_etiquetas():
    return jsonify({"etiquetas": api.get_labels() or []})


@bp.route("/api/tradicional/os-pai")
@exige_sessao
def api_os_pai():
    """OsPaiPicker._buscar: digitou o nº → `api.buscar_os_pai(termo)`; vazio não busca."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"resultados": []})
    return jsonify({"resultados": api.buscar_os_pai(q) or []})


def _corpo_e_imagens() -> tuple[dict, dict]:
    """JSON puro quando não há anexo; multipart quando há: o campo `payload` traz o MESMO JSON e cada arquivo vem em
    `imagens:<code do ativo>` (vários por ativo). Os bytes seguem para `imagens_por_ativo` como o app manda."""
    if not (request.mimetype or "").startswith("multipart/"):
        return request.get_json(silent=True) or {}, {}
    try:
        corpo = json.loads(request.form.get("payload") or "{}")
    except ValueError:
        corpo = {}
    pares = []
    for chave in request.files:
        if not chave.startswith("imagens:"):
            continue
        code = chave.split(":", 1)[1]
        for f in request.files.getlist(chave):
            dados = f.read()
            if dados:
                pares.append((code, f.filename or "imagem.png", dados))
    return corpo if isinstance(corpo, dict) else {}, trad.agrupar_imagens(pares)


@bp.route("/api/tradicional/criar", methods=["POST"])
@exige_sessao
def api_criar():
    corpo, imagens = _corpo_e_imagens()
    modo, args, kwargs, erro = trad.montar_payload(corpo, api.load_assets_cached(), imagens)
    if erro:
        return jsonify({"erro": erro}), 400
    if modo == "agrupada":                                            # app.py:999 — "Agrupar em UMA OS com várias tarefas"
        return jsonify(trad.mensagem_agrupada(api.create_work_orders_agrupada(*args, **kwargs)))
    return jsonify(trad.mensagem_bulk(api.create_work_orders_bulk(*args, **kwargs)))   # app.py:1009 — uma OS por ativo


@bp.errorhandler(RequestEntityTooLarge)
def _upload_grande(_e):
    """MAX_CONTENT_LENGTH do app é 4 MB: a tela avisa antes, mas se passar, a resposta é JSON legível, não um 413 em HTML."""
    return jsonify({"erro": ERRO_TAMANHO}), 413

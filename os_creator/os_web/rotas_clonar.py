# os_creator/os_web/rotas_clonar.py
"""Clonar OS na web — espelho do `steps/clonar.py` (ClonarOSDialog) e da barra "Clonar OS nº" do `app.py`.

Lê a OS de referência com TODAS as tarefas (`api.get_os_para_clonar`), deixa trocar ativo/descrição/subtarefas e a
data/hora de cada tarefa, e cria UMA OS nova com `api.clonar_os` — os mesmos argumentos do `_criar` do app."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

import api

from . import clonar_web
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_clonar", __name__, url_prefix="/os")


def _catalogo() -> list:
    return api.load_assets_cached() or []


def _por_id(catalogo: list) -> dict:
    return {a.get("id"): a for a in catalogo if a.get("id") is not None}


@bp.route("/clonar")
@exige_sessao
def clonar():
    folio = (request.args.get("folio") or "").strip()
    folio = folio if folio.isdigit() else ""
    try:
        pessoas = sorted(api.get_responsaveis() or [], key=lambda x: (x.get("name") or "").lower())
    except api.FracttalError:
        raise
    except Exception:                                   # noqa: BLE001 — a lista pode ser recarregada pela tela
        pessoas = []
    return render_template("clonar.html", conta=_conta(), aba="criar", folio=folio, pessoas=pessoas)


@bp.route("/api/clonar/os")
@exige_sessao
def api_os():
    folio = (request.args.get("folio") or "").strip()
    wid = api._wo_id_por_folio(folio) if folio.isdigit() else None
    if not wid:
        return jsonify({"erro": f"Não achei nenhuma OS com o nº {folio or '?'}."}), 404
    d = dict(api.get_os_para_clonar(wid) or {})
    catalogo = _catalogo()
    tarefas = []
    for t in (d.get("tarefas") or []):
        t = dict(t)
        t["event_date"] = clonar_web.data_local(t.get("event_date_orig"))
        t["candidatos"] = clonar_web.candidatos(t.get("asset"), catalogo)
        for s in (t.get("subtarefas") or []):
            if isinstance(s, dict):
                s.setdefault("_keep", True)
        tarefas.append(t)
    d.update(tarefas=tarefas, id_work_order=wid, folio=d.get("folio") or int(folio))
    return jsonify(d)


@bp.route("/api/clonar/modelo", methods=["POST"])
@exige_sessao
def api_modelo():
    """'Atualizar do modelo': re-seleciona no Fracttal o modelo de tarefa do mesmo nome p/ o ativo e devolve as
    subtarefas atuais (só leitura no Fracttal; quem aplica é a tela)."""
    corpo = request.get_json(silent=True) or {}
    asset = _por_id(_catalogo()).get(corpo.get("asset_id"))
    if not asset:
        return jsonify({"erro": "Selecione uma tarefa com ativo."}), 400
    r = dict(api.get_template_subtarefas(asset, corpo.get("descricao") or "") or {})
    if r.get("achou"):
        for s in (r.get("subtarefas") or []):
            s["_keep"] = True
    return jsonify(r)


@bp.route("/api/clonar/modelo-todas", methods=["POST"])
@exige_sessao
def api_modelo_todas():
    corpo = request.get_json(silent=True) or {}
    por_id = _por_id(_catalogo())
    tarefas = [clonar_web.completar_asset(dict(t), por_id) for t in (corpo.get("tarefas") or []) if isinstance(t, dict)]
    res = api.atualizar_modelos_subtarefas(tarefas) or []
    for r in res:
        if r and r.get("achou"):
            for s in (r.get("subtarefas") or []):
                s["_keep"] = True
    return jsonify({"resultados": res})


@bp.route("/api/clonar/criar", methods=["POST"])
@exige_sessao
def api_criar():
    corpo = request.get_json(silent=True) or {}
    prontas, erro = clonar_web.preparar_tarefas(corpo.get("tarefas") or [], _por_id(_catalogo()))
    if erro:
        return jsonify({"erro": erro}), 400
    idp = corpo.get("id_responsible")
    if not idp:
        return jsonify({"erro": "Escolha o responsável."}), 400
    nome = (corpo.get("responsible_name") or "").strip()
    eids = (corpo.get("etiqueta_ids") or None) if corpo.get("clonar_etiquetas") else None
    note = (corpo.get("note") or "").strip()
    res = api.clonar_os(prontas, idp, nome, eids, note)
    return jsonify(clonar_web.mensagem_resultado(res))

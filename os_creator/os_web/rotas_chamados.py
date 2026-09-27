# os_creator/os_web/rotas_chamados.py
"""Chamados na web — UM card, três portas: Inspeção de chamados, Acompanhamento de chamados (rotas_acomp.py) e
Controle de fornecedores (rotas_fornecedores.py). Levi, 27/09/2026: "quero que só tenha um card de chamados; quando eu
clicar vai aparecer Acompanhamento de chamados e Inspeção de chamados" — e, no mesmo dia, "crie mais um campo dentro de
chamados com o nome de controle de fornecedores".

A Inspeção é o `steps/insp_chamado.py` do app, clonado: as regras estão em `insp_web.py` (puro) e a escrita é a MESMA
função do app, `api.create_inspecao_chamado` — subtarefas do `chamado_insp_spec`, tipo Inspeção, classificação
Programada/Elétrica e a etiqueta "Aguardando Garantia".

O botão "Abrir chamado" do card da OS (Históricos) chega aqui com `?pai=<nº>`: a tela abre com o ATIVO, a DATA DO
INCIDENTE e o RESPONSÁVEL daquela OS, que vira a OS pai da inspeção. O atalho da aba Ativos chega com `?ativo=<id>`."""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

import api
import chamado_modelos_store as modelos

from . import insp_web as iw
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_chamados", __name__, url_prefix="/os")


@bp.before_request
def _modelos_em_dia():
    """Os modelos salvos no Controle de fornecedores valem para a inspeção deste servidor: relê o banco quando a
    última leitura passou do TTL (o store nunca levanta — sem banco, fica o que já estava, e o código por baixo)."""
    modelos.garantir()


def _cat() -> list:
    return iw.catalogo(api.load_assets_cached())


# ── o card e as três portas ─────────────────────────────────────────────────────────────────────
@bp.route("/chamados")
@exige_sessao
def chamados():
    return render_template("chamados.html", conta=_conta(), aba="criar")


@bp.route("/chamados/inspecao")
@exige_sessao
def inspecao():
    agora = iw.agora_brt()
    return render_template("insp.html", conta=_conta(), aba="criar", etiqueta=api.LABEL_INSPECAO,
                           agora=iw.para_input(agora), programada=iw.para_input(iw.amanha_8h(agora)),
                           pai=(request.args.get("pai") or "").strip(), ativo=(request.args.get("ativo") or "").strip(),
                           sem=dict(cli=iw.SEM_CLI, usi=iw.SEM_USI, tipo=iw.SEM_TIPO, ativo=iw.SEM_ATIVO,
                                    marca=iw.SEM_MARCA, pai=iw.SEM_PAI, previa=iw.SEM_PREVIA))


# endereços antigos: o atalho da aba Ativos apontava para /os/inspecao e o card da OS para /os/chamados/abrir, que
# nunca existiram — quem tiver a página aberta desde antes cai no lugar certo em vez de um 404
@bp.route("/inspecao")
@exige_sessao
def inspecao_antiga():
    return redirect(url_for("os_web_chamados.inspecao", **request.args.to_dict()))


@bp.route("/chamados/abrir")
@exige_sessao
def abrir_antigo():
    return redirect(url_for("os_web_chamados.inspecao", pai=(request.args.get("folio") or "").strip()))


# ── o que a tela pede enquanto a pessoa preenche ────────────────────────────────────────────────
@bp.route("/api/insp/catalogo")
@exige_sessao
def api_catalogo():
    """A cascata do app, aos pedaços: clientes → usinas do cliente → tipos e ativos da usina."""
    cat = _cat()
    cliente = (request.args.get("cliente") or "").strip()
    usina = (request.args.get("usina") or "").strip()
    if usina:
        return jsonify({"tipos": iw.tipos(cat, usina), "ativos": iw.ativos(cat, usina)})
    if cliente:
        return jsonify({"usinas": iw.usinas(cat, cliente)})
    return jsonify({"clientes": iw.clientes(cat)})


@bp.route("/api/insp/ativo/<id_item>")
@exige_sessao
def api_ativo(id_item):
    """Um ativo → a cascata que o seleciona (o `aplicar_ativo` do app)."""
    a = iw.ativo_por_id(_cat(), id_item)
    if not a:
        return jsonify({"erro": "Este ativo não tem modelo de inspeção de chamado."}), 404
    return jsonify(iw.cascata(a))


@bp.route("/api/insp/marcas")
@exige_sessao
def api_marcas():
    cat = _cat()
    a = iw.ativo_por_id(cat, request.args.get("ativo"))
    tipo = (request.args.get("tipo") or (a or {}).get("tipo") or "").strip()
    return jsonify(iw.marcas(a, tipo, cat))


@bp.route("/api/insp/subtarefas")
@exige_sessao
def api_subtarefas():
    return jsonify(iw.previa((request.args.get("tipo") or "").strip(), (request.args.get("marca") or "").strip()))


@bp.route("/api/insp/ultimas-os")
@exige_sessao
def api_ultimas_os():
    """As últimas 10 OS do ativo — o painel do botão "Últimas OS" (clicar numa vira a OS pai)."""
    id_item = (request.args.get("ativo") or "").strip()
    if not id_item:
        return jsonify({"linhas": []})
    linhas = api.ultimas_os_do_ativo(id_item, 10) or []
    for l in linhas:
        l["data_br"] = api.fmt_data_br(l.get("event_date")) or ""
        l["cor"] = iw.COR_STATUS.get(l.get("status") or "", "")
    return jsonify({"linhas": linhas})


@bp.route("/api/insp/pai")
@exige_sessao
def api_pai():
    """A OS pai: o que ela passa para a inspeção (data do incidente, responsável) e o ativo dela."""
    folio = (request.args.get("folio") or "").strip()
    if not folio:
        return jsonify({"texto": iw.SEM_PAI})
    try:
        d = api.get_os_detalhes_por_folio(folio)
    except Exception as e:                              # noqa: BLE001
        return jsonify({"erro": "não consegui ler essa OS: %s" % e}), 502
    if not d:
        return jsonify({"erro": "OS não encontrada — confira o número."}), 404
    try:
        pessoas = api.get_responsaveis() or []
    except Exception:                                   # noqa: BLE001 — sem a lista, herda só a data
        pessoas = []
    h = iw.herdar_do_pai(d, pessoas, data_painel=(request.args.get("data") or "").strip() or None)
    cat = _cat()
    a = iw.ativo_por_code(cat, d.get("code"))
    h["ativo"] = iw.cascata(a) if a else None
    h["aviso_ativo"] = iw.aviso_ativo_do_pai(d, cat)
    return jsonify(h)


@bp.route("/api/insp/criar", methods=["POST"])
@exige_sessao
def api_criar():
    kwargs, erro = iw.validar_criar(request.get_json(silent=True) or {}, _cat())
    if erro:
        return jsonify({"erro": erro}), 400
    try:
        r = api.create_inspecao_chamado(**kwargs)
    except Exception as e:                              # noqa: BLE001
        return jsonify({"erro": "Não consegui criar a OS: %s" % e}), 502
    return jsonify(dict(iw.mensagem_criou(r, api.LABEL_INSPECAO), ok=True, folio=r.get("wo_folio")))


@bp.route("/api/insp/confirmacao", methods=["POST"])
@exige_sessao
def api_confirmacao():
    """O texto da pergunta antes de criar, montado pelas MESMAS contas da criação (nº de subtarefas do modelo)."""
    corpo = request.get_json(silent=True) or {}
    cat = _cat()
    a = iw.ativo_por_id(cat, corpo.get("ativo"))
    marca = str(corpo.get("marca") or "").strip()
    if not a or not marca:
        return jsonify({"erro": iw.ERRO_ATIVO if not a else iw.ERRO_MARCA}), 400
    n = len(iw.ci.subtarefas(a.get("tipo"), marca))
    return jsonify({"texto": iw.confirmacao(n, a, marca, api.LABEL_INSPECAO)})

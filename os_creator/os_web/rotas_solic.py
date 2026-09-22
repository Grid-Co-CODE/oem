# os_creator/os_web/rotas_solic.py
"""Aba Solicitação / PCM na web — a criação do pedido, o painel, a fila do PCM e o histórico.

Espelha `steps/solicitacao.py` (criar), `steps/solic_pcm.py` (painel + fila) e
`steps/historico_solic.py` (histórico), com o MESMO motor: `api.create_solicitacoes_bulk`,
`api.list_minhas_solicitacoes`, `api.aprovar_solicitacao`, `api.mudar_status_solicitacao` e
`api.editar_observacao_solicitacao`. As regras que não são de rede estão em `solic_web.py`.

MENOS DINAMICIDADE, de propósito (Levi, 21/09): no app o painel é um quadro vivo com cartões que
se rearranjam, spinner por coluna e recarga automática. Aqui a página é renderizada pelo servidor
e recarrega quando alguém age. O único JS é a cascata cliente→usina→ativo (que reaproveita o
`/os/api/tradicional/catalogo`) e o painel de aprovação, que precisa buscar a solicitação. O resto
é formulário que faz POST e volta — é o que a fila do PCM realmente precisa fazer, e é o que
sobrevive a uma aba aberta a manhã inteira.

O CATÁLOGO DE ATIVOS NÃO VEM DO NAVEGADOR. O ativo da OS é resolvido no servidor por id_item/código
(`solic_web.asset_da`), nunca por nome: "Chave Seccionadora 1" existe em várias usinas, e casar por
nome já escolheu o ativo de outro cliente uma vez (solicitação 3534, em 02/09).
"""
from __future__ import annotations
import datetime as dt

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

import api
import solic_spec as sp

from . import solic_web as sw
from . import tradicional_web as trad
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_solic", __name__, url_prefix="/os")

LIMITE = 400            # o mesmo do painel do app (steps/solic_pcm.py: list_minhas_solicitacoes("TODOS", 400))


def _rows(busca: str = "") -> dict:
    """As solicitações já separadas pelas colunas do painel, cada uma com o bloco [PCM] lido."""
    cru = api.list_minhas_solicitacoes("TODOS", LIMITE) or []
    por = sw.separar([sw.linha(s) for s in cru], busca)
    return por


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
    try:
        pessoas = sorted(api.get_responsaveis() or [], key=lambda x: (x.get("name") or "").lower())
    except Exception:                               # noqa: BLE001 — "técnico sugerido" é opcional
        pessoas = []
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
    """As subtarefas que o tema traz — a lista que o supervisor pode editar antes de enviar."""
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
    res = api.create_solicitacoes_bulk(
        escolhidos, str(corpo.get("descricao") or "").strip(), corpo.get("classif1"),
        id_type=corpo.get("grupo") or None, id_type_2=corpo.get("classif2") or None,
        observation=obs, date_incident=sw.data_brt(corpo.get("data")),
        is_urgent=bool(corpo.get("urgente")),
        desc_type_1=corpo.get("classif1_txt") or "", desc_type=corpo.get("grupo_txt") or "",
        desc_type_2=corpo.get("classif2_txt") or "")
    return jsonify(sw.mensagem_bulk(res))


# ── o painel e a fila do PCM ─────────────────────────────────────────────────────────────────
@bp.route("/solicitacao/fila")
@exige_sessao
def fila():
    busca = (request.args.get("busca") or "").strip()
    ver = (request.args.get("ver") or sw.PENDENTE).strip()
    ver = ver if ver in (sw.PENDENTE, sw.ANDAMENTO, sw.FINALIZADA) else sw.PENDENTE
    por = _rows(busca)
    try:
        pessoas = sorted(api.get_responsaveis() or [], key=lambda x: (x.get("name") or "").lower())
    except Exception:                                       # noqa: BLE001
        pessoas = []
    try:
        d = api.get_tipos_classif() or {}
    except Exception:                                       # noqa: BLE001
        d = {}
    try:
        etiquetas = api.get_labels() or []
    except Exception:                                       # noqa: BLE001
        etiquetas = []
    return render_template(
        "solic_fila.html", conta=_conta(), aba="solic", busca=busca, ver=ver, por=por,
        colunas=sw.COLUNAS, itens=por.get(ver) or [], pessoas=pessoas, etiquetas=etiquetas,
        tipos=d.get("tipos") or [], cl1=d.get("c1") or [], cl2=d.get("c2") or [],
        tipo_padrao=sw.TIPO_PADRAO, classif1_padrao=sw.CLASSIF1_PADRAO, nenhuma=sw.SEM_CLASSIF,
        status_cat=_status_cat())


def _status_cat() -> list:
    """[(id, código, rótulo)] do que o Fracttal aceita — sem os dois que a fila não deve oferecer.

    "Aberta" e "Pendente" são o estado de quem ESTÁ na fila; oferecê-los como ação só produziria
    uma mudança de status que não muda nada."""
    try:
        cat = api.status_solicitacao_catalogo() or []
    except Exception:                                       # noqa: BLE001
        cat = list(api.STATUS_SOLICITACAO)
    return [t for t in cat if t[1] not in ("OPEN_STATUS", "REQUEST_TODO")]


@bp.route("/api/solic/<id_code>")
@exige_sessao
def api_detalhe(id_code):
    """A solicitação como o painel de aprovação precisa dela: ativo resolvido e subtarefas prontas.

    As subtarefas vêm do bloco [PCM] quando o supervisor as editou — respeitar essa edição é o
    motivo de o bloco existir; sem isso o PCM veria de novo a lista padrão do tema."""
    row = api._solicitacao_row(id_code)
    if not row:
        return jsonify({"erro": "Não achei a solicitação nº %s." % id_code}), 404
    s = sw.linha(api._req_row_to_d(row, api._code_to_loc()))
    asset = sw.asset_da(s, api.load_assets_cached())
    subs = s.get("_subs") or []
    if not subs:                                    # sem edição do supervisor: a lista do tema
        subs = sp.de_api(sw.subtarefas_do_tema(s.get("_tema") or "", (asset or {}).get("tipo") or ""))
    return jsonify({
        "id_code": s.get("id_code"), "descricao": s.get("descricao_full") or s.get("descricao"),
        "cliente": s.get("cliente"), "usina": s.get("usina"), "ativo": s.get("_ativo"),
        "relato": s.get("_relato"), "observacao": s.get("observacao"),
        "tema": s.get("_tema"), "tema_nome": s.get("_tema_nome"),
        "tecnico": s.get("_tecnico"), "data_sugerida": s.get("_data_sug"),
        "criado_por": s.get("criado_por"), "status": s.get("status"),
        "os_folio": s.get("os_folio"), "coluna": s.get("_coluna"),
        "subtarefas": subs, "ativo_ok": bool(asset),
        "ativo_aviso": "" if asset else sw.ERRO_SEM_ASSET})


@bp.route("/api/solic/<id_code>/aprovar", methods=["POST"])
@exige_sessao
def api_aprovar(id_code):
    """Vira OS numerada. O ativo é resolvido AQUI, e não enviado pela tela (ver o topo do módulo)."""
    corpo = request.get_json(silent=True) or {}
    if not corpo.get("id_responsible"):
        return jsonify({"erro": "Escolha o responsável pela OS. Sem responsável a tarefa é criada "
                                "mas NÃO vira OS numerada — ela fica pendente no kanban do "
                                "Fracttal e ninguém a vê."}), 400
    row = api._solicitacao_row(id_code)
    if not row:
        return jsonify({"erro": "Não achei a solicitação nº %s." % id_code}), 404
    s = sw.linha(api._req_row_to_d(row, api._code_to_loc()))
    asset = sw.asset_da(s, api.load_assets_cached())
    if not asset:
        return jsonify({"erro": sw.ERRO_SEM_ASSET}), 400
    subs = corpo.get("subtarefas")
    subs = sp.para_api(subs) if subs else sw.subtarefas_do_tema(s.get("_tema") or "", asset.get("tipo") or "")
    classif = (corpo.get("classif1") or sw.CLASSIF1_PADRAO, corpo.get("classif2") or "")
    res = api.aprovar_solicitacao(
        asset, str(corpo.get("descricao") or s.get("descricao_full") or "").strip(), subs,
        s.get("id_code"), corpo.get("id_responsible"), corpo.get("responsavel") or "",
        tipo=corpo.get("tipo") or sw.TIPO_PADRAO, note=str(s.get("observacao") or ""),
        etiqueta_ids=corpo.get("etiquetas") or None, id_parent=corpo.get("id_parent") or None,
        classif=classif)
    out = sw.mensagem_aprovacao(res, id_code)
    return (jsonify(out), 200) if out.get("ok") else (jsonify({"erro": out["mensagem"]}), 400)


@bp.route("/api/solic/<id_code>/status", methods=["POST"])
@exige_sessao
def api_status(id_code):
    """Recusar / cancelar / resolver sem OS. O MOTIVO é obrigatório aqui, e no Fracttal não é.

    É escolha, a mesma do app: status trocado sem motivo vira o tipo de registro que ninguém
    consegue explicar três meses depois."""
    corpo = request.get_json(silent=True) or {}
    motivo = str(corpo.get("motivo") or "").strip()
    if not motivo:
        return jsonify({"erro": "Escreva o motivo — ele fica no histórico da solicitação."}), 400
    codigo = str(corpo.get("codigo") or "").strip()
    alvo = next((t for t in api.STATUS_SOLICITACAO if t[1] == codigo), None)
    if not alvo:
        return jsonify({"erro": "Escolha um status da lista."}), 400
    api.mudar_status_solicitacao(id_code, alvo[0], alvo[1], motivo)
    return jsonify({"ok": True, "mensagem": "Solicitação %s marcada como %s." % (id_code, alvo[2])})


@bp.route("/api/solic/<id_code>/observacao", methods=["POST"])
@exige_sessao
def api_observacao(id_code):
    """Reescreve a observação MANTENDO o bloco [PCM].

    Gravar só o texto novo apagaria tema, técnico e subtarefas editadas — e a fila perderia a
    sugestão que justifica ela existir."""
    corpo = request.get_json(silent=True) or {}
    row = api._solicitacao_row(id_code)
    if not row:
        return jsonify({"erro": "Não achei a solicitação nº %s." % id_code}), 404
    atual = str(row.get("observation") or "")
    inteiro = (str(corpo.get("relato") or "").strip() + "\n" + sp.so_bloco(atual)).strip()
    api.editar_observacao_solicitacao(id_code, inteiro)
    return jsonify({"ok": True, "mensagem": "Observação da solicitação %s atualizada." % id_code})


# ── histórico ────────────────────────────────────────────────────────────────────────────────
@bp.route("/solicitacao/historico")
@exige_sessao
def historico():
    """Tudo o que já saiu da fila — inclusive as "Reabertas (refazer)", que o painel esconde."""
    busca = (request.args.get("busca") or "").strip()
    cru = [sw.linha(s) for s in (api.list_minhas_solicitacoes("TODOS", LIMITE) or [])]
    q = busca.lower()
    if q:
        cru = [s for s in cru if q in " ".join(str(s.get(k) or "") for k in
               ("id_code", "usina", "ativo", "descricao", "criado_por", "status", "os_folio")).lower()]
    return render_template("solic_hist.html", conta=_conta(), aba="solic", busca=busca,
                           itens=cru, fmt=api.fmt_data_br)


@bp.route("/solicitacao/atualizar")
@exige_sessao
def atualizar():
    """O ↻ da fila: recarrega o catálogo de ativos e volta. Existe porque a causa mais comum de
    "não consegui identificar o ativo" é catálogo velho — um ativo cadastrado hoje de manhã."""
    api.load_assets_cached(True)
    return redirect(url_for("os_web_solic.fila", busca=request.args.get("busca") or "",
                            ver=request.args.get("ver") or sw.PENDENTE))

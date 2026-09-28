# os_creator/os_web/rotas_cos.py
"""Card COS na web — a tela `steps/varias_os.py` (VariasOSsDialog) numa página, com os mesmos sete cards do app.

As rotas são finas de propósito: a regra mora em `cos_web` (sem Flask, testável) e o motor é o `api.py` do desktop,
dentro da sessão da pessoa. O que no app era worker vira pedido:

  /os/cos                 a tela (cos.html + cos.js)
  /os/api/cos/usinas      o combo Usina pela carteira (_fill_usinas)
  /os/api/cos/ativos      o `_on_usi`: cliente pela usina, usinas alvo, a poda dos marcados, os tipos e os candidatos
  /os/api/cos/preview     título, observação, "Registrada no Fracttal como", permissivo e fora de serviço (_preview)
  /os/api/cos/listas      tipos/classificações, as listas da falha (+ a sugestão) e os responsáveis — os três workers
                          do __init__; uma lista que falha não derruba as outras
  /os/api/cos/os-modelo   o clonador do COS (api.get_os_detalhes_por_folio)
  /os/api/cos/criar       o `_criar`: api.create_work_orders_bulk ou api.create_work_orders_datas, com os argumentos
                          posicionais do app

Erro do Fracttal sobe para o handler do app (`rotas._erro_fracttal`): 502 com a mensagem, ou 401 e volta ao login
quando a sessão caiu. Qualquer outro erro na criação vira 502 em JSON — o ApiWorker do app também mostra qualquer
exceção como mensagem, e uma página 500 em HTML deixaria o operador sem saber o que aconteceu com as OS."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

import api

from . import cos_web as cw
from . import sessao
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_cos", __name__, url_prefix="/os")


def _catalogo() -> list:
    return api.load_assets_cached() or []


def _cru(v):
    """O valor como veio, sem aparar: o nome da usina é a chave de junção com o catálogo e existe com espaço duplo
    ("Athon -  Timon 1 - MA", tests/test_os_web_option_value.py). Só o "vazio" é normalizado."""
    return v if isinstance(v, str) and v.strip() else None


def _texto_cru(nome: str):
    return _cru(request.args.get(nome))


def _json() -> dict:
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def _lista_ou_erro(nome: str, fn, erros: dict):
    """Um dos três workers do __init__: o erro dele fica no `erros` e as outras listas seguem. Sessão morta sobe — aí o
    certo é voltar ao login, não mostrar três listas vazias."""
    try:
        return fn()
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        erros[nome] = str(e)
    except Exception as e:                              # noqa: BLE001 — o worker do app mostra qualquer erro
        erros[nome] = str(e) or e.__class__.__name__
    return None


@bp.route("/cos")
@exige_sessao
def cos():
    return render_template("cos.html", conta=_conta(), aba="criar", **cw.contexto_pagina(_catalogo(), cw.agora_brt()))


@bp.route("/api/cos/usinas")
@exige_sessao
def api_usinas():
    cliente = _texto_cru("cliente")
    return jsonify({"usinas": cw.usinas_para(_catalogo(), cliente), "cliente": cliente or ""})


# A prévia e a cascata aceitam GET (query) e POST (o mesmo JSON do `estado` da tela). A tela usa POST: no modo várias
# usinas a maior carteira lista 12.291 ativos (medido no catálogo em 27/09), e um "Selecionar todos" ali poria milhares
# de ids na URL — acima do que o túnel aceita numa linha de pedido.
@bp.route("/api/cos/ativos", methods=["GET", "POST"])
@exige_sessao
def api_ativos():
    """usina, cliente, multi, marcados → {cliente, usinas, tipos, ativos, marcados} (o `_on_usi`)."""
    if request.method == "POST":
        d = _json()
        return jsonify(cw.alvo(_catalogo(), usina=_cru(d.get("usina")), cliente=_cru(d.get("cliente")),
                               multi=bool(d.get("multi")), marcados=cw.ler_ids(d.get("marcados") or [])))
    return jsonify(cw.alvo(_catalogo(), usina=_texto_cru("usina"), cliente=_texto_cru("cliente"),
                           multi=request.args.get("multi") == "1", marcados=cw.ler_ids(request.args.getlist("marcados"))))


@bp.route("/api/cos/preview", methods=["GET", "POST"])
@exige_sessao
def api_preview():
    try:
        st = (cw.estado(_json()) if request.method == "POST"
              else cw.estado_da_query({k: request.args.getlist(k) for k in request.args}))
    except cw.ErroTela as e:
        return jsonify({"erro": str(e)}), 400
    # o catálogo só entra quando há ativo marcado: sem ele (ou em usina de terceiros) a prévia não o consulta
    return jsonify(cw.preview(st, _catalogo() if (st.ids and not st.terceiros) else []))


@bp.route("/api/cos/listas")
@exige_sessao
def api_listas():
    """?so=classif,falhas,responsaveis (padrão: as três). A sugestão da falha e a severidade padrão vêm com as falhas."""
    so = {x.strip() for x in (request.args.get("so") or "").split(",") if x.strip()} or {"classif", "falhas", "responsaveis"}
    out, erros = {}, {}
    if "classif" in so:
        out["classif"] = _lista_ou_erro("classif", api.get_tipos_classif, erros) or {"tipos": [], "c1": [], "c2": []}
    if "falhas" in so:
        falhas = _lista_ou_erro("falhas", api.get_falha_listas, erros) or {"tipos": [], "causas": [], "metodos": []}
        out["falhas"] = falhas
        out["sugestoes"] = cw.sugestoes_falha(falhas)
        out["severidade_padrao"] = cw.SEVERIDADE_PADRAO
    if "responsaveis" in so:
        out["responsaveis"] = cw.ordenar_pessoas(_lista_ou_erro("responsaveis", api.get_responsaveis, erros) or [])
    out["erros"] = erros
    return jsonify(out)


@bp.route("/api/cos/os-modelo")
@exige_sessao
def api_os_modelo():
    """O clonador: o nº de uma OS do COS → o formulário remontado. O nº vai ao `api` como foi digitado (o app faz igual)."""
    num = (request.args.get("folio") or "").strip()
    if not num:
        return jsonify({"erro": cw.CLONE_VAZIO}), 400
    try:
        d = api.get_os_detalhes_por_folio(num)
    except api.FracttalError:
        raise
    except Exception as e:                              # noqa: BLE001 — o _clone_err do app mostra qualquer erro
        return jsonify({"erro": str(e) or e.__class__.__name__}), 502
    modelo, erro, status = cw.modelo_clone(d, _catalogo() if isinstance(d, dict) else [])
    if erro:
        return jsonify({"erro": erro}), status
    return jsonify(modelo)


def _classif_para_criar() -> dict:
    """As listas de tipo/classificação no momento da criação. Sem elas o `_tipo_dict` sai sem id_main e a criação para
    na frase "Os tipos ainda não carregaram…" — é o `_classif_err` do app."""
    try:
        return api.get_tipos_classif() or {}
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        return {}
    except Exception:                                   # noqa: BLE001
        return {}


def _falhas_para_criar() -> dict:
    try:
        return api.get_falha_listas() or {}
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        return {}
    except Exception:                                   # noqa: BLE001 — sem as listas, a validação da falha barra
        return {}


@bp.route("/api/cos/criar", methods=["POST"])
@exige_sessao
def api_criar():
    corpo = request.get_json(silent=True) or {}
    # as listas da falha só são lidas com "O ativo falhou?" marcado: é delas que saem as descrições do bloco
    trilho, args, erro = cw.criacao(corpo, _catalogo(), _classif_para_criar(),
                                    _falhas_para_criar() if cw.falha_marcada(corpo) else {})
    if erro:
        return jsonify({"erro": erro}), 400
    fn = api.create_work_orders_datas if trilho == cw.TRILHO_DATAS else api.create_work_orders_bulk
    try:
        res = fn(*args)
    except api.FracttalError:
        raise
    except Exception as e:                              # noqa: BLE001
        return jsonify({"erro": str(e) or e.__class__.__name__}), 502
    return jsonify(cw.mensagem_resultado(res))

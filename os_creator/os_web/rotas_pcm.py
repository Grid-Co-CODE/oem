# os_creator/os_web/rotas_pcm.py
"""Card PCM na web — a clonagem de planos, a `PcmTab` do app (steps/pcm.py): UMA OS com várias tarefas a partir dos
planos de tarefa do Fracttal (Handover, MPM, MPA, MPS, MPQ, MPW, MPT), cada ativo marcado vira uma tarefa.

/os/pcm é a tela — a porta "Clonagem de planos" do setor PCM (/os/setor/pcm) acende sozinha no dia em que esta rota
existe (`lancador.portas_vivas`). /os/api/pcm/* são os pedidos dela, na ordem do app: a cascata (usinas, ativos), o
"Carregar planos" (`api.get_plans_for_assets` + a contagem de subtarefas dos planos que as linhas mostram de saída), as
contagens sob demanda (o `_fetch_counts_visiveis` quando a pessoa troca a família ou o plano de uma linha), a OS pai
(`api.buscar_os_pai`, o OsPaiPicker) e a criação — `api.create_planned_os_multi` ou `api.create_os_sem_plano`, com o
payload de `pcm_web.montar_criacao`, nos mesmos argumentos do `_criar` / `_criar_sem_plano`. O responsável vem de
/os/api/responsaveis (rotas.py), a mesma lista da Performance e do Tradicional."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

import api

from . import pcm_web as pcm
from . import sessao
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_pcm", __name__, url_prefix="/os")


def _catalogo() -> list:
    return [a for a in (api.load_assets_cached() or []) if isinstance(a, dict)]


def _contagens(pares) -> dict:
    """{'subt': {id_task: n}, 'dur': {id_task: segundos}}. O `get_subtask_counts` roda em paralelo (tasks_details) e,
    de carona, guarda a duração de cada plano (`api.duracao_do_plano`) — é o tempo que a linha mostra.

    Falha aqui não derruba a tela: é o `_counts_err` do app, que só esquece o pedido, e a linha fica em "…". A sessão
    morta sobe, para a tela mandar a pessoa entrar de novo."""
    if not pares:
        return {"subt": {}, "dur": {}}
    try:
        d = api.get_subtask_counts(pares) or {}
    except api.FracttalError:
        if sessao.morta():
            raise
        d = {}
    except Exception:                                   # noqa: BLE001 — a contagem é informativa, como no app
        d = {}
    return {"subt": {str(k): v for k, v in d.items()}, "dur": {str(k): api.duracao_do_plano(k) for k in d}}


@bp.route("/pcm")
@exige_sessao
def pcm_tela():
    assets = _catalogo()
    return render_template("pcm.html", conta=_conta(), aba="criar",
                           clientes=pcm.clientes(assets), hoje=pcm.hoje_brt())


@bp.route("/api/pcm/usinas")
@exige_sessao
def api_usinas():
    # o nome vai como veio, sem strip: é a chave de junção com o catálogo (o `currentText()` do app)
    return jsonify({"usinas": pcm.usinas(_catalogo(), request.args.get("cliente") or "")})


@bp.route("/api/pcm/ativos")
@exige_sessao
def api_ativos():
    """Tipos + ativos da usina; o filtro por tipo e a busca são locais, na tela, como no `_refresh` do app."""
    assets = _catalogo()
    cliente, usina = request.args.get("cliente") or "", request.args.get("usina") or ""
    return jsonify({"tipos": pcm.tipos(assets, cliente, usina), "ativos": pcm.ativos(assets, cliente, usina)})


@bp.route("/api/pcm/planos")
@exige_sessao
def api_planos():
    """"Carregar planos" (`_carregar_planos` → `_set_planos` → `_fetch_counts_visiveis`). `ativos` = TODOS os marcados;
    `visiveis` = as linhas da tabela (o app só conta as subtarefas de quem está nela); `conhecidos` = os planos cuja
    contagem a tela já tem; `familia` = a do combo (sem ela, a primeira, como o app faz a cada carga)."""
    ids = set(pcm.parse_ids(request.args.get("ativos")))
    # o registro INTEIRO do catálogo, na ordem dele — é o `[a for a in self._assets if a["id"] in self._checked]` do app
    # (o id_group_task vai junto: é por ele que o task_events_list acha os planos do ativo)
    assets = [a for a in _catalogo() if a.get("id") in ids]
    if not assets:
        return jsonify({"erro": pcm.ERRO_SEM_ATIVO_PLANOS}), 400
    planos = api.get_plans_for_assets(assets) or []
    visiveis = set(pcm.parse_ids(request.args.get("visiveis"))) if "visiveis" in request.args else None
    corpo, pares = pcm.montar_planos(planos, [a.get("id") for a in assets], request.args.get("familia"),
                                     visiveis, pcm.parse_ids(request.args.get("conhecidos")))
    corpo.update(_contagens(pares))
    return jsonify(corpo)


@bp.route("/api/pcm/subtarefas")
@exige_sessao
def api_subtarefas():
    """Contagem sob demanda: `pares=id_task:id_ativo,...` — a pessoa trocou a família ou o plano de uma linha."""
    return jsonify(_contagens(pcm.parse_pares(request.args.get("pares"))))


@bp.route("/api/pcm/os-pai")
@exige_sessao
def api_os_pai():
    """OsPaiPicker._buscar: digitou o nº → `api.buscar_os_pai(termo)`; vazio não busca."""
    termo = (request.args.get("termo") or "").strip()
    if not termo:
        return jsonify({"resultados": []})
    return jsonify({"resultados": api.buscar_os_pai(termo) or []})


@bp.route("/api/pcm/criar", methods=["POST"])
@exige_sessao
def api_criar():
    modo, args, kwargs, erro = pcm.montar_criacao(request.get_json(silent=True) or {}, _catalogo())
    if erro:
        return jsonify({"erro": erro}), 400
    criar = api.create_os_sem_plano if modo == "sem_plano" else api.create_planned_os_multi
    return jsonify(pcm.mensagem_resultado(criar(*args, **kwargs)))

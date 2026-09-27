# os_creator/os_web/rotas_acomp.py
"""Acompanhamento de chamados — a porta do card de Chamados que faltava (Levi, 27/09/2026: "uma espécie de kanban
mostrando OSs que chegam, que a Singrid já escreveu número de tickets e OSs finalizadas! Ao clicar na OS abre uma tela
onde ela vê todas as informações do chamado daquele ativo e pode escrever observações").

DE ONDE VEM CADA COISA — nada aqui inventa estado:
- o quadro: as OS com a etiqueta CHAMADOS (`api.list_chamados`) que são OS de acompanhamento, e o nº do ticket de cada
  uma, que é a ÚNICA subtarefa dela (`api.tickets_os3_em_massa`);
- o ticket se grava NA subtarefa, pela mesma função do "fazer a tarefa" do card (`api.salvar_subtarefas`);
- finalizar é o Concluir do card, a mesma função (`api.concluir_os_checado`), com a reconferência da data de fim;
- as observações moram no banco da Gridco (`chamados_obs_store`), uma linha por observação, com a data do servidor.

A regra pura (colunas, tempo parado, a nota lida de volta) está em `acomp_web.py`."""
from __future__ import annotations

import datetime as dt

import requests
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

import api
import chamado_spec as cs
import chamados_obs_store as obs_store
import gridco_abas as ga

from . import acomp_web as aw
from . import rotas, sessao
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_acomp", __name__, url_prefix="/os")

TTL_QUADRO = 180          # s: a lista do Fracttal por pessoa — trocar de tela e voltar não busca de novo
DIAS_BUSCA = 365          # a primeira OS de acompanhamento é de ago/2026; um ano cobre as abertas com folga


def _quem() -> tuple:
    c = session.get("conta") or {}
    return (str(c.get("nome") or "").strip(), str(c.get("email") or "").strip())


def _dados(forcar: bool = False) -> dict:
    """A lista das OS de acompanhamento + o ticket de cada uma, na memória por TTL_QUADRO (por pessoa: a lista vem
    com a sessão dela no Fracttal)."""
    def _buscar():
        hoje = aw.agora_brt()
        de = (dt.date.today() - dt.timedelta(days=DIAS_BUSCA)).isoformat()
        linhas = [l for l in (api.list_chamados(de=de) or []) if aw.eh_os3(l)]
        ids = [l.get("id") for l in linhas if aw.precisa_ticket(l, hoje)]
        return {"linhas": linhas, "tickets": api.tickets_os3_em_massa(ids) if ids else {},
                "quando": hoje.strftime("%d/%m/%Y %H:%M")}
    return rotas._memo(("acomp", rotas._quem()), TTL_QUADRO, _buscar, forcar)


def _esquecer():
    """Depois de gravar ticket ou finalizar: a próxima leitura do quadro vai ao Fracttal (de todo mundo)."""
    with rotas._MEMO_LOCK:
        for k in [k for k in rotas._MEMO if isinstance(k, tuple) and k and k[0] == "acomp"]:
            rotas._MEMO.pop(k, None)


def _ultimas(forcar: bool = False) -> tuple:
    """({nº: última observação}, {nº: quando foi finalizada}, erro)."""
    try:
        if forcar:
            obs_store.listar(forcar=True)
        return obs_store.ultima_por_os(), obs_store.finalizado_por_os(), ""
    except Exception as e:                              # noqa: BLE001 — sem o banco, o quadro sai; só o "dias sem" usa a chegada
        return {}, {}, "Não consegui ler as observações no banco da Gridco (%s)." % str(e)[:120]


def _ler_quadro(forcar: bool = False) -> tuple:
    try:
        return _dados(forcar), None
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        return {"linhas": [], "tickets": {}, "quando": ""}, str(e)


@bp.route("/chamados/acompanhamento")
@exige_sessao
def quadro():
    forcar = request.args.get("atualizar") == "1"
    d, erro = _ler_quadro(forcar)
    ultimas, fins, erro_obs = _ultimas(forcar)
    q = aw.montar_quadro(d["linhas"], d["tickets"], ultimas, aw.agora_brt(), fins)
    return render_template("acomp.html", conta=_conta(), aba="criar", q=q, quando=d.get("quando") or "", erro=erro,
                           erro_obs=erro_obs, equipe=aw.equipe()[1])


@bp.route("/em-breve/chamados")
@exige_sessao
def em_breve_antigo():
    """O hub apontava para o "em breve" até 27/09 — quem tiver a página aberta cai no quadro."""
    return redirect(url_for("os_web_acomp.quadro"))


def _linha_de(d: dict, folio: int):
    return next((l for l in d["linhas"] if str(l.get("folio")) == str(folio)), None)


def _nota_da_os(det: dict, linha: dict) -> str:
    for txt in (det.get("notas") or "", (linha or {}).get("note") or ""):
        if aw.MARCA_NOTA in str(txt):
            return str(txt)
    return str(det.get("notas") or (linha or {}).get("note") or "")


@bp.route("/chamados/acompanhamento/<int:folio>")
@exige_sessao
def detalhe(folio):
    d, _erro = _ler_quadro()
    linha = _linha_de(d, folio)
    wid = (linha or {}).get("id") or api._wo_id_por_folio(folio)
    if not wid:
        return render_template("erro.html", conta=_conta(), aba="criar",
                               mensagem="Não achei a OS %s no Fracttal." % folio), 404
    det = api.get_os_detalhes(wid) or {}
    nota = _nota_da_os(det, linha)
    item = aw.item_do_ticket(det.get("subtarefas"))
    ticket = str((item or {}).get("resposta") or "").strip()
    if linha is None:                                  # fora da lista (mais velha que DIAS_BUSCA): o mínimo do detalhe
        linha = {"id": wid, "folio": folio, "note": nota, "descricao": det.get("descricao"), "ativo": det.get("ativo"),
                 "status_id": 3 if det.get("data_fim") else 1, "atribuido_a": det.get("responsavel")}
    try:
        obs, erro_obs = obs_store.do_os(folio), ""
    except Exception as e:                              # noqa: BLE001
        obs, erro_obs = [], "Não consegui ler as observações no banco da Gridco (%s)." % str(e)[:120]
    hoje = aw.agora_brt()
    fim_tela = max((o["quando"] for o in obs if o["tipo"] == "finalizado"), default="")
    c = aw.cartao(dict(linha, note=nota), ticket, (obs[-1]["quando"] if obs else ""), hoje, fim_tela)
    n = aw.ler_nota(nota)
    todos = [aw.cartao(l, d["tickets"].get(l.get("id"), ""), "", hoje) for l in d["linhas"]]
    return render_template("acomp_os.html", conta=_conta(), aba="criar", c=c, n=n, wid=wid, item=item,
                           tl=aw.linha_do_tempo(c, obs), outros=aw.outros(c, todos), canal=cs.CANAL.get(c["marca"], ""),
                           menos7=aw.menos_7d(n["data_falha"], hoje), copiar=aw.copiar_tudo(n["campos"]),
                           erro_obs=erro_obs, pode_gravar=ga.pode_gravar(), equipe=aw.equipe()[1])


# ── as três escritas ────────────────────────────────────────────────────────────────────────────────────────
def _corpo() -> dict:
    return request.get_json(silent=True) or {}


def _erro(msg, status=400):
    return jsonify({"erro": str(msg)}), status


def _os_conferida(folio: int, wid) -> tuple:
    """(wid, detalhe) — o id que o navegador mandou tem de ser o DESTA OS. Sem conferir, um id trocado gravaria o ticket
    na OS de outro chamado."""
    try:
        wid = int(wid or 0)
    except (TypeError, ValueError):
        wid = 0
    wid = wid or api._wo_id_por_folio(folio)
    if not wid:
        return None, None
    det = api.get_os_detalhes(wid) or {}
    if str(det.get("folio") or "") != str(folio):
        return None, None
    return wid, det


def _anotar(folio, texto, tipo, det) -> str:
    """A anotação automática (ticket, finalizado). Falhar aqui NÃO desfaz o que já foi gravado no Fracttal: vira aviso."""
    nome, email = _quem()
    try:
        obs_store.adicionar(folio, texto, tipo, ativo=(det or {}).get("code") or "", quem=nome, email=email)
        return ""
    except Exception as e:                              # noqa: BLE001
        return "A anotação automática não entrou no banco da Gridco: %s" % str(e)[:160]


@bp.route("/api/acomp/<int:folio>/ticket", methods=["POST"])
@exige_sessao
def api_ticket(folio):
    c = _corpo()
    novo = " ".join(str(c.get("ticket") or "").split())
    if not novo:
        return _erro("Escreva o nº do ticket ou do protocolo.")
    if len(novo) > 120:
        return _erro("O nº do ticket passa de 120 caracteres.")
    wid, det = _os_conferida(folio, c.get("wid"))
    if not wid:
        return _erro("Não achei a OS %s no Fracttal." % folio, 404)
    item = aw.item_do_ticket(det.get("subtarefas"))
    if not item or not item.get("id_form_item") or not item.get("id_tarefa"):
        return _erro("A OS %s não tem a subtarefa do nº do ticket — ela não é uma OS de acompanhamento." % folio)
    antigo = str(item.get("resposta") or "").strip()
    if antigo == novo:
        return jsonify({"ok": True, "ticket": novo, "mensagem": "O ticket já era este.", "aviso": ""})
    api.salvar_subtarefas(wid, item["id_tarefa"], [{"id_form_item": item["id_form_item"], "valor": novo,
                                                   "tipo": item.get("tipo_id") or 1}])
    _esquecer()
    aviso = _anotar(folio, aw.texto_ticket(novo, antigo), "ticket", det)
    return jsonify({"ok": True, "ticket": novo, "mensagem": "Ticket gravado na OS %s." % folio, "aviso": aviso})


@bp.route("/api/acomp/<int:folio>/obs", methods=["POST"])
@exige_sessao
def api_obs(folio):
    c = _corpo()
    nome, email = _quem()
    try:
        reg = obs_store.adicionar(folio, c.get("texto"), "obs", ativo=str(c.get("ativo") or ""), quem=nome, email=email)
    except ValueError as e:
        return _erro(e)
    except ga.SemCredencial as e:
        return _erro(e, 403)
    except requests.RequestException as e:
        return _erro("O banco da Gridco não respondeu: %s" % str(e)[:160], 502)
    return jsonify({"ok": True, "entrada": dict(aw.entrada(reg), novo=True)})


@bp.route("/api/acomp/<int:folio>/finalizar", methods=["POST"])
@exige_sessao
def api_finalizar(folio):
    wid, det = _os_conferida(folio, _corpo().get("wid"))
    if not wid:
        return _erro("Não achei a OS %s no Fracttal." % folio, 404)
    res = api.concluir_os_checado(wid)                           # o Concluir do card (os_detalhe.py:896)
    if isinstance(res, dict) and res.get("ok") is False:
        return _erro(res.get("msg") or "O Fracttal não concluiu a OS.")
    _esquecer()
    # O card da OS avisa em vermelho quando a conclusão fica SEM data de fim — lá é defeito (o cronômetro não foi usado
    # numa OS de campo). Aqui é o esperado: ninguém executa a OS administrativa, e a data que vale é a da finalização,
    # que vai para o banco logo abaixo. Dizer isso é melhor que assustar a Singrid a cada chamado fechado.
    chk = (res or {}).get("data_fim") if isinstance(res, dict) else None
    sem_fim = bool((chk or {}).get("sem_fim")) if isinstance(chk, dict) else False
    nota = _anotar(folio, "Chamado finalizado", "finalizado", det)
    return jsonify({"ok": True, "mensagem": "Chamado finalizado: a OS %s foi concluída no Fracttal." % folio,
                    "aviso": ("Sem registro de execução, o Fracttal deixa a data de fim vazia; o quadro usa a data "
                              "desta finalização." if sem_fim else ""), "aviso_obs": nota})

# os_creator/os_web/rotas_acomp.py
"""Acompanhamento de chamados — a porta do card de Chamados que faltava (Levi, 27/09/2026: "uma espécie de kanban
mostrando OSs que chegam, que a analista de chamados já escreveu número de tickets e OSs finalizadas! Ao clicar na OS abre uma tela
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
import time

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
TTL_TICKET_FIM = 1800     # s: o ticket de OS CONCLUÍDA, por pessoa (ver `_tickets`)

# O que cada leitura guarda, POR PESSOA (a lista vem com a sessão dela no Fracttal; uma pessoa nunca vê a cópia de
# outra). Levi, 08/10/2026: "O carregamento de Acompanhamento de chamados e a tela que abre quando clica na OS está
# demorando um pouco para carregar". Com o Fracttal falso a 300 ms por pedido (65 tickets lidos, 8 de cada vez):
# - ("acomp_linhas", pessoa): as OS de acompanhamento (lista + tarefas), SEM os tickets. É o que a tela de um chamado
#   precisa; antes, abrir um chamado com o quadro vencido relia os 65 tickets só para achar a linha;
# - ("acomp", pessoa): o quadro inteiro, as linhas acima + o ticket de cada uma;
# - ("acomp_tk", pessoa): o ticket das OS CONCLUÍDAS, {id: (quando, ticket)}. Concluída não volta e o Fracttal não
#   aceita mais editar (ver `api.editar_nota_os`: ERROR_WO_FINISHED_BY_OTHER_USER), então o ticket dela não muda: vale
#   30 min. O "Atualizar" relê a lista, as abertas e as em verificação.
# Tudo na memória do rotas (`rotas._MEMO`, com o teto dela): quem limpa a memória limpa tudo.


def _quem() -> tuple:
    c = session.get("conta") or {}
    return (str(c.get("nome") or "").strip(), str(c.get("email") or "").strip())


def _guardado(chave, ttl: float = None):
    """O que a memória do rotas tem nesta chave, sem buscar nada. Com `ttl`, só se ainda vale; sem, mesmo vencido (só
    para o que não muda, como o id de um nº de OS). None se nada."""
    with rotas._MEMO_LOCK:
        v = rotas._MEMO.get(chave)
    if not v or (ttl is not None and time.monotonic() - v[0] >= ttl):
        return None
    return v[1]


def _sessao_viva():
    """Leitura feita com a sessão morta NÃO vai para a memória. A listagem e os tickets engolem o erro de cada pedido
    (o `api` devolve vazio ou None), e o quadro vazio ficaria 3 min guardado para a pessoa, mesmo depois de ela entrar
    de novo. Até 08/10 quem acusava era a busca da etiqueta, o 1º pedido de toda leitura; com a lista guardada para o
    quadro reaproveitar, o quadro pode nem passar por ela. JWT vencido sem renovação levanta aqui mesmo (sem pedido)."""
    api._rpc_headers()


def _conferir_sessao():
    if sessao.morta():
        raise api.SessionExpired("Sua sessão do Fracttal expirou ou foi encerrada. Faça login de novo.")


def _linhas(forcar: bool = False) -> dict:
    """{"linhas", "quando"}: as OS de acompanhamento do Fracttal, sem os tickets, na memória por TTL_QUADRO."""
    def _buscar():
        hoje = aw.agora_brt()
        de = (dt.date.today() - dt.timedelta(days=DIAS_BUSCA)).isoformat()
        linhas = [l for l in (api.list_chamados(de=de) or []) if aw.eh_os3(l)]
        _conferir_sessao()
        return {"linhas": linhas, "quando": hoje.strftime("%d/%m/%Y %H:%M")}
    return rotas._memo(("acomp_linhas", rotas._quem()), TTL_QUADRO, _buscar, forcar)


def _tickets(linhas, hoje, pessoa) -> dict:
    """{id: ticket} das OS que o quadro mostra (`aw.precisa_ticket`). O das concluídas sai de ("acomp_tk", pessoa)
    quando lido há menos de 30 min; o resto vai ao Fracttal (8 de cada vez, `api.tickets_os3_em_massa`). None = não
    li: não é guardado."""
    ids = [l.get("id") for l in linhas if aw.precisa_ticket(l, hoje)]
    if not ids:
        return {}
    fechadas = {l.get("id") for l in linhas if l.get("status_id") == 3}
    chave, agora = ("acomp_tk", pessoa), time.monotonic()
    with rotas._MEMO_LOCK:
        v = rotas._MEMO.get(chave)
        meus = v[1] if v and isinstance(v[1], dict) else {}
        prontos = {i: meus[i][1] for i in ids if i in fechadas and i in meus and agora - meus[i][0] < TTL_TICKET_FIM}
    faltam = [i for i in ids if i not in prontos]
    lidos = api.tickets_os3_em_massa(faltam) if faltam else {}
    with rotas._MEMO_LOCK:
        v = rotas._MEMO.get(chave)
        meus = {k: x for k, x in (v[1] if v and isinstance(v[1], dict) else {}).items() if agora - x[0] < TTL_TICKET_FIM}
        meus.update({i: (agora, t) for i, t in lidos.items() if i in fechadas and t is not None})
        rotas._MEMO[chave] = (agora, meus)
    out = dict(lidos)
    out.update(prontos)
    return out


def _dados(forcar: bool = False) -> dict:
    """A lista das OS de acompanhamento + o ticket de cada uma, na memória por TTL_QUADRO (por pessoa: a lista vem
    com a sessão dela no Fracttal). A lista é a de `_linhas`: se a tela de um chamado acabou de lê-la, o quadro só
    busca os tickets."""
    pessoa = rotas._quem()

    def _buscar():
        _sessao_viva()
        hoje = aw.agora_brt()
        lv = _linhas(forcar)
        tickets = _tickets(lv["linhas"], hoje, pessoa)
        _conferir_sessao()
        return {"linhas": lv["linhas"], "tickets": tickets, "quando": lv["quando"]}
    return rotas._memo(("acomp", pessoa), TTL_QUADRO, _buscar, forcar)


def _esquecer(wid=None):
    """Depois de gravar ticket ou finalizar: a próxima leitura do quadro vai ao Fracttal (de todo mundo), e o ticket
    guardado desta OS sai."""
    with rotas._MEMO_LOCK:
        for k in [k for k in rotas._MEMO if isinstance(k, tuple) and k and k[0] in ("acomp", "acomp_linhas")]:
            rotas._MEMO.pop(k, None)
        if wid:
            for k, (_q, v) in rotas._MEMO.items():
                if isinstance(k, tuple) and k and k[0] == "acomp_tk" and isinstance(v, dict):
                    v.pop(wid, None)


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
    # as observações (banco da Gridco) vêm ao mesmo tempo que o Fracttal, e não depois dele (08/10/2026)
    with api._ExecutorComContexto(max_workers=1) as ex:
        f_obs = ex.submit(_ultimas, forcar)
        d, erro = _ler_quadro(forcar)
        ultimas, fins, erro_obs = f_obs.result()
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


def _detalhe_enxuto(wid) -> dict:
    """O detalhe da OS sem a solicitação, a OS pai e o cancelamento (`api.enxuta`): esta tela não mostra os três."""
    with api.enxuta("vinculos"):
        return api.get_os_detalhes(wid) or {}


def _obs_do_os(folio) -> tuple:
    """(observações desta OS, erro) — do banco da Gridco."""
    try:
        return obs_store.do_os(folio), ""
    except Exception as e:                              # noqa: BLE001
        return [], "Não consegui ler as observações no banco da Gridco (%s)." % str(e)[:120]


def _lista_da_tela(pessoa) -> dict:
    """As linhas para a tela de um chamado: o quadro inteiro, se ainda vale; senão só as linhas (`_linhas`, sem os
    tickets). A tela só usa a linha desta OS e os "outros chamados" (nº, marca, ativo, chegada), e nada disso vem do
    ticket: reler os tickets de todas as OS só para abrir uma era o que levava 5,6 s com o quadro vencido."""
    cheio = _guardado(("acomp", pessoa), TTL_QUADRO)
    if cheio is not None:
        return cheio
    try:
        return _linhas()
    except api.FracttalError as e:
        if sessao.morta() or isinstance(e, api.SessionExpired):
            raise
        return {"linhas": [], "quando": ""}


def _wid_ja_lido(folio, pessoa):
    """O id da OS deste nº numa leitura anterior DESTA pessoa, mesmo vencida (o id de um nº não muda). Com ele, o
    detalhe da OS vai ao Fracttal junto com a lista, e não depois dela."""
    for chave in (("acomp", pessoa), ("acomp_linhas", pessoa)):
        v = _guardado(chave)
        linha = _linha_de(v, folio) if v else None
        if linha and linha.get("id"):
            return linha["id"]
    return None


def _cartoes(d: dict, hoje) -> list:
    """Os cartões de todas as OS da leitura, para os "outros chamados" do mesmo ativo e da mesma OS de campo. Montados
    uma vez por leitura e guardados nela: ler de volta as notas de 80 OS custava ~0,2 s a cada chamado aberto, e o
    "outros" não mostra nada que mude de um minuto para o outro."""
    feitos = d.get("_cartoes")
    if feitos is None:
        tickets = d.get("tickets") or {}
        feitos = [aw.cartao(l, tickets.get(l.get("id"), ""), "", hoje) for l in d.get("linhas") or []]
        d["_cartoes"] = feitos
    return feitos


@bp.route("/chamados/acompanhamento/<int:folio>")
@exige_sessao
def detalhe(folio):
    """A tela de um chamado. A lista, o detalhe da OS e as observações vão ao mesmo tempo (Levi, 08/10/2026: "a tela que
    abre quando clica na OS está demorando"); o detalhe vem sem a solicitação e a OS pai, que esta tela não mostra."""
    pessoa = rotas._quem()
    talvez = _wid_ja_lido(folio, pessoa)
    with api._ExecutorComContexto(max_workers=2) as ex:
        f_obs = ex.submit(_obs_do_os, folio)
        f_det = ex.submit(_detalhe_enxuto, talvez) if talvez else None
        d = _lista_da_tela(pessoa)
        linha = _linha_de(d, folio)
        wid = (linha or {}).get("id") or talvez or api._wo_id_por_folio(folio)
        if not wid:
            return render_template("erro.html", conta=_conta(), aba="criar",
                                   mensagem="Não achei a OS %s no Fracttal." % folio), 404
        det = None
        if f_det is not None and wid == talvez:
            det = f_det.result() or {}
            if det.get("folio") and str(det["folio"]) != str(folio):     # não deve acontecer: o id de um nº não muda
                det = None
        if det is None:
            det = _detalhe_enxuto(wid)
        obs, erro_obs = f_obs.result()
    nota = _nota_da_os(det, linha)
    item = aw.item_do_ticket(det.get("subtarefas"))
    ticket = str((item or {}).get("resposta") or "").strip()
    if linha is None:                                  # fora da lista (mais velha que DIAS_BUSCA): o mínimo do detalhe
        linha = {"id": wid, "folio": folio, "note": nota, "descricao": det.get("descricao"), "ativo": det.get("ativo"),
                 "status_id": 3 if det.get("data_fim") else 1, "atribuido_a": det.get("responsavel")}
    hoje = aw.agora_brt()
    fim_tela = max((o["quando"] for o in obs if o["tipo"] == "finalizado"), default="")
    c = aw.cartao(dict(linha, note=nota), ticket, (obs[-1]["quando"] if obs else ""), hoje, fim_tela)
    n = aw.ler_nota(nota)
    todos = _cartoes(d, hoje)
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
    det = _detalhe_enxuto(wid)                         # a conferência não usa a solicitação nem a OS pai
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
    _esquecer(wid)
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
    _esquecer(wid)
    # O card da OS avisa em vermelho quando a conclusão fica SEM data de fim — lá é defeito (o cronômetro não foi usado
    # numa OS de campo). Aqui é o esperado: ninguém executa a OS administrativa, e a data que vale é a da finalização,
    # que vai para o banco logo abaixo. Dizer isso é melhor que assustar a analista de chamados a cada chamado fechado.
    chk = (res or {}).get("data_fim") if isinstance(res, dict) else None
    sem_fim = bool((chk or {}).get("sem_fim")) if isinstance(chk, dict) else False
    nota = _anotar(folio, "Chamado finalizado", "finalizado", det)
    return jsonify({"ok": True, "mensagem": "Chamado finalizado: a OS %s foi concluída no Fracttal." % folio,
                    "aviso": ("Sem registro de execução, o Fracttal deixa a data de fim vazia; o quadro usa a data "
                              "desta finalização." if sem_fim else ""), "aviso_obs": nota})

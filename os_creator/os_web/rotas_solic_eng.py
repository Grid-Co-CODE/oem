# os_creator/os_web/rotas_solic_eng.py
"""Rotas da Nova solicitação para a ENGENHARIA (06/10/2026). As regras moram no `solic_eng_web`; aqui só a tela, a
cascata e a criação. Uma OS por ativo sai pelo `api.create_work_orders_bulk` — o mesmo caminho da OS de análise
(`api.create_os_analise`); uma OS com todos os ativos (08/10), pelo `api.create_work_orders_agrupada`, o do "Agrupar em
UMA OS" do Tradicional. Nos dois: tipo 'Administrativa', só a Classificação 1 'Programada' (pelo nome), as etiquetas
REMOTO e ENGENHARIA (só elas), sem plano e com o título por ativo no `por_ativo`. Os anexos (08/10) sobem depois de a
OS existir, pelo `api.attach_imagem_os`, o mesmo caminho das imagens da Performance e do Tradicional."""
from __future__ import annotations
import datetime as dt
import json

from flask import Blueprint, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

import api

from . import perf_web
from . import solic_eng_web as reg
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_solic_eng", __name__, url_prefix="/os")
_FMT = "%Y-%m-%dT%H:%M"


def _agora() -> dt.datetime:
    return dt.datetime.now(reg.BRT).replace(second=0, microsecond=0)


@bp.route("/solicitacao/engenharia")
@exige_sessao
def tela():
    assets = api.load_assets_cached()
    agora = _agora()
    # a hora COM segundos: é a base de onde a tela anda o relógio da data mostrada (que o servidor recalcula ao criar)
    agora_s = dt.datetime.now(reg.BRT).strftime(_FMT + ":%S")
    return render_template("solic_eng.html", conta=_conta(), aba="solic",
                           clientes=sorted(perf_web.clientes_reais(assets)), usinas=perf_web.usinas_para(assets, None),
                           agora=agora_s, evento=agora.strftime(_FMT),
                           programada=reg.data_br(reg.data_padrao(agora, False)), dias=reg.DIAS_PADRAO,
                           dias_urgente=reg.DIAS_URGENTE, sub_descricao=reg.SUB_DESCRICAO, rotulo_problema=reg.ROTULO_PROBLEMA,
                           # os limites dos anexos vêm daqui para a tela: o navegador confere com os MESMOS números
                           anexo_max=reg.MAX_ARQUIVOS, anexo_mb=reg.MAX_MB_ARQUIVO, anexo_total_mb=reg.MAX_MB_TOTAL,
                           anexo_envios=reg.MAX_ENVIOS, anexo_envios_mb=reg.MAX_MB_ENVIOS, anexo_aceitar=reg.ACEITAR,
                           anexo_tipos=reg.tipos_aceitos())


@bp.route("/api/solicitacao/engenharia/usinas")
@exige_sessao
def api_usinas():
    cliente = (request.args.get("cliente") or "").strip() or None
    return jsonify({"usinas": perf_web.usinas_para(api.load_assets_cached(), cliente)})


@bp.route("/api/solicitacao/engenharia/ativos")
@exige_sessao
def api_ativos():
    ativos = reg.ativos_da_usina(api.load_assets_cached(), (request.args.get("usina") or "").strip(), api._asset_short_name)
    return jsonify({"ativos": ativos, "tipos": [{"tipo": t, "nome": n} for t, n in reg.tipos_de(ativos)]})


@bp.route("/api/solicitacao/engenharia/responsaveis")
@exige_sessao
def api_responsaveis():
    nomes = reg.nomes_configurados()
    if not nomes:
        return jsonify({"pessoas": [], "faltam": [], "configurado": False})
    pessoas, faltam = reg.responsaveis(api.get_responsaveis() or [], nomes)
    return jsonify({"pessoas": pessoas, "faltam": faltam, "configurado": True})


def _abrir_limite():
    """O app aceita 4 MB por pedido (MAX_CONTENT_LENGTH, pensado nas imagens do Tradicional), e um PDF de relatório ou
    a foto do celular passam disso. Só ESTA rota abre para os anexos (`reg.LIMITE_PEDIDO`). O limite por pedido é do
    Flask 3.1; num Flask mais velho vale o do app, e a recusa sai legível (`_pedido_grande`)."""
    try:
        request.max_content_length = reg.LIMITE_PEDIDO
    except AttributeError:
        pass


def _corpo_e_anexos() -> tuple[dict, list]:
    """JSON puro quando não há anexo (como era); multipart quando há, no molde do Tradicional: o campo `payload` traz o
    MESMO JSON e cada arquivo vem em `anexos`."""
    if not (request.mimetype or "").startswith("multipart/"):
        return request.get_json(silent=True) or {}, []
    try:
        corpo = json.loads(request.form.get("payload") or "{}")
    except ValueError:
        corpo = {}
    brutos = [(f.filename or "", f.read()) for f in request.files.getlist("anexos")]
    return (corpo if isinstance(corpo, dict) else {}), brutos


@bp.route("/api/solicitacao/engenharia/criar", methods=["POST"])
@exige_sessao
def api_criar():
    _abrir_limite()
    corpo, brutos = _corpo_e_anexos()
    por_id = {str(a.get("id")): a for a in (api.load_assets_cached() or []) if isinstance(a, dict)}
    # o responsável é conferido de novo AQUI: a lista da tela é só a primeira barreira
    permitidos, _ = reg.responsaveis(api.get_responsaveis() or [], reg.nomes_configurados())
    ativos, c, erro = reg.montar(corpo, por_id, permitidos, _agora(), api.perf_os_nome)
    if erro:
        return jsonify({"erro": erro}), 400
    # os anexos ANTES de criar, como as etiquetas: anexo recusado = nenhuma OS criada
    anexos, erro = reg.anexos(brutos)
    if not erro:
        erro = reg.erro_envios(anexos, 1 if c["agrupar"] else len(ativos))
    if erro:
        return jsonify({"erro": erro}), 400
    # as etiquetas ANTES de criar: REMOTO e ENGENHARIA sempre, e só elas — faltando uma no Fracttal, nenhuma OS sai
    etiquetas, faltam = reg.etiquetas(api.get_labels() or [])
    if faltam:
        return jsonify({"erro": reg.erro_etiquetas(faltam)}), 400
    # só a Classificação 1, pelo NOME (como a OS de análise): nome que não existir no catálogo apenas não entra
    cl = api._classif_ids(reg.CLASSIF_1, "")
    tipo = {"id_c1": cl["id_task_type"], "desc_c1": cl.get("tasks_types_description") or ""} \
        if cl.get("id_task_type") is not None else None
    comum = {"etiqueta_ids": etiquetas, "id_responsible": c["id_responsible"], "responsible_name": c["responsible_name"],
             "note": c["note"], "tipo": tipo, "event_date": c["event_date"], "prog_date": c["prog_date"],
             "por_ativo": c["por_ativo"]}
    if c["agrupar"]:
        # cada ativo vira uma atividade (tarefa) com o seu '[Ativo] - Descrição', e todas entram numa OS só
        res = api.create_work_orders_agrupada(ativos, c["descricao"], reg.TIPO_TAREFA, [], **comum)
        out, oss = reg.mensagem_agrupada(res, ativos, c["prog_date"]), reg.oss_da_agrupada(res)
    else:
        res = api.create_work_orders_bulk(ativos, c["descricao"], reg.TIPO_TAREFA, [],
                                          responsible_code=c["responsible_code"], **comum)
        out, oss = reg.mensagem(res, ativos, c["prog_date"]), reg.oss_do_bulk(res)
    if anexos:
        alvos = [o for o in oss if o.get("id_work_order")]
        with api._ExecutorComContexto(max_workers=reg.ENVIOS_PARALELOS) as ex:
            resultados = reg.anexar(alvos, anexos, api.attach_imagem_os, api._ids_tarefas_da_os, mapa=ex.map)
        out = reg.com_anexos(out, resultados, len(anexos), sem_numero=len(oss) - len(alvos))
    # algo nasceu no Fracttal (mesmo sem número) = 200: a tela tira os ativos da seleção, e um 2º clique não duplica
    return jsonify(out), (200 if out["ok"] or out.get("pendentes") else 400)


@bp.errorhandler(RequestEntityTooLarge)
def _pedido_grande(_e):
    """A tela confere os anexos antes de enviar; passou do limite mesmo assim, a resposta é JSON legível (e não um 413
    em HTML), e nada foi criado — o corpo nem chegou a ser lido."""
    limite = (request.max_content_length or reg.LIMITE_PEDIDO) // reg.MB
    return jsonify({"erro": "O envio passou do limite do servidor (%d MB): anexe menos arquivos, ou arquivos menores. "
                            "Nenhuma OS foi criada." % limite}), 413

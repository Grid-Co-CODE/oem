# os_creator/os_web/rotas_os_acoes.py
"""As AÇÕES do card de detalhe da OS na web — o que no desktop são os botões do `steps/os_detalhe.py` e os diálogos
`steps/cancelar_os.py`, `steps/os_fluxo.py`, `steps/galeria.py` e `steps/documentos.py`.

Toda escrita passa pela MESMA função do `api.py` que o desktop chama, com os MESMOS argumentos (o comentário em cada
rota aponta a linha do desktop). As rotas devolvem JSON sob `/os/api/os/<wid>/...`; o JS (`static/os_acoes.js`) confirma
antes de escrever e recarrega o fragmento do card (`/os/os/<wid>?parcial=1`) ao terminar. Erro do Fracttal sobe para o
`app_errorhandler` do rotas.py (sessão morta → 401 com `login`; recusa → 502 com a mensagem)."""
from __future__ import annotations
import mimetypes
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request

import api

from . import os_acoes_web as regra
from . import tradicional_web as trad
from .rotas import exige_sessao

bp = Blueprint("os_web_os_acoes", __name__, url_prefix="/os")


# ── o que o template do card precisa e o `rotas.os_detalhe` não passa (ele não é deste pacote) ────────────────
@bp.app_template_global("acoes_nota_regra")
def _tg_nota_regra(d, status):
    """(pode, motivo) do botão Editar da observação — a regra do card do app, com o status que a web conhece."""
    return regra.nota_pode_editar(regra.status_id_de(status, d), len((d or {}).get("tarefas") or []))


@bp.app_template_global("acoes_sem_fim")
def _tg_sem_fim(d):
    return regra.tarefas_sem_fim((d or {}).get("tarefas"))


@bp.app_template_global("acoes_tarefas_pendentes")
def _tg_tarefas_pendentes(d):
    """As tarefas da OS com subtarefa em branco — é por elas que o "fazer a tarefa" é oferecido."""
    return regra.tarefas_pendentes(d)


def _corpo() -> dict:
    return request.get_json(silent=True) or {}


def _erro(msg, status=400):
    return jsonify({"erro": str(msg)}), status


# ── leituras ──────────────────────────────────────────────────────────────────────────────────────────
@bp.route("/api/os/<int:wid>/fluxo")
@exige_sessao
def api_fluxo(wid):
    # os_fluxo.py:139 — ApiWorker(api.fluxo_da_os, self._wo, 0): 0 = sem o histórico do ativo (só a cadeia, Levi 06/08)
    return jsonify(regra.fluxo_web(api.fluxo_da_os(wid, 0) or {}, api.fmt_data_br))


@bp.route("/api/os/<int:wid>/anexos-lista")
@exige_sessao
def api_anexos_lista(wid):
    """Imagens, documentos e notas dos dois cards (verde = das subtarefas, azul = da OS), já com a URL pré-assinada que o
    api resolve e o link que a renova — as duas chamadas do `_carregar` do card (get_os_subtarefa_anexos + get_os_anexos)."""
    subs = api.get_os_subtarefa_anexos(wid) or []
    oss = api.get_os_anexos(wid) or []
    return jsonify(regra.anexos_web(subs, oss, wid))


@bp.route("/api/os/<int:wid>/anexo")
@exige_sessao
def api_anexo_baixar(wid):
    """'Baixar' de um anexo: RENOVA a URL pré-assinada (companies.s3_object_get) e devolve os bytes como download.

    Por quê renovar em vez de mandar a URL da lista: a URL do Fracttal expira, e no desktop o remédio era 'reabrir os
    anexos renova' (documentos.py). Aqui o clique já renova. Os bytes vêm pelo `api.baixar_imagem` — a mesma
    requisição sem cabeçalhos de auth do S3 que a galeria usa (documentos.py faz o mesmo GET por conta própria)."""
    value = (request.args.get("value") or "").strip()
    if not value:
        return _erro("Anexo sem caminho no S3.")
    nome = regra.fname(request.args.get("nome") or "") or regra.fname(value) or "anexo"
    url = api.s3_get_url(value)
    if not url:
        return _erro("Não consegui renovar o link deste anexo no Fracttal (reabra os anexos e tente de novo).", 404)
    dados = api.baixar_imagem(url)                                   # FracttalError sobe → 502 JSON
    tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
    ascii_ = nome.encode("ascii", "ignore").decode() or "anexo"
    return Response(dados, mimetype=tipo, headers={
        "Content-Disposition": 'attachment; filename="%s"; filename*=UTF-8\'\'%s' % (ascii_.replace('"', ""), quote(nome, safe="")),
        "Cache-Control": "private, no-store"})


@bp.route("/api/os/<int:wid>/etiquetas")
@exige_sessao
def api_etiquetas(wid):
    """Catálogo (`get_labels`, como o `_EtiquetasDialog` carrega) + as etiquetas da OS. O card manda as atuais pelos chips
    (`?atuais=1,2` — o desktop também recebe `atuais` do card, sem ir ao servidor); sem o parâmetro, lê a OS."""
    catalogo = [{"id": l.get("id"), "description": str(l.get("description") or "").strip(), "color": regra.cor_hex(l.get("color"))}
                for l in (api.get_labels() or []) if isinstance(l, dict) and l.get("id") is not None
                and str(l.get("description") or "").strip()]                 # o `_filtrar` do app pula etiqueta sem descrição
    lista = request.args.get("atuais")
    if lista is not None:
        atuais = [int(x) for x in lista.split(",") if x.strip().isdigit()]
    else:
        atuais = [e.get("id") for e in ((api.get_os_detalhes(wid) or {}).get("etiquetas") or [])
                  if isinstance(e, dict) and e.get("id") is not None]
    return jsonify({"catalogo": catalogo, "atuais": atuais})


@bp.route("/api/os/<int:wid>/cancel-motivos")
@exige_sessao
def api_cancel_motivos(wid):
    # cancelar_os.py:50 — ApiWorker(api.get_cancel_motivos)
    return jsonify({"motivos": api.get_cancel_motivos() or []})


# ── escritas ──────────────────────────────────────────────────────────────────────────────────────────
@bp.route("/api/os/<int:wid>/responsavel", methods=["POST"])
@exige_sessao
def api_responsavel(wid):
    """Trocar responsável — `TrocarResponsavelDialog._salvar`. Só `id_personnel`: o desktop não manda nota, e o `nota` do
    `mudar_responsavel` vai para o `note` do work_orders_update, que é a OBSERVAÇÃO da OS (ver `editar_nota_os`) —
    mandar algo daqui reescreveria a observação sem a pessoa saber."""
    c = _corpo()
    idp = c.get("id_personnel")
    if not idp:
        return _erro("escolha a pessoa.")
    r = api.mudar_responsavel(wid, idp)                              # os_detalhe.py:331 — (self._wo, p["id_personnel"])
    if not (isinstance(r, dict) and r.get("ok")):
        return _erro((r or {}).get("erro") or "não deu")
    return jsonify({"ok": True, "mensagem": "OS %s agora está com %s." % (c.get("folio") or wid, c.get("name") or "—")})


@bp.route("/api/os/<int:wid>/etiquetas", methods=["POST"])
@exige_sessao
def api_etiquetas_salvar(wid):
    """Etiquetas — `_EtiquetasDialog._salvar`. `labels_sync` SUBSTITUI o conjunto: o JS manda TODAS as marcadas, não a
    diferença. Vazio não vai (o app pede 'ao menos uma'; o `apply_labels` recusaria de qualquer jeito)."""
    ids = [(int(x) if str(x).strip().isdigit() else x) for x in (_corpo().get("ids") or []) if x not in (None, "")]
    if not ids:
        return _erro("Marque ao menos uma etiqueta (ou Cancelar).")
    r = api.apply_labels(wid, ids)                                   # os_detalhe.py:420 — (self._wo, ids)
    if isinstance(r, dict) and r.get("ok") is False:
        return _erro(r.get("erro") or "não foi possível salvar")
    return jsonify({"ok": True})


@bp.route("/api/os/<int:wid>/nota", methods=["POST"])
@exige_sessao
def api_nota(wid):
    """Observação da OS — `_nota_salvar`. Antes de gravar, a mesma régua do botão Editar, conferida contra a OS lida
    agora (não contra o que o navegador diz): OS cancelada e OS de várias tarefas não passam, e nada chega ao Fracttal."""
    c = _corpo()
    d = api.get_os_detalhes(wid) or {}
    pode, motivo = regra.nota_pode_editar(regra.status_id_de(c.get("status"), d), len(d.get("tarefas") or []))
    if not pode:
        return _erro(motivo)
    novo = str(c.get("nota") or "").strip()                          # o app grava `toPlainText().strip()`
    r = api.editar_nota_os(wid, novo)                                # os_detalhe.py:1361 — (self._wo, novo)
    if not (isinstance(r, dict) and r.get("ok")):
        return _erro((r or {}).get("erro") or "Não consegui salvar a observação.")
    # a API apara os espaços das pontas — devolver o que ELA gravou, não o que foi digitado
    return jsonify({"ok": True, "nota": r.get("nota", novo)})


@bp.route("/api/os/<int:wid>/concluir", methods=["POST"])
@exige_sessao
def api_concluir(wid):
    """Concluir OS — IRREVERSÍVEL, dois passos dentro do `concluir_os_checado` (status 3 + recalculate) e a reconferência
    da data de fim na volta (`_concluiu`). A confirmação (o `_ConcluirDialog`) é no navegador, antes deste POST."""
    folio = _corpo().get("folio") or wid
    res = api.concluir_os_checado(wid)                               # os_detalhe.py:896 — (self._wo)
    if isinstance(res, dict) and res.get("ok") is False:
        return _erro(res.get("msg") or "Não foi possível concluir.")
    texto, aviso = regra.mensagem_concluida(folio, (res or {}).get("data_fim") if isinstance(res, dict) else None)
    return jsonify({"ok": True, "mensagem": texto, "aviso": aviso,
                    "data_fim": (res or {}).get("data_fim") if isinstance(res, dict) else None})


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/checklist")
@exige_sessao
def api_checklist(wid, tid):
    """O checklist de UMA tarefa, com o valor que já está lá — o que a janela precisa desenhar."""
    campos = api.subtarefas_da_tarefa(tid)
    return jsonify({"id_tarefa": tid, "id_work_order": wid, "campos": campos,
                    "pendentes": len([c for c in campos if not str(c.get("valor") or "").strip()])})


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/executar", methods=["POST"])
@exige_sessao
def api_executar(wid, tid):
    """Fazer a tarefa: grava o checklist e lança o registro de execução, NESTA ORDEM.

    A ordem é a da tela do Fracttal e não é indiferente: se o registro fosse primeiro e o checklist
    falhasse, a OS ficaria com horas lançadas para um serviço que não foi registrado — e o
    contrário (checklist gravado, registro falhou) é recuperável, basta lançar o registro de novo.
    """
    c = _corpo()
    valores = c.get("valores") or {}
    campos = api.subtarefas_da_tarefa(tid)
    faltam = regra.faltando_obrigatorias(campos, valores)
    if faltam:
        return _erro(regra.ERRO_OBRIGATORIA % "; ".join(faltam[:4]))
    try:
        ini = trad.data_brt(c.get("inicio"))
    except (ValueError, TypeError):
        return _erro(regra.ERRO_SEM_INICIO)
    if not str(c.get("inicio") or "").strip():
        return _erro(regra.ERRO_SEM_INICIO)
    fim = None
    if str(c.get("fim") or "").strip():
        try:
            fim = trad.data_brt(c.get("fim"))
        except (ValueError, TypeError):
            return _erro("Data de fim inválida.")
        if fim < ini:
            return _erro(regra.ERRO_FIM_ANTES)
    por_id = {str(x.get("id_form_item")): x for x in campos}
    a_gravar = [{"id_form_item": por_id[k]["id_form_item"], "valor": v,
                 "tipo": por_id[k].get("tipo") or 1}
                for k, v in valores.items() if k in por_id and str(v or "").strip()]
    n = 0
    if a_gravar:
        n = (api.salvar_subtarefas(wid, tid, a_gravar) or {}).get("n") or 0
    res = api.registrar_execucao(tid, ini, fim, note=str(c.get("nota") or "").strip())
    texto, aviso = regra.mensagem_execucao(n, res, lambda x: api.fmt_data_br(x) or "—")
    return jsonify({"ok": True, "mensagem": texto, "aviso": aviso, "n": n,
                    "confirmado": bool(res.get("confirmado"))})


@bp.route("/api/os/<int:wid>/cancelar", methods=["POST"])
@exige_sessao
def api_cancelar(wid):
    """Cancelar OS — `CancelarOSDialog._confirmar`: motivo (status custom) obrigatório + observação opcional; o tipo é fixo
    ('Cancelar OS', dentro do `cancel_os`). A AUTORIZAÇÃO é a do usuário no Fracttal: recusa vira FracttalError → 502."""
    c = _corpo()
    idm = c.get("id_status_custom")
    if idm in (None, "", 0, "0"):
        return _erro("Escolha o motivo do cancelamento.")
    api.cancel_os(wid, idm, str(c.get("note") or "").strip())        # cancelar_os.py:77 — (self._wo, idm, obs.strip())
    return jsonify({"ok": True, "mensagem": "OS %s cancelada com sucesso." % (c.get("folio") or wid)})

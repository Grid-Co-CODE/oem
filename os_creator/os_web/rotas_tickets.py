# os_creator/os_web/rotas_tickets.py
"""A tela de Tickets na web — o 5º card da Performance (`steps/tickets.py::TicketsTab`).

Levi, 22/09/2026: "mas tem uma visão só para tickets que nem no OS Creator Desktop??". Não tinha —
o que existia era a GERAÇÃO de ticket ao criar a OS. Esta é a tela de consulta e edição: as
ocorrências de trackers e strings, em que pé cada uma está, e a edição da causa, do vínculo com a
OS e das datas.

O MOTOR É O MESMO, sem cópia: `tickets_api` lê, `tickets_escrita` grava, `tickets_spec` diz as
abas e o ciclo de vida, `tickets_calc` faz as contas de data e `tickets_diario` repõe o que o sync
desfez. Os cinco já eram puros. O que o desktop tinha a mais era Qt, e essa parte está em
`tickets_web.py`.

DUAS COISAS QUE A TELA PRECISA DIZER EM VOZ ALTA, e diz:
· o sync do pipeline ainda pode sobrescrever a aba (por isso o diário existe);
· sem a credencial de escrita nesta máquina, a tela é só leitura — e avisa antes, não no Salvar.
"""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, jsonify, render_template, request

import api
import tickets_api
import tickets_diario
import tickets_escrita
import tickets_spec

from . import tickets_painel as tp
from . import tickets_web as tw
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_tickets", __name__, url_prefix="/os")

ABA_PADRAO = "Trackers"


def _diario_por_cima(aba: str, ocs: list) -> dict:
    """Aplica o diário. Falha de leitura NÃO derruba a tela: sem ele a lista é a do banco, que é o
    que se via antes de o diário existir — pior que o ideal, muito melhor que uma tela em branco."""
    try:
        return tickets_diario.aplicar(aba, ocs, tickets_diario.ler()) or {}
    except Exception:                                   # noqa: BLE001
        return {"erro": True}


def _carregar(aba: str) -> tuple:
    """(ocorrências, ocultas, placar do diário) — a aba como a TELA a vê.

    UM leitor só para a lista e para o painel de acompanhamento: se cada tela montasse a sua, o
    "627 abertas" de uma não bateria com o da outra na primeira edição feita pelo app. A ordem
    importa: montar → cliente → diário → recalcular (o diário muda OS e Fim, que decidem o estado).
    Erro de leitura da aba sobe; o do diário não (ver `_diario_por_cima`)."""
    linhas = tickets_api.listar_linhas(tickets_spec.ABAS[aba]["sheet_id"])
    ocs, ocultas = tw.montar(linhas)
    tw.preencher_cliente(ocs)
    placar_diario = _diario_por_cima(aba, ocs) if ocs else {}
    tw.recalcular(ocs)
    return ocs, ocultas, placar_diario


def _ler_com_diario(aba: str, sheet_id: int, row: int) -> dict:
    """A linha como a TELA a vê: a da planilha com o diário por cima.

    Sem o diário, o painel mostrava a OS e o Status do ticket SEMPRE vazios — os dois só existem
    lá (a planilha não tem coluna para eles) — e o que o sync tivesse desfeito voltava a aparecer
    desfeito. A lista já aplicava; o painel, que relê a linha, não aplicava."""
    oc = tickets_escrita.ler_linha(sheet_id, row)
    oc["_row"] = row
    try:
        tickets_diario.aplicar(aba, [oc], tickets_diario.ler())
    except Exception:                                   # noqa: BLE001 — sem diário, a da planilha
        pass
    return oc


def _pode_gravar() -> bool:
    """A credencial de escrita existe nesta máquina? Dito ANTES, e não no Salvar."""
    try:
        return bool(tickets_escrita._token())
    except Exception:                                   # noqa: BLE001
        return False


@bp.route("/tickets")
@exige_sessao
def tickets():
    aba = request.args.get("aba") or ABA_PADRAO
    if aba not in tickets_spec.ABAS:
        aba = ABA_PADRAO
    estado = request.args.get("estado") or ""
    busca = (request.args.get("busca") or "").strip()
    so_alarme = request.args.get("alarme") == "1"
    cliente = (request.args.get("cliente") or "").strip()
    usina = (request.args.get("usina") or "").strip()

    erro = ""
    try:
        ocs, ocultas, placar_diario = _carregar(aba)
    except Exception as e:                              # noqa: BLE001
        ocs, ocultas, placar_diario = [], [], {}
        erro = "Não consegui ler a aba %s: %s" % (aba, e)
    # o cliente escolhido restringe a lista de usinas do 2o dropdown, e uma usina escolhida que
    # nao seja daquele cliente e descartada em vez de zerar a tela sem explicacao
    usinas = tw.usinas_de(ocs, cliente)
    if usina and usina not in usinas:
        usina = ""
    # O ESTADO NAO FILTRA NO SERVIDOR (Levi, 22/09: "clico e direciona para um link novo"). A
    # pagina traz todos os estados e o clique no contador filtra na hora, no navegador. Os outros
    # filtros (cliente, usina, busca, +30 dias) continuam aqui — e os CONTADORES passam a contar
    # so o que eles deixaram: antes o "Aberta 627" era da aba inteira mesmo com um cliente
    # escolhido, e o numero do cartao nao batia com a lista embaixo dele.
    itens = tw.filtrar(ocs, "", busca, so_alarme, cliente, usina)
    grupos = tw.agrupar(itens, aba)

    return render_template(
        # `abas_tk`, e não `abas`: `abas` é a variável global das abas do topo (base.html), e
        # sobrescrevê-la deixava o menu Criar OS / Solicitação / Históricos com dois links vazios
        "tickets.html", conta=_conta(), aba_nav="criar", aba=aba, abas_tk=list(tickets_spec.ABAS),
        estados=tickets_spec.ESTADOS, estado=estado, busca=busca, so_alarme=so_alarme,
        cliente=cliente, usina=usina, clientes=tw.clientes_de(ocs), usinas=usinas,
        colunas=tw.colunas_da_aba(aba), grupos=grupos, n_itens=len(itens), placar=tw.placar(itens),
        total=len(itens), ocultas=len(ocultas), erro=erro, qtd_de=lambda o: tw.qtd_de(o, aba),
        rotulo_coluna=tw.ROTULO_COLUNA, numero_da_os=tw.numero_da_os,
        rotulo_qtd=tw.ROTULO_QTD.get(aba, "equipamentos parados"),
        restaurados=int((placar_diario or {}).get("aplicados") or 0),
        pode_gravar=_pode_gravar(), status_opts=tw.STATUS,
        celula=lambda o, c: tw.celula(o, c, aba), alarme=tw.alarme,
        para_input=tw.para_input, cor_estado=tickets_spec.COR_ESTADO,
        nome_estado=tickets_spec.NOME_ESTADO, editaveis=tw.EDITAVEIS)


@bp.route("/tickets/painel")
@exige_sessao
def tickets_painel():
    """O painel de acompanhamento (Levi, 22/09: item 11; mockup aprovado no mesmo dia).

    As DUAS abas numa ida só: a troca Trackers/Strings é instantânea, como no mockup, e a leitura
    das duas custa ~1 s a mais que a de uma (medido em 22/09: Trackers 0,9 s, Strings 0,2 s, diário
    0,6 s). A aba que falhar vira aviso naquela aba — a outra continua de pé."""
    aba = request.args.get("aba") or ABA_PADRAO
    if aba not in tickets_spec.ABAS:
        aba = ABA_PADRAO
    agora = dt.datetime.now()
    dados = {}
    for a in tickets_spec.ABAS:
        try:
            ocs, _ocultas, _placar = _carregar(a)
            dados[a] = tp.resumo(ocs, a, agora)
        except Exception as e:                          # noqa: BLE001
            dados[a] = {"aba": a, "erro": "Não consegui ler a aba %s: %s" % (a, e)}
    return render_template("tickets_painel.html", conta=_conta(), aba_nav="criar", aba=aba,
                           abas_tk=list(tickets_spec.ABAS), dados=dados,
                           estados_def=tp.estados_def(), sem_cliente=tw.SEM_CLIENTE,
                           lido=agora.strftime("%d/%m/%Y às %H:%M"))


@bp.route("/api/tickets/<aba>/<int:row>")
@exige_sessao
def api_ocorrencia(aba, row):
    """UMA ocorrência, relida do banco — é o que o painel de edição abre.

    Relê em vez de confiar no que a tabela já tinha: entre carregar a lista e clicar numa linha
    pode ter passado um sync, e editar por cima de dado velho é como se perde o trabalho do outro.
    """
    if aba not in tickets_spec.ABAS:
        return jsonify({"erro": tw.ERRO_ABA % aba}), 400
    sheet_id = tickets_spec.ABAS[aba]["sheet_id"]
    try:
        oc = _ler_com_diario(aba, sheet_id, row)
    except Exception as e:                              # noqa: BLE001
        return jsonify({"erro": "Não consegui reler a linha %s: %s" % (row, e)}), 502
    ocs, _ = tw.montar([oc])
    if not ocs:
        return jsonify({"erro": "A linha %s não é uma ocorrência (está 'Em conformidade')." % row}), 400
    o = ocs[0]
    campos = [{"campo": c, "valor": "" if o.get(c) is None else str(o.get(c)),
               "data": c in ("Início da ocorrência", "Início do chamado pela Grid Co.",
                             "Fim da ocorrência"),
               "input": tw.para_input(o.get(c))} for c in tw.EDITAVEIS]
    return jsonify({"row": row, "aba": aba, "estado": o.get("_estado"),
                    "dias": o.get("_dias"), "periodo": tw.periodo_txt(o.get("_dias")),
                    "horas": o.get("_horas"), "usina": str(o.get("Usina") or "—"),
                    "ativo": str(o.get("Ativo") or ""), "campos": campos,
                    "status_opts": tw.STATUS, "pode_gravar": _pode_gravar(),
                    "os": tw.numero_da_os(o.get("OS")), "pode_vincular": tw.pode_vincular(o),
                    # o que a exclusão confere na volta: a linha N ainda é ESTA ocorrência?
                    "impressao": tickets_diario.impressao(aba, o),
                    "confirma_1": tw.APAGAR_QUAL % (tickets_spec.ABAS[aba]["rotulo"],
                                                    tw.identificacao(aba, o),
                                                    (str(o.get("Causa raiz") or "").strip()[:70]
                                                     or "sem causa registrada"), row),
                    "confirma_2": tw.APAGAR_ALCANCE})


@bp.route("/api/tickets/<aba>/<int:row>/salvar", methods=["POST"])
@exige_sessao
def api_salvar(aba, row):
    """Grava o que a PESSOA mudou, com a LINHA INTEIRA no PUT e o registro no diário, nesta ordem.

    · linha inteira: o PUT substitui a linha; mandar só o que mudou apagaria as outras colunas;
    · conflito: só quando outra pessoa mudou o MESMO campo desde que o painel abriu (409);
    · planilha antes do diário: registrar antes de saber se gravou criaria um "restaurado" para
      algo que nunca existiu;
    · o autor no diário é quem está LOGADO, não o usuário do Windows do processo."""
    if aba not in tickets_spec.ABAS:
        return jsonify({"erro": tw.ERRO_ABA % aba}), 400
    if not _pode_gravar():
        return jsonify({"erro": "Falta a credencial de escrita nesta máquina — a tela está só "
                                "em leitura."}), 403
    corpo = request.get_json(silent=True) or {}
    sheet_id = tickets_spec.ABAS[aba]["sheet_id"]
    try:
        atual = _ler_com_diario(aba, sheet_id, row)
    except Exception as e:                              # noqa: BLE001
        return jsonify({"erro": "Não consegui reler a linha %s antes de gravar: %s" % (row, e)}), 502
    originais = corpo.get("originais")
    originais = originais if isinstance(originais, dict) else None
    mudou, erro = tw.validar_edicao(aba, atual, corpo.get("valores") or {}, originais)
    if erro:
        return jsonify({"erro": erro}), 400
    brigam = tw.conflitos(atual, originais, mudou)
    if brigam:
        return jsonify({"erro": "Outra pessoa alterou %s nesta ocorrência depois que você abriu o "
                                "painel. Nada foi gravado — reabra para ver o valor novo."
                                % ", ".join(brigam), "conflito": brigam}), 409
    try:
        cab = tickets_api.cabecalho_vivo(sheet_id) or tickets_api.cabecalho_de(sheet_id)
    except Exception as e:                              # noqa: BLE001
        return jsonify({"erro": "Não consegui ler as colunas da aba: %s" % e}), 502
    if not cab:
        return jsonify({"erro": "Não sei a ordem das colunas desta aba — nada foi gravado."}), 502
    if tw.muda_a_planilha(mudou, cab):
        # a conferência de conflito já foi feita acima, contra a leitura fresca; o `base` aqui
        # compararia com a linha CRUA (sem diário) e acusaria conflito em todo campo reposto
        tickets_escrita.gravar_linha(sheet_id, row, tw.linha_inteira(atual, mudou, cab), cab)
    aviso = ""
    try:
        # o RETRATO inteiro, não só o que mudou: dos registros de uma linha só o mais novo vale, e
        # um registro sem a OS faria o vínculo feito antes sumir da tela (ver retrato_para_diario)
        tickets_diario.registrar(aba, atual, tw.retrato_para_diario(atual, mudou, tickets_diario.CAMPOS),
                                 autor=(_conta() or {}).get("nome") or "")
    except Exception as e:                              # noqa: BLE001
        aviso = ("Gravado na planilha, mas não consegui registrar no diário (%s). "
                 "Se o sync desfizer esta edição, ela não volta sozinha." % e)
    return jsonify({"ok": True, "mensagem": tw.mensagem_salvo(mudou, atual),
                    "aviso": aviso, "campos": sorted(mudou)})


# ── EXCLUIR ──────────────────────────────────────────────────────────────────────────────────
@bp.route("/api/tickets/<aba>/<int:row>/excluir", methods=["POST"])
@exige_sessao
def api_excluir(aba, row):
    """Apaga a linha do banco. As DUAS confirmações são da tela; aqui fica a trava que ela não tem.

    A TRAVA É A IMPRESSÃO DA LINHA. A tela manda a usina+ativo que ela mostrava, e o servidor
    confere contra a linha RELIDA agora. Se alguém apagou uma linha acima nesse meio-tempo, os
    números descem — e "apagar a linha 101" apagaria a ocorrência de baixo, que ninguém escolheu.
    É o mesmo critério com que o diário decide se um registro ainda é da mesma ocorrência."""
    if aba not in tickets_spec.ABAS:
        return jsonify({"erro": tw.ERRO_ABA % aba}), 400
    if not _pode_gravar():
        return jsonify({"erro": "Falta a credencial de escrita nesta máquina — a tela está só "
                                "em leitura."}), 403
    corpo = request.get_json(silent=True) or {}
    esperada = str(corpo.get("impressao") or "").strip()
    if not esperada:
        return jsonify({"erro": "Sem a identificação da ocorrência — reabra o painel."}), 400
    sheet_id = tickets_spec.ABAS[aba]["sheet_id"]
    try:
        atual = _ler_com_diario(aba, sheet_id, row)
    except Exception as e:                              # noqa: BLE001
        return jsonify({"erro": "Não consegui reler a linha %s: %s" % (row, e)}), 502
    if tickets_diario.impressao(aba, atual) != esperada:
        return jsonify({"erro": tw.ERRO_LINHA_MUDOU}), 409
    tickets_escrita.apagar_linha(sheet_id, row)
    return jsonify({"ok": True, "mensagem": "Ocorrência apagada (linha %s)." % row})


# ── VINCULAR OS ──────────────────────────────────────────────────────────────────────────────
@bp.route("/api/tickets/buscar-os")
@exige_sessao
def api_buscar_os():
    """As OS cujo número contém o que foi digitado — a mesma busca do app (`buscar_os_pai`)."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"resultados": []})
    return jsonify({"resultados": [{"folio": x.get("folio"), "descricao": x.get("descricao"),
                                    "responsavel": x.get("responsavel"), "data": x.get("data")}
                                   for x in (api.buscar_os_pai(q, limit=12) or [])]})


@bp.route("/api/tickets/os/<int:folio>")
@exige_sessao
def api_os_do_ticket(folio):
    """A OS escolhida: a data de CRIAÇÃO (vira o "Início do chamado") e o status (dá o padrão do
    "Status do ticket"). Numa chamada à parte porque a busca não traz nenhum dos dois — o que ela
    traz é a data do SERVIÇO, e na OS 9208 são cinco dias de diferença (medido em 31/08)."""
    w = api.os_por_folio(folio)
    if not w:
        return jsonify({"erro": "Não achei a OS %s no Fracttal." % folio}), 404
    status = {1: "Em Processo", 2: "Em Verificação", 3: "Concluída", 4: "Cancelada"}.get(
        w.get("id_status_work_order"), "")
    criada = tw.para_iso(api.fmt_data_br(w.get("creation_date"))) if w.get("creation_date") else ""
    return jsonify({"folio": str(folio), "status": status, "criada": criada,
                    "criada_input": tw.para_input(criada),
                    "status_ticket_padrao": tw.status_ao_vincular("", status)})


# ── TROCAR A USINA ───────────────────────────────────────────────────────────────────────────
@bp.route("/api/tickets/usinas")
@exige_sessao
def api_usinas_fracttal():
    """As usinas do cadastro do Fracttal, com o NOME que vai para a planilha (`curto`)."""
    return jsonify({"usinas": tw.usinas_do_catalogo(api.load_assets_cached())})


@bp.route("/api/tickets/<aba>/usina-escopo")
@exige_sessao
def api_usina_escopo(aba):
    """Quantas linhas mudam, e a pergunta a fazer ANTES de mexer em qualquer uma."""
    if aba not in tickets_spec.ABAS:
        return jsonify({"erro": tw.ERRO_ABA % aba}), 400
    antigo = (request.args.get("antigo") or "").strip()
    novo = (request.args.get("novo") or "").strip()
    ocs, ocultas = tw.montar(tickets_api.listar_linhas(tickets_spec.ABAS[aba]["sheet_id"]))
    esc = tw.escopo_da_usina(ocs, ocultas, antigo)
    return jsonify(dict(esc, pergunta=tw.pergunta_usina(antigo, novo, esc), lote=tw.LOTE_USINA))


@bp.route("/api/tickets/<aba>/renomear-usina", methods=["POST"])
@exige_sessao
def api_renomear_usina(aba):
    """Um LOTE da troca de usina: até LOTE_USINA linhas por chamada, e a tela mostra o avanço.

    · o nome novo tem de EXISTIR no cadastro do Fracttal — sem isso esta rota escreveria qualquer
      texto na coluna Usina de dezenas de linhas;
    · cada linha vai INTEIRA no PUT, só com a Usina trocada, a partir de um retrato relido agora;
    · a linha que já não tem o nome antigo é pulada e contada, não sobrescrita: alguém a mudou;
    · uma falha não derruba as outras — a lista volta para a tela dizer quais ficaram."""
    if aba not in tickets_spec.ABAS:
        return jsonify({"erro": tw.ERRO_ABA % aba}), 400
    if not _pode_gravar():
        return jsonify({"erro": "Falta a credencial de escrita nesta máquina — a tela está só "
                                "em leitura."}), 403
    corpo = request.get_json(silent=True) or {}
    antigo = str(corpo.get("antigo") or "").strip()
    novo = str(corpo.get("novo") or "").strip()
    try:
        linhas = [int(x) for x in (corpo.get("linhas") or [])][:tw.LOTE_USINA]
    except (TypeError, ValueError):
        return jsonify({"erro": "Lista de linhas inválida."}), 400
    if not antigo or not novo or novo == antigo or not linhas:
        return jsonify({"erro": "Nada a trocar."}), 400
    nomes = {u["curto"] for u in tw.usinas_do_catalogo(api.load_assets_cached())}
    if novo not in nomes:
        return jsonify({"erro": "“%s” não é uma usina do cadastro do Fracttal." % novo}), 400
    sheet_id = tickets_spec.ABAS[aba]["sheet_id"]
    cab = tickets_api.cabecalho_vivo(sheet_id) or tickets_api.cabecalho_de(sheet_id)
    if not cab:
        return jsonify({"erro": "Não sei a ordem das colunas desta aba — nada foi gravado."}), 502
    retrato = {l.get("_row"): l for l in tickets_api.listar_linhas(sheet_id)}
    corrigidas, falhas = [], []
    for row in linhas:
        l = retrato.get(row)
        if not l or str(l.get("Usina") or "").strip() != antigo:
            falhas.append({"linha": row, "erro": "a linha já não tem o nome “%s”" % antigo})
            continue
        dados = {c: l.get(c) for c in cab if str(c or "").strip()}
        dados["Usina"] = novo
        try:
            tickets_escrita.gravar_linha(sheet_id, row, dados, cab, base={"Usina": antigo},
                                         ler=lambda _sid, r: retrato.get(r) or {})
            corrigidas.append(row)
        except Exception as e:                          # noqa: BLE001 — as outras seguem
            falhas.append({"linha": row, "erro": str(e)[:160]})
    return jsonify({"ok": True, "corrigidas": corrigidas, "falhas": falhas})

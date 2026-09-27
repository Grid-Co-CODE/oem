# os_creator/os_web/acomp_web.py
"""Acompanhamento de chamados (Levi, 27/09/2026): o quadro das OS de acompanhamento e a tela de cada uma. PURO — sem
Flask e sem rede; as rotas moram em `rotas_acomp.py`.

O QUE É A OS DE ACOMPANHAMENTO (a "OS 3" do chamado de garantia; ver app-campo-docs/notas-e-os-administrativa.html):
ninguém cria na mão. Quando o técnico fecha a inspeção do chamado no App de Campo, o servidor do App cria sozinho a OS
"[Ativo] - Acompanhamento de chamado <marca>" — tipo Administrativa, etiqueta CHAMADOS, filha da inspeção, no nome
da equipe de chamados — com as respostas do técnico na NOTA e UMA subtarefa: o nº do ticket aberto no fornecedor.

AS TRÊS COLUNAS saem da própria OS, sem estado paralelo em lugar nenhum:
    Chegaram       em processo e a subtarefa do ticket ainda vazia — é a fila da Singrid
    Ticket aberto  a subtarefa do ticket preenchida — o chamado está com o fornecedor
    Finalizados    a OS concluída (ou em verificação), nos últimos 90 dias
Cancelada fica fora do quadro (e é contada, para ninguém achar que sumiu).
"""
from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata

import chamado_insp_spec as ci
import chamado_modelos_store as modelos

BRT = dt.timezone(dt.timedelta(hours=-3))
MARCA_NOTA = "[CHAMADO] Acompanhamento"
DIAS_FINALIZADOS = 90

# o nome técnico do campo (o que a nota traz) → como a tela chama. É esse nome que liga a resposta do técnico ao campo
# do formulário do fornecedor — por isso ele continua visível, pequeno, embaixo do rótulo.
ROTULO = {"problema": "Descrição do problema", "acoes": "Ações já realizadas", "serial": "Nº de série",
          "modelo": "Modelo", "alarme": "ID do alarme", "tag": "TAG na usina", "tipo_equip": "Componente com falha",
          "mac": "Nº de MAC", "testes": "Testes e valores medidos", "serial_dl": "Nº de série do datalogger",
          "op_desde": "Em operação desde", "evidencias": "Fotos da instalação", "titulo_ch": "Objetivo do chamado",
          "gw_id": "ID do Gateway", "tracker_id": "IDs dos rastreadores", "produto": "Produto (catálogo Sungrow)",
          "posicao": "Posição do sensor", "acessorios": "Acessórios"}
MONO = {"serial", "mac", "modelo", "serial_dl", "gw_id", "tracker_id", "alarme"}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def agora_brt() -> dt.datetime:
    """Agora em Brasília, SEM fuso no objeto (as contas de dia são todas em horário local)."""
    return dt.datetime.now(BRT).replace(tzinfo=None, microsecond=0)


def utc_para_brt(iso):
    """'2026-09-03T11:25:36' (UTC, como o Fracttal devolve) → datetime de Brasília sem fuso. Vazio/estragado → None."""
    s = str(iso or "").strip().replace(" ", "T")[:19]
    if len(s) < 19:
        return None
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S") - dt.timedelta(hours=3)
    except ValueError:
        return None


def brt_iso(iso):
    """'2026-09-26T09:12:05-03:00' (a data das observações, já em Brasília) → datetime sem fuso."""
    try:
        d = dt.datetime.fromisoformat(str(iso or "").strip())
    except ValueError:
        return None
    return d.astimezone(BRT).replace(tzinfo=None) if d.tzinfo else d


def dias(de, ate) -> int | None:
    if de is None or ate is None:
        return None
    return max(0, (ate.date() - de.date()).days)


# ── a OS 3 e a nota dela ──────────────────────────────────────────────────────────────────────────────────────
def eh_os3(l: dict) -> bool:
    """A OS de acompanhamento, e não as 55 antigas com a etiqueta CHAMADOS (modelo de antes, etiqueta colada numa OS
    qualquer). O bloco da nota é o sinal forte; o título + tipo Administrativa cobrem nota vazia."""
    if MARCA_NOTA in str(l.get("note") or ""):
        return True
    return "acompanhamento de chamado" in _norm(l.get("descricao")) and "administrativa" in _norm(l.get("tipo_tarefa"))


def _perguntas() -> list:
    """Os textos de pergunta que a nota pode trazer em "Demais respostas" — do modelo em vigor e do código (a nota foi
    montada pelo App, que usa a cópia DELE do pacote). Do mais longo ao mais curto, para casar o mais específico."""
    blocos = [ci.BASE, modelos._ORIG["BASE"]]
    for d in (ci.POR_TIPO, modelos._ORIG["POR_TIPO"], ci.POR_FABRICANTE, modelos._ORIG["POR_FABRICANTE"]):
        blocos += list(d.values())
    return sorted({s["desc"] for b in blocos for s in b if s.get("desc")}, key=len, reverse=True)


def ler_nota(nota: str) -> dict:
    """A nota da OS 3 de volta em partes: marca e tipo, a cadeia (OS de campo → inspeção → ativo), a data da falha, os
    campos do formulário do fornecedor e as demais respostas.

    A pergunta das "Demais respostas" é casada contra o texto do modelo, porque ela mesma tem ':' ("Localização na
    planta: fileira, posição e nº dos trackers afetados: Tracker 40") — partir no primeiro ':' cortaria a pergunta."""
    out = {"marca": "", "tipo": "", "os_campo": "", "inspecao": "", "ativo": "", "data_falha": "", "menos7_nota": None,
           "campos": [], "demais": []}
    txt = str(nota or "")
    i = txt.find(MARCA_NOTA)
    if i < 0:
        return out
    linhas = txt[i:].split("\n")
    m = re.match(r"\[CHAMADO\] Acompanhamento\s+—\s+(.+?)\s+·\s+(.+)$", linhas[0].strip())
    if m:
        out["marca"], out["tipo"] = m.group(1).strip(), m.group(2).strip()
    perguntas = None
    modo = ""
    for l in linhas[1:]:
        s = l.strip()
        if not s:
            continue
        if s.startswith("OS de campo:"):
            for k, rx in (("os_campo", r"OS de campo:\s*(\d+)"), ("inspecao", r"Inspeção:\s*(\d+)"),
                          ("ativo", r"Ativo:\s*(\S+)")):
                mm = re.search(rx, s)
                out[k] = mm.group(1) if mm else ""
        elif s.startswith("Data da falha:"):
            mm = re.search(r"Data da falha:\s*(\d{2}/\d{2}/\d{4}(?: \d{2}:\d{2})?)", s)
            out["data_falha"] = mm.group(1) if mm else ""
            mm = re.search(r"Menos de 7 dias:\s*(Sim|Não)", s)
            out["menos7_nota"] = (mm.group(1) == "Sim") if mm else None
        elif s.startswith("Campos do formulário"):
            modo = "campos"
        elif s.startswith("Demais respostas"):
            modo = "demais"
        elif modo == "campos":
            k, _, v = s.partition(":")
            k = k.strip()
            out["campos"].append({"chave": k, "rotulo": ROTULO.get(k, k), "valor": v.strip(), "mono": k in MONO})
        elif modo == "demais":
            perguntas = perguntas or _perguntas()
            p = next((q for q in perguntas if s.startswith(q + ":")), None)
            if p:
                out["demais"].append({"pergunta": p, "resposta": s[len(p) + 1:].strip()})
            else:
                k, _, v = s.partition(":")
                out["demais"].append({"pergunta": k.strip(), "resposta": v.strip()})
    return out


def marca_do_titulo(titulo: str) -> str:
    m = re.search(r"Acompanhamento de chamado\s+(.+)$", str(titulo or "").strip())
    return m.group(1).strip() if m else ""


def menos_7d(data_falha: str, hoje: dt.datetime) -> dict:
    """"Menos de 7 dias" RECALCULADO hoje. A nota congela o que valia no fechamento da inspeção; o formulário da Huawei
    pergunta no dia em que a Singrid abre o ticket (13926: a nota diz Sim, nove dias depois já é Não)."""
    try:
        f = dt.datetime.strptime(str(data_falha or "").strip()[:16], "%d/%m/%Y %H:%M")
    except ValueError:
        try:
            f = dt.datetime.strptime(str(data_falha or "").strip()[:10], "%d/%m/%Y")
        except ValueError:
            return {"sim": None, "dias": None}
    d = max(0, (hoje - f).days)
    return {"sim": d < ci.DIAS_DOA, "dias": d}


def item_do_ticket(subtarefas) -> dict | None:
    """A subtarefa do nº do ticket na lista do `get_os_detalhes` (a OS 3 tem só ela; casa pelo texto)."""
    for s in subtarefas or []:
        d = _norm(s.get("descricao"))
        if "ticket" in d or "protocolo" in d:
            return s
    return None


def texto_ticket(novo: str, antigo: str) -> str:
    antigo = str(antigo or "").strip()
    return ("Ticket alterado: %s → %s" % (antigo, novo)) if antigo else ("Ticket registrado: %s" % novo)


def equipe() -> tuple:
    """(id, nome) da equipe de chamados no Fracttal — o MESMO padrão do servidor do App (CHAMADO_RESP_ID/NOME, v198).

    Vem do .env (`OS_WEB_CHAMADO_RESP_ID`, `OS_WEB_CHAMADO_RESP_NOME`) e não do código: o repositório é público e não leva
    nome nem id de gente. Lido a cada chamada, e não no import, porque o .env só entra quando o `api` é importado."""
    try:
        rid = int(os.environ.get("OS_WEB_CHAMADO_RESP_ID") or 0)
    except ValueError:
        rid = 0
    return rid, " ".join((os.environ.get("OS_WEB_CHAMADO_RESP_NOME") or "").split())


def da_equipe(l: dict) -> bool:
    """A OS está no nome da equipe de chamados? Pelo id quando a linha traz; pelo nome quando não.

    Sem a equipe no .env, ninguém é "de fora": o aviso de OS no nome de outra pessoa só vale quando se sabe quem é a
    equipe — acusar todas as OS do quadro seria um alarme falso em cada card."""
    rid, nome = equipe()
    if not rid and not nome:
        return True
    try:
        if rid and l.get("id_atribuido") not in (None, ""):
            return int(l["id_atribuido"]) == rid
    except (TypeError, ValueError):
        pass
    return bool(nome) and _norm(l.get("atribuido_a")) == _norm(nome)


def coluna(status_id, ticket) -> str:
    if status_id == 4:
        return ""                                         # cancelada: fora do quadro
    if status_id in (2, 3):
        return "fim"
    return "ticket" if str(ticket or "").strip() else "chegou"


def local_txt(cliente, usina) -> str:
    return " · ".join(x for x in (str(cliente or "").strip(), str(usina or "").strip()) if x and x != "—")


def _quando_txt(n: int | None, jeito: str) -> str:
    if n is None:
        return ""
    if jeito == "chegou":
        return "chegou hoje" if n == 0 else ("chegou há 1 dia" if n == 1 else "chegou há %d dias" % n)
    return "atualizado hoje" if n == 0 else ("há 1 dia sem atualização" if n == 1 else "há %d dias sem atualização" % n)


def urgencia(col: str, n: int | None) -> str:
    """A cor do tempo segue o SEMÁFORO. Chegou: a fila é nossa, e 8 dias parada já é vermelho. Ticket aberto: é a
    régua da cobrança — a planilha tinha mediana de 22 dias sem atualização, 75% passando de 15."""
    if n is None or col == "fim":
        return "m"
    if col == "chegou":
        return "r" if n >= 8 else ("a" if n >= 3 else "m")
    if n == 0:
        return "g"
    return "r" if n >= 16 else ("a" if n >= 8 else "m")


def cartao(l: dict, ticket, ultima_obs: str, hoje: dt.datetime, finalizado: str = "") -> dict:
    """Uma linha da lista do Fracttal + o ticket + a última observação → o que o card e a tela precisam.

    `finalizado` = quando a tela finalizou (do banco). A OS de acompanhamento é concluída sem registro de execução, e
    o Fracttal deixa a data de fim vazia nesse caso — então a data da finalização é a que diz "em 26/09"."""
    n = ler_nota(l.get("note"))
    chegou = utc_para_brt(l.get("data"))
    fim = utc_para_brt(l.get("data_fim")) or (brt_iso(finalizado) if finalizado else None)
    ult = brt_iso(ultima_obs) if ultima_obs else None
    referencia = max([x for x in (chegou, ult) if x is not None], default=None)
    col = coluna(l.get("status_id"), ticket)
    d_chegou, d_sem = dias(chegou, hoje), dias(referencia, hoje)
    marca = n["marca"] or marca_do_titulo(l.get("descricao"))
    c = {"id": l.get("id"), "folio": str(l.get("folio") or ""), "col": col, "status_id": l.get("status_id"),
         "status": l.get("status") or "", "ativo_nome": str(l.get("ativo") or "").strip() or n["ativo"],
         "code": n["ativo"], "cliente": l.get("cliente") or "", "usina": l.get("usina") or "",
         "local": local_txt(l.get("cliente"), l.get("usina")), "marca": marca, "tipo": n["tipo"] or l.get("tipo") or "",
         "inspecao": n["inspecao"], "os_campo": n["os_campo"], "data_falha": n["data_falha"],
         "ticket": str(ticket or "").strip(), "ticket_nao_lido": ticket is None,
         "chegou": chegou.strftime("%d/%m/%Y %H:%M") if chegou else "", "dias": d_chegou, "dias_sem": d_sem,
         # sem data nenhuma de fim (concluída direto no Fracttal, sem execução), a idade vem da chegada — senão a OS
         # nunca sairia da coluna dos 90 dias
         "fim": fim.strftime("%d/%m") if fim else "", "dias_fim": dias(fim or chegou, hoje),
         "responsavel": " ".join(str(l.get("atribuido_a") or "").split()), "da_equipe": da_equipe(l)}
    if col == "chegou":
        c["tempo"], c["urg"] = _quando_txt(d_chegou, "chegou"), urgencia(col, d_chegou)
        # a etiqueta do card: a coluna já diz "esperando ticket", o número basta
        c["tempo_curto"] = "" if d_chegou is None else ("hoje" if d_chegou == 0 else
                                                        ("1 dia" if d_chegou == 1 else "%d dias" % d_chegou))
    elif col == "ticket":
        c["tempo"], c["urg"] = _quando_txt(d_sem, "ticket"), urgencia(col, d_sem)
        c["tempo_curto"] = c["tempo"].replace("há ", "")
    else:
        c["tempo"], c["urg"] = ("em %s" % c["fim"]) if c["fim"] else "", "m"
        c["tempo_curto"] = c["tempo"]
    c["busca"] = _norm(" ".join(str(x or "") for x in (c["folio"], c["inspecao"], c["os_campo"], c["code"],
                                                          c["ativo_nome"], c["cliente"], c["usina"], marca,
                                                          c["ticket"], c["responsavel"])))
    return c


def precisa_ticket(l: dict, hoje: dt.datetime) -> bool:
    """Quem tem o ticket LIDO no Fracttal: as abertas e as finalizadas que ainda aparecem no quadro. A cota do Fracttal
    é por EMPRESA (200/min) — ler o ticket de OS que não vai para a tela seria gastar a dos outros."""
    st = l.get("status_id")
    if st in (1, 2):
        return True
    if st == 3:
        # sem data de fim (concluída sem execução) conta a chegada: lê de mais, nunca de menos
        d = dias(utc_para_brt(l.get("data_fim")) or utc_para_brt(l.get("data")), hoje)
        return d is None or d <= DIAS_FINALIZADOS
    return False


def montar_quadro(linhas, tickets: dict, ultimas: dict, hoje: dt.datetime, fins: dict = None) -> dict:
    fins = fins or {}
    cards = [cartao(l, tickets.get(l.get("id"), ""), (ultimas or {}).get(str(l.get("folio") or ""), ""), hoje,
                    fins.get(str(l.get("folio") or ""), "")) for l in (linhas or []) if eh_os3(l)]
    col = {"chegou": [], "ticket": [], "fim": []}
    canceladas = antigas = 0
    for c in cards:
        if not c["col"]:
            canceladas += 1
        elif c["col"] == "fim" and c["dias_fim"] is not None and c["dias_fim"] > DIAS_FINALIZADOS:
            antigas += 1
        else:
            col[c["col"]].append(c)
    # a mais parada primeiro nas duas filas de trabalho; a finalizada mais recente primeiro
    col["chegou"].sort(key=lambda c: (-(c["dias"] or 0), c["folio"]))
    col["ticket"].sort(key=lambda c: (-(c["dias_sem"] or 0), c["folio"]))
    col["fim"].sort(key=lambda c: ((c["dias_fim"] if c["dias_fim"] is not None else 9999), c["folio"]))
    vis = col["chegou"] + col["ticket"] + col["fim"]
    opc = lambda k: sorted({c[k] for c in vis if c[k]}, key=lambda x: _norm(x))     # noqa: E731
    return {"colunas": col, "n": {k: len(v) for k, v in col.items()}, "total": len(vis), "canceladas": canceladas,
            "antigas": antigas, "fora": sum(1 for c in vis if not c["da_equipe"]),
            # a régua da cobrança na faixa de números: quantas esperam ticket há mais de uma semana, e a mais antiga
            "mais_7": sum(1 for c in col["chegou"] if (c["dias"] or 0) > 7),
            "mais_antiga": col["chegou"][0] if col["chegou"] else None,
            "opcoes": {"marca": opc("marca"), "cliente": opc("cliente"), "tipo": opc("tipo")}}


def outros(c: dict, todos) -> dict:
    """Os outros chamados do MESMO ativo e os da MESMA OS de campo (a 13761 abriu dois: Inversor 1.4 e 1.1)."""
    ativo = [x for x in todos if x["folio"] != c["folio"] and c.get("code") and x.get("code") == c["code"]]
    campo = [x for x in todos if x["folio"] != c["folio"] and c.get("os_campo") and x.get("os_campo") == c["os_campo"]
             and x not in ativo]
    return {"ativo": ativo, "campo": campo}


def entrada(reg: dict) -> dict:
    """Uma observação do banco → uma entrada da linha do tempo."""
    q = brt_iso(reg.get("quando"))
    return {"d": q.strftime("%d/%m") if q else "", "a": q.strftime("%Y") if q else "", "texto": reg.get("texto") or "",
            "autor": " · ".join(x for x in (reg.get("quem") or "", q.strftime("%d/%m %H:%M") if q else "") if x),
            "ev": reg.get("tipo") in ("ticket", "finalizado"), "quando": reg.get("quando") or ""}


def linha_do_tempo(c: dict, obs) -> list:
    """As observações da mais nova para a mais antiga, com a chegada da OS no fim (ela nasceu antes de tudo). O verde é
    EXCLUSIVO da entrada mais recente — "é o que aconteceu por último" (revisão do design do 1B)."""
    chegada = {"d": (c["chegou"] or "")[:5], "a": (c["chegou"] or "")[6:10],
               "texto": "Chegou: a OS %s nasceu sozinha no fechamento da inspeção %s." % (c["folio"], c["inspecao"] or "—"),
               "autor": "App de Campo · %s" % c["chegou"] if c["chegou"] else "App de Campo", "ev": False, "quando": ""}
    # ordena do mais velho ao mais novo e VIRA: no empate (duas anotações no mesmo segundo — o ticket e a finalização
    # automáticos podem cair assim), a gravada depois fica em cima. `sorted(..., reverse=True)` manteria o empate na
    # ordem de gravação, e a finalização apareceria ABAIXO do ticket (visto na foto da bancada, 27/09).
    ordem = sorted(obs or [], key=lambda r: str(r.get("quando") or ""))
    lista = [entrada(r) for r in reversed(ordem)] + [chegada]
    for i, e in enumerate(lista):
        e["novo"] = i == 0 and len(lista) > 1
    return lista


def copiar_tudo(campos) -> str:
    return "\n".join("%s: %s" % (x["rotulo"], x["valor"]) for x in campos or [])

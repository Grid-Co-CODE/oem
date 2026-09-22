# os_creator/os_web/tickets_painel.py
"""O painel de acompanhamento dos tickets — PURO: sem Flask, sem rede.

Levi, 22/09/2026 (item 11 do lote): "Gostaria de um dashboard de acompanhamento dos tickets". O
mockup com dado real foi aprovado no mesmo dia ("Gostei do dashboard!") e está em
`docs/design/dashboard-tickets-mockup.html`.

AS OCORRÊNCIAS CHEGAM PRONTAS, do MESMO leitor da tela de Tickets (`rotas_tickets._carregar`):
diário aplicado, estado recalculado, cliente preenchido. Aqui só se conta. Contar a partir do banco
cru faria o "sem OS" deste painel discordar do da lista na primeira OS vinculada pelo app.

"ABERTA", AQUI, É TUDO O QUE NÃO ESTÁ ENCERRADO (Aberta, OS criada, Em verificação, A fechar): é o
passivo. O ciclo de vida inteiro aparece à parte, estado por estado.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
import unicodedata

import tickets_calc
import tickets_spec

from . import tickets_web as tw

SEMANAS = 12            # três meses de fluxo: dá para ver tendência sem achatar a última semana
TOP_USINAS = 10
MAX_CLIENTES = 8        # do nono em diante vira "outros": barra demais não se lê

# As faixas de idade. O corte em 30 dias é o do alarme da tela de Tickets (`tw.ALARME_DIAS`), e é
# ele que pinta a barra de vermelho — por isso a faixa diz se passou do alarme, e o JS só obedece.
FAIXAS = (("0-7", 0, 7), ("8-30", 8, 30), ("31-90", 31, 90), ("91-180", 91, 180),
          ("181-365", 181, 365), (">365", 366, None))

# O que o alerta diz quando os fechamentos param. Não cita data nem arquivo: a causa medida em 22/09
# (o Excel só sobe quando alguém roda o sync) é estrutural, e uma data escrita aqui ficaria velha.
TEXTO_CAUSA = ("Se a equipe fecha os tickets no Excel, o fechamento só chega aqui quando o sync da "
               "planilha roda. Fechar pela tela de Tickets grava direto no banco.")


def _data(v):
    d = tickets_calc._para_dt(v)
    return d.date() if d is not None else None


def _abertas(ocs: list) -> list:
    return [o for o in (ocs or []) if o.get("_estado") != "encerrada"]


def faixas(abertas: list) -> list:
    """Quantas abertas em cada faixa de idade. Sem Início legível a ocorrência fica FORA (e é
    contada à parte): pô-la em "0-7" diria que é nova, e ela pode ter um ano."""
    out = []
    for rotulo, lo, hi in FAIXAS:
        n = sum(1 for o in abertas if o.get("_dias") is not None
                and o["_dias"] >= lo and (hi is None or o["_dias"] <= hi))
        out.append({"rotulo": rotulo, "n": n, "alarme": lo > tw.ALARME_DIAS})
    return out


def semanas(ocs: list, hoje: dt.date, n: int = SEMANAS) -> list:
    """Quantas ocorrências COMEÇARAM e quantas TERMINARAM em cada uma das últimas `n` semanas.

    A semana termina HOJE, não no domingo: com a do calendário, numa terça a última barra teria
    dois dias e pareceria uma queda que não aconteceu. Conta todas as ocorrências da aba, abertas e
    encerradas — é o fluxo de entrada e de saída, não o estoque."""
    sem = [{"de": hoje - dt.timedelta(days=7 * k + 6), "ate": hoje - dt.timedelta(days=7 * k),
            "abertas": 0, "fechadas": 0} for k in range(n - 1, -1, -1)]
    for o in (ocs or []):
        for campo, chave in (("Início da ocorrência", "abertas"), ("Fim da ocorrência", "fechadas")):
            d = _data(o.get(campo))
            if d is None:
                continue
            k = (hoje - d).days // 7          # 0 = a semana que termina hoje
            if 0 <= (hoje - d).days and k < n:
                sem[n - 1 - k][chave] += 1
    return [{"de": w["de"].strftime("%d/%m"), "ate": w["ate"].strftime("%d/%m"),
             "abertas": w["abertas"], "fechadas": w["fechadas"]} for w in sem]


def _media(xs: list) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def alerta(sem: list):
    """{titulo, texto} quando as últimas semanas não têm NENHUM fechamento; None quando não há o
    que dizer.

    Compara com a MÉDIA das 4 semanas anteriores ao buraco, não com a última: uma semana fraca logo
    antes faria o buraco parecer normal. Duas semanas é o mínimo — uma só pode ser feriado."""
    if not sem:
        return None
    n = 0
    for w in reversed(sem):
        if w["fechadas"]:
            break
        n += 1
    if n < 2:
        return None
    if n == len(sem):
        if not any(w["abertas"] for w in sem):
            return None                       # aba parada dos dois lados: nada entra, nada sai
        return {"titulo": "Nenhuma ocorrência fechada nas últimas %d semanas" % n,
                "texto": TEXTO_CAUSA}
    antes = [w["fechadas"] for w in sem[:len(sem) - n][-4:]]
    media = _media(antes)
    if media < 1:
        return None                           # já não fechava quase nada: não é notícia
    ultima_com = sem[len(sem) - 1 - n]["ate"]
    texto = "Nas 4 semanas anteriores fechavam-se em média %d por semana." % round(media)
    entrada = _media([w["abertas"] for w in sem[-5:-1]])
    if entrada >= 5 and sem[-1]["abertas"] < entrada * 0.1:
        texto += (" E na última semana só entraram %d (a média era %d): a planilha pode ter parado "
                  "de ser alimentada." % (sem[-1]["abertas"], round(entrada)))
    return {"titulo": "Nenhuma ocorrência fechada há %d semanas — a última semana com fechamento "
                      "terminou em %s" % (n, ultima_com),
            "texto": texto + " " + TEXTO_CAUSA}


def clientes(abertas: list, aba: str) -> list:
    """[[cliente, ocorrências abertas, equipamentos parados]], do cliente com mais equipamento
    parado para o com menos. Do nono em diante vira uma barra "outros (N)"."""
    por = {}
    for o in abertas:
        c = o.get("_cliente") or tw.SEM_CLIENTE
        g = por.setdefault(c, [c, 0, 0])
        g[1] += 1
        g[2] += tw.qtd_de(o, aba)
    lst = sorted(por.values(), key=lambda g: (-g[2], -g[1], g[0].lower()))
    if len(lst) > MAX_CLIENTES:
        resto = lst[MAX_CLIENTES - 1:]
        lst = lst[:MAX_CLIENTES - 1] + [["outros (%d)" % len(resto), sum(g[1] for g in resto),
                                         sum(g[2] for g in resto)]]
    return lst


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


_NUMERAL = re.compile(r"\b(\d+|i{1,3}|iv|v)\b")         # "tem número": 2, II, IV
_RADICAL = re.compile(r"\b(\d+|i{1,3}|iv|v|e)\b")       # sai do radical: número e o "e" de "1 e 2"


def _pl(n: int, singular: str, plural: str) -> str:
    return "%d %s" % (n, singular if n == 1 else plural)


def grafias_duplicadas(abertas: list, aba: str) -> list:
    """Pares de nomes que parecem a MESMA usina escrita de dois jeitos: [[a, qtd_a, b, qtd_b]], com
    os equipamentos parados de cada grafia.

    A régua é conservadora de propósito, porque "Ibaté 1" e "Ibaté 2" são usinas diferentes. Dois
    nomes com o mesmo radical (sem acento, sem número) só viram par quando diferem APENAS em acento
    ou caixa ("Santarem 1 e 2" × "Santarém 1 e 2"), ou quando um deles NÃO tem número
    ("Macaíba" × "Macaiba 1"). Medido em 22/09 contra as abertas: acha esses dois e nenhum falso —
    Araçoiaba da Serra 1/2, Alto Paraná 1/2, Ibaté 1/2, Coração 1/2 e Santarém 1/2 ficam de fora."""
    cont = {}
    for o in abertas:
        u = str(o.get("Usina") or "").strip()
        if u:
            cont[u] = cont.get(u, 0) + tw.qtd_de(o, aba)
    grupos = {}
    for u in cont:
        grupos.setdefault(" ".join(_RADICAL.sub(" ", _sem_acento(u)).split()), []).append(u)
    pares = []
    for nomes in grupos.values():
        nomes = sorted(nomes, key=lambda x: (-cont[x], x))
        for i, a in enumerate(nomes):
            for b in nomes[i + 1:]:
                so_acento = " ".join(_sem_acento(a).split()) == " ".join(_sem_acento(b).split())
                sem_numero = bool(_NUMERAL.search(_sem_acento(a))) != bool(_NUMERAL.search(_sem_acento(b)))
                if so_acento or sem_numero:
                    pares.append([a, cont[a], b, cont[b]])
    return pares


def qualidade(abertas: list, r: dict, aba: str) -> list:
    """O que impede o painel de contar certo — cada item com o NÚMERO em destaque e, quando há, o
    filtro da tela de Tickets que mostra essas ocorrências. [{destaque, texto, filtro}]."""
    itens = []
    n = len(abertas)
    if n:
        # o filtro "Aberta" da tela de Tickets É o "sem OS": aberta = sem OS e sem Fim
        if r["sem_os"] == n == 1:
            itens.append({"destaque": "A única aberta", "texto": " não tem OS vinculada — a tela de "
                          "Tickets permite vincular.", "filtro": {"estado": "aberta"}})
        elif r["sem_os"] == n:
            itens.append({"destaque": "Nenhuma", "texto": " das %s tem OS vinculada — o número da OS "
                          "mora só no diário; a tela de Tickets permite vincular."
                          % _pl(n, "aberta", "abertas"), "filtro": {"estado": "aberta"}})
        elif r["sem_os"]:
            itens.append({"destaque": "%d de %d" % (r["sem_os"], n),
                          "texto": " abertas sem OS vinculada — a tela de Tickets permite vincular.",
                          "filtro": {"estado": "aberta"}})
    if r["sem_cliente"]:
        us = len({str(o.get("Usina") or "").strip() for o in abertas if o.get("_cliente") == tw.SEM_CLIENTE})
        itens.append({"destaque": _pl(r["sem_cliente"], "aberta", "abertas"),
                      "texto": ", em %s, sem cliente em lugar nenhum da planilha." % _pl(us, "usina", "usinas"),
                      "filtro": {"cliente": tw.SEM_CLIENTE}})
    if r["sem_inicio"]:
        itens.append({"destaque": _pl(r["sem_inicio"], "aberta", "abertas"),
                      "texto": " sem data de início — a idade não é calculável e fica fora da mediana "
                               "e das faixas.", "filtro": None})
    if r["inicio_futuro"]:
        itens.append({"destaque": _pl(r["inicio_futuro"], "aberta", "abertas"),
                      "texto": " com início depois de hoje — data digitada errada.", "filtro": None})
    rotulo = tw.ROTULO_QTD.get(aba, "equipamentos parados")
    for a, qa, b, qb in grafias_duplicadas(abertas, aba):
        itens.append({"destaque": "“%s” e “%s”" % (a, b),
                      "texto": " (%d e %d %s) parecem a mesma usina escrita de dois jeitos."
                               % (qa, qb, rotulo), "filtro": None})
    return itens


def resumo(ocs: list, aba: str, agora=None) -> dict:
    """Tudo o que o painel desenha para UMA aba."""
    agora = agora or dt.datetime.now()
    hoje = agora.date()
    ab = _abertas(ocs)
    dias = [o["_dias"] for o in ab if o.get("_dias") is not None]
    sem_data = {id(o) for o in ab if tickets_calc._para_dt(o.get("Início da ocorrência")) is None}
    fechadas_30d = 0
    for o in (ocs or []):
        f = _data(o.get("Fim da ocorrência"))
        if f is not None and 0 <= (hoje - f).days < 30:
            fechadas_30d += 1
    sem = semanas(ocs, hoje)
    r = {
        "aba": aba,
        "rotulo_qtd": tw.ROTULO_QTD.get(aba, "equipamentos parados"),
        "total": len(ocs or []),
        "abertas": len(ab),
        "qtd": sum(tw.qtd_de(o, aba) for o in ab),
        "sem_os": sum(1 for o in ab if not str(o.get("OS") or "").strip()),
        "mais_30": sum(1 for o in ab if tw.alarme(o)),
        "mediana_dias": int(round(statistics.median(dias))) if dias else None,
        "sem_inicio": len(sem_data),
        # Início legível mas no futuro: `dias_desde` devolve None e ela sumiria das faixas sem aviso
        "inicio_futuro": sum(1 for o in ab if o.get("_dias") is None and id(o) not in sem_data),
        "fechadas_30d": fechadas_30d,
        "sem_cliente": sum(1 for o in ab if o.get("_cliente") == tw.SEM_CLIENTE),
        "estados": tw.placar(ocs),
        "faixas": faixas(ab),
        "clientes": clientes(ab, aba),
        "top": [[g["usina"], g["cliente"], g["qtd"], g["n_abertas"]]
                for g in tw.agrupar(ab, aba)[:TOP_USINAS]],
        "semanas": sem,
        "alerta": alerta(sem),
    }
    r["qualidade"] = qualidade(ab, r, aba)
    return r


def estados_def() -> list:
    """[[chave, rótulo, cor]] na ordem do ciclo de vida — o JS desenha nesta ordem."""
    return [[k, rot, cor] for k, rot, cor in tickets_spec.ESTADOS]

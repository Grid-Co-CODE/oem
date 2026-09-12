# os_creator/os_web/perf_web.py
"""Regras da aba Performance na web — as MESMAS do `steps/performance.py`, sem Qt.

Cascata Cliente -> Usina pela carteira real (o campo `cliente` do ativo E o prefixo da usina, porque o Fracttal
diverge entre os dois: "Ultragaz" x "Utragaz - Ibirapuã 1 e 2 - BA"), ativos com o plano pelo `api.get_performance_alvos`,
nome '[Ativo] - base' pelo `api.perf_os_nome`, título literal para ETM e Usina, e a criação de UMA OS POR ATIVO pelo
`api.create_performance_os` com o mesmo payload que o app monta em `PerfCriar._criar`.

Constantes copiadas do app de propósito (o módulo de lá é Qt); `tests/test_os_web_fidelidade.py` acusa divergência."""
from __future__ import annotations
import datetime as dt

import api

FRASE_COLETA = "coleta de dados de geracao"
# (titulo, frase do plano no Fracttal, icone, badge, subtitulo) — mesma ordem da grade do app
PLANOS = [
    {"titulo": "Geração e ETM", "frase": FRASE_COLETA, "icone": "activity", "badge": "Inversor · ETM",
     "sub": "Geração por inversor • ou coleta e análise da estação meteorológica"},
    {"titulo": "Inspeção Geral do Inversor", "frase": "inspecao geral do inversor", "icone": "searchcheck", "badge": "Inversor",
     "sub": "Checklist completo • conexões • alarmes • temperatura • strings"},
    {"titulo": "Recomposição de String", "frase": "recomposicao de string", "icone": "zap", "badge": "Inversor",
     "sub": "Diagnóstico e normalização de string sem corrente"},
    {"titulo": "Verificação de Tracker Parado", "frase": "verificacao de tracker parado", "icone": "alert", "badge": "Trackers",
     "sub": "Tracker travado • fim de curso • alinhamento"},
]
USINA_TITULO = "[Usina] - Coleta e análise de dados de geração"   # título LITERAL, como o ETM
ETM_TITULO = "[ETM] - Coleta e análise de dados"                  # título LITERAL, sem o prefixo [Ativo]
ETM_ETIQUETAS = ("ENGENHARIA",)                                    # somadas à PERFORMANCE, que já é padrão
# Tipos de EQUIPAMENTO de planta — decidem quais clientes/usinas são "reais" (o catálogo tem inventário/material)
CARTEIRA_EQUIP = frozenset({"Inversor", "Cabine", "Tracker", "Estrutura Trackers", "Estação Meteorológica", "Skid"})
ETM_TIPO = "Estação Meteorológica"
USINA_TIPO = "Usina"                                               # o item-usina, a planta como ativo
MODOS = (("geracao", "Geração"), ("usina", "Usina"), ("etm", "ETM"))
BRT = dt.timezone(dt.timedelta(hours=-3))


def plano_por_frase(frase: str):
    fn = api._norm_txt(frase)
    return next((p for p in PLANOS if api._norm_txt(p["frase"]) == fn), None)


def tem_modos(frase: str) -> bool:
    """Só o card 'Geração e ETM' abre em três modos (Geração / Usina / ETM)."""
    return api._norm_txt(frase) == FRASE_COLETA


def eh_tracker(frase: str) -> bool:
    return "tracker" in api._norm_txt(frase)


def coluna_qtd(frase: str) -> str:
    return "Trackers" if eh_tracker(frase) else "Strings"


def aba_ticket(frase: str) -> str:
    """A aba de tickets que o plano alimenta no app ('' = plano que não gera ocorrência). Best-effort."""
    try:
        import tickets_nasce
        return tickets_nasce.aba_do_plano(frase) or ""
    except Exception:                                   # noqa: BLE001 — sem o módulo de tickets, sem coluna
        return ""


# ── cascata (espelho de PerfCriar._carteira*, _fill_clientes, _fill_usinas, _cliente_da_usina) ──
def carteira(usina: str) -> str:
    return (usina or "").split(" - ", 1)[0].strip()


def carteiras_de(a: dict) -> set:
    out = set()
    c = (a.get("cliente") or "").strip()
    if c:
        out.add(c)
    u = a.get("usina") or ""
    if " - " in u and carteira(u):
        out.add(carteira(u))
    return out


def clientes_reais(assets: list) -> set:
    return {a.get("cliente") for a in assets if a.get("tipo") in CARTEIRA_EQUIP and a.get("cliente")}


def usinas_para(assets: list, cliente: str | None) -> list:
    reais = clientes_reais(assets)
    base = [a for a in assets if a.get("usina") and a.get("tipo") in CARTEIRA_EQUIP and (carteiras_de(a) & reais)]
    if cliente:
        return sorted({a["usina"] for a in base if cliente in carteiras_de(a)})
    return sorted({a["usina"] for a in base})


def cliente_da_usina(assets: list, usina: str) -> str:
    for a in assets:
        if a.get("usina") == usina and (a.get("cliente") or "").strip():
            return a["cliente"].strip()
    return carteira(usina)


def ativos_da_usina(assets: list, usina: str, frase: str) -> list:
    """Os ativos da usina que o plano pode ter: PERF_TIPOS e, só no card de coleta, o item-usina (modo Usina)."""
    tipos = tuple(api.PERF_TIPOS) + ((USINA_TIPO,) if tem_modos(frase) else ())
    return [a for a in assets if a.get("usina") == usina and a.get("tipo") in tipos]


# ── resumo do plano (espelho de PerfCriar._set_resumo) ───────────────────────
_CRIT = {i: n for (n, i) in api.CRITICIDADES}


def resumo_plano(plan: dict) -> str:
    plan = plan or {}
    partes = []
    tipo = (plan.get("tasks_types_main_description") or "").strip()
    c1 = (plan.get("tasks_types_description") or "").strip()
    c2 = (plan.get("tasks_types_2_description") or "").strip()
    crit = _CRIT.get(plan.get("id_priorities"))
    dur = int(plan.get("duration") or 0)
    if tipo:
        partes.append(f"Tipo: {tipo}")
    if c1:
        partes.append(f"Classif. 1: {c1}")
    if c2:
        partes.append(f"Classif. 2: {c2}")
    if crit:
        partes.append(f"Criticidade: {crit}")
    if dur:
        partes.append(f"Duração: {round(dur / 60)} min")
    return "  ·  ".join(partes) if partes else "Plano sem detalhes (confira no Fracttal)."


# ── criação (espelho de PerfCriar._criar / _criou) ───────────────────────────
def titulo_os(asset: dict, base: str, modo: str) -> str:
    """ETM e Usina têm título literal (pedido do Levi); o resto é '[Ativo] - base'."""
    if modo == "etm":
        return ETM_TITULO
    if modo == "usina":
        return USINA_TITULO
    return api.perf_os_nome(asset, base)


def data_brt(texto: str) -> dt.datetime:
    """'2026-09-12T01:10' (o que o <input type=datetime-local> manda) → aware em Brasília, como o app."""
    return dt.datetime.fromisoformat(str(texto)).replace(tzinfo=BRT)


def montar_itens(corpo: dict) -> tuple[list, dict, str]:
    """Do JSON da tela → (itens, kwargs do create_performance_os, erro). Mesma validação e mesmo payload do app;
    o que a web ainda não faz (tickets, imagens, agrupar) entra desligado, explicitamente."""
    corpo = corpo or {}
    itens_in = [it for it in (corpo.get("itens") or []) if isinstance(it, dict) and isinstance(it.get("asset"), dict)]
    if not itens_in:
        return [], {}, "Marque ao menos um ativo."
    resp = corpo.get("responsavel") or {}
    if not isinstance(resp, dict) or not resp.get("id_personnel"):
        return [], {}, "Escolha o responsável."
    modo = str(corpo.get("modo") or "geracao")
    base = (corpo.get("base") or "").strip()
    try:
        evt = data_brt(corpo.get("evento") or dt.datetime.now(BRT).strftime("%Y-%m-%dT%H:%M"))
        prog = data_brt(corpo["programada"]) if corpo.get("programada") else evt + dt.timedelta(minutes=10)
    except ValueError:
        return [], {}, "Data inválida."
    literal = ETM_TITULO if modo == "etm" else (USINA_TITULO if modo == "usina" else "")
    itens = []
    for it in itens_in:
        itens.append({"asset": it["asset"], "plano_id_task": it.get("plano_id_task"), "plano_id_item": it.get("plano_id_item"),
                      "linkar": bool(it.get("linkar", True)), "base": base, "note": (it.get("note") or "").strip(),
                      "gerar_ticket": False, "qtd_ticket": None,          # ocorrência em Tickets: só no app por ora
                      "titulo": literal, "os_pai": (str(it.get("os_pai") or "")).strip(), "imagens": []})
    kwargs = {"id_responsible": resp.get("id_personnel"), "responsible_name": resp.get("name") or "",
              "event_date": evt, "prog_date": prog,
              "etiquetas_extra": list(ETM_ETIQUETAS) if modo == "etm" else None}
    return itens, kwargs, ""


def mensagem_resultado(res: list) -> dict:
    """[{ok, asset, folio|erro}] → {'ok','falhas','mensagem'} com a frase do app."""
    res = res or []
    ok = [r for r in res if r.get("ok")]
    fail = [r for r in res if not r.get("ok")]
    if not ok:
        msg = "Nenhuma OS criada.\n" + "\n".join(f"• {r.get('asset')}: {r.get('erro')}" for r in fail[:8])
    else:
        folios = ", ".join(str(r.get("folio") or "?") for r in ok[:12])
        msg = f"{len(ok)} OS criada(s) — Nº {folios}" + (" …" if len(ok) > 12 else "") + "."
        if fail:
            msg += f"\n\n{len(fail)} falharam:\n" + "\n".join(f"• {r.get('asset')}: {r.get('erro')}" for r in fail[:6])
    erros_img = [e for r in ok for e in (r.get("img_erro") or [])]
    return {"ok": len(ok), "falhas": len(fail), "mensagem": msg, "folios": [r.get("folio") for r in ok],
            "detalhes": erros_img}


def contar_subtarefas(assets: list) -> dict:
    """{frase: [nomes das subtarefas]} de cada plano — espelho de `_contar_subtarefas` do app. Amostra: 1 ativo de
    cada tipo relevante (Inversor, Estação, tracker generalizado). Best-effort: plano não achado → fora do dict."""
    inv = next((a for a in assets if a.get("tipo") == "Inversor"), None)
    est = next((a for a in assets if a.get("tipo") == ETM_TIPO), None)
    trk = next((a for a in assets if api._eh_tracker_generalizado(a)), None)
    sample = [x for x in (inv, est, trk) if x]
    if not sample:
        return {}
    plans = api.get_plans_for_assets(sample)
    pares, frase_task = [], {}
    for entry in PLANOS:
        frase = entry["frase"]
        fn = api._norm_txt(frase)
        p = next((pl for pl in plans if fn in api._norm_txt(pl.get("description"))), None)
        if p and p.get("asset"):
            frase_task[frase] = p["id_task"]
            pares.append((p["id_task"], p["asset"]["id"]))
    nomes = api.get_subtask_names(pares)
    return {frase: nomes[tid] for frase, tid in frase_task.items() if nomes.get(tid) is not None}

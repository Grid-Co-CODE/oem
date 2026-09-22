# os_creator/os_web/perf_web.py
"""Regras da aba Performance na web — as MESMAS do `steps/performance.py`, sem Qt.

Cascata Cliente -> Usina pela carteira real (o campo `cliente` do ativo E o prefixo da usina, porque o Fracttal
diverge entre os dois: "Ultragaz" x "Utragaz - Ibirapuã 1 e 2 - BA"), ativos com o plano pelo `api.get_performance_alvos`,
nome '[Ativo] - base' pelo `api.perf_os_nome`, título literal para ETM e Usina, e a criação de UMA OS POR ATIVO pelo
`api.create_performance_os` com o mesmo payload que o app monta em `PerfCriar._criar`.

Constantes copiadas do app de propósito (o módulo de lá é Qt); `tests/test_os_web_fidelidade.py` acusa divergência."""
from __future__ import annotations
import datetime as dt
import re

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


def qtd_sugerida(frase: str, texto: str) -> dict:
    """Quantas ocorrências a linha de ticket vai registrar → {'qtd', 'via'}.

    SEM PORTAR A REGRA PARA O JAVASCRIPT: contar "PV/STR/String" no texto é regra medida, que já
    mora em `tickets_nasce.contar_strings` e vale para o app e para a web. Uma cópia em JS seria
    uma segunda verdade, e a primeira divergência apareceria numa planilha de produção.
    Tracker é sempre 1 por ativo — é o próprio tracker que está parado."""
    if eh_tracker(frase):
        return {"qtd": 1, "via": "tracker"}
    try:
        import tickets_nasce
        qtd, via, _nomes = tickets_nasce.contar_strings(texto or "")
        return {"qtd": int(qtd), "via": via}
    except Exception:                                   # noqa: BLE001
        return {"qtd": 1, "via": "presumido"}


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


# ── imagens anexadas na criação (Levi, 21/09) ────────────────────────────────────────────────
# O navegador manda base64; o `create_performance_os` quer bytes, no MESMO formato do app
# (`{'bytes','nome'}`), e é ele quem sobe para o S3 depois de a OS existir. Ou seja: a web não
# ganhou caminho de upload próprio — ela só passou a preencher um campo que já era lido.
MAX_IMG_ATIVO = 12                    # por ativo; acima disso é lote, e lote trava a criação
MAX_BYTES_IMG = 8 * 1024 * 1024       # 8 MB por imagem: foto de celular cabe, vídeo não
EXT_IMG = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")


def imagens_do_item(it: dict) -> tuple[list, str]:
    """[{nome, b64}] da tela → ([{'bytes','nome'}], erro).

    Erro em vez de descarte silencioso: a pessoa anexou a foto porque ela importa, e uma OS que
    nasce sem o anexo que alguém escolheu é pior do que uma criação que não acontece."""
    import base64
    brutas = [x for x in (it.get("imagens") or []) if isinstance(x, dict) and x.get("b64")]
    if not brutas:
        return [], ""
    quem = str((it.get("asset") or {}).get("label") or (it.get("asset") or {}).get("code") or "ativo")
    if len(brutas) > MAX_IMG_ATIVO:
        return [], "%s: %d imagens — o limite é %d por ativo." % (quem, len(brutas), MAX_IMG_ATIVO)
    out = []
    for x in brutas:
        # barra vira sublinhado: o nome entra na chave do S3 (".ot/<OS>/<nome>"), e uma "/" ali
        # abriria uma subpasta — ou, com "..", sairia da pasta da OS. A tela já troca; o servidor
        # não confia nela, porque o nome agora é digitado.
        nome = re.sub(r"[\\/]+", "_", str(x.get("nome") or "imagem.png").strip()) or "imagem.png"
        if not nome.lower().endswith(EXT_IMG):
            return [], "%s: '%s' não é imagem." % (quem, nome)
        try:
            dados = base64.b64decode(str(x.get("b64") or ""), validate=True)
        except Exception:                             # noqa: BLE001
            return [], "%s: não consegui ler '%s'." % (quem, nome)
        if not dados:
            return [], "%s: '%s' veio vazia." % (quem, nome)
        if len(dados) > MAX_BYTES_IMG:
            return [], ("%s: '%s' tem %.1f MB — o limite é %d MB por imagem."
                        % (quem, nome, len(dados) / 1048576.0, MAX_BYTES_IMG // 1048576))
        out.append({"bytes": dados, "nome": nome})
    return out, ""


def _qtd_ou_none(v):
    """O número que a pessoa escreveu no card, ou None para o `nascer_ticket` contar sozinho."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def montar_itens(corpo: dict) -> tuple[list, dict, str]:
    """Do JSON da tela → (itens, kwargs do create_performance_os, erro). Mesma validação e mesmo payload do app;
    o que a web ainda não faz (tickets, agrupar) entra desligado, explicitamente. As IMAGENS a web
    já manda desde 21/09."""
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
        imgs, err = imagens_do_item(it)
        if err:
            return [], {}, err
        itens.append({"asset": it["asset"], "plano_id_task": it.get("plano_id_task"), "plano_id_item": it.get("plano_id_item"),
                      "linkar": bool(it.get("linkar", True)), "base": base, "note": (it.get("note") or "").strip(),
                      # a caixa "Gerar ticket" da tela e o número editável ao lado do ativo — o
                      # `nascer_ticket` conta sozinho quando `qtd_ticket` vem vazio (Levi, 21/09)
                      "gerar_ticket": bool(corpo.get("gerar_ticket", True)),
                      "qtd_ticket": _qtd_ou_none(it.get("qtd_ticket")),
                      "titulo": literal, "os_pai": (str(it.get("os_pai") or "")).strip(), "imagens": imgs})
    kwargs = {"id_responsible": resp.get("id_personnel"), "responsible_name": resp.get("name") or "",
              "event_date": evt, "prog_date": prog,
              "etiquetas_extra": list(ETM_ETIQUETAS) if modo == "etm" else None}
    return itens, kwargs, ""


def frase_tickets(res: list, frase: str, gerar: bool) -> tuple:
    """(frase, erros) sobre as ocorrências — porte de `PerfCriar._frase_tickets`.

    Existe pelo mesmo motivo do app: a OS criada aparecia e a ocorrência não, então a tela parecia
    não fazer o que já fazia. Diz igualmente alto quando NÃO registrou — caixa desmarcada ou
    gravação falhada."""
    aba = aba_ticket(frase)
    if not aba:
        return "", []
    if not gerar:
        return "\nSem ticket: nenhuma ocorrência foi registrada na planilha.", []
    tks = [r.get("ticket") for r in (res or []) if isinstance(r.get("ticket"), dict)]
    ok = [t for t in tks if t.get("ok")]
    falhas = [t for t in tks if not t.get("ok") and not t.get("desligado")]
    total = sum(int(t.get("quantidade") or 0) for t in ok)
    try:
        import tickets_spec
        aba_nome = tickets_spec.ABAS.get(aba, {}).get("rotulo", aba)
    except Exception:                                   # noqa: BLE001
        aba_nome = aba
    unid = ("tracker parado" if total == 1 else "trackers parados") if eh_tracker(frase) \
        else ("string" if total == 1 else "strings")
    txt = ""
    if ok:
        txt += ("\n%d ticket%s criado%s na aba %s — %d %s no total."
                % (len(ok), "" if len(ok) == 1 else "s", "" if len(ok) == 1 else "s",
                   aba_nome, total, unid))
    if falhas:
        txt += ("\n%s — a OS existe, a linha não."
                % ("1 ocorrência NÃO foi registrada" if len(falhas) == 1
                   else "%d ocorrências NÃO foram registradas" % len(falhas)))
    return txt, [str(t.get("erro") or t.get("aviso_os") or "") for t in falhas if t]


def mensagem_resultado(res: list, frase: str = "", gerar_ticket: bool = True) -> dict:
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
    tk_txt, tk_erros = frase_tickets(res, frase, gerar_ticket)
    return {"ok": len(ok), "falhas": len(fail), "mensagem": msg + tk_txt,
            "folios": [r.get("folio") for r in ok], "detalhes": erros_img + tk_erros}


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

# os_creator/os_web/clonar_web.py
"""Clonar OS — a parte pura (sem Flask) do porte de `steps/clonar.py`: preparar as tarefas como o `_criar` do app e
traduzir o resultado do `api.clonar_os` para a frase que o app mostra."""
from __future__ import annotations
import datetime as dt

from .perf_web import BRT, data_brt


def data_local(iso) -> str:
    """ISO UTC (event_date_orig) → 'YYYY-MM-DDTHH:MM' em Brasília para o input datetime-local. Vazio se não houver —
    a tela cai em hoje 08:00, como o `_iso_para_qdatetime` do app."""
    if not iso:
        return ""
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(BRT).strftime("%Y-%m-%dT%H:%M")


def completar_asset(t: dict, catalogo_por_id: dict) -> dict:
    """A tela manda o ativo enxuto; o `api.clonar_os` quer o registro do catálogo (id_type_item, id_group_task…)."""
    a = t.get("asset")
    if isinstance(a, dict) and a.get("id") is not None:
        t["asset"] = catalogo_por_id.get(a["id"]) or a
    return t


def preparar_tarefas(tarefas: list, catalogo_por_id: dict) -> tuple[list, str]:
    """O que o `_criar` do app faz antes de chamar `api.clonar_os`: data de cada tarefa em Brasília, só as subtarefas
    marcadas (com o texto editado), só os ativos marcados (não-_skip). A tarefa SEM ativo vai junto — é o `api.clonar_os`
    quem a ignora, como no app. → (tarefas, erro)."""
    out = []
    for t in (tarefas or []):
        if not isinstance(t, dict) or t.get("_skip"):
            continue
        t = completar_asset(dict(t), catalogo_por_id)
        if t.get("event_date"):
            try:
                t["event_date"] = data_brt(str(t["event_date"]))
            except ValueError:
                return [], "Data inválida."
        else:
            t.pop("event_date", None)
        t["subtarefas"] = [s for s in (t.get("subtarefas") or []) if isinstance(s, dict) and s.get("_keep", True)]
        out.append(t)
    com_ativo = [t for t in out if isinstance(t.get("asset"), dict) and t["asset"].get("id")]
    if not com_ativo:
        return [], "Nenhum ativo marcado para clonar."
    return out, ""


def candidatos(asset: dict, catalogo: list) -> list:
    """Ativos do MESMO cliente e usina, para trocar o ativo da tarefa (o combo do card 'Tarefa selecionada')."""
    if not isinstance(asset, dict):
        return []
    cli, usi = asset.get("cliente"), asset.get("usina")
    c = sorted([a for a in catalogo if a.get("cliente") == cli and a.get("usina") == usi],
               key=lambda a: (a.get("label") or a.get("code") or "").lower())
    if asset.get("id") is not None and not any(a.get("id") == asset.get("id") for a in c):
        c.insert(0, asset)
    return c


def mensagem_resultado(r: dict) -> dict:
    """{'ok','os':{wo_folio…},'n_criadas','aviso','erro'} → a frase do `_ok` do app."""
    r = r or {}
    if r.get("ok"):
        folio = (r.get("os") or {}).get("wo_folio")
        n = r.get("n_criadas")
        msg = f"OS clonada com sucesso{f' — Nº {folio}' if folio else ''}."
        if n:
            msg += f"\n{n} tarefa(s) recriada(s)."
        if r.get("aviso"):
            msg += f"\n\nObs.: {r['aviso']}"
        return {"ok": True, "folio": folio, "id_work_order": (r.get("os") or {}).get("id_work_order"), "n_criadas": n, "mensagem": msg}
    return {"ok": False, "mensagem": r.get("erro") or "Falha desconhecida ao clonar."}

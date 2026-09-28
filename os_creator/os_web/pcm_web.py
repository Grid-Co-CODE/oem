# os_creator/os_web/pcm_web.py
"""Regras do card PCM na web — a clonagem de planos, a `PcmTab` do app (steps/pcm.py, performance=False) — sem Qt,
sem Flask e sem rede.

UMA OS com VÁRIAS tarefas a partir dos PLANOS DE TAREFA do Fracttal (Handover, MPM, MPA, MPS, MPQ, MPW, MPT): marca os
ativos → "Carregar planos" → escolhe a família → cada linha mostra o plano daquela família, o nº de subtarefas, a
data/hora e o tempo; cada ativo marcado vira uma tarefa. Aqui mora o que não é tela: a cascata (`_fill_clientes`,
`_on_cli`, `_on_usi`, `_refresh`), o índice dos planos com a família PERFORMANCE escondida (`_set_planos`), o plano que a
linha mostra de saída (`_fill_row`), os pares da contagem de subtarefas (`_fetch_counts_visiveis`), o payload de
`api.create_planned_os_multi` / `api.create_os_sem_plano` — nos MESMOS argumentos, na MESMA ordem em que o `_criar` e o
`_criar_sem_plano` do app os passam — e a frase do `_criou`.

Constantes copiadas do app de propósito: o módulo de lá importa PyQt6 no topo."""
from __future__ import annotations
import datetime as dt
import re


FAM_ORDER = ["Handover", "MPM", "MPA", "MPS", "MPQ", "MPW", "MPT"]    # steps/pcm.py::_FAM_ORDER
TRACKER_TIPO = "Estrutura Trackers"                                 # steps/pcm.py::_TRACKER_TIPO
FAMILIA_PERFORMANCE = "PERFORMANCE"                                 # a família da aba Performance: o PCM a esconde
BRT = dt.timezone(dt.timedelta(hours=-3))                           # o `brt` do _criar: a data escolhida é Brasília

# As frases do app (QMessageBox). As duas últimas não existem lá porque o QDateTimeEdit e o QTimeEdit nunca ficam
# inválidos; na web o POST pode chegar com qualquer coisa, então a recusa precisa de frase (o mesmo caso do Tradicional).
ERRO_SEM_ATIVO_PLANOS = "Marque ao menos um ativo primeiro."              # _carregar_planos
ERRO_SEM_PLANO = "Carregue os planos e marque ao menos um ativo com plano."   # _criar
ERRO_SEM_ATIVO = "Marque ao menos um ativo."                              # _criar_sem_plano
ERRO_SEM_RESP = "Escolha o responsável."                                  # _criar / _criar_sem_plano
ERRO_DATA = "Data inválida."
ERRO_TEMPO = "Tempo inválido."
FALHA = "Falha ao criar a OS planejada."                                  # _criou

_DATA_TELA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?")      # o que o <input type=datetime-local> manda
_INTEIRO = re.compile(r"[0-9]+")
_PAR = re.compile(r"\s*([0-9]+)\s*:\s*([0-9]+)\s*")


class _Recusa(ValueError):
    """Um campo que o app nunca deixaria chegar assim; a mensagem é a frase que volta para a tela."""


def _int_ou_none(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    return int(s) if _INTEIRO.fullmatch(s) else None


def hoje_brt() -> str:
    """O dia de hoje em Brasília (o `QDate.currentDate()` da programação em massa)."""
    return dt.datetime.now(BRT).date().isoformat()


# ── cascata (espelho de _fill_clientes / _on_cli / _on_usi / _refresh) ───────────────────────────
def clientes(assets: list) -> list:
    """TODOS os clientes que têm o campo, em ordem. O PCM não filtra por carteira (a Performance filtra) nem esconde
    cliente nenhum (o Tradicional esconde o almoxarifado e o ambiente de teste): é o `_fill_clientes` do app."""
    return sorted({a.get("cliente") for a in (assets or []) if isinstance(a, dict) and a.get("cliente")})


def usinas(assets: list, cliente) -> list:
    """`_on_cli`: sem cliente, sem usina."""
    if not cliente:
        return []
    return sorted({a.get("usina") for a in (assets or [])
                   if isinstance(a, dict) and a.get("cliente") == cliente and a.get("usina")})


def tipos(assets: list, cliente, usina) -> list:
    """`_on_usi`: SEM restrição de tipo (há plano para muitos tipos) — todos os tipos da usina. Conta também os tipos
    cujos ativos a tabela não mostra (os trackers individuais), como o app."""
    if not cliente or not usina:
        return []
    return sorted({a.get("tipo") for a in (assets or [])
                   if isinstance(a, dict) and a.get("cliente") == cliente and a.get("usina") == usina and a.get("tipo")})


def ativos(assets: list, cliente, usina) -> list:
    """Os ativos da tabela (`_refresh` sem o tipo e a busca, que são locais, na tela): os da usina com tipo, e em
    "Estrutura Trackers" só o ativo GENERALIZADO (o nome traz "Estrutura Trackers") — tracker individual nunca entra.
    Enxutos, na ordem do catálogo: quem ordena é a tela, porque a ordem depende do plano (com plano no topo)."""
    if not cliente or not usina:
        return []
    out = []
    for a in assets or []:
        if not isinstance(a, dict):
            continue
        if a.get("cliente") != cliente or a.get("usina") != usina or not a.get("tipo"):
            continue
        if a.get("tipo") == TRACKER_TIPO and "estrutura trackers" not in (a.get("label") or "").lower():
            continue
        out.append({"id": a.get("id"), "code": a.get("code"), "label": a.get("label"), "tipo": a.get("tipo")})
    return out


# ── planos (espelho de _set_planos / _fill_row / _fetch_counts_visiveis) ──────────────────────────
def parse_ids(texto) -> list:
    """'11, 12,x,11' → [11, 12]: os ids que a tela manda na URL, sem lixo e sem repetir, na ordem."""
    out = []
    for parte in str(texto or "").split(","):
        n = _int_ou_none(parte)
        if n is not None and n not in out:
            out.append(n)
    return out


def parse_pares(texto) -> list:
    """'901:11, 906:12,lixo,7' → [(901, 11), (906, 12)]: os pares (id_task, id do ativo) do `get_subtask_counts`."""
    out = []
    for parte in str(texto or "").split(","):
        m = _PAR.fullmatch(parte)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out


def so_pcm(planos) -> list:
    """`_set_planos` com performance=False: o PCM esconde a família PERFORMANCE (ela é da aba Performance)."""
    return [p for p in (planos or []) if isinstance(p, dict) and p.get("family") != FAMILIA_PERFORMANCE]


def familias_ordenadas(fams) -> list:
    """As famílias na ordem do app: primeiro as do `_FAM_ORDER`, depois as desconhecidas em ordem alfabética."""
    fams = {f for f in (fams or ()) if f}
    return [f for f in FAM_ORDER if f in fams] + sorted(fams - set(FAM_ORDER))


def indexar(planos) -> tuple:
    """(planos por ativo, famílias) — o `_planos_by_asset` e o combo de família do `_set_planos`. O plano sem família
    reconhecida (a descrição não diz qual é) entra no índice e só aparece em "(todas)", como no app."""
    por_ativo: dict = {}
    for p in planos or []:
        aid = (p.get("asset") or {}).get("id")
        if aid is not None:
            por_ativo.setdefault(aid, []).append(p)
    return por_ativo, familias_ordenadas({p.get("family") for p in (planos or []) if p.get("family")})


def familia_inicial(pedida, familias):
    """A família do combo depois do Carregar: o app faz `setCurrentIndex(1 if ordenadas else 0)` — a PRIMEIRA família
    (o índice 0 é "(todas)"), toda vez que carrega. "todas" é o "(todas)" (None = qualquer família); a que não veio cai
    na primeira."""
    fams = list(familias or [])
    if pedida in ("todas", "(todas)"):
        return None
    if pedida and pedida in fams:
        return pedida
    return fams[0] if fams else None


def plano_padrao(planos, familia):
    """O plano que a linha mostra de saída (`_fill_row`): os planos da família em ordem alfabética, e o padrão é o
    primeiro com "grid" no nome — o "[Grid Co.]" — senão o primeiro. None = sem plano nesta família (linha vermelha)."""
    ps = sorted([p for p in (planos or []) if familia is None or p.get("family") == familia],
                key=lambda p: (p.get("description") or "").lower())
    if not ps:
        return None
    g = next((p for p in ps if "grid" in (p.get("description") or "").lower()), None)
    return (g or ps[0]).get("id_task")


def montar_planos(planos_api, ids, familia=None, visiveis=None, conhecidos=()) -> tuple:
    """Do que o `get_plans_for_assets` devolveu → (corpo da resposta, pares da contagem).

    O corpo é o que a tela guarda (`_planos_by_asset`, as famílias, a família do combo); cada plano vai sem o ativo
    repetido. Os pares são os do `_fetch_counts_visiveis` que o app dispara logo depois de carregar: uma linha por ativo
    com plano na família, o plano que o combo mostra de saída, só as linhas da TABELA (`visiveis`; None = todos os
    pedidos) e só os planos cuja contagem a tela ainda não tem (`conhecidos`, o cache `_subt`)."""
    planos = so_pcm(planos_api)
    por_ativo, familias = indexar(planos)
    fam = familia_inicial(familia, familias)
    conhecidos = set(conhecidos or ())
    pares = []
    for aid in ids or []:
        if visiveis is not None and aid not in visiveis:
            continue
        idt = plano_padrao(por_ativo.get(aid, []), fam)
        if idt is not None and idt not in conhecidos:
            pares.append((idt, aid))
    corpo = {"familias": familias, "familia": fam, "n_planos": len(planos),
             "por_ativo": {str(aid): [{"id_task": p.get("id_task"), "description": p.get("description"),
                                       "family": p.get("family")} for p in ps]
                           for aid, ps in por_ativo.items()}}
    return corpo, pares


# ── criação (espelho de _criar / _criar_sem_plano) ───────────────────────────────────────────────
def data_brt(texto) -> dt.datetime:
    """'2026-09-15T07:00' → aware em Brasília: o `.toPyDateTime().replace(tzinfo=brt)` do app. Só o formato do
    datetime-local — um ISO com fuso seria reinterpretado como Brasília e mudaria de hora sem ninguém ver."""
    s = str(texto or "").strip()
    if not _DATA_TELA.fullmatch(s):
        raise _Recusa(ERRO_DATA)
    try:
        return dt.datetime.fromisoformat(s).replace(tzinfo=BRT)
    except ValueError:
        raise _Recusa(ERRO_DATA) from None


def _evento(v):
    """A data/hora da linha. None = a linha veio sem data (no app ela sempre tem); o `create_planned_os` usa agora."""
    return None if v is None else data_brt(v)


def _duracao(v):
    """O tempo editado na linha, em segundos (o `_dur_by_asset` do app). None = a pessoa não mexeu e vale a duração do
    plano — é o que o app manda quando ninguém tocou no campo. 0 vai como 0, e o motor também cai na do plano."""
    if v is None or v == "":
        return None
    n = _int_ou_none(v)
    if n is None or not 0 <= n < 24 * 3600:                  # o QTimeEdit vai de 00:00 a 23:59
        raise _Recusa(ERRO_TEMPO)
    return n


def montar_criacao(corpo: dict, assets: list) -> tuple:
    """Do JSON da tela → ('multi'|'sem_plano', args posicionais, kwargs, erro).

    `selecoes` são as linhas MARCADAS da tabela, na ordem da tela: {asset_id, id_task, event_date, duracao} com plano,
    {asset_id, event_date} sem. O ativo volta a ser o registro INTEIRO do catálogo (o app guarda o dict na linha e o
    manda assim: `create_planned_os` tira dele description, id_group_task, id_type_item e o caminho).

    Com plano (`_criar`): `create_planned_os_multi(sel, id_personnel, name, None, id_parent=...)` — a data geral vai
    None (cada linha leva a sua) e a OBSERVAÇÃO NÃO VAI: o app não a manda neste caminho. A linha sem plano nesta
    família fica de fora. Sem plano (`_criar_sem_plano`): `create_os_sem_plano(sel, id_personnel, name, descrição,
    observação, id_parent=...)`, com o tipo de tarefa no padrão do motor (Corretiva), que o app também não mexe."""
    corpo = corpo if isinstance(corpo, dict) else {}
    catalogo = {a.get("id"): a for a in (assets or []) if isinstance(a, dict) and a.get("id") is not None}
    sem_plano = bool(corpo.get("sem_plano"))
    sel = []
    try:
        for s in corpo.get("selecoes") or []:
            if not isinstance(s, dict):
                continue
            a = catalogo.get(_int_ou_none(s.get("asset_id")))
            if a is None:                                       # fora do catálogo não vira tarefa
                continue
            if sem_plano:
                sel.append({"asset": a, "event_date": _evento(s.get("event_date"))})
                continue
            idt = _int_ou_none(s.get("id_task"))
            if not idt:                                         # sem plano nesta família: fica de fora
                continue
            sel.append({"asset": a, "id_task": idt, "event_date": _evento(s.get("event_date")),
                        "duracao": _duracao(s.get("duracao"))})   # o tempo da linha; None deixa valer o do plano
    except _Recusa as e:
        return "", (), {}, str(e)
    if not sel:
        return "", (), {}, (ERRO_SEM_ATIVO if sem_plano else ERRO_SEM_PLANO)
    resp = corpo.get("responsavel") if isinstance(corpo.get("responsavel"), dict) else {}
    id_personnel = _int_ou_none(resp.get("id_personnel"))
    if not id_personnel:
        return "", (), {}, ERRO_SEM_RESP
    nome = resp.get("name")                                     # p.get("name"), como veio do get_responsaveis
    nome = nome if nome is None or isinstance(nome, str) else str(nome)
    kwargs = {"id_parent": _int_ou_none(corpo.get("id_parent"))}          # self.os_pai.id_parent()
    if sem_plano:
        desc = str(corpo.get("descricao") or "").strip()                   # self.ed_desc.text().strip()
        note = str(corpo.get("note") or "").strip()                        # self.obs.toPlainText().strip()
        return "sem_plano", (sel, id_personnel, nome, desc, note), kwargs, ""
    return "multi", (sel, id_personnel, nome, None), kwargs, ""


# ── resultado (espelho de _criou) ────────────────────────────────────────────────────────────────
def mensagem_resultado(res) -> dict:
    """{ok, os, n_criadas, erros, aviso} do motor → {'ok','mensagem'} com a frase do app; no sucesso, o id e o nº da OS
    (a tela abre o detalhe por eles)."""
    res = res if isinstance(res, dict) else {}
    if not res.get("ok"):
        return {"ok": False, "mensagem": res.get("erro") or FALHA}
    os_ = res.get("os") or {}
    folio = os_.get("wo_folio")
    msg = f"OS criada{f' — Nº {folio}' if folio else ''} com {res.get('n_criadas') or 0} tarefa(s)."
    if res.get("aviso"):
        msg += f"\n\nObs.: {res['aviso']}"
    if res.get("erros"):
        msg += "\n\nAlgumas tarefas falharam:\n- " + "\n- ".join(str(e) for e in res["erros"][:8])
    return {"ok": True, "mensagem": msg, "id_work_order": os_.get("id_work_order"), "folio": folio}

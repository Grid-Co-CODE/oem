# os_creator/os_web/tradicional_web.py
"""Regras do card Tradicional (Criar OS do zero, passo a passo) na web — as MESMAS do wizard do desktop, sem Qt.

O desktop é `app.py` (STEP_LABELS, `_gerar_os`, `ResponsavelDialog._gerar`) + `steps/step1.py` (cascata Cliente → Usina →
Tipo → Ativos, duas datas), `steps/step2.py` + `steps/tipo_tarefa.py` (descrição, observação, etiquetas, tipo/classificações/
criticidade), `steps/step3.py` (subtarefas), `steps/finalizar.py` ("já realizada") e `steps/ospai.py` (OS pai). Aqui mora o
que não é tela: a cascata, a montagem do payload que vai para `api.create_work_orders_bulk` / `create_work_orders_agrupada`
— nos MESMOS argumentos, na MESMA ordem em que o `_gerar` do app os passa — e as mensagens de resultado.

Constantes copiadas do app de propósito (os módulos de lá são Qt); `tests/test_os_web_tradicional.py` lê o código-fonte
do app (ast) e acusa divergência."""
from __future__ import annotations
import datetime as dt

import api

STEP_LABELS = ["Ativo + Data", "Detalhes da Tarefa", "Sub tarefas", "Responsável"]   # app.py::STEP_LABELS
CLIENTES_OCULTOS = {"almoxarifado", "teste - pa"}                                    # steps/step1.py — almoxarifado e ambiente de teste
TODOS_CLIENTE = "— Selecione o cliente —"
TODOS_USINA = "— Selecione a usina —"                                                # steps/step1.py
TODOS_TIPO = "Todos os tipos"                                                        # steps/step1.py
NENHUMA = "— nenhuma —"                                                              # steps/tipo_tarefa.py::_NENHUMA
BRT = dt.timezone(dt.timedelta(hours=-3))                                            # o `brt` de ResponsavelDialog._gerar

# Frases do app. As três primeiras existem lá como QMessageBox; as demais não têm frase no desktop porque o botão fica
# DESABILITADO até preencher (Step2._upd, Step3._upd, b_ok do ResponsavelDialog) — na web o POST pode chegar sem o campo,
# então a frase precisa existir. "Data do evento não aceita futuro" é o tooltip de `travar_no_passado` (steps/ui.py).
ERRO_SEM_ATIVO = "Marque ao menos um ativo no Passo 1."
ERRO_TIPO = ("O tipo de tarefa ainda não carregou (ou a sessão expirou). Aguarde um instante ou relogue antes de gerar.")
ERRO_DATAS = "A Data final não pode ser anterior à Data inicial."
ERRO_SEM_DESC = "Preencha a Descrição da tarefa no Passo 2."
ERRO_SEM_SUB = "Adicione ao menos uma subtarefa no Passo 3."
ERRO_SEM_RESP = "Escolha o responsável."
ERRO_FUTURO = "Data do evento não aceita futuro — é quando aconteceu."
ERRO_DATA = "Data inválida."
# folga para relógio do navegador adiantado em relação ao servidor: o desktop trava no próprio widget (teto = agora, renovado
# a cada minuto); aqui o teto é o do servidor, e 10 min evitam recusar quem lançou "agora" num PC com o relógio adiantado
_FOLGA_FUTURO = dt.timedelta(minutes=10)


# ── cascata do Step 1 (set_assets / _on_cliente / _on_usina / _refresh_ativos) ────────────────────
def _cliente_oculto(c) -> bool:
    return (c or "").strip().lower() in CLIENTES_OCULTOS


def clientes(assets: list) -> list:
    return sorted({a.get("cliente") for a in (assets or []) if a.get("cliente") and not _cliente_oculto(a.get("cliente"))})


def usinas_de(assets: list, cliente: str) -> list:
    if not cliente:
        return []
    return sorted({a.get("usina") for a in (assets or []) if a.get("cliente") == cliente and a.get("usina")})


def tipos_de(assets: list, cliente: str, usina: str) -> list:
    """`a["tipo"] in ALLOWED_TIPOS` no app é "qualquer tipo não vazio" (o filtro por tipo foi removido em 01/07)."""
    if not usina:
        return []
    return sorted({a.get("tipo") for a in (assets or []) if a.get("cliente") == cliente and a.get("usina") == usina and a.get("tipo")})


def ativos_de(assets: list, cliente: str, usina: str, tipo: str | None = None, busca: str = "") -> list:
    """Os ativos da usina, enxutos para a tabela (id, code, label, tipo), na ordem do catálogo. A busca é a do app:
    substring do `label` em minúsculas, sem tirar acento."""
    if not usina:
        return []
    txt = (busca or "").strip().lower()
    out = []
    for a in (assets or []):
        if a.get("cliente") != cliente or a.get("usina") != usina or not a.get("tipo"):
            continue
        if tipo and a.get("tipo") != tipo:
            continue
        if txt and txt not in str(a.get("label") or "").lower():
            continue
        out.append({"id": a.get("id"), "code": a.get("code"), "label": a.get("label"), "tipo": a.get("tipo")})
    return out


# ── datas ─────────────────────────────────────────────────────────────────────────────────────────
def data_brt(texto) -> dt.datetime:
    """'2026-09-12T01:10' (o que o <input type=datetime-local> manda) → aware em Brasília. É o `.replace(tzinfo=brt)` que o
    `_gerar` faz sobre o datetime ingênuo do QDateTimeEdit."""
    return dt.datetime.fromisoformat(str(texto)).replace(tzinfo=BRT)


def agora_brt() -> dt.datetime:
    return dt.datetime.now(BRT).replace(second=0, microsecond=0)


def _int_ou_none(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def agrupar_imagens(pares) -> dict:
    """[(code, nome, bytes)] → {code: [{'bytes','nome'}]}, o formato de `Step1.selected_images()`."""
    out: dict = {}
    for code, nome, dados in pares or []:
        if not code or not dados:
            continue
        out.setdefault(code, []).append({"bytes": dados, "nome": nome or "imagem.png"})
    return out


# ── o payload do ResponsavelDialog._gerar ────────────────────────────────────────────────────────
def montar_payload(corpo: dict, assets: list, imagens: dict | None = None) -> tuple[str, tuple, dict, str]:
    """Do JSON da tela → ('bulk'|'agrupada', args posicionais, kwargs, erro).

    Espelha `MainWindow._gerar_os` (validação de ativo e de tipo) e `ResponsavelDialog._gerar` (datas, finalizar, agrupar,
    OS pai). Os posicionais saem na ordem exata do app — `create_work_orders_bulk(ativos, desc, tipo, subs, etiqueta, code,
    name, id_personnel, etiqueta_ids, obs, tipo=..., finalizar=..., event_date=..., id_parent=..., imagens_por_ativo=...,
    prog_date=...)` e a agrupada sem o `code` e sem `finalizar` — para o motor receber o que já recebe do desktop."""
    corpo = corpo or {}
    ids = set()
    for x in corpo.get("ativos") or []:
        ids.add(_int_ou_none(x.get("id")) if isinstance(x, dict) else _int_ou_none(x))
    ids.discard(None)
    ativos = [a for a in (assets or []) if a.get("id") in ids]       # ordem do catálogo, como Step1.selected_assets()
    if not ativos:
        return "", (), {}, ERRO_SEM_ATIVO
    tipo_in = corpo.get("tipo") if isinstance(corpo.get("tipo"), dict) else {}
    id_main = _int_ou_none(tipo_in.get("id_main"))
    if id_main is None:                                               # Step2.tipo_ready(): currentData() is not None
        return "", (), {}, ERRO_TIPO
    desc = str(corpo.get("desc") or "").strip()
    if not desc:
        return "", (), {}, ERRO_SEM_DESC
    subs = [str(s).strip() for s in (corpo.get("subs") or []) if str(s or "").strip()]   # Step3.subtarefas()
    if not subs:
        return "", (), {}, ERRO_SEM_SUB
    resp = corpo.get("responsavel") if isinstance(corpo.get("responsavel"), dict) else {}
    id_personnel = _int_ou_none(resp.get("id_personnel"))
    if id_personnel is None:
        return "", (), {}, ERRO_SEM_RESP
    nome_resp = str(resp.get("name") or "").strip()
    code_resp = resp.get("code")                                      # p["code"] vai como veio do get_responsaveis
    obs = str(corpo.get("obs") or "").strip()                         # Step2.observacao()
    etiq = [e for e in (corpo.get("etiquetas") or []) if isinstance(e, dict) and _int_ou_none(e.get("id")) is not None]
    etiqueta_ids = [_int_ou_none(e.get("id")) for e in etiq]          # Step2.etiqueta_ids()
    etiqueta = ", ".join(n for n in (str(e.get("description") or "").strip() for e in etiq) if n)   # Step2.etiqueta()
    prio = _int_ou_none(tipo_in.get("id_priorities"))
    id_c1, id_c2 = _int_ou_none(tipo_in.get("id_c1")), _int_ou_none(tipo_in.get("id_c2"))
    tipo_dict = {"id_main": id_main,                                  # TipoTarefaBox.tipo_dict()
                 "id_priorities": prio if prio is not None else api.CRITICIDADE_DEFAULT,
                 "id_c1": id_c1, "desc_c1": str(tipo_in.get("desc_c1") or "") if id_c1 is not None else "",
                 "id_c2": id_c2, "desc_c2": str(tipo_in.get("desc_c2") or "") if id_c2 is not None else ""}
    tipo_txt = str(tipo_in.get("desc_main") or "").strip()           # TipoTarefaBox.descricao_tipo()
    try:
        event = data_brt(corpo["event"]) if corpo.get("event") else agora_brt()
        prog = data_brt(corpo["prog"]) if corpo.get("prog") else agora_brt() + dt.timedelta(days=1)   # default do Step1: amanhã
    except (ValueError, TypeError):
        return "", (), {}, ERRO_DATA
    if event > dt.datetime.now(BRT) + _FOLGA_FUTURO:                 # travar_no_passado: o incidente já aconteceu
        return "", (), {}, ERRO_FUTURO
    agrupar = bool(corpo.get("agrupar")) and len(ativos) > 1         # o checkbox só existe com mais de um ativo
    os_pai = corpo.get("os_pai")
    id_parent = _int_ou_none(os_pai.get("id")) if isinstance(os_pai, dict) else _int_ou_none(os_pai)
    codes = {a.get("code") for a in ativos}
    imagens_por_ativo = {c: lista for c, lista in (imagens or {}).items() if c in codes and lista}   # só dos MARCADOS
    finalizar = None
    fin = corpo.get("finalizar") if isinstance(corpo.get("finalizar"), dict) else None
    # Agrupar e "já realizada" não combinam (app.py::_on_agrupar esconde o painel): com agrupar, o painel é ignorado.
    if fin and not agrupar:
        try:
            ini = data_brt(fin["ini"]) if fin.get("ini") else event
            fim = data_brt(fin["fim"]) if fin.get("fim") else event
        except (ValueError, TypeError):
            return "", (), {}, ERRO_DATA
        if fim < ini:
            return "", (), {}, ERRO_DATAS
        event = ini                                                   # app.py:988 — finalizada usa a data inicial do painel
        respostas = [str(r or "").strip() for r in (fin.get("respostas") or [])][:len(subs)]
        respostas += [""] * (len(subs) - len(respostas))              # FinalizarPanel: uma caixa por subtarefa
        finalizar = {"to_in_review": bool(fin.get("to_in_review")), "final_date": fim,
                     "id_assigned_user": id_personnel, "name": nome_resp, "respostas": respostas}
    if agrupar:                                                       # app.py:999-1003
        args = (ativos, desc, tipo_txt, subs, etiqueta, nome_resp, id_personnel, etiqueta_ids, obs)
        kwargs = {"tipo": tipo_dict, "event_date": event, "id_parent": id_parent,
                  "imagens_por_ativo": imagens_por_ativo, "prog_date": prog}
        return "agrupada", args, kwargs, ""
    args = (ativos, desc, tipo_txt, subs, etiqueta, code_resp, nome_resp, id_personnel, etiqueta_ids, obs)   # app.py:1009-1011
    kwargs = {"tipo": tipo_dict, "finalizar": finalizar, "event_date": event, "id_parent": id_parent,
              "imagens_por_ativo": imagens_por_ativo, "prog_date": prog}
    return "bulk", args, kwargs, ""


# ── resultado (ResponsavelDialog._pronto / _pronto_agrupada) ─────────────────────────────────────
def mensagem_bulk(res: list) -> dict:
    res = res or []
    ok = [r for r in res if r.get("ok")]
    fail = [r for r in res if not r.get("ok")]
    if not ok:
        return {"ok": False, "folios": [],
                "mensagem": "Nenhuma OS criada.\n" + "\n".join(f"• {r.get('code')}: {r.get('erro')}" for r in fail[:6])}
    def num(r):
        o = r.get("os") or {}
        return str(o.get("wo_folio") or o.get("id_work_order") or o.get("id_task") or "?")
    msg = f"{len(ok)} OS criada(s) — Nº {', '.join(num(r) for r in ok)}."
    avisos = [f"• {r.get('code')}: {r['os']['aviso']}" for r in ok if (r.get("os") or {}).get("aviso")]
    if avisos:
        msg += f"\n\n⚠ {len(avisos)} com ressalva:\n" + "\n".join(avisos[:4])
    if fail:
        msg += f"\n\n{len(fail)} falharam:\n" + "\n".join(f"• {r.get('code')}: {r.get('erro')}" for r in fail[:4])
    return {"ok": True, "mensagem": msg, "folios": [(r.get("os") or {}).get("wo_folio") for r in ok]}


def mensagem_agrupada(res: dict) -> dict:
    res = res or {}
    if not res.get("ok"):
        return {"ok": False, "mensagem": res.get("erro") or "Não consegui criar a OS.", "folios": []}
    o = res.get("os") or {}
    num = o.get("wo_folio") or o.get("id_work_order") or "?"
    msg = "OS %s criada com %d tarefa(s)." % (num, res.get("n_criadas") or 0)
    if res.get("aviso"):
        msg += "\n\n⚠ " + str(res["aviso"])
    if res.get("erros"):
        msg += "\n\n%d ativo(s) ficaram de fora:\n" % len(res["erros"]) + "\n".join("• " + str(e) for e in res["erros"][:4])
    return {"ok": True, "mensagem": msg, "folios": [o.get("wo_folio")] if o.get("wo_folio") else []}

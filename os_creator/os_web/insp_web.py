# os_creator/os_web/insp_web.py
"""A Inspeção de chamados na web — PURO: sem Flask, sem Qt, sem rede.

Porte do `steps/insp_chamado.py` (Levi, 27/09/2026: "para inspeção de chamados clone o inspeção de
chamados com o OS Creator app"). As REGRAS são as do app, uma por uma — a marca que vem do cadastro
do ativo, a marca inferida pelos ativos irmãos, a herança da OS pai, a ida a campo amanhã às 8h — e
as subtarefas vêm do MESMO `chamado_insp_spec` (que repassa o pacote `chamado_garantia`, o mesmo do
App de Campo). Duas cópias da regra seriam a OS do supervisor e a do técnico pedindo coisas
diferentes ao mesmo fabricante, que é o problema que a inspeção veio resolver.

Os textos da tela também são os do app; `tests/test_os_web_insp.py` lê o código-fonte do app e falha
se um lado mudar sem o outro.
"""
from __future__ import annotations

import datetime as dt

import chamado_insp_spec as ci

from .tradicional_web import BRT, agora_brt, data_brt

# ── os textos do app (steps/insp_chamado.py) ────────────────────────────────────────────────────
SEM_CLI = "— Selecione o cliente —"
SEM_USI = "— Selecione a usina —"
SEM_TIPO = "— Selecione o tipo de ativo —"
SEM_ATIVO = "— Selecione o ativo —"
SEM_MARCA = "— Selecione a marca —"
SEM_PAI = "Sem OS pai: a data do incidente é a que você escolher abaixo."
SEM_PREVIA = "Escolha o ativo e a marca para ver as subtarefas."
TETO_ATIVOS = 2000            # o app corta a lista aqui; usina real tem ~150 do mesmo tipo

# as cores dos status das últimas OS (COR_STATUS do app; o verde é o GREEN do steps/ui)
COR_STATUS = {"Em Processo": "#d9a441", "Em Verificação": "#57b6f5",
              "Concluída": "#8fce3f", "Cancelada": "#e0645f"}

ERRO_ATIVO = "Escolha o ativo."
ERRO_MARCA = "Escolha a marca do ativo."
ERRO_RESP = "Escolha o responsável em campo."


# ── o catálogo da inspeção ──────────────────────────────────────────────────────────────────────
def catalogo(assets: list) -> list:
    """Só o que tem modelo de inspeção e usina. `ci.aceita` e não `in POR_TIPO`: piranômetro,
    sensor de temperatura e fieldlogger são tipos próprios no Fracttal e usam o bloco da Estação
    Meteorológica pelo ALIAS_TIPO (a regra do `_set_assets` do app)."""
    return [a for a in (assets or []) if isinstance(a, dict) and ci.aceita(a.get("tipo")) and a.get("usina")]


def nome_ativo(a: dict) -> str:
    """O nome do ativo como o combo do app mostra: sem o `{ CODE }` do fim, cortado em 70."""
    return (str((a or {}).get("description") or "").split("{")[0]).strip()[:70]


def clientes(cat: list) -> list:
    return sorted({a.get("cliente") for a in cat if a.get("cliente")})


def usinas(cat: list, cliente: str = "") -> list:
    return sorted({a["usina"] for a in cat if not cliente or a.get("cliente") == cliente})


def tipos(cat: list, usina: str = "") -> list:
    return sorted({a["tipo"] for a in cat if not usina or a.get("usina") == usina})


def ativos(cat: list, usina: str = "", tipo: str = "") -> list:
    """Os ativos da usina (e do tipo, quando há), na ordem do app: pela descrição."""
    itens = [a for a in cat if (not usina or a.get("usina") == usina) and (not tipo or a.get("tipo") == tipo)]
    itens.sort(key=lambda a: str(a.get("description") or ""))
    return [{"id": a.get("id"), "code": a.get("code"), "nome": nome_ativo(a), "tipo": a.get("tipo")}
            for a in itens[:TETO_ATIVOS]]


def ativo_por_id(cat: list, id_item):
    alvo = str(id_item or "").strip()
    return next((a for a in cat if alvo and str(a.get("id")) == alvo), None)


def ativo_por_code(cat: list, code):
    alvo = str(code or "").strip()
    return next((a for a in cat if alvo and str(a.get("code") or "").strip() == alvo), None)


def cascata(a: dict) -> dict:
    """O que os combos têm de mostrar para UM ativo — o `aplicar_ativo` do app (atalho da aba Ativos)."""
    if not isinstance(a, dict):
        return {}
    return {"cliente": a.get("cliente") or "", "usina": a.get("usina") or "", "tipo": a.get("tipo") or "",
            "id": a.get("id"), "code": a.get("code") or "", "nome": nome_ativo(a)}


# ── a marca ─────────────────────────────────────────────────────────────────────────────────────
def marca_pelos_irmaos(a: dict, cat: list, marcas: list) -> str:
    """Marca inferida dos ATIVOS IRMÃOS da mesma usina, quando o próprio não a diz.

    NCU, RSU e os sensores da estação se chamam só 'NCU 1', 'Piranômetro 1' — não há marca no texto.
    Mas os trackers da mesma planta dizem ('Tracker 1.100 STI …'), e a NCU de uma planta de trackers
    STI é STI. Só sugere quando os irmãos apontam para UMA marca válida: duas marcas na mesma usina
    viram campo vazio, que é a resposta honesta. (O `_marca_pelos_irmaos` do app, sem mudança.)"""
    usi = (a or {}).get("usina")
    if not usi or not marcas:
        return ""
    validas = set(marcas)
    achadas = set()
    for x in cat:
        if x.get("usina") != usi or x is a:
            continue
        m = ci.marca_do_ativo(x)
        if m in validas:
            achadas.add(m)
            if len(achadas) > 1:
                return ""
    return next(iter(achadas), "")


def marcas(a, tipo: str, cat: list) -> dict:
    """{marcas, sugerida, aviso} — o `_fill_marcas` do app.

    A marca reconhecida no ativo mas SEM processo de chamado escrito (SolarEdge, Growatt…) não é
    selecionada e vira aviso: sem ele a pessoa fica procurando o nome na lista sem entender por que
    não está lá."""
    lista = ci.marcas_para(tipo or "")
    sugerida = ci.marca_do_ativo(a) if isinstance(a, dict) else ""
    if not sugerida and isinstance(a, dict):
        sugerida = marca_pelos_irmaos(a, cat, lista)
    aviso = ""
    if sugerida and sugerida not in lista:
        aviso = ("O ativo é %s, que ainda não tem processo de chamado documentado — escolha a marca "
                 "correta ou fale com a analista de chamados." % sugerida)
        sugerida = ""
    return {"marcas": lista, "sugerida": sugerida, "aviso": aviso}


def previa(tipo: str, marca: str) -> dict:
    """{resumo, linhas:[{n, texto, obrigatoria, anexo}]} — o `_preview` do app."""
    if not tipo or not marca:
        return {"resumo": SEM_PREVIA, "linhas": []}
    subs = ci.subtarefas(tipo, marca)
    return {"resumo": ci.resumo(tipo, marca),
            "linhas": [{"n": i, "texto": s.get("description") or "",
                        "obrigatoria": bool(s.get("is_required")),
                        "anexo": bool(s.get("attachments_required"))} for i, s in enumerate(subs, 1)]}


# ── as datas ────────────────────────────────────────────────────────────────────────────────────
def _parse_iso(x):
    """ISO do Fracttal → datetime ingênuo (a MESMA leitura do `api._parse_iso`). None se inválido."""
    s = str(x or "").strip().replace(" ", "T")[:19]
    if not s:
        return None
    for fmt, n in (("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%dT%H:%M", 16)):
        try:
            return dt.datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    return None


def iso_para_brt(iso):
    """ISO do Fracttal (UTC) → datetime em Brasília. Inválido → None.

    O Fracttal devolve `event_date` em UTC. Ler a string crua punha a hora 3 h à frente: a OS 10391
    tem incidente às 08:00 e o campo do app mostrava 11:00 (o `_iso_para_brt` do app)."""
    d = _parse_iso(iso)
    if d is None:
        return None
    return d.replace(tzinfo=dt.timezone.utc).astimezone(BRT).replace(second=0, microsecond=0)


def amanha_8h(agora=None) -> dt.datetime:
    """Amanhã às 8h — o horário em que a equipe de campo efetivamente sai."""
    agora = agora or agora_brt()
    return dt.datetime.combine(agora.date() + dt.timedelta(days=1), dt.time(8, 0), tzinfo=BRT)


def prog_apos(inc: dt.datetime, agora=None) -> dt.datetime:
    """Ida a campo: AMANHÃ às 8h — amanhã em relação a HOJE, nunca ao incidente (Levi, 03/08).

    O incidente só serve de piso: se ele for futuro (OS aberta com antecedência), a visita vai para o
    dia seguinte a ELE. Para trás nunca — incidente de 28/07 herdado de uma OS pai agendava a
    inspeção para 29/07, uma data que já passou, e a OS nascia atrasada (o `_prog_apos` do app)."""
    amanha = amanha_8h(agora)
    do_inc = dt.datetime.combine(inc.date() + dt.timedelta(days=1), dt.time(8, 0), tzinfo=BRT)
    return do_inc if do_inc > amanha else amanha


def para_input(d) -> str:
    """datetime → o valor de um <input type=datetime-local>. None → ''."""
    return d.strftime("%Y-%m-%dT%H:%M") if isinstance(d, dt.datetime) else ""


# ── a OS pai ────────────────────────────────────────────────────────────────────────────────────
def _norm(s) -> str:
    return " ".join(str(s or "").split()).lower()


def casar_responsavel(nome: str, pessoas: list):
    """(id_personnel, nome da lista) para o responsável da OS pai, ou (None, "").

    A ordem do app — o nome exato, depois o 1º nome — com um passo a mais no meio: o MESMO nome com
    espaço duplo. O cadastro do Fracttal grava "Pedro  Beta" e a OS pode trazer "Pedro Beta";
    sem esse passo o app caía no 1º nome e escolhia o PRIMEIRO Pedro da lista."""
    nome = str(nome or "").strip()
    if not nome:
        return None, ""
    for p in pessoas or []:
        if str(p.get("name") or "") == nome:
            return p.get("id_personnel"), str(p.get("name") or "")
    alvo = _norm(nome)
    for p in pessoas or []:
        if _norm(p.get("name")) == alvo:
            return p.get("id_personnel"), str(p.get("name") or "")
    primeiro = alvo.split()[0]
    for p in pessoas or []:
        if str(p.get("name") or "").lower().startswith(primeiro):
            return p.get("id_personnel"), str(p.get("name") or "")
    return None, ""


def herdar_do_pai(pai: dict, pessoas: list, agora=None, data_painel=None) -> dict:
    """O que a OS pai passa para a inspeção: DATA DO INCIDENTE (com a hora) e RESPONSÁVEL (Levi,
    30/07 — a inspeção é a mesma ocorrência, tocada por quem já está com ela). A data programada não
    é herdada: ela nasce um dia depois do incidente, pela régua do `prog_apos`.

    `data_painel` é a data que a lista de últimas OS MOSTROU: nem toda OS tem `event_date` no
    detalhe (a 6647 não tem), e sem ela o campo ficava em hoje com a linha clicada dizendo 20/05.
    → {folio, id_work_order, texto, inc, prog, resp_id, resp_nome, code}"""
    pai = pai or {}
    herdado = []
    inc = iso_para_brt(pai.get("event_date") or data_painel)
    prog = prog_apos(inc, agora) if inc else None
    if inc:
        herdado.append("incidente %s" % inc.strftime("%d/%m/%Y %H:%M"))
    resp = str(pai.get("responsavel") or "").strip()
    resp_id, resp_nome = casar_responsavel(resp, pessoas) if resp else (None, "")
    if resp and resp_id:
        herdado.append("responsável %s" % " ".join(resp_nome.split()))
    elif resp:
        herdado.append("responsável da OS pai é %s, que não está na lista" % resp)
    texto = "OS %s · %s%s" % (pai.get("folio"), (str(pai.get("descricao") or "—"))[:60],
                              ("  ·  herdado: " + ", ".join(herdado)) if herdado else "")
    return {"folio": str(pai.get("folio") or ""), "id_work_order": pai.get("id_work_order"),
            "texto": texto, "inc": para_input(inc), "prog": para_input(prog),
            "resp_id": resp_id, "resp_nome": resp_nome, "code": str(pai.get("code") or "")}


def aviso_ativo_do_pai(pai: dict, cat: list) -> str:
    """Quando o ativo da OS pai não entra na inspeção (cabine, usina, tipo sem modelo): dizer em vez
    de deixar os combos vazios sem explicação."""
    code = str((pai or {}).get("code") or "").strip()
    if not code or ativo_por_code(cat, code):
        return ""
    nome = str((pai or {}).get("ativo") or code)
    return ("O ativo da OS %s (%s) não tem modelo de inspeção de chamado — escolha o equipamento com "
            "falha." % ((pai or {}).get("folio"), nome))


# ── criar ───────────────────────────────────────────────────────────────────────────────────────
def validar_criar(corpo: dict, cat: list) -> tuple:
    """(kwargs para o `api.create_inspecao_chamado`, erro) — as travas do `_criar` do app, na MESMA
    ordem, mais as que a web precisa porque o corpo chega de fora: a marca tem de ser do tipo do
    ativo e o tipo+marca tem de ter modelo."""
    corpo = corpo or {}
    a = ativo_por_id(cat, corpo.get("ativo"))
    if not a:
        return None, ERRO_ATIVO
    marca = str(corpo.get("marca") or "").strip()
    if not marca or marca not in ci.marcas_para(a.get("tipo") or ""):
        return None, ERRO_MARCA
    try:
        resp_id = int(corpo.get("resp_id"))
    except (TypeError, ValueError):
        return None, ERRO_RESP
    if not ci.subtarefas(a.get("tipo"), marca):
        return None, "Não há modelo de inspeção para %s / %s." % (a.get("tipo") or "?", marca)
    try:
        inc = data_brt(corpo["inc"]) if corpo.get("inc") else agora_brt()
        prog = data_brt(corpo["prog"]) if corpo.get("prog") else amanha_8h()
    except ValueError:
        return None, "Data inválida — confira a data do incidente e a programada."
    pai = corpo.get("pai_id")
    try:
        pai = int(pai) if pai not in (None, "") else None
    except (TypeError, ValueError):
        pai = None
    return {"asset": a, "fabricante": marca, "id_responsible": resp_id,
            "responsible_name": str(corpo.get("resp_nome") or "").strip(),
            "event_date": inc, "prog_date": prog, "id_parent": pai,
            "note": str(corpo.get("obs") or "").strip()}, ""


def confirmacao(n: int, a: dict, marca: str, etiqueta: str) -> str:
    """A pergunta do app antes de criar. Sem a última frase do app ("abra o card desta OS e use Abrir
    chamado — as respostas dele vão preenchidas"): na web o "Abrir chamado" do card leva para ESTA
    tela (Levi, 27/09), e a frase mandaria a pessoa fazer uma inspeção da inspeção."""
    return ("Criar a OS de inspeção com %d subtarefas?\n\nAtivo: %s\nMarca: %s\nEtiqueta: %s"
            % (n, nome_ativo(a)[:60], marca, etiqueta))


def mensagem_criou(r: dict, etiqueta: str) -> dict:
    """{texto, aviso} depois de criar — o `_criou` do app."""
    r = r or {}
    texto = "OS %s criada com %s subtarefas." % (r.get("wo_folio") or "?", r.get("n_subtarefas"))
    aviso = ""
    if r.get("etiqueta_erro"):
        aviso = "A OS existe, mas a etiqueta %s não foi aplicada: %s" % (etiqueta, r["etiqueta_erro"])
    return {"texto": texto, "aviso": aviso}

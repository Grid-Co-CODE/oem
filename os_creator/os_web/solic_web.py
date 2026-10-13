# os_creator/os_web/solic_web.py
"""Regras da aba Solicitação / PCM na web — PURO: sem Flask, sem PyQt, sem rede.

O motor continua sendo o mesmo do desktop (`api.create_solicitacao`, `api.list_minhas_solicitacoes`,
`api.aprovar_solicitacao`, `api.mudar_status_solicitacao`) e os temas continuam vindo do
`solic_spec`, que já é puro — com os do BANCO por cima desde 27/09/2026: o `rotas_solic` chama o
`temas_store.garantir()` antes de cada rota. O que este módulo tem é o pedaço de decisão que hoje vive dentro do
`steps/solic_pcm.py` — um arquivo Qt de 2.474 linhas que um servidor web não pode importar sem
carregar o PyQt6 inteiro.

O que foi portado é pequeno e está aqui de propósito: a régua de em que coluna cada solicitação
cai, o encurtamento do nome do ativo e os dois padrões da OS que nasce da fila. `tests/
test_os_web_solic.py` lê o código-fonte do app e falha se um lado mudar sem o outro — a mesma
trava que o `lancador.py` já usa para os textos dos cards.
"""
from __future__ import annotations
import datetime as dt
import re
import unicodedata

import solic_spec as sp

from . import ativo_curto as nomes  # o módulo; `ativo_curto` aqui embaixo é a função antiga do painel

# ── a régua do painel (steps/solic_pcm.py) ───────────────────────────────────────────────────
PENDENTE, ANDAMENTO, FINALIZADA, FORA = "pendente", "andamento", "finalizada", "fora"
_CANCELADAS = {"cancelada", "rejeitada"}
_REFAZER = "reaberta"

# Os dois padrões da OS que nasce da fila, com o motivo original: "Programada" porque é isto que
# o PCM faz ao aprovar — programar; "Corretiva" porque é o tipo com que essa OS sempre nasceu.
# ATENÇÃO: são DUAS listas com o mesmo nome no Fracttal. `requests.types_1_list` classifica a
# SOLICITAÇÃO (é lá que vive "Não Para o Ativo", que o tema sugere) e `tasks.tasks_types_list`
# classifica a OS. A sugestão do tema NÃO serve para os campos da OS.
TIPO_PADRAO = "Corretiva"
CLASSIF1_PADRAO = "Programada"
SEM_CLASSIF = "— nenhuma —"

BRT = dt.timezone(dt.timedelta(hours=-3))

COLUNAS = [(PENDENTE, "Pendentes", "o que o PCM ainda precisa analisar"),
           (ANDAMENTO, "Em andamento", "já viraram OS e estão em execução"),
           (FINALIZADA, "Finalizadas", "concluídas, resolvidas sem OS, canceladas ou rejeitadas")]


def coluna_de(s: dict) -> str:
    """Em que coluna do painel esta solicitação cai.

    Não usa id_status de propósito: a solicitação criada pelo app volta como OPEN_STATUS (1) e a
    criada pela web do Fracttal, como REQUEST_TODO (7) — as duas pendentes. O que separa de
    verdade é ter ou não OS vinculada.

    "Reaberta (refazer)" sai do quadro (FORA) por decisão do Levi (03/09): enquanto o supervisor
    não refizer, não há o que o PCM aprovar. Continua visível no Histórico.
    """
    st = (s.get("status") or "").strip().lower()
    if any(c in st for c in _CANCELADAS):
        return FINALIZADA
    if _REFAZER in st and not s.get("id_work_order"):
        return FORA
    if not s.get("id_work_order"):
        return PENDENTE
    return FINALIZADA if "conclu" in st or "resolvid" in st else ANDAMENTO


def ativo_curto(txt) -> str:
    """Só o nome do ativo — sem endereço, sem estado, sem lote.

    O `items_description` do Fracttal traz o cadastro inteiro numa string só: "Estrutura Trackers
    2a Secao Colonia Tapejara, Lote N 152-Re, ...". O que identifica o ativo está antes da primeira
    vírgula; o resto é endereço, e numa linha de fila ele só rouba largura."""
    t = str(txt or "").split("{")[0].strip()
    return (t.split(",")[0].strip() or t)[:46]


def separar(rows: list, busca: str = "") -> dict:
    """As solicitações divididas pelas colunas do painel, já com a busca aplicada.

    → {'pendente': [...], 'andamento': [...], 'finalizada': [...], 'fora': n, 'total': n}
    `fora` é contagem, não lista: elas não aparecem no quadro, mas some-las em silêncio faria o
    total da tela não bater com o do Fracttal."""
    q = (busca or "").strip().lower()
    por = {PENDENTE: [], ANDAMENTO: [], FINALIZADA: []}
    fora = 0
    for s in (rows or []):
        if q and q not in " ".join(str(s.get(k) or "") for k in
                                  ("id_code", "usina", "ativo", "descricao", "criado_por")).lower():
            continue
        col = coluna_de(s)
        if col == FORA:
            fora += 1
            continue
        por[col].append(s)
    por["fora"] = fora
    por["total"] = sum(len(por[c]) for c, _r, _d in COLUNAS)
    return por


def linha(s: dict) -> dict:
    """A solicitação como a tela precisa dela: ativo curto, relato sem o bloco [PCM] e o tema lido.

    O tema volta do próprio texto porque a solicitação não tem campo para ele — quem cria escreve
    o bloco `[PCM]` na observação, e é dali que a fila o recupera (`solic_spec.parse`)."""
    d = dict(s or {})
    b = sp.parse(d.get("observacao"))
    d["_ativo"] = ativo_curto(d.get("ativo"))
    d["_relato"] = sp.relato(d.get("observacao") or "")
    d["_tema"] = b.get("tema") or ""
    d["_tema_nome"] = (sp.TEMAS.get(b.get("tema") or "") or {}).get("nome", "")
    d["_tecnico"] = b.get("tecnico") or ""
    d["_data_sug"] = b.get("data") or ""
    d["_subs"] = b.get("subtarefas") or []
    d["_coluna"] = coluna_de(d)
    return d


def asset_da(s: dict, assets: list):
    """Registro completo do ativo da solicitação. None quando não dá para ter CERTEZA.

    Só id_item e código valem. NÃO casar por nome: "Chave Seccionadora 1" existe em várias usinas,
    e ao aprovar a 3534 (TESTE - PA) o casamento por nome escolheu o ativo da APG100 — outra
    usina, de cliente de verdade. A criação falhou por outro motivo e o erro não chegou a produzir
    OS, mas teria criado no lugar errado sem dar erro nenhum.

    Devolver None e pedir para recarregar é sempre melhor do que acertar por acaso."""
    idi = (s or {}).get("id_item")
    if idi:
        for a in (assets or []):
            if a.get("id") == idi:
                return a
    code = str((s or {}).get("code") or "").strip()
    if code:
        for a in (assets or []):
            if str(a.get("code") or "").strip() == code:
                return a
    return None


ERRO_SEM_ASSET = ("Não consegui identificar com certeza o ativo desta solicitação no catálogo. "
                  "Recarregue o catálogo e tente de novo — criar a OS no ativo errado é pior.")


def temas_para_tela() -> list:
    """[{chave, nome, classif1, tipo, n_subs}] — os temas na ordem de volume, com o que cada um
    sugere. `n_subs` já conta a base, que é o que a OS vai receber de fato."""
    out = []
    for chave, nome in sp.temas():
        c = sp.classificacao(chave)
        try:
            n = len(sp.subtarefas(chave))
        except KeyError:                     # tema declarado sem checklist escrito ainda
            n = len(sp.subtarefas_base())
        out.append({"chave": chave, "nome": nome, "classif1": c.get("classif1") or "",
                    "tipo": c.get("tipo") or "", "n_subs": n, "motivo": sp.motivo(chave),
                    "tipos": tipos_do_tema(chave)})
    return out


# ── o tema segue o TIPO de ativo (Levi, 27/09/2026) ──────────────────────────────────────────────
# "só deve aparecer caso o tema seja daquele tipo de ativo selecionado, então se for inversor, só vai aparecer tema de
# inversores, se for trackers só trackers, se for ETM só ETM, se for nenhum então vai ficar sem tema mesmo!"
# Quem manda é o `tipo_equipamento` do tema: o PCM escolhe na tela de Temas, e é o mesmo campo que desde 04/09 filtra os
# ativos pelo tema. Vazio — 9 dos 10 temas em 27/09 —, vale esta tabela, escrita com os tipos do CADASTRO (o campo
# `tipo` do catálogo, conferido em 27/09: NBRK é o nobreak, RELE o relé da cabine, DTRF e DJMT os disjuntores do
# transformador e de média tensão, Usina o item da planta). Tema novo sem nada disso cai na regra do nome
# (tracker/TCU, inversor, ETM); fora dela ele não aparece em tipo nenhum — e a tela diz que o tipo está sem tema.
TIPOS_DO_TEMA = {
    "inversor_inspecao": ("Inversor",), "inversor_substituicao": ("Inversor",), "inversor_garantia": ("Inversor",),
    "tracker_reset_tcu": ("Estrutura Trackers",), "tracker_inject": ("Estrutura Trackers",),
    "tracker_motor": ("Estrutura Trackers",), "tracker_chamado": ("Estrutura Trackers",),
    "nobreak": ("NBRK",),
    "protecao_transformador": ("Transformador", "Cabine", "RELE", "DTRF", "DJMT"),
    "vegetacao": ("Usina",),
}
_PELO_NOME = ((r"\btracker", "Estrutura Trackers"), (r"\btcu\b", "Estrutura Trackers"), (r"\binversor", "Inversor"),
              (r"\betm\b", "Estação Meteorológica"), (r"\bestacao meteo", "Estação Meteorológica"),
              (r"\bmeteorolog", "Estação Meteorológica"))


def _sem_acento(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


def tipos_do_tema(chave: str) -> list:
    """Os tipos de ativo em que o tema aparece: o `tipo_equipamento` dele; senão a tabela; senão o nome."""
    t = sp.TEMAS.get(chave) or {}
    eq = str(t.get("tipo_equipamento") or "").strip()
    if eq:
        return [eq]
    if chave in TIPOS_DO_TEMA:
        return list(TIPOS_DO_TEMA[chave])
    base = _sem_acento(str(chave).replace("_", " ") + " " + str(t.get("nome") or ""))
    for regra, tipo in _PELO_NOME:
        if re.search(regra, base):
            return [tipo]
    return []


# ── o título "[Ativo] - Motivo" (Levi, 27/09/2026) ─────────────────────────────────────────────────
# O tema sugere "[Ativo] - <motivo>" e a marca vira o nome curto de CADA ativo ao criar: são N solicitações com os mesmos
# campos, uma por ativo, e o título de uma não pode levar o nome da outra. O nome curto é o da coluna Ativo do
# Histórico ("Inversor 1.5", sem marca nem modelo — `os_web/ativo_curto.py`).
MARCA_ATIVO = "[Ativo]"


def nome_curto(asset: dict, frases=None) -> str:
    return nomes.do_catalogo(asset, frases)


def titulo_do_ativo(descricao: str, asset: dict, frases=None) -> str:
    descricao = str(descricao or "")
    if MARCA_ATIVO not in descricao:
        return descricao
    return descricao.replace(MARCA_ATIVO, "[%s]" % nome_curto(asset, frases))


def subtarefas_do_tema(tema: str, tipo_ativo: str = "") -> list:
    """As subtarefas que a OS vai receber. Sem tema (ou tema sem checklist), a BASE — nunca vazio:
    uma OS sem subtarefa nenhuma é pior que uma com as três genéricas."""
    if tema and sp.existe(tema):
        return sp.subtarefas(tema, tipo_ativo)
    return sp.subtarefas_base()


def observacao(relato: str, tema: str = "", tecnico: str = "", data: str = "",
               subtarefas: list | None = None) -> str:
    """O relato do supervisor MAIS o bloco [PCM] — é assim que a sugestão chega à fila."""
    return sp.observacao_com_bloco(relato or "", {"tema": tema or "", "tecnico": tecnico or "",
                                                  "data": data or "", "subtarefas": subtarefas or []})


def data_brt(texto) -> dt.datetime:
    """'2026-09-21T14:30' (o que o <input type=datetime-local> manda) → datetime em Brasília."""
    t = (texto or "").strip().replace(" ", "T")[:16]
    if not t:
        return dt.datetime.now(BRT)
    return dt.datetime.strptime(t, "%Y-%m-%dT%H:%M").replace(tzinfo=BRT)


ERRO_SEM_DESC = "O título não pode ficar em branco."
ERRO_SEM_ATIVO = "Selecione o ativo (cliente → usina → ativo)."
ERRO_SEM_C1 = "A Classificação 1 é obrigatória."


def validar_criar(corpo: dict) -> str:
    """'' quando dá para criar; senão a frase de erro — as MESMAS três do `SolicitacaoTab._criar`."""
    if not str((corpo or {}).get("descricao") or "").strip():
        return ERRO_SEM_DESC
    if not (corpo or {}).get("ativos"):
        return ERRO_SEM_ATIVO
    if not (corpo or {}).get("classif1"):
        return ERRO_SEM_C1
    return ""


def mensagem_bulk(res: list) -> dict:
    """[{code, ok, id_code|erro}] → {'ok','falhas','mensagem'}.

    Diz o número de cada solicitação criada: é por ele que se acha o pedido no Fracttal, e uma
    tela que só diz "criado" obriga a pessoa a ir procurar."""
    res = res or []
    ok = [r for r in res if r.get("ok")]
    fail = [r for r in res if not r.get("ok")]
    if not res:
        return {"ok": 0, "falhas": 0, "mensagem": "Nada foi criado."}
    nums = ", ".join(str(r.get("id_code")) for r in ok if r.get("id_code"))
    msg = ("1 solicitação criada — Nº %s." % nums) if len(ok) == 1 else \
          ("%d solicitações criadas — Nº %s." % (len(ok), nums) if ok else "")
    if fail:
        msg += ("\n%d não foi criada: %s" % (len(fail), fail[0].get("erro"))) if len(fail) == 1 \
            else ("\n%d não foram criadas." % len(fail))
    return {"ok": len(ok), "falhas": len(fail), "mensagem": msg.strip(),
            "numeros": [r.get("id_code") for r in ok],
            "detalhes": [str(r.get("code")) + ": " + str(r.get("erro")) for r in fail]}


def subs_para_api(subs: list) -> list:
    """As subtarefas que a OS vai levar, como ficaram na tela — COM o anexo obrigatório.

    O `sp.para_api` sozinho põe attachments_required=False em todas: a foto obrigatória que o tema (ou o supervisor)
    marcou sumia na aprovação pela web, sem aviso. É o mesmo conserto do `EditorSubtarefas.para_api` do app."""
    out = []
    for x in subs or []:
        if not str((x or {}).get("desc") or "").strip():
            continue
        d = sp.para_api([x])[0]
        d["attachments_required"] = bool(x.get("anexo"))
        out.append(d)
    return out


# ── as quatro páginas do PCM, como no app (Levi, 13/10/2026) ─────────────────────────────────────────────────────────
# "Fila do PCM não está levando para a fila do PCM, referência é a fila do app desktop, nem painel do PCM nem histórico
# nem temas." A web juntava o Painel e a Fila numa tabela com um painel de aprovação menor que a ficha do app, o Histórico
# era uma tabela sem filtros e os Temas não existiam. Agora são as páginas da `SolicPcmTab` (steps/solic_pcm.py), com os
# nomes e a ordem dela; daqui para baixo é o pedaço de decisão de cada uma, sem rede.
NAV_PCM = [("nova", "Nova solicitação", "/os/solicitacao"), ("painel", "Painel", "/os/solicitacao/painel"),
           ("fila", "Fila do PCM", "/os/solicitacao/fila"), ("hist", "Histórico", "/os/solicitacao/historico"),
           ("temas", "Temas", "/os/solicitacao/temas")]
POR_COLUNA = 40      # `_Painel._pintar`: no máximo 40 cartões por coluna; a contagem diz o total
TIPOS_SUB = [("texto", "Texto"), ("simnao", "Sim/Não"), ("verif", "Verificação"), ("num", "Numérico")]   # subtarefas_edit


def _utc(iso):
    """'2026-10-13T11:20:03' (UTC, como o Fracttal devolve a data da solicitação) → datetime com fuso, ou None."""
    s = str(iso or "").strip().replace(" ", "T")[:19]
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def data_br(iso, com_hora: bool = True) -> str:
    """A data em horário de BRASÍLIA (a conta do `api.fmt_data_br`). O app mostra a data crua do Fracttal no Painel e na
    Fila (UTC: três horas adiantada) e a convertida nos Históricos; aqui as quatro páginas mostram a convertida."""
    d = _utc(iso)
    if d is None:
        return "—"
    return d.astimezone(BRT).strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def dia_brt(iso) -> str:
    """'AAAA-MM-DD' em Brasília — o que o filtro de período do Histórico compara."""
    d = _utc(iso)
    return d.astimezone(BRT).strftime("%Y-%m-%d") if d else ""


def ha_quanto(iso, agora=None) -> str:
    """`_ha_quanto` do app: 'agora', 'há 2 h', 'ontem', 'há 3 dias', '12/08'. Relativo perto e absoluto longe — o que
    importa na fila é a solicitação estar parada, e 86 dias de mediana não cabem em 'há 2064 h'."""
    d = _utc(iso)
    if d is None:
        return ""
    seg = ((agora or dt.datetime.now(dt.timezone.utc)) - d).total_seconds()
    if seg < 3600:
        return "agora"
    if seg < 86400:
        return "há %d h" % int(seg // 3600)
    if seg < 172800:
        return "ontem"
    if seg < 86400 * 7:
        return "há %d dias" % int(seg // 86400)
    return d.astimezone(BRT).strftime("%d/%m")


def de_hoje(iso, agora=None) -> bool:
    """Chegou hoje (em Brasília)? É o "M chegaram hoje" do cabeçalho da Fila."""
    d = _utc(iso)
    agora = agora or dt.datetime.now(dt.timezone.utc)
    return bool(d) and d.astimezone(BRT).date() == agora.astimezone(BRT).date()


def _busca(s: dict) -> str:
    return " ".join(str(s.get(k) or "") for k in ("id_code", "usina", "ativo", "descricao", "criado_por")).lower()


def cartao(s: dict) -> dict:
    """Um cartão do Painel (`_Cartao`): nº, status, 'ativo · usina', o título, a linha do tema (o nome do tema; sem tema,
    a OS que ele virou; sem as duas, "sem tema") e o rodapé com quem pediu e o dia. `s` é a `linha()`."""
    tema = s.get("_tema") or ""
    if tema:
        linha_tema, tem_tema = (sp.TEMAS.get(tema) or {}).get("nome") or tema, True
    elif s.get("os_folio"):
        linha_tema, tem_tema = "OS %s" % s["os_folio"], False
    else:
        linha_tema, tem_tema = "sem tema", False
    alvo = " · ".join(x for x in (s.get("_ativo") or "", str(s.get("usina") or "")) if x and x != "—")
    return {"id": s.get("id_code"), "status": s.get("status") or "—", "cor": s.get("cor_status") or "",
            "alvo": alvo or "—", "descricao": s.get("descricao") or "—", "tema": linha_tema, "tem_tema": tem_tema,
            "quem": s.get("criado_por") or "—", "dia": data_br(s.get("data"), False), "coluna": s.get("_coluna"),
            "busca": _busca(s)}


def _data_sugerida_iso(texto) -> str:
    """'15/10/2026 08:00' ou só '15/10/2026' (as solicitações antigas: o dia vira 08:00, como no app) → o valor do
    <input type=datetime-local>. '' se não der para ler."""
    t = str(texto or "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            d = dt.datetime.strptime(t, fmt)
        except ValueError:
            continue
        if fmt == "%d/%m/%Y":
            d = d.replace(hour=8)
        return d.strftime("%Y-%m-%dT%H:%M")
    return ""


def ficha(s: dict, asset=None, agora=None) -> dict:
    """O que a ficha da Fila (`_Fila._selecionar`) mostra de UMA solicitação, já lido: o título no padrão do tema (e o que
    o supervisor escreveu, riscado), o pedido, o relato SEM o bloco [PCM] (o bloco volta intacto ao gravar), o técnico e
    a data sugeridos, as subtarefas (as do bloco têm precedência: o supervisor pode tê-las editado) e o ativo do catálogo
    — só por id ou código (`asset_da`), nunca pelo nome."""
    tema = s.get("_tema") or ""
    tipo_ativo = (asset or {}).get("tipo") or (s.get("tipo") if s.get("tipo") != "—" else "") or ""
    subs = list(s.get("_subs") or [])
    if not subs:                       # sem a edição do supervisor: a lista do tema; sem tema, a base — nunca vazia
        subs = sp.de_api(subtarefas_do_tema(tema, tipo_ativo))
    orig = str(s.get("descricao_full") or s.get("descricao") or "")
    novo = sp.titulo(s.get("usina") or "", s.get("ativo") or "", tema) if tema and tema in sp.TEMAS else ""
    return {"id": s.get("id_code"), "status": s.get("status") or "", "cor": s.get("cor_status") or "",
            "usina": s.get("usina") or "—", "cliente": s.get("cliente") or "—", "ativo": s.get("ativo") or "—",
            "ativo_limpo": sp._limpa_ativo(s.get("ativo") or ""), "solicitante": s.get("criado_por") or "—",
            "quando": ha_quanto(s.get("data"), agora), "aberta": data_br(s.get("data")),
            "hoje": de_hoje(s.get("data"), agora),
            "titulo_orig": orig, "titulo": novo or orig,
            "relato": s.get("_relato") or "", "bloco": sp.so_bloco(s.get("observacao") or ""),
            "tema": tema, "tecnico": s.get("_tecnico") or "", "data_sug": s.get("_data_sug") or "",
            "data_sug_iso": _data_sugerida_iso(s.get("_data_sug")),
            "subs": subs, "subs_do_bloco": bool(s.get("_subs")), "ativo_ok": bool(asset), "tipo_ativo": tipo_ativo,
            "perf_ativo": sp.exige_performance("", s.get("ativo") or "", []),
            "os_folio": s.get("os_folio"), "id_work_order": s.get("id_work_order"), "coluna": s.get("_coluna")}


def temas_da_fila() -> list:
    """O combo de tema da Fila (`_encher_temas`: '— sem tema —' + os temas do maior volume para o menor), com o que cada
    um sugere: o motivo (o título), a disciplina (a Classificação 2 da OS) e as etiquetas. `etiquetas` None = o tema
    nunca foi salvo pela tela de Temas; aí vale a regra antiga (`sp.exige_performance`), como no `_CardEtiquetas`."""
    out = []
    for chave, nome in sp.temas():
        t = sp.TEMAS.get(chave) or {}
        out.append({"chave": chave, "nome": nome, "motivo": t.get("motivo") or "",
                    "disciplina": (sp.classificacao(chave) or {}).get("tipo") or "",
                    "etiquetas": ([str(x).strip() for x in (t.get("etiquetas") or []) if str(x).strip()]
                                  if "etiquetas" in t else None),
                    "perf_tema": str(chave).startswith("tracker")})
    return out


# o selo de status no Histórico (historico_solic.py: `_ST_VIVO` na tabela, `_ST_DARK` na ficha) — sem lilás
ST_VIVO = {"Aberta": "#F5A623", "Aprovada": "#4A9EF5", "OS em processo": "#4A9EF5", "OS em verificação": "#35C1B8",
           "Concluída": "#48D07A", "OS concluída": "#48D07A", "Resolvida com OS": "#48D07A",
           "Resolvida sem OS": "#48D07A", "Cancelada": "#F5766B", "Rejeitada": "#F5766B"}
NAO_CANCELAVEL = {"Cancelada", "Rejeitada", "Concluída", "OS concluída", "Resolvida com OS", "Resolvida sem OS"}


def linha_hist(s: dict) -> dict:
    """Uma linha do Histórico (`HistoricoSolic._aplica`) e a ficha dela (`SolicitacaoDialog`)."""
    st = s.get("status") or ""
    return {"id": s.get("id_code"), "cliente": s.get("cliente") or "—", "usina": s.get("usina") or "—",
            "ativo": s.get("ativo") or "", "ativo_curto": s.get("_ativo") or "", "tipo": s.get("tipo") or "—",
            "descricao": s.get("descricao") or "—", "descricao_full": s.get("descricao_full") or "",
            "observacao": s.get("observacao") or "", "criado_por": s.get("criado_por") or "",
            "data": data_br(s.get("data")), "dia": dia_brt(s.get("data")), "status": st,
            "cor": ST_VIVO.get(st) or s.get("cor_status") or "", "os_folio": s.get("os_folio") or "",
            "id_work_order": s.get("id_work_order") or "", "cancelavel": bool(st) and st not in NAO_CANCELAVEL,
            "tema": s.get("_tema_nome") or ""}


# ── Temas (steps/temas.py) ─────────────────────────────────────────────────────────────────────────────────────────
TIPOS_OS = ["", "Elétrica", "Mecânica", "Civil", "Preditiva", "Outros"]
CLASSIF1_TEMA = ["", "Não Para o Ativo", "Leve (Não Parou o Ativo, mas Afetou a Eficiência)",
                 "Moderado (Impacto Parcial no Ativo)", "Grave (Parou o Ativo)"]


def chave_de(nome) -> str:
    """`TemasTab._chave_de`: a chave nasce do NOME, sem acento e sem espaço — é ela que a observação da solicitação
    carrega, então precisa ser estável e legível (`inversor_inspecao`, não um número)."""
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    t = "".join(c if c.isalnum() else "_" for c in t.lower())
    while "__" in t:
        t = t.replace("__", "_")
    return t.strip("_")[:48]


def tipos_de_ativo(assets) -> list:
    """[(tipo, n)] do CADASTRO, do mais comum ao menos (`set_tipos_de_ativo`): "Estrutura Trackers" e "Inversor" ficam no
    topo em vez de perdidos numa lista alfabética de mais de trinta tipos. É o mesmo campo `tipo` que o filtro de ativos
    da Solicitação compara, então os dois nunca divergem."""
    import collections
    return collections.Counter(a.get("tipo") for a in (assets or []) if a.get("tipo")).most_common()


def tema_para_tela(t: dict) -> dict:
    """Um tema como a tela de Temas o edita. As etiquetas são as EFETIVAS (`ts.etiquetas_efetivas`, a mesma regra da
    Fila): o tema que nunca foi salvo pela tela nova mostra a PERFORMANCE que a regra antiga põe, e quem salvar a leva."""
    import temas_store as ts
    return {"chave": t.get("chave") or "", "nome": t.get("nome") or "", "motivo": t.get("motivo") or "",
            "classif1": t.get("classif1") or "", "tipo_os": t.get("tipo_os") or "",
            "tipo_equipamento": t.get("tipo_equipamento") or "", "solicitacoes": t.get("solicitacoes") or 0,
            "arquivado": bool(t.get("arquivado")),
            "subtarefas": [{"desc": str(x.get("desc") or ""), "tipo": x.get("tipo") or "texto", "anexo": bool(x.get("anexo"))}
                           for x in (t.get("subtarefas") or [])],
            "etiquetas": ts.etiquetas_efetivas(dict(t, chave=t.get("chave") or ""))}


def tema_para_salvar(corpo: dict, atuais: list):
    """(tema pronto para o `temas_store.salvar`, '') ou (None, a frase do erro) — as validações do `TemasTab._salvar`.

    A chave de um tema que já existe NUNCA muda (renomear mantém a chave: as solicitações antigas a carregam no bloco);
    as `solicitacoes` e o `arquivado` vêm do banco, não da tela."""
    c = corpo or {}
    nome = str(c.get("nome") or "").strip()
    if not nome:
        return None, "O tema precisa de um nome."
    chave = str(c.get("chave") or "").strip()
    novo_tema = not chave
    if novo_tema:
        chave = chave_de(nome)
        if not chave:
            return None, "Não consegui gerar a chave a partir desse nome."
    base = next((t for t in (atuais or []) if t.get("chave") == chave), None)
    if novo_tema and base is not None:
        return None, "Já existe um tema com esse nome."
    if not novo_tema and base is None:
        return None, "Esse tema não está mais no banco. Recarregue a tela de Temas."
    tipos = {k for k, _r in TIPOS_SUB}
    subs = [{"desc": str(x.get("desc") or "").strip(),
             "tipo": x.get("tipo") if x.get("tipo") in tipos else "texto", "anexo": bool(x.get("anexo"))}
            for x in (c.get("subtarefas") or []) if isinstance(x, dict) and str(x.get("desc") or "").strip()]
    etq = []
    for e in c.get("etiquetas") or []:
        e = str(e or "").strip()
        if e and e.upper() not in {x.upper() for x in etq}:
            etq.append(e)
    base = dict(base or {"solicitacoes": 0, "arquivado": False})
    for k in ("_linha",):
        base.pop(k, None)
    return dict(base, chave=chave, nome=nome, motivo=str(c.get("motivo") or "").strip(),
                classif1=str(c.get("classif1") or "").strip(), tipo_os=str(c.get("tipo_os") or "").strip(),
                tipo_equipamento=str(c.get("tipo_equipamento") or "").strip(), subtarefas=subs, etiquetas=etq), ""


def mensagem_aprovacao(res: dict, id_code) -> dict:
    """O resultado do `api.aprovar_solicitacao` em uma frase.

    Distingue os dois fracassos que parecem um só: "a tarefa nasceu mas não virou OS" deixa o
    pedido preso no kanban do Fracttal, onde ninguém o vê — e quem aprovou precisa saber disso
    para tentar de novo (a função retoma pela fase 2)."""
    r = res or {}
    os_ = r.get("os") if isinstance(r.get("os"), dict) else {}
    folio = os_.get("wo_folio")
    if r.get("ok") and folio:
        return {"ok": True, "mensagem": "Solicitação %s aprovada — OS Nº %s." % (id_code, folio),
                "folio": folio, "id_work_order": os_.get("id_work_order")}
    if r.get("ok"):
        # ok=True SEM folio e o caso perigoso: a tarefa nasceu e nao virou OS numerada, entao ela
        # fica no kanban do Fracttal onde ninguem a ve, e a solicitacao segue na fila. Dizer
        # "aprovada" aqui era o bug que o app ja corrigiu — a tela tem de falar do jeito dificil.
        return {"ok": False, "mensagem": "%s A solicitação %s continua na fila — aprove de novo, "
                                         "que a aprovação retoma de onde parou."
                                         % (r.get("aviso") or "A OS não recebeu número.", id_code)}
    return {"ok": False, "mensagem": "Não consegui aprovar a solicitação %s. %s"
                                     % (id_code, str(r.get("erro") or "a API não disse o motivo."))}

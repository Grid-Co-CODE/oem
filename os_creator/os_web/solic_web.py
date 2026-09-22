# os_creator/os_web/solic_web.py
"""Regras da aba Solicitação / PCM na web — PURO: sem Flask, sem PyQt, sem rede.

O motor continua sendo o mesmo do desktop (`api.create_solicitacao`, `api.list_minhas_solicitacoes`,
`api.aprovar_solicitacao`, `api.mudar_status_solicitacao`) e os temas continuam vindo do
`solic_spec`, que já é puro. O que este módulo tem é o pedaço de decisão que hoje vive dentro do
`steps/solic_pcm.py` — um arquivo Qt de 2.474 linhas que um servidor web não pode importar sem
carregar o PyQt6 inteiro.

O que foi portado é pequeno e está aqui de propósito: a régua de em que coluna cada solicitação
cai, o encurtamento do nome do ativo e os dois padrões da OS que nasce da fila. `tests/
test_os_web_solic.py` lê o código-fonte do app e falha se um lado mudar sem o outro — a mesma
trava que o `lancador.py` já usa para os textos dos cards.
"""
from __future__ import annotations
import datetime as dt

import solic_spec as sp

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
                    "tipo": c.get("tipo") or "", "n_subs": n})
    return out


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

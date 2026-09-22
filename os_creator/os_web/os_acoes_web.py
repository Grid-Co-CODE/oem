# os_creator/os_web/os_acoes_web.py
"""Regras PURAS das ações do card da OS (sem Flask, testáveis) — copiadas do desktop, função a função.

Cada função aponta de onde veio. A ideia é a mesma do `perf_web.py`: a rota web só monta a requisição e a resposta;
o que decide alguma coisa mora aqui e tem a MESMA regra do `steps/os_detalhe.py` / `steps/os_fluxo.py`, para o Levi
comparar lado a lado."""
from __future__ import annotations
import os
import urllib.parse

# ── textos do card (steps/os_detalhe.py) ────────────────────────────────────────────────────────────────
NOTA_MOTIVO_OK = "Editar a observação desta OS"
NOTA_MOTIVO_FECHADA = "OS %s — o Fracttal não aceita mais editar a observação."
NOTA_MOTIVO_VARIAS = ("Esta OS tem %d tarefas, e cada uma tem a sua observação. A edição por aqui só é segura em OS de "
                      "uma tarefa — use o Fracttal.")
# `_ConcluirDialog` / `_concluiu`
CONCLUIDA = "A OS %s foi concluída."
CONCLUIDA_SEM_FIM = ("A OS %s foi concluída, mas %s ficou SEM data de fim.\n\nO campo não é preenchido depois: para registrar a "
                     "data seria preciso ter usado o cronômetro de execução antes de fechar.")
# cor por status do fluxo — semáforo, não a paleta da marca (steps/os_fluxo.py::COR_STATUS)
COR_STATUS = {"Concluída": "#3fb27f", "Em Processo": "#4a9eff", "Em Verificação": "#eb8b57", "Cancelada": "#e05454"}
COR_STATUS_PADRAO = "#8A93A8"                     # MUTED do steps/ui.py (= --f-muted do os.css)
_WO_STATUS = {1: "Em Processo", 2: "Em Verificação", 3: "Concluída", 4: "Cancelada"}     # api.WO_STATUS, sem importar o api
_IMG = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def status_id_de(status_nome, d: dict):
    """`id_status_work_order` da OS como a web consegue saber. O `get_os_detalhes` não devolve o status; o card recebe o
    NOME pela URL (a linha do Histórico manda `?status=`) e o cancelamento só vem preenchido em OS cancelada (o api só
    busca o motivo quando o status é 4). None = não sei — e aí a regra deixa passar, o Fracttal é quem recusa."""
    d = d or {}
    if str(d.get("cancel_motivo") or "").strip() or str(d.get("cancel_nota") or "").strip():
        return 4
    for k, v in _WO_STATUS.items():
        if v == str(status_nome or "").strip():
            return k
    return None


def nota_pode_editar(status_id, n_tarefas: int):
    """(pode, motivo) — `OsDetalheDialog._nota_pode_editar`. Duas recusas, cada uma medida:

    · OS CONCLUÍDA/CANCELADA — o Fracttal recusa com ERROR_WO_FINISHED_BY_OTHER_USER (OS 10575, 02/09).
    · OS com VÁRIAS TAREFAS — a nota é presa à tarefa, mas o `work_orders_update` grava no nível da OS; com várias não se
      sabe qual receberia, e sobrescrever a observação da tarefa errada é pior que não editar."""
    if status_id in (3, 4):
        return False, NOTA_MOTIVO_FECHADA % ("concluída" if status_id == 3 else "cancelada")
    if int(n_tarefas or 0) > 1:
        return False, NOTA_MOTIVO_VARIAS % int(n_tarefas)
    return True, NOTA_MOTIVO_OK


def tarefas_sem_fim(tarefas) -> list:
    """Títulos das tarefas SEM data de fim — o lado 'antes' do double check (`_concluir_os`): sai do que o card já
    carregou, sem ida extra ao servidor."""
    return [str(t.get("titulo") or t.get("ativo") or "(tarefa sem título)") for t in (tarefas or [])
            if isinstance(t, dict) and not str(t.get("fim") or "").strip()]


def mensagem_concluida(folio, chk) -> tuple:
    """(texto, aviso) depois do `concluir_os_checado` — `_concluiu`. `aviso=True` quando fechou sem data de fim: é o 2º
    lado do double check, o que ninguém percebeu na 10509."""
    chk = chk if isinstance(chk, dict) else {}
    n = len(chk.get("sem_fim") or [])
    if n:
        quem = "a tarefa" if n == 1 else "%d das %d tarefas" % (n, chk.get("total") or n)
        return CONCLUIDA_SEM_FIM % (folio, quem), True
    return CONCLUIDA % folio, False


def cor_hex(cor) -> str:
    """Cor da etiqueta do Fracttal → '#rrggbb' (fallback cinza) — `_cor_hex`."""
    c = str(cor or "").strip().lstrip("#")
    return "#" + c if len(c) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in c) else "#A6A6A6"


# ── anexos (steps/os_detalhe.py: _fname, _recount, _separar_anexos, _abrir_anexos_*; steps/documentos.py: _ext) ──
def fname(u) -> str:
    """Nome do arquivo a partir de uma URL/caminho (tira query, diretórios e decodifica %20 etc.) — `_fname`."""
    if not u:
        return ""
    return urllib.parse.unquote(str(u).split("?")[0].rstrip("/").rsplit("/", 1)[-1])


def ext(nome) -> str:
    """Extensão em maiúscula, o identificador mais rápido de ler numa lista (`documentos._ext`)."""
    return (os.path.splitext(str(nome or ""))[1] or "").lstrip(".").upper() or "ARQ"


def anexos_da_os_unicos(anexos_sub, anexos_os) -> list:
    """Do card da OS tira o que já é anexo de subtarefa (evita o mesmo arquivo nos 2 cards) — `_recount`."""
    sub_nomes = set()
    for im in anexos_sub or []:
        if not isinstance(im, dict):
            continue
        for k in (im.get("nome"), fname(im.get("value")), fname(im.get("url"))):
            if k:
                sub_nomes.add(str(k).lower())
    return [a for a in (anexos_os or []) if isinstance(a, dict)
            and (fname(a.get("value")) or fname(a.get("url")) or str(a.get("nome") or "")).lower() not in sub_nomes]


def separar_anexos(itens) -> tuple:
    """(galeria, documentos, notas) — `_separar_anexos`. Sem URL não há arquivo: é nota de texto. Com URL, quem decide é a
    EXTENSÃO (`is_image`), nunca o fato de ter URL — a pré-assinada do S3 vem igual para uma foto e para um ZIP (OS 11458)."""
    itens = [a for a in (itens or []) if isinstance(a, dict)]
    imgs = [a for a in itens if a.get("url") and a.get("is_image")]
    docs = [a for a in itens if a.get("url") and not a.get("is_image")]
    notas = [a for a in itens if not a.get("url")]
    return imgs, docs, notas


def link_baixar(wid, value, nome) -> str:
    """Rota que RENOVA a URL pré-assinada e devolve os bytes. Na web não há 'reabrir os anexos renova': o clique renova."""
    return "/os/api/os/%d/anexo?value=%s&nome=%s" % (int(wid), urllib.parse.quote(str(value), safe=""),
                                                      urllib.parse.quote(str(nome or ""), safe=""))


def _item(tipo, wid, a, nome, legenda, quem, texto=""):
    url = a.get("url") or None
    value = str(a.get("value") or "").strip()
    return {"tipo": tipo, "nome": nome, "url": url, "legenda": legenda, "quem": quem, "texto": texto,
            "ext": ext(nome) if tipo == "documento" else "",
            "baixar": link_baixar(wid, value, nome) if value else url}


def itens_subtarefas(anexos_sub, wid) -> list:
    """Os anexos das subtarefas como a janela do app os abre (`_abrir_anexos_sub`): foto → galeria com a legenda da
    subtarefa; arquivo → documentos com a subtarefa no lugar do usuário; sem URL → nota de texto."""
    imgs, docs, cru = separar_anexos(anexos_sub)
    out = []
    for a in imgs:
        nome = a.get("nome") or fname(a.get("url")) or "foto"
        out.append(_item("imagem", wid, a, nome, str(a.get("descricao") or nome), str(a.get("subtarefa") or "")))
    for a in docs:
        nome = a.get("nome") or a.get("descricao") or "arquivo"
        out.append(_item("documento", wid, a, nome, str(a.get("descricao") or ""), str(a.get("subtarefa") or "")))
    for a in cru:
        texto = str(a.get("descricao") or a.get("nome") or "").strip()
        out.append(_item("nota", wid, a, str(a.get("nome") or "nota"), str(a.get("descricao") or a.get("nome") or "nota"),
                         str(a.get("subtarefa") or ""), texto))
    return out


def itens_os(anexos_os_unicos, wid) -> list:
    """Os anexos da OS como a janela do app os abre (`_abrir_anexos_os`): legenda 'nome  ·  usuário' na foto."""
    fotos, docs, cru = separar_anexos(anexos_os_unicos)
    out = []
    for a in fotos:
        nome = a.get("nome") or fname(a.get("url")) or "anexo"
        out.append(_item("imagem", wid, a, nome, "%s  ·  %s" % (a.get("nome") or "anexo", a.get("user") or "—"), str(a.get("user") or "")))
    for a in docs:
        nome = a.get("nome") or "arquivo"
        out.append(_item("documento", wid, a, nome, str(a.get("desc") or ""), str(a.get("user") or "")))
    for a in cru:
        texto = str(a.get("desc") or a.get("nome") or "").strip()
        out.append(_item("nota", wid, a, str(a.get("nome") or "nota"), str(a.get("nome") or "nota"), str(a.get("user") or ""), texto))
    return out


def anexos_web(anexos_sub, anexos_os, wid) -> dict:
    """O JSON dos dois cards de anexos. As contagens são as mesmas do `/os/os/<wid>/anexos` (verde = subtarefas, todas;
    azul = da OS, sem o que já é de subtarefa)."""
    subs = [a for a in (anexos_sub or []) if isinstance(a, dict)]
    uniq = anexos_da_os_unicos(subs, anexos_os)
    return {"sub": {"itens": itens_subtarefas(subs, wid), "n": len(subs)},
            "os": {"itens": itens_os(uniq, wid), "n": len(uniq)},
            "n": {"sub": len(subs), "os": len(uniq)}}


# ── fluxo (steps/os_fluxo.py) ───────────────────────────────────────────────────────────────────────────
def subtitulo_fluxo(ativo: dict) -> str:
    """DEDUPLICA nome/usina/cliente: no item-usina o nome do ativo JÁ é o nome da planta, e o subtítulo saía
    'Axis - Marialva 1 - PR Marialva Paraná Brasil · Axis - Marialva 1 - PR · Axis' (`FluxoDialog._pronto`)."""
    ativo = ativo or {}
    partes, vistos = [], set()
    for x in (ativo.get("nome"), ativo.get("usina"), ativo.get("cliente")):
        x = str(x or "").strip()
        n = x.lower()
        if x and not any(n in v or v in n for v in vistos):
            partes.append(x)
            vistos.add(n)
    return "  ·  ".join(partes) or "—"


def fluxo_web(fx: dict, fmt) -> dict:
    """O fluxo para o JS pintar: só a CADEIA, centralizada, ordenada pelo api (número da OS). `fmt` = api.fmt_data_br.
    Os cortes de texto (tipo 26, descrição 30) são os do nó de 226 px do app (`_No`)."""
    fx = fx or {}
    atual_id = (fx.get("atual") or {}).get("id")
    cadeia = []
    for no in fx.get("cadeia") or []:
        if not isinstance(no, dict):
            continue
        status = str(no.get("status") or "—")
        data = fmt(no.get("event_date") or no.get("criacao"), False) if (no.get("event_date") or no.get("criacao")) else ""
        cadeia.append({"id": no.get("id"), "folio": str(no.get("folio") or "—"), "tipo_tarefa": str(no.get("tipo_tarefa") or "—")[:26],
                       "descricao": str(no.get("descricao") or "")[:30], "status": status,
                       "cor": COR_STATUS.get(status, COR_STATUS_PADRAO), "data": data, "atual": no.get("id") == atual_id,
                       "href": "/os/os/%s?status=%s" % (no.get("id"), urllib.parse.quote(status if status != "—" else "", safe=""))})
    return {"folio": str((fx.get("atual") or {}).get("folio") or ""), "subtitulo": subtitulo_fluxo(fx.get("ativo") or {}),
            "cadeia": cadeia, "vazio": len(cadeia) <= 1, "aviso": str(fx.get("aviso") or "")}


# ── "fazer a tarefa" antes de concluir (Levi, 21/09/2026) ───────────────────────────────────
# O pedido: "se tiver tarefa pendente tem que dar a opção de fazer a tarefa". Até aqui a web só
# sabia AVISAR quais subtarefas ficariam pendentes; para preenchê-las a pessoa tinha de sair para o
# Fracttal, e nessa saída o que mais se perdia era o REGISTRO de início e fim — o campo que a
# conclusão não preenche depois e que deixou a OS 10509 sem data de fim para sempre.
ERRO_SEM_TAREFA = "Esta OS não tem tarefa com subtarefa pendente."
ERRO_SEM_INICIO = "Informe a data e a hora de início da execução."
ERRO_FIM_ANTES = "A data de fim não pode ser anterior à de início."
ERRO_OBRIGATORIA = "Preencha as subtarefas obrigatórias: %s"
EXECUTADA = "Tarefa registrada: %d subtarefa(s) gravada(s) e a execução lançada de %s a %s."
EXECUTADA_SEM_CONFIRMAR = ("As subtarefas foram gravadas, mas NÃO consegui confirmar o registro de "
                           "execução relendo a tarefa. Confira no Fracttal antes de concluir a OS.")


def tarefas_pendentes(d: dict) -> list:
    """[{id_tarefa, titulo, n_pendentes}] — as tarefas da OS que ainda têm subtarefa em branco.

    Agrupa por `id_tarefa` porque uma OS de preventiva pode ter treze: oferecer "fazer a tarefa"
    sem dizer QUAL faria a pessoa preencher o checklist da tarefa errada."""
    d = d or {}
    titulos = {}
    for t in (d.get("tarefas") or []):
        if isinstance(t, dict) and t.get("id") is not None:
            titulos[t.get("id")] = str(t.get("titulo") or t.get("ativo") or "").strip()
    por = {}
    for s_ in (d.get("subtarefas") or []):
        if not isinstance(s_, dict) or s_.get("feito"):
            continue
        tid = s_.get("id_tarefa")
        if tid is None:
            continue
        por.setdefault(tid, 0)
        por[tid] += 1
    return [{"id_tarefa": tid, "titulo": titulos.get(tid) or ("Tarefa %s" % tid), "n_pendentes": n}
            for tid, n in sorted(por.items(), key=lambda kv: -kv[1])]


def faltando_obrigatorias(campos: list, valores: dict) -> list:
    """Descrições das subtarefas OBRIGATÓRIAS que continuariam em branco.

    A checagem é nossa, não do Fracttal: ele aceita gravar o checklist pela metade (a captura de
    21/09 mostra a gravação com um campo a menos, sem reclamação nenhuma). Quem pediu para poder
    fazer a tarefa aqui não quer descobrir depois que ela ficou meia-feita."""
    faltam = []
    for c in (campos or []):
        if not isinstance(c, dict) or not c.get("obrigatorio"):
            continue
        fid = c.get("id_form_item")
        novo = str((valores or {}).get(str(fid), "") or "").strip()
        atual = str(c.get("valor") or "").strip()
        if not novo and not atual:
            faltam.append(str(c.get("descricao") or "(sem descrição)"))
    return faltam


def mensagem_execucao(n_campos: int, exec_res: dict, fmt_hora) -> tuple:
    """(texto, aviso). `aviso=True` quando gravou mas não deu para confirmar o registro relendo."""
    exec_res = exec_res or {}
    if not exec_res.get("confirmado"):
        return EXECUTADA_SEM_CONFIRMAR, True
    return EXECUTADA % (n_campos, fmt_hora(exec_res.get("inicio")), fmt_hora(exec_res.get("fim"))), False

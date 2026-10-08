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
    carregou, sem ida extra ao servidor. O título é o do `rotulos_tarefas`: com 8 tarefas de mesmo título, o aviso
    repetia a mesma frase (08/10/2026)."""
    rot = rotulos_tarefas(tarefas)
    return [rot.get(t.get("id")) or str(t.get("titulo") or t.get("ativo") or "(tarefa sem título)")
            for t in (tarefas or []) if isinstance(t, dict) and not str(t.get("fim") or "").strip()]


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


def tem_arquivo(a) -> bool:
    """Arquivo = tem a URL pré-assinada OU o caminho no S3 (`value`). Até 28/09 valia só a URL, como no app: o PDF cujo
    link não veio (o s3_object_get falhou, ou o files_list trouxe só o caminho) aparecia como NOTA, com o caminho do S3
    por texto, e não dava para baixar. Com o caminho, a rota do Baixar renova o link."""
    return bool(a.get("url")) or (bool(str(a.get("value") or "").strip()) and not a.get("is_text"))


def separar_anexos(itens) -> tuple:
    """(galeria, documentos, notas) — `_separar_anexos`. Sem arquivo (`tem_arquivo`) é nota de texto. Com arquivo, quem
    decide é a EXTENSÃO (`is_image`), nunca o fato de ter URL — a pré-assinada do S3 vem igual para uma foto e para um
    ZIP (OS 11458)."""
    itens = [a for a in (itens or []) if isinstance(a, dict)]
    imgs = [a for a in itens if tem_arquivo(a) and a.get("is_image")]
    docs = [a for a in itens if tem_arquivo(a) and not a.get("is_image")]
    notas = [a for a in itens if not tem_arquivo(a)]
    return imgs, docs, notas


def link_baixar(wid, value, nome) -> str:
    """Rota que RENOVA a URL pré-assinada e devolve os bytes. Na web não há 'reabrir os anexos renova': o clique renova."""
    return "/os/api/os/%d/anexo?value=%s&nome=%s" % (int(wid), urllib.parse.quote(str(value), safe=""),
                                                      urllib.parse.quote(str(nome or ""), safe=""))


def _item(tipo, wid, a, nome, legenda, quem, texto=""):
    url = a.get("url") or None
    value = str(a.get("value") or "").strip()
    if not url and value and tipo != "nota":          # sem a pré-assinada: a rota renova o link e mostra ali mesmo
        url = link_baixar(wid, value, nome) + "&abrir=1"
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
    # `baixar` = o N do "Baixar todos (N)" de cada card: o que vai para o .zip (arquivo, ou nota com texto)
    return {"sub": {"itens": itens_subtarefas(subs, wid), "n": len(subs),
                    "baixar": len(plano_do_zip(itens_para_baixar("sub", subs, anexos_os)))},
            "os": {"itens": itens_os(uniq, wid), "n": len(uniq),
                   "baixar": len(plano_do_zip(itens_para_baixar("os", subs, anexos_os)))},
            "n": {"sub": len(subs), "os": len(uniq)}}


# ── baixar todos (steps/documentos.py: _limpar_nome, _baixaveis, baixar_em_massa) ─────────────────────────────────────
# O app grava numa PASTA que a pessoa escolhe (pedido do Levi, 04/09: "só quero conseguir baixar em massa"); a web não
# escolhe pasta — entrega um .zip com a MESMA arrumação: uma subpasta por subtarefa, a numeração DENTRO de cada uma, a
# nota de texto como .txt ("é ela que costuma explicar a foto") e o nome repetido (o celular manda tudo como image.jpg)
# com " (2)". tests/test_os_web_anexos_zip.py roda a função do app numa pasta e compara caminho por caminho.
def limpar_nome(t, padrao="arquivo") -> str:
    """Nome que o Windows aceita — `documentos._limpar_nome`: `\\ / : * ? " < > |` viram "_" e o nome não termina em ponto
    nem em espaço."""
    t = "".join("_" if c in '\\/:*?"<>|' else c for c in str(t or "")).strip(" .")
    return (t or padrao)[:120]


def itens_para_baixar(grupo, anexos_sub, anexos_os) -> list:
    """Os anexos de UM card no formato do `baixar_em_massa` ({url, value, nome, descricao, subtarefa, is_text}): 'sub' =
    os das subtarefas, cada um na pasta da sua; 'os' = os da OS sem os que já são de subtarefa (`_recount`), na raiz."""
    subs = [a for a in (anexos_sub or []) if isinstance(a, dict)]
    if grupo == "sub":
        return [{"url": a.get("url"), "value": str(a.get("value") or "").strip(), "nome": a.get("nome"),
                 "descricao": a.get("descricao"), "subtarefa": a.get("subtarefa") or "", "is_text": bool(a.get("is_text"))}
                for a in subs]
    return [{"url": a.get("url"), "value": str(a.get("value") or "").strip(), "nome": a.get("nome"),
             "descricao": a.get("desc") or a.get("nome"), "subtarefa": "", "is_text": bool(a.get("is_text"))}
            for a in anexos_da_os_unicos(subs, anexos_os)]


def plano_do_zip(itens) -> list:
    """[{caminho, tipo ('arquivo' | 'nota'), item, texto}] — o `baixar_em_massa` sem gravar nada. A numeração conta até a
    nota vazia que fica de fora, como lá. Diferença (mais segura): o arquivo sem URL mas com o caminho no S3 continua
    arquivo — o app o gravaria como .txt com o caminho; aqui o servidor renova o link (`tem_arquivo`)."""
    out, usados, n_sub = [], set(), {}
    for i, d in enumerate(itens or [], 1):
        if not isinstance(d, dict):
            continue
        sub = limpar_nome(d.get("subtarefa") or "", "")
        pasta = sub + "/" if sub else ""
        n_sub[sub] = n_sub.get(sub, 0) + 1
        k = n_sub[sub]
        if d.get("is_text") or not tem_arquivo(d):
            txt = str(d.get("descricao") or d.get("value") or "").strip()
            if txt:
                out.append({"caminho": pasta + "%02d - %s.txt" % (k, limpar_nome(d.get("nome") or "nota", "nota")),
                            "tipo": "nota", "item": d, "texto": txt})
            continue
        base = limpar_nome(d.get("nome") or "anexo_%d" % i)
        cam = pasta + "%02d - %s" % (k, base)
        raiz, extensao = os.path.splitext(cam)
        j = 2
        while cam.lower() in usados:
            cam = "%s (%d)%s" % (raiz, j, extensao)
            j += 1
        usados.add(cam.lower())
        out.append({"caminho": cam, "tipo": "arquivo", "item": d, "texto": ""})
    return out


_JA_COMPRIMIDO = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".zip", ".rar", ".7z", ".gz", ".mp4", ".mov", ".pdf", ".docx",
                  ".xlsx", ".pptx")
TETO_ZIP = 250 * 1024 * 1024
NAO_VIERAM = "_nao_vieram.txt"


def montar_zip(destino, plano, baixar, teto=TETO_ZIP, mapa=map) -> dict:
    """Grava o .zip em `destino` seguindo o `plano`. `baixar(item) -> bytes` e `mapa` (o `ex.map` de um executor, para
    baixar em paralelo) são injetáveis — o teste roda sem rede. Um arquivo que falha NÃO derruba o lote (a URL
    pré-assinada expira; se o décimo morrer, os outros dezenove valem): vai para o _nao_vieram.txt, e a tela conta.
    → {arquivos, notas, falhas: [(caminho, motivo)], bytes}"""
    import zipfile

    def _um(p):
        if p["tipo"] == "nota":
            return p, p["texto"].encode("utf-8"), None
        try:
            dados = baixar(p["item"])
        except Exception as e:                        # noqa: BLE001 — um arquivo que falha não derruba o lote
            return p, None, (str(e) or type(e).__name__)[:160]
        return p, dados, (None if dados else "veio vazio")

    arquivos = notas = total = 0
    falhas = []
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p, dados, erro in mapa(_um, plano):
            if erro:
                falhas.append((p["caminho"], erro))
                continue
            if total + len(dados) > teto:
                falhas.append((p["caminho"], "o .zip passou de %d MB" % (teto // (1024 * 1024))))
                continue
            leve = p["caminho"].lower().endswith(_JA_COMPRIMIDO)      # foto e ZIP já vêm comprimidos: só guardar
            zf.writestr(p["caminho"], dados, compress_type=zipfile.ZIP_STORED if leve else zipfile.ZIP_DEFLATED)
            total += len(dados)
            if p["tipo"] == "nota":
                notas += 1
            else:
                arquivos += 1
        if falhas:
            zf.writestr(NAO_VIERAM, ("Estes anexos não vieram (a URL do Fracttal expira; abrir os anexos de novo renova):\n\n"
                                     + "\n".join("· %s — %s" % f for f in falhas) + "\n").encode("utf-8"))
    return {"arquivos": arquivos, "notas": notas, "falhas": falhas, "bytes": total}


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


# ── as TAREFAS da OS no card (Levi, 08/10/2026) ─────────────────────────────────────────────────────────────────────────
# "Nas OSs que aparecem no OS Creator Web quando a OS tem mais que uma tarefa está duplicando as subtarefas e não
# aparecendo as tarefas, tem que dividir por tarefa quando clicar!". A lista corrida juntava as subtarefas de todas as
# tarefas: numa OS de tarefas com o mesmo checklist (a coleta de geração, uma por inversor) a mesma pergunta saía uma vez
# por tarefa, sem dizer de qual. Com mais de uma tarefa, o card mostra AS TAREFAS e cada uma abre as subtarefas DELA: é o
# seletor de tarefa do app (steps/os_detalhe.py), em lista.
SEM_TAREFA = "Subtarefas sem tarefa identificada"


def situacao_tarefa(t: dict) -> tuple:
    """(rótulo, classe do semáforo no os.css) pela execução registrada na tarefa: com fim, Finalizada; só com início,
    Iniciada; sem os dois, Não iniciada. São as datas que o card já lê (`inicio`/`fim`), sem pedido a mais."""
    t = t or {}
    if str(t.get("fim") or "").strip():
        return "Finalizada", "ok"
    if str(t.get("inicio") or "").strip():
        return "Iniciada", "and"
    return "Não iniciada", "nao"


def rotulos_tarefas(tarefas) -> dict:
    """{id da tarefa: o nome que a distingue das outras da MESMA OS}. É o título; quando o título se repete (o mesmo plano
    em vários ativos: 8 tarefas "Coleta de dados de geração"), leva o ativo junto — o seletor do app põe o ativo pelo
    mesmo motivo. Sem título nem ativo, "Tarefa N" pela posição na OS."""
    lista = [t for t in (tarefas or []) if isinstance(t, dict) and t.get("id") is not None]
    nomes = [str(t.get("titulo") or t.get("ativo") or "").strip() for t in lista]
    out = {}
    for i, (t, nome) in enumerate(zip(lista, nomes), 1):
        ativo = str(t.get("ativo") or "").strip()
        if not nome:
            nome = "Tarefa %d" % i
        elif nomes.count(nome) > 1 and ativo and ativo != nome:
            nome = "%s · %s" % (nome, ativo)
        out.setdefault(t.get("id"), nome)
    return out


def subtarefas_por_tarefa(d: dict) -> list:
    """As tarefas do card com as subtarefas de cada uma, na ordem das tarefas: [{id, n, titulo, ativo, tipo, programada,
    inicio, fim, situacao, sit, subtarefas, feitas, total}]. [] quando a OS tem uma tarefa só: aí fica a lista direta.

    Cada subtarefa vai para a tarefa DELA (`id_tarefa` = `id` da tarefa, o join conferido ao vivo na OS 8709: 45 de 45) e
    para uma só: a tarefa que viesse repetida não ganha as subtarefas de novo. A que não casa com tarefa nenhuma vai num
    grupo no fim (`n` None), para nada sumir da conta."""
    d = d or {}
    subs = [s for s in (d.get("subtarefas") or []) if isinstance(s, dict)]
    por = {}
    for s in subs:
        por.setdefault(s.get("id_tarefa"), []).append(s)
    grupos, usadas = [], set()
    for t in (d.get("tarefas") or []):
        if not isinstance(t, dict) or (t.get("id") is not None and t.get("id") in usadas):
            continue
        tid = t.get("id")
        ss = por.get(tid, []) if tid is not None else []
        if tid is not None:
            usadas.add(tid)
        situacao, sit = situacao_tarefa(t)
        n = len(grupos) + 1
        ativo = str(t.get("ativo") or "").strip()
        grupos.append({"id": tid, "n": n, "titulo": str(t.get("titulo") or "").strip() or ativo or "Tarefa %d" % n,
                       "ativo": ativo, "tipo": str(t.get("tipo") or "").strip(), "programada": t.get("programada"),
                       "inicio": t.get("inicio"), "fim": t.get("fim"), "situacao": situacao, "sit": sit,
                       "subtarefas": ss, "feitas": sum(1 for s in ss if s.get("feito")), "total": len(ss)})
    if len(grupos) < 2:
        return []
    soltas = [s for s in subs if s.get("id_tarefa") is None or s.get("id_tarefa") not in usadas]
    if soltas:
        grupos.append({"id": None, "n": None, "titulo": SEM_TAREFA, "ativo": "", "tipo": "", "programada": None,
                       "inicio": None, "fim": None, "situacao": "", "sit": "", "subtarefas": soltas,
                       "feitas": sum(1 for s in soltas if s.get("feito")), "total": len(soltas)})
    return grupos


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
    sem dizer QUAL faria a pessoa preencher o checklist da tarefa errada. Pelo mesmo motivo o título
    é o `rotulos_tarefas`: com 8 tarefas de mesmo título, os botões saíam iguais (08/10/2026)."""
    d = d or {}
    titulos = rotulos_tarefas(d.get("tarefas"))
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

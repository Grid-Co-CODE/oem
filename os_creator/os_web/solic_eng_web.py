# os_creator/os_web/solic_eng_web.py
"""A Nova solicitação para a ENGENHARIA (Levi, 06/10/2026): "Em 'Nova Solicitação' aparecerá duas opções, PCM e
Engenharia. PCM realmente criará uma solicitação. Para engenharia terá uma tela nova, estilo Performance > Geração e ETM
> ETM ... porém liberada para todos os ativos".

O que a tela cria é uma OS (não uma solicitação), no molde da OS de análise (`api.create_os_analise`), com o título
'[Ativo] - Descrição'. Não usa plano: as telas da Performance dependem do plano do Fracttal, que só inversor, ETM e usina
têm — e aqui vale qualquer ativo. O resto, pedido por ele:
  - tipo de tarefa 'Administrativa' e SÓ a Classificação 1, 'Programada' (06/10: "o tipo de tarefa seria administrativa
    e class1 é programada!"); a 2 fica vazia — a tela vale para qualquer ativo, e 'Elétrica' não serve a uma cerca;
  - as etiquetas Remoto e ENGENHARIA, sempre, e só elas (06/10: "Etiqueta de remoto e engenharia fixas sempre! só essas
    etiquetas viu, sem performance"): nem PERFORMANCE nem "Dar prioridade" no urgente;
  - a data do EVENTO vem da tela, editável e com padrão agora, como na ETM (06/10: "tem que ter data do evento"); não
    pode estar no futuro;
  - data programada 7 dias depois da criação; "Urgente" (em vermelho) põe em 2 dias. NÃO se edita (Levi, 06/10:
    "data programada não deve ser possível editar!"): a tela só mostra, e o servidor calcula na hora de criar;
  - o responsável só entre os nomes da Engenharia — que vêm do .env (`OS_WEB_ENGENHARIA_RESPONSAVEIS`), nunca do
    código: o repositório é público, e nome de gente não vai para lá (é o mesmo caminho do responsável dos chamados);
  - o tipo de ativo dá para escrever, e a sigla do cadastro (NBRK) aparece com o nome (Nobreak).

Pedidos do Levi de 08/10/2026:
  - "Agrupar ativos em atividades por OS": além de uma OS por ativo (o padrão, como era), uma OS só, com uma atividade
    (tarefa) por ativo — o `api.create_work_orders_agrupada`, o mesmo do "Agrupar em UMA OS" do Tradicional;
  - "Engenharia poder anexar arquivos": PDF, imagem, planilha ou documento, que sobem DEPOIS de a OS existir, pelo mesmo
    caminho do anexo de hoje (`api.attach_imagem_os`), em cada OS criada; a tela diz o que subiu e o que falhou.

Regras puras (sem Flask): o teste as roda sem rede, e a rota só monta a requisição e a resposta."""
from __future__ import annotations
import datetime as dt
import os
import re
import unicodedata

BRT = dt.timezone(dt.timedelta(hours=-3))
DIAS_PADRAO = 7
DIAS_URGENTE = 2
TIPO_TAREFA = "Administrativa"
CLASSIF_1 = "Programada"
ETIQUETAS = ("Remoto", "ENGENHARIA")         # os nomes como estão no catálogo do Fracttal (Levi, 06/10: "é Remoto")
ENV_RESPONSAVEIS = "OS_WEB_ENGENHARIA_RESPONSAVEIS"
SUB_DESCRICAO = "Atividade a ser realizada (de forma direta)"
ROTULO_PROBLEMA = "Descreva o problema"

# A sigla do cadastro (o campo `tipo` do catálogo) → o nome que aparece na tela. Tirado dos PRÓPRIOS ativos de cada tipo
# (06/10, catálogo de 16.289 ativos: "XXX-NBRK — Nobreak", "XXX-DINV — Disjuntor do Inversor"…). Sigla que não está aqui
# aparece como veio (NCU e RSU, dos trackers, não têm nome no cadastro). O VALOR filtrado continua sendo a sigla.
NOME_TIPO = {
    "ALB": "Albedômetro", "ALRM": "Central de Alarme", "ANM": "Anemômetro", "ARCD": "Ar Condicionado",
    "BRT": "Biruta", "CBCA": "Cabos CA", "CBCC": "Cabos CC", "CCOM": "Cabo de Comunicação", "CCPU": "Computador (CPU)",
    "CETH": "Cabo Ethernet", "CGAT": "Conversor Serial (Gateway)", "CHSC": "Chave Seccionadora",
    "CMBB": "Combiner Box", "CMRA": "Câmeras de Segurança", "CNM": "Conversor de Mídia", "CPF": "Captor Franklin",
    "CRC": "Cerca (Perímetro)", "CTRL": "Controladores", "CXDA": "Caixa d'Água", "CXDP": "Caixa de Passagem",
    "DINV": "Disjuntor do Inversor", "DJMT": "Disjuntor de Média Tensão", "DTRF": "Disjuntor do Transformador",
    "EFIX": "Estrutura Fixa", "FBOT": "Fibra Ótica", "FDL": "Fieldlogger", "FSEP": "Fossa Séptica",
    "GATE": "Gateway Ethernet", "HSAT": "Haste de Aterramento", "ILMN": "Iluminação", "MDFV": "Módulo Fotovoltaico",
    "MLAT": "Malha de Aterramento", "NBRK": "Nobreak", "NVR": "NVR (gravador das câmeras)",
    "PECN": "Ponto de Entrega", "PGINVR": "Preventiva Grupo de Inversores", "PLCS": "Placas de Sinalização",
    "PLV": "Pluviômetro", "PPCI": "Sistema de Combate a Incêndio", "PRN": "Piranômetro", "PRTE": "Portão de Entrada",
    "QGBT": "Quadro Geral de Baixa Tensão (QGBT)", "RELE": "Relé da Cabine", "SCMD": "Sala de Comando",
    "SDP": "Sensor de Pás", "SDRN": "Sistema de Drenagem", "SDT": "Sensor de Temperatura",
    "SPDA": "SPDA (Para-raios)", "SWTC": "Switch", "TMH": "Termohigrômetro", "TRAX": "Transformador Auxiliar",
}


def rotulo_tipo(tipo) -> str:
    t = str(tipo or "").strip()
    return NOME_TIPO.get(t, t) or "—"


def _sem_acento(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


# ── os ativos (todos os tipos) ───────────────────────────────────────────────────────────────────────
def ativos_da_usina(assets, usina: str, curto=None) -> list:
    """Todos os ativos da usina, de qualquer tipo — a diferença para a Performance, que só mostra os do plano.
    `curto(asset)` é o nome que vai entre colchetes no título (`api._asset_short_name`), para a prévia da tela ser a OS."""
    out = [{"id": a.get("id"), "code": a.get("code"), "label": a.get("label") or a.get("description") or a.get("code"),
            "tipo": a.get("tipo") or "", "tipo_nome": rotulo_tipo(a.get("tipo")),
            "curto": curto(a) if curto else (a.get("label") or a.get("code"))}
           for a in (assets or []) if isinstance(a, dict) and a.get("usina") == usina and a.get("id") is not None]
    out.sort(key=lambda a: (_sem_acento(a["tipo_nome"]), _sem_acento(a["label"])))
    return out


def tipos_de(ativos) -> list:
    """[(sigla, nome)] dos tipos presentes, em ordem pelo NOME que a pessoa lê."""
    vistos = {}
    for a in ativos or []:
        if a.get("tipo"):
            vistos[a["tipo"]] = rotulo_tipo(a["tipo"])
    return sorted(vistos.items(), key=lambda kv: _sem_acento(kv[1]))


# ── os responsáveis da Engenharia ─────────────────────────────────────────────────────────────────────
def nomes_configurados(valor: str | None = None) -> list:
    """Os nomes do .env, separados por ';' (ou vírgula). Sem a variável: lista vazia — e a tela diz isso."""
    bruto = os.environ.get(ENV_RESPONSAVEIS, "") if valor is None else valor
    return [n.strip() for n in re.split(r"[;,]", bruto or "") if n.strip()]


def _casa(nome_cfg: str, nome_pessoa: str) -> bool:
    """"Ana Teste" casa com "Ana Teste da Silva": o 1º nome igual e todos os pedaços do nome configurado no nome
    da pessoa, inteiros e sem acento — "Bruno" não casa com "Brunoso"."""
    cfg, pes = _sem_acento(nome_cfg).split(), _sem_acento(nome_pessoa).split()
    return bool(cfg) and bool(pes) and cfg[0] == pes[0] and all(p in pes for p in cfg)


def responsaveis(pessoas, nomes) -> tuple[list, list]:
    """(as pessoas do Fracttal que casam com os nomes configurados, os nomes que não acharam ninguém). Pessoa sem
    id_personnel fica de fora: sem ele a OS não ganha responsável (é o id_responsible)."""
    achadas, faltam, vistos = [], [], set()
    for n in nomes or []:
        hits = [p for p in (pessoas or []) if isinstance(p, dict) and p.get("id_personnel") and _casa(n, p.get("name"))]
        if not hits:
            faltam.append(n)
        for p in hits:
            if p["id_personnel"] not in vistos:
                vistos.add(p["id_personnel"])
                achadas.append({"id_personnel": p["id_personnel"], "code": p.get("code") or "", "name": p.get("name") or ""})
    achadas.sort(key=lambda p: _sem_acento(p["name"]))
    return achadas, faltam


# ── as etiquetas ───────────────────────────────────────────────────────────────────────────────────────
def _nome_etq(t) -> str:
    return " ".join(_sem_acento(t).split())


def etiquetas(catalogo) -> tuple[list, list]:
    """(ids das ETIQUETAS no catálogo do Fracttal, os nomes que faltam). Pelo nome EXATO, sem acento e sem caixa: a busca
    por trecho do `api.label_id_por_nome` tomaria a 'Religamento Remoto' pela 'Remoto'. Faltou uma: quem chama não cria
    nada — OS da Engenharia sem as duas etiquetas não sai."""
    por_nome = {}
    for e in catalogo or []:
        if isinstance(e, dict) and e.get("id"):
            por_nome.setdefault(_nome_etq(e.get("description")), e["id"])
    ids = [por_nome[_nome_etq(n)] for n in ETIQUETAS if _nome_etq(n) in por_nome]
    return ids, [n for n in ETIQUETAS if _nome_etq(n) not in por_nome]


def erro_etiquetas(faltam) -> str:
    um = len(faltam) == 1
    return "Não achei no Fracttal %s %s. Nenhuma OS foi criada." % ("a etiqueta" if um else "as etiquetas", ", ".join(faltam))


# ── a data programada ──────────────────────────────────────────────────────────────────────────────────
def data_padrao(agora: dt.datetime, urgente: bool) -> dt.datetime:
    """A ÚNICA data programada possível: a hora da criação + 7 dias (Urgente: + 2). Não há data vinda da tela."""
    return agora + dt.timedelta(days=DIAS_URGENTE if urgente else DIAS_PADRAO)


def data_br(d: dt.datetime) -> str:
    return d.strftime("%d/%m/%Y %H:%M")


# ── o pedido ───────────────────────────────────────────────────────────────────────────────────────────
def montar(corpo: dict, assets_por_id: dict, permitidos: list, agora: dt.datetime, nome_os) -> tuple[list, dict, str]:
    """Do JSON da tela → (ativos do catálogo, campos da criação, erro). `nome_os(asset, base)` é o `api.perf_os_nome`
    ('[Ativo] - base'), passado de fora para a regra não depender do api."""
    corpo = corpo or {}
    ids = [i for i in (corpo.get("ativos") or []) if i is not None]
    assets = [assets_por_id.get(str(i)) for i in ids]
    if not ids:
        return [], {}, "Marque ao menos um ativo."
    if any(a is None for a in assets):
        return [], {}, "Um dos ativos marcados não está no catálogo — recarregue a página."
    descricao = " ".join(str(corpo.get("descricao") or "").split())
    if not descricao:
        return [], {}, "Escreva a atividade a ser realizada (o nome da OS)."
    problema = str(corpo.get("problema") or "").strip()
    if not problema:
        return [], {}, "Descreva o problema."
    resp = corpo.get("responsavel") or {}
    pid = resp.get("id_personnel") if isinstance(resp, dict) else None
    pessoa = next((p for p in permitidos or [] if str(p.get("id_personnel")) == str(pid)), None)
    if not pessoa:
        return [], {}, "Escolha o responsável entre os nomes da Engenharia."
    try:
        evento = dt.datetime.fromisoformat(str(corpo["evento"])).replace(tzinfo=BRT) if corpo.get("evento") else agora
    except ValueError:
        return [], {}, "Data do evento inválida."
    if evento > agora + dt.timedelta(minutes=5):           # o evento já aconteceu: no futuro é dado errado
        return [], {}, "A data do evento não pode estar no futuro."
    urgente = bool(corpo.get("urgente"))
    prog = data_padrao(agora, urgente)          # uma "programada" no pedido é ignorada: a data não se edita
    # o título '[Ativo] - Descrição' é o da OS de cada ativo e, na OS agrupada, o da atividade de cada ativo
    por_ativo = {a.get("code"): {"description": nome_os(a, descricao)} for a in assets}
    # com um ativo só, as duas escolhas dão a mesma OS: vai pelo caminho de sempre (o Tradicional faz igual)
    agrupar = bool(corpo.get("agrupar")) and len(assets) > 1
    campos = {"descricao": descricao, "note": problema, "urgente": urgente, "event_date": evento, "prog_date": prog,
              "id_responsible": pessoa["id_personnel"], "responsible_code": pessoa.get("code") or "",
              "responsible_name": pessoa.get("name") or "", "por_ativo": por_ativo, "agrupar": agrupar}
    return assets, campos, ""


def _nomes(assets) -> dict:
    return {a.get("code"): (a.get("label") or a.get("code")) for a in assets or []}


def mensagem(res, assets, prog: dt.datetime | None = None) -> dict:
    """[{code, ok, os:{wo_folio}} | {code, ok:False, erro}] do `create_work_orders_bulk` → {ok, falhas, mensagem, folios}.
    Com `prog`, a mensagem diz a data que o servidor pôs — a tela não a escolhe, então quem criou precisa vê-la."""
    nome = _nomes(assets)
    res = res or []
    ok = [r for r in res if r.get("ok")]
    fail = [r for r in res if not r.get("ok")]
    folios = [(r.get("os") or {}).get("wo_folio") for r in ok]
    if not ok:
        msg = "Nenhuma OS criada.\n" + "\n".join("• %s: %s" % (nome.get(r.get("code"), r.get("code")), r.get("erro")) for r in fail[:8])
    else:
        msg = "%d OS criada(s) para a Engenharia — Nº %s" % (len(ok), ", ".join(str(f or "?") for f in folios[:12]))
        msg += (" — programada(s) para %s." % data_br(prog)) if prog else "."
        if fail:
            msg += "\n\n%d falharam:\n" % len(fail) + "\n".join(
                "• %s: %s" % (nome.get(r.get("code"), r.get("code")), r.get("erro")) for r in fail[:6])
    avisos = [str((r.get("os") or {}).get("aviso")) for r in ok if (r.get("os") or {}).get("aviso")]
    return {"ok": len(ok), "falhas": len(fail), "mensagem": msg, "folios": folios, "avisos": avisos}


def _lista_erros(erros, nome) -> str:
    """Os erros da agrupada vêm como 'CÓDIGO: motivo'; na tela vai o nome do ativo, como no `mensagem`."""
    linhas = []
    for e in [x for x in erros or [] if x][:6]:
        code, sep, resto = str(e).partition(": ")
        linhas.append("• %s: %s" % (nome.get(code, code), resto) if sep else "• %s" % e)
    return "\n".join(linhas)


def mensagem_agrupada(res, assets, prog: dt.datetime | None = None) -> dict:
    """O {ok, os:{wo_folio}, n_criadas, erros, aviso} do `create_work_orders_agrupada` → o formato do `mensagem`, mais
    `pendentes`: as atividades que nasceram no Fracttal mas ficaram sem a OS numerada (a OS não fechou). Isso não é
    "nenhuma criada" — a tela precisa tirar os ativos da seleção, ou um 2º clique criaria tudo de novo."""
    res = res or {}
    nome = _nomes(assets)
    if not res.get("ok"):
        return {"ok": 0, "falhas": len(assets or []) or 1, "pendentes": 0, "folios": [], "avisos": [],
                "mensagem": "Nenhuma OS criada.\n" + _lista_erros(res.get("erros") or [res.get("erro")], nome)}
    folio = (res.get("os") or {}).get("wo_folio")
    n = int(res.get("n_criadas") or 0)
    erros = res.get("erros") or []
    if folio:
        msg = "1 OS criada para a Engenharia — Nº %s, com %d atividade(s), uma por ativo" % (folio, n)
        msg += (" — programada para %s." % data_br(prog)) if prog else "."
    else:
        msg = ("As %d atividade(s) nasceram no Fracttal, mas a OS não foi numerada: elas ficaram pendentes. Gere a OS a "
               "partir delas no Fracttal — não crie de novo aqui." % n)
    if erros:
        msg += "\n\n%d ativo(s) ficaram de fora:\n" % len(erros) + _lista_erros(erros, nome)
    return {"ok": 1 if folio else 0, "falhas": len(erros) + (0 if folio else 1), "pendentes": 0 if folio else n,
            "mensagem": msg, "folios": [folio] if folio else [], "avisos": [str(res["aviso"])] if res.get("aviso") else []}


def oss_do_bulk(res) -> list:
    """As OS criadas pelo `create_work_orders_bulk`, para receber os anexos: [{folio, id_work_order}]."""
    return [{"folio": (r.get("os") or {}).get("wo_folio"), "id_work_order": (r.get("os") or {}).get("id_work_order")}
            for r in res or [] if r.get("ok")]


def oss_da_agrupada(res) -> list:
    o = (res or {}).get("os") or {}
    return [{"folio": o.get("wo_folio"), "id_work_order": o.get("id_work_order")}] if (res or {}).get("ok") else []


# ── os anexos (Levi, 08/10/2026: "Engenharia poder anexar arquivos") ─────────────────────────────────────
# Sobem DEPOIS de a OS existir, pelo MESMO caminho do anexo que o OS Creator já usa (`api.attach_imagem_os`:
# s3_object_post → upload no S3 → tasks.work_orders_tasks_files_insert), que serve a qualquer arquivo: o tipo vai pela
# extensão. O anexo é preso a uma TAREFA da OS; na OS agrupada vai na 1ª, e o card da OS o mostra uma vez só (a lista
# de anexos da OS junta as tarefas dela).
MB = 1024 * 1024
MAX_ARQUIVOS = 5              # por criação: é documento de apoio, não acervo
MAX_MB_ARQUIVO = 10           # um relatório em PDF ou a foto do celular cabem; vídeo não
MAX_MB_TOTAL = 20             # o que um pedido carrega. O app aceita 4 MB (as imagens do Tradicional): esta rota abre
LIMITE_PEDIDO = (MAX_MB_TOTAL + 1) * MB      # para os anexos + 1 MB do resto do formulário
# Com uma OS por ativo, cada anexo sobe para CADA OS. Cada envio custa 2 pedidos ao Fracttal (a cota é da EMPRESA,
# 200/min, dividida com o App de Campo) mais o arquivo para o S3, e a resposta tem de voltar antes de o túnel desistir
# (o cloudflared do supervisório corta em ~100 s). Passou disto, a tela pede "Uma OS com todos os ativos" (os anexos
# sobem uma vez) ou menos anexos — e nada é criado.
MAX_ENVIOS = 30
MAX_MB_ENVIOS = 100
ENVIOS_PARALELOS = 4          # ao mesmo tempo: menos rajada na cota que os 8 das leituras do card da OS
MAX_NOME = 120

# extensão → (como conferir o conteúdo, o que é). O conteúdo é conferido porque a extensão é só o nome: um executável
# renomeado para .pdf subiria para o Fracttal, e lá qualquer um o baixa. Os formatos antigos (.xls, .doc) aceitam também
# texto: muito sistema exporta "xls" que por dentro é HTML ou CSV, e o Word salva RTF como .doc. Tipo novo = uma linha.
TIPOS_ANEXO = {
    ".pdf": ("pdf", "PDF"),
    ".jpg": ("imagem", "imagem"), ".jpeg": ("imagem", "imagem"), ".png": ("imagem", "imagem"),
    ".webp": ("imagem", "imagem"), ".gif": ("imagem", "imagem"), ".bmp": ("imagem", "imagem"),
    ".xlsx": ("zip", "planilha"), ".xls": ("ole", "planilha"), ".csv": ("texto", "planilha"), ".ods": ("zip", "planilha"),
    ".docx": ("zip", "documento"), ".doc": ("ole", "documento"), ".odt": ("zip", "documento"), ".txt": ("texto", "documento"),
}
ACEITAR = ",".join(TIPOS_ANEXO)          # o accept do <input type=file>: o seletor do navegador já filtra
_UM = {"PDF": "um PDF", "imagem": "uma imagem", "planilha": "uma planilha", "documento": "um documento"}
_IMAGEM = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM")
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"          # o .xls e o .doc de antes do Office 2007


def tipos_aceitos() -> str:
    """'PDF; imagem (JPG, JPEG, …); planilha (…); documento (…)' — a mesma frase na tela e nas recusas."""
    grupos: dict = {}
    for ext, (_, nome) in TIPOS_ANEXO.items():
        grupos.setdefault(nome, []).append(ext[1:].upper())
    return "; ".join(n if exts == [n] else "%s (%s)" % (n, ", ".join(exts)) for n, exts in grupos.items())


def tamanho_br(n: int) -> str:
    """Arredonda para CIMA: um arquivo de 10 MB e 5 bytes recusado como "10,0 MB — o limite é 10 MB" não se explica."""
    if n < MB:
        return "%d KB" % max(1, -(-n // 1024))
    return ("%.1f MB" % (-(-n * 10 // MB) / 10)).replace(".", ",")


def nome_seguro(nome) -> str:
    """O nome vira a chave do arquivo no S3 do Fracttal ('.ot/<OS>/<nome>'): uma barra abriria uma subpasta (com '..',
    sairia da pasta da OS) e '#', '?', '%' e '+' estragam o link de baixar. Ficam letra (com acento), número, espaço,
    ponto, vírgula, hífen, sublinhado e parênteses; o resto vira '_'. O caminho que alguns navegadores mandam junto
    ('C:\\fakepath\\…') sai."""
    base = re.split(r"[\\/]", str(nome or ""))[-1]
    base = re.sub(r"[^\w .,()-]+", "_", unicodedata.normalize("NFC", base))
    base = re.sub(r"\s+", " ", base).strip(" ._")
    raiz, ext = os.path.splitext(base)
    return (raiz[:MAX_NOME].rstrip(" ._") + ext) if raiz else ""


def _parece_texto(dados: bytes) -> bool:
    """Texto não tem byte zero no começo (um executável tem vários); o UTF-16 do Bloco de Notas tem, e começa pela marca."""
    amostra = dados[:4096]
    return amostra.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" not in amostra


def conteudo_bate(ext: str, dados: bytes) -> bool:
    jeito = TIPOS_ANEXO[ext][0]
    if jeito == "pdf":
        return b"%PDF-" in dados[:1024]                   # o leitor tolera lixo antes do cabeçalho, até 1 KB
    if jeito == "imagem":                                  # qualquer imagem: '.jpg' que é WEBP por dentro abre igual
        return dados.startswith(_IMAGEM) or (dados[:4] == b"RIFF" and dados[8:12] == b"WEBP")
    if jeito == "zip":
        return dados.startswith(b"PK\x03\x04")            # xlsx, docx, ods e odt são zip por dentro
    if jeito == "ole":
        return dados.startswith(_OLE) or _parece_texto(dados)
    return _parece_texto(dados)


def _sem_repetir(nome: str, vistos: set) -> str:
    """Dois anexos com o mesmo nome iriam para a MESMA chave no S3 da OS, e o segundo apagaria o primeiro: o segundo
    ganha ' (2)', como no zip do 'Baixar todos'."""
    raiz, ext = os.path.splitext(nome)
    novo, i = nome, 2
    while novo.lower() in vistos:
        novo, i = "%s (%d)%s" % (raiz, i, ext), i + 1
    vistos.add(novo.lower())
    return novo


def anexos(brutos) -> tuple[list, str]:
    """[(nome, bytes)] do formulário → ([{nome, bytes, tamanho}], erro). Erro, e não descarte calado, como nas imagens
    da Performance: a pessoa anexou porque o arquivo importa, e a rota não cria OS nenhuma enquanto os anexos não passam."""
    brutos = [(n, b) for n, b in (brutos or []) if n or b]
    nada = " Nenhuma OS foi criada."
    if len(brutos) > MAX_ARQUIVOS:
        return [], "São %d anexos — o limite é %d por criação.%s" % (len(brutos), MAX_ARQUIVOS, nada)
    out, vistos, total = [], set(), 0
    for nome_in, dados in brutos:
        nome = nome_seguro(nome_in)
        quem = "“%s”" % (nome or str(nome_in or "").strip() or "sem nome")
        ext = os.path.splitext(nome)[1].lower()
        if ext not in TIPOS_ANEXO:
            return [], "%s: tipo de arquivo não aceito. Aceitos: %s.%s" % (quem, tipos_aceitos(), nada)
        if not dados:
            return [], "%s veio vazio.%s" % (quem, nada)
        if len(dados) > MAX_MB_ARQUIVO * MB:
            return [], "%s tem %s — o limite é %d MB por arquivo.%s" % (quem, tamanho_br(len(dados)), MAX_MB_ARQUIVO, nada)
        if not conteudo_bate(ext, dados):
            return [], ("%s não é %s de verdade: o conteúdo não bate com a extensão.%s"
                        % (quem, _UM[TIPOS_ANEXO[ext][1]], nada))
        total += len(dados)
        out.append({"nome": _sem_repetir(nome, vistos), "bytes": dados, "tamanho": len(dados)})
    if total > MAX_MB_TOTAL * MB:
        return [], "Os anexos somam %s — o limite é %d MB no total.%s" % (tamanho_br(total), MAX_MB_TOTAL, nada)
    return out, ""


def erro_envios(anexos_ok, n_os: int) -> str:
    """Com uma OS por ativo, cada anexo sobe para cada OS: limite no número de envios e no volume (ver MAX_ENVIOS)."""
    if not anexos_ok:
        return ""
    n_os = max(1, int(n_os or 1))
    envios = len(anexos_ok) * n_os
    volume = sum(a["tamanho"] for a in anexos_ok) * n_os
    if envios <= MAX_ENVIOS and volume <= MAX_MB_ENVIOS * MB:
        return ""
    return ("Com uma OS por ativo, cada anexo sobe para cada OS: %d OS × %d anexo(s) = %d envios (%s). O limite por "
            "criação é %d envios e %d MB. Escolha “Uma OS com todos os ativos” (os anexos sobem uma vez só) ou anexe "
            "menos arquivos. Nenhuma OS foi criada."
            % (n_os, len(anexos_ok), envios, tamanho_br(volume), MAX_ENVIOS, MAX_MB_ENVIOS))


def _curto(e) -> str:
    return (str(e).strip() or type(e).__name__)[:160]


def anexar(oss, anexos_ok, subir, tarefas, mapa=map) -> list:
    """Sobe cada anexo em cada OS. `oss` = [{folio, id_work_order}]; `subir(id_wo, id_tarefa, bytes, nome)` é o
    `api.attach_imagem_os` e `tarefas(id_wo)` o `api._ids_tarefas_da_os` — passados de fora, para o teste usar o Fracttal
    falso. `mapa` é o map do executor que leva a sessão para as threads (`api._ExecutorComContexto`).
    Nenhum erro escapa daqui: a OS já existe, e quem criou precisa saber o que subiu e o que não. Uma sessão que cai no
    meio vira a falha daquele envio, e a resposta continua dizendo quais OS nasceram (sem isso, a pessoa criaria de novo).
    → [{nome, tamanho, ok: [nº da OS], falhas: [(nº da OS, erro)]}], na ordem dos anexos."""
    if not anexos_ok or not oss:
        return []

    def _tarefa(o):
        if not o.get("id_work_order"):
            return None, "a OS não foi numerada"
        try:
            ts = tarefas(o["id_work_order"]) or []
        except Exception as e:                             # noqa: BLE001 — vira a falha dos envios desta OS
            return None, "não consegui ler a tarefa da OS (%s)" % _curto(e)
        return (ts[0], "") if ts else (None, "não achei a tarefa da OS")
    alvos = list(zip(oss, mapa(_tarefa, oss)))

    def _um(trabalho):
        o, (tid, erro), a = trabalho
        if not tid:
            return erro
        try:
            subir(o["id_work_order"], tid, a["bytes"], a["nome"])
        except Exception as e:                             # noqa: BLE001 — idem
            return _curto(e)
        return ""
    erros = list(mapa(_um, [(o, t, a) for a in anexos_ok for o, t in alvos]))
    out = []
    for i, a in enumerate(anexos_ok):
        r = {"nome": a["nome"], "tamanho": a["tamanho"], "ok": [], "falhas": []}
        for j, (o, _t) in enumerate(alvos):
            ref = str(o.get("folio") or o.get("id_work_order") or "sem número")
            e = erros[i * len(alvos) + j]
            if e:
                r["falhas"].append((ref, e))
            else:
                r["ok"].append(ref)
        out.append(r)
    return out


def _nas(refs) -> str:
    if len(refs) == 1:
        return "na OS %s" % refs[0]
    if len(refs) <= 4:
        return "nas OS %s e %s" % (", ".join(refs[:-1]), refs[-1])
    return "nas %d OS" % len(refs)


def com_anexos(out: dict, resultados: list, n_anexos: int, sem_numero: int = 0) -> dict:
    """A resposta do criar com o que subiu e o que falhou, arquivo por arquivo (Levi, 08/10: "a tela diz o que subiu e o
    que falhou"). `sem_numero` = OS que nasceram sem número (a tarefa não virou OS): não têm onde receber o anexo.
    `anexos_falhas` = envios que não aconteceram (a tela pinta o resultado de vermelho)."""
    if not n_anexos:
        return out
    out = dict(out)
    falhas = sem_numero * n_anexos
    if not resultados:
        falhas = max(falhas, n_anexos)
        bloco = "Anexos: nenhum foi enviado — %s." % ("nenhuma OS foi criada" if not sem_numero else
                                                       "a OS não foi numerada" if sem_numero == 1 else
                                                       "as OS não foram numeradas")
    else:
        linhas = []
        for r in resultados:
            partes = ["subiu " + _nas(r["ok"])] if r["ok"] else []
            if r["falhas"]:
                falhas += len(r["falhas"])
                ruins = "; ".join("na OS %s (%s)" % f for f in r["falhas"][:3])
                if len(r["falhas"]) > 3:
                    ruins += "; e em mais %d" % (len(r["falhas"]) - 3)
                partes.append(("falhou " if r["ok"] else "NÃO subiu: ") + ruins)
            linhas.append("• %s (%s): %s." % (r["nome"], tamanho_br(r["tamanho"]), "; ".join(partes)))
        if sem_numero:
            linhas.append("• %d OS sem número %s sem os anexos." % (sem_numero, "ficou" if sem_numero == 1 else "ficaram"))
        bloco = "Anexos:\n" + "\n".join(linhas)
    out["mensagem"] = (out.get("mensagem") or "") + "\n\n" + bloco
    out["anexos"] = [{"nome": r["nome"], "tamanho": r["tamanho"], "ok": r["ok"],
                      "falhas": [{"os": f, "erro": e} for f, e in r["falhas"]]} for r in resultados]
    out["anexos_falhas"] = falhas
    return out

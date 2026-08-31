"""O diário de edições do app — a "cópia no banco" que o sync não alcança.

POR QUE EXISTE
O pipeline sobe o `Tickets de Performance.xlsx` inteiro com `replace=true`, então uma edição
feita aqui pode ser desfeita no sync seguinte. Enquanto esse sync existir, gravar só na aba
original é aceitar que o trabalho de quem digitou volte atrás sozinho.

A saída é uma aba que o pipeline NÃO alcança. Medido em 31/08 contra o `zz_teste_claude_apagar`:
subindo o arquivo sem duas abas, a API respondeu `{"sheets":13,...,"deleted":0}` e a linha-marca
que eu havia gravado numa delas continuava lá. **`replace=true` só substitui as abas presentes
no arquivo.** Como esta aba nasce pela API e nunca existe no `.xlsx`, nada a apaga.

DIÁRIO, NÃO CÓPIA INTEGRAL
Duplicar as 2.796 linhas e passar a ler só a cópia teria um custo escondido: ocorrência nova
digitada no Excel nunca mais apareceria no app, e reconciliar as duas trariam de volta o mesmo
problema de sobrescrita, agora nos dois sentidos. Aqui guarda-se só **o que o app gravou**:
uma linha por salvamento, com quem, quando e os campos. Na leitura, o app aplica o diário por
cima do que veio do banco. Ocorrência nova do Excel aparece normalmente; edição do app
sobrevive ao sync; e, quando o sync morrer, isto continua valendo como histórico de quem mudou
o quê — que a spec já pedia.

O QUE PROTEGE CONTRA APLICAR NA LINHA ERRADA
A chave natural é o `row_number`, e ele NÃO é estável: linha apagada no meio do Excel desloca
todas as de baixo, e o diário passaria a corrigir a ocorrência do vizinho — errado em silêncio,
que é a pior forma de errar aqui. Por isso cada registro carrega uma IMPRESSÃO (usina + o ativo
identificado) e só é aplicado quando ela bate com a ocorrência daquela linha. Não batendo, o
registro é ignorado e contado como órfão, para alguém poder olhar.
"""
import datetime as _dt
import os

import requests

import tickets_escrita as _esc

BASE = _esc.BASE
TIMEOUT = _esc.TIMEOUT
WORKBOOK = "tickets_performance"
NOME_ABA = "Edicoes do app"          # sem acento: é nome de aba, e o .xlsx não a conhece

# 'quando' em ISO para ordenar como texto; o resto são os campos que a tela edita.
CAMPOS = ["Causa raiz", "Responsabilidade da Grid Co.?", "Início da ocorrência",
          "Início do chamado pela Grid Co.", "Fim da ocorrência", "Comentários gerais", "OS"]

# Campos que NÃO existem como coluna na planilha e por isso vivem só aqui. Duas consequências:
# eles nunca são "restaurados" (não há valor no banco para o sync desfazer, então anunciar seria
# ruído em toda abertura), e a gravação na aba real simplesmente os ignora — `para_valores` só
# escreve o que está no cabeçalho.
#
# 'OS' é o caso: a planilha não tem coluna de OS (conferido nas duas abas em 31/08) e criar uma
# não adiantaria enquanto o pipeline subir o .xlsx — o sync encolhe a aba de volta. Então o
# vínculo com a OS mora no diário até o corte.
CAMPOS_SEM_COLUNA = {"OS"}

COLUNAS = ["quando", "quem", "aba", "linha", "impressao"] + CAMPOS

_SHEET_ID = {}          # nome da aba → sheet_id, resolvido uma vez por execução


def _norm(v) -> str:
    return " ".join(str(v or "").split()).strip().lower()


def impressao(aba: str, oc: dict) -> str:
    """Usina + ativo. NÃO entra data aqui: a tela edita as duas datas, e uma impressão que muda
    quando a pessoa corrige o Início deixaria de bater com o próprio registro que a gravou."""
    if aba == "Trackers":
        ativo = "%s/%s" % (_norm(oc.get("Nº do SKID")), _norm(oc.get("Nº do tracker / Identificação")))
    else:
        ativo = _norm(oc.get("Inversor"))
    return "%s|%s" % (_norm(oc.get("Usina")), ativo)


def quem() -> str:
    """Quem está mexendo. O usuário do Windows basta e não acopla este módulo ao login do
    Fracttal — são as mesmas quatro pessoas que editam a planilha hoje."""
    return (os.environ.get("USERNAME") or os.environ.get("USER") or "?").strip()


def _get(caminho: str):
    r = requests.get(BASE + caminho, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def garantir_aba(listar=None, criar=None) -> int:
    """O sheet_id da aba do diário, criando-a se ainda não existir. Injetável para teste."""
    if NOME_ABA in _SHEET_ID:
        return _SHEET_ID[NOME_ABA]
    abas = listar() if listar is not None else _get("/api/sheets")
    for s in abas or []:
        if s.get("workbook_key") == WORKBOOK and s.get("sheet_name") == NOME_ABA:
            return _liberar(s["id"])
    corpo = {"sheet_name": NOME_ABA, "headers": list(COLUNAS)}
    if criar is not None:
        nova = criar(corpo)
    else:
        r = requests.post("%s/api/workbooks/%s/sheets" % (BASE, WORKBOOK),
                          headers=_esc._cabecalho(), json=corpo, timeout=TIMEOUT)
        r.raise_for_status()
        nova = r.json()
    return _liberar(nova["id"])


def _liberar(sheet_id: int) -> int:
    """A trava de escrita é por id, e o id desta aba só se conhece rodando — ela nasce pela API.
    Registrar aqui não afrouxa a trava: esta aba é a única que o `.xlsx` do pipeline nunca
    contém, ou seja, exatamente a que não corre o risco que a trava existe para evitar."""
    _SHEET_ID[NOME_ABA] = sheet_id
    _esc.SHEETS_LIBERADAS.setdefault(sheet_id, "%s/%s" % (WORKBOOK, NOME_ABA))
    return sheet_id


def registrar(aba: str, oc: dict, valores: dict, agora=None, enviar=None, sheet_id=None) -> dict:
    """Acrescenta uma linha ao diário. Nunca atualiza: é log, e o mais novo é que vale."""
    sid = sheet_id if sheet_id is not None else garantir_aba()
    quando = (agora or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    dados = {"quando": quando, "quem": quem(), "aba": aba,
             "linha": oc.get("_row"), "impressao": impressao(aba, oc)}
    for c in CAMPOS:
        dados[c] = valores.get(c, "")
    return _esc.criar_linha(sid, dados, COLUNAS, enviar=enviar)


def _mais_recentes(registros: list, aba: str) -> dict:
    """(linha) → registro mais novo daquela aba. Empate de 'quando' desempata pela ordem de
    gravação, que é a ordem em que a API devolve — o último a entrar é o que vale."""
    por_linha = {}
    for r in registros or []:
        if str(r.get("aba") or "") != aba:
            continue
        try:
            linha = int(r.get("linha"))
        except (TypeError, ValueError):
            continue
        anterior = por_linha.get(linha)
        if anterior is None or str(r.get("quando") or "") >= str(anterior.get("quando") or ""):
            por_linha[linha] = r
    return por_linha


def aplicar(aba: str, ocorrencias: list, registros: list) -> dict:
    """Põe o diário por cima do que veio do banco.

    Marca em `_restaurado` os campos que o diário teve de repor — a tela mostra isso, porque
    "o app desfez o que o sync desfez" precisa ser visível, não mágica. Devolve o placar."""
    por_linha = _mais_recentes(registros, aba)
    if not por_linha:
        return {"aplicados": 0, "campos": 0, "orfaos": 0}
    por_row = {}
    for oc in ocorrencias:
        try:
            por_row[int(oc.get("_row"))] = oc
        except (TypeError, ValueError):
            continue
    aplicados = campos = orfaos = 0
    for linha, reg in por_linha.items():
        oc = por_row.get(linha)
        # impressão diferente = a linha não é mais a mesma ocorrência (alguém apagou uma linha
        # no Excel e tudo desceu). Ignorar é o certo: aplicar seria corrigir a ocorrência errada.
        if oc is None or _norm(reg.get("impressao")) != _norm(impressao(aba, oc)):
            orfaos += 1
            continue
        repostos = []
        for c in CAMPOS:
            novo = reg.get(c)
            if _norm(novo) != _norm(oc.get(c)):
                oc[c] = "" if novo is None else novo
                if c not in CAMPOS_SEM_COLUNA:
                    repostos.append(c)
        if repostos:
            oc["_restaurado"] = repostos
            aplicados += 1
            campos += len(repostos)
    return {"aplicados": aplicados, "campos": campos, "orfaos": orfaos}


def ler(sheet_id=None, listar=None) -> list:
    """As linhas do diário. Falha de leitura não pode derrubar a tela — quem chama decide."""
    import tickets_api
    sid = sheet_id if sheet_id is not None else garantir_aba()
    return (listar or tickets_api.listar_linhas)(sid)

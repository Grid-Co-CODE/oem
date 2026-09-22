"""A OCORRÊNCIA NASCE COM A OS — o "pulo do gato" (Levi, 31/08).

Até aqui a ordem era ao contrário: alguém digitava a ocorrência na planilha e, dias depois,
abria a OS. O tempo entre as duas é justamente o que ninguém conseguia medir, e a linha só
existia se alguém lembrasse de criá-la. Agora, criar uma OS de "Recomposição de String" ou de
"Verificação de Tracker Parado" no Performance acrescenta a linha na aba de tickets na hora, já
com a OS vinculada.

O QUE ENTRA NA LINHA: usina, o ativo (inversor ou skid/tracker), o início da ocorrência (a data
do incidente que a pessoa escolheu na tela) e o "Início do chamado pela Grid Co." (agora, que é
quando a Grid abriu a OS). Causa raiz fica VAZIA de propósito — quem diz é o técnico, no fim.

QUANTIDADE E OBSERVAÇÃO (Levi, 10/09/2026). Até aqui a quantidade era `1` FIXO nas duas abas, e
em Strings isso é falso: o inversor cai com seis strings e a planilha registrava uma. Agora a
tela manda o número — contado da observação por `contar_strings` e conferido no card ao lado do
ativo. E a observação da OS (ou da tarefa, quando é uma OS com vários ativos) desce para
"Comentários gerais" como frase pronta: "Ipv10, Ipv11 e Ipv12 com corrente nula em 10/09/2026
07:30". Vai nessa coluna, e não em "Comentários para os clientes", porque aquela é a que o
cliente lê no relatório e é escrita por gente.

O QUE NÃO ENTRA: a OS. Ela não tem coluna na planilha e vive no diário, junto do status inicial
"OS Programada" — mesma regra do vínculo feito à mão na tela.

FALHAR AQUI NÃO PODE DERRUBAR A CRIAÇÃO DA OS. A OS é o que a equipe precisa; a linha de ticket
é registro. Por isso todo o caminho é best-effort e o erro volta como aviso, não como exceção.
"""
import datetime as _dt
import re

import api
import tickets_api
import tickets_diario
import tickets_escrita
import tickets_spec

# frase do plano (normalizada) → aba de tickets que recebe a linha
PLANOS = {
    "recomposicao de string": "Strings",
    "verificacao de tracker parado": "Trackers",
}

_NUM_INV = re.compile(r"(\d+(?:\.\d+)*)")

# ── A RÉGUA DAS STRINGS (Levi, 10/09/2026) ───────────────────────────────────────────────────────
# "a palavra isolada tem que vir com um número colado ou um número logo após o space".
#
# POR QUE NÃO É "contar toda ocorrência de PV/STR/String": a plataforma manda
# "Strings Ipv10, Ipv11 e Ipv12 com corrente nula" — contar a palavra do texto corrido junto com os
# nomes daria 4 para três strings, e "String Ipv4 com corrente nula" daria 2 para uma. Medido nos
# dois formatos que o deep link gera hoje (`_osObs` do index.html da plataforma).
#
# "string" ANTES de "str" na alternância: a regex casa a primeira alternativa que serve, e com
# "str" na frente "String 4" tentaria "str" + "ing 4" e falharia no \d+.
# SEM fronteira à esquerda: o nome real vem grudado num prefixo — em "Ipv10" o marcador é o "pv"
# no meio da palavra, e um \b ali faria a régua não achar nada.
_RE_TOK = re.compile(r"(?:string|str|pv)\s*[-_.]?\s*(\d+)", re.I)
# Saída de emergência: o número vem ANTES da palavra ("3 strings sem corrente"), que é como se
# escreve quando não se lista nome nenhum.
_RE_ANTES = re.compile(r"(\d+)\s*(?:strings?|str|pv)\b", re.I)


def contar_strings(texto):
    """(quantidade, via, nomes) das strings citadas numa observação.

    `via` diz DE ONDE veio o número, e a tela usa isso para marcar o card: 'tokens' são nomes
    achados, 'antes' é o número que veio antes da palavra, 'presumido' é o mínimo de 1 — porque
    zero não pode ir para a planilha: se a OS está sendo aberta, pelo menos uma string caiu.

    Os NOMES voltam como a pessoa escreveu ('Ipv10', não 'pv10'): a regex casa a partir do 'pv',
    então é preciso voltar enquanto for letra para não citar o ativo pela metade na observação
    do ticket."""
    t = str(texto or "")
    vistos, nomes = [], []
    for m in _RE_TOK.finditer(t):
        tok = re.sub(r"[\s\-_.]", "", m.group(0).lower())
        if tok in vistos:                 # "Ipv10 e Ipv10" é a mesma string citada duas vezes
            continue
        vistos.append(tok)
        i = m.start()
        while i > 0 and t[i - 1].isalpha():
            i -= 1
        nomes.append(t[i:m.end()])
    if vistos:
        return len(vistos), "tokens", nomes
    achou = _RE_ANTES.search(t)
    if achou:
        n = int(achou.group(1))
        if n > 0:
            return n, "antes", []
    return 1, "presumido", []


def _lista(nomes) -> str:
    """['A','B','C'] → 'A, B e C' — o 'e' antes do último, como se escreve em português."""
    nomes = [n for n in (nomes or []) if str(n).strip()]
    if not nomes:
        return ""
    if len(nomes) == 1:
        return nomes[0]
    return "%s e %s" % (", ".join(nomes[:-1]), nomes[-1])


def observacao_ticket(aba: str, nota, quantidade=None, quando=None) -> str:
    """A frase que vai para "Comentários gerais" da linha.

    Três formatos, nesta ordem (Levi, 10/09): os nomes achados na observação; a observação livre
    inteira, quando não há nomes; e um texto mínimo quando não há observação nenhuma. A data é
    sempre a do incidente — é o que a planilha chama de início da ocorrência, e sem ela a frase
    não se sustenta sozinha na coluna."""
    txt = str(nota or "").strip()
    data = (quando or _dt.datetime.now()).strftime("%d/%m/%Y %H:%M")
    if aba == "Strings":
        n, via, nomes = contar_strings(txt)
        if via == "tokens" and nomes:
            return "%s com corrente nula em %s" % (_lista(nomes), data)
        if txt:
            return "%s — em %s" % (txt, data)
        q = int(quantidade or n)
        return "%d string%s sem corrente em %s" % (q, "" if q == 1 else "s", data)
    if txt:
        return "%s — em %s" % (txt, data)
    return "Tracker parado em %s" % data


def aba_do_plano(descricao) -> str:
    """A aba de tickets que corresponde ao plano, ou '' quando o plano não gera ocorrência."""
    d = api._norm_txt(descricao)
    for frase, aba in PLANOS.items():
        if frase in d:
            return aba
    return ""


def _identificacao(asset: dict):
    """(skid, numero) a partir do nome do ativo, para as duas colunas da planilha.

    O NÚMERO É O NOME INTEIRO, sempre: 'Tracker 3.101' → '3.101', e não '3'. Até 09/09 o primeiro
    pedaço virava skid e o resto virava o número — de 'Tracker 3.101' saía skid '3', número
    '3.101'. Errado dos dois lados: em Diamantino o '3' é o TRACKER (o '101' é a cabine), e o
    número com o sufixo não casava com nada, porque o índice de `steps.tickets` descartava os três
    dígitos finais. Ou seja, ocorrência criada pelo app nunca achava o próprio ativo. Agora o
    índice guarda o nome inteiro, e mandar o nome inteiro casa EXATO — sem depender de adivinhar o
    que o sufixo significa naquela usina (em Diamantino é cabine; no MAB100, 'Tracker 1.102', é o
    número do tracker, e o skid é o 1).

    O SKID só sai quando o nome tem TRÊS partes — 'Tracker 1.5.101' em Boa Esperança, onde o
    primeiro pedaço é de fato a sub-usina. Com duas partes não dá para saber se a segunda é cabine
    ou número, e chutar enche a coluna Cabine da tela com o número do tracker."""
    nome = str(api._asset_short_name(asset) or "")
    achou = _NUM_INV.search(nome)
    num = achou.group(1) if achou else ""
    skid = num.split(".", 1)[0] if num.count(".") >= 2 else ""
    return skid, num


def usina_do_ativo(asset: dict) -> str:
    """O CÓDIGO da usina a partir do code do ativo: penúltimo segmento ('THPN-SDN100-INVR1.1' →
    'SDN100', 'JCD100-INVR2.1' → 'JCD100'). É o formato que a maioria das linhas da planilha usa
    e é por segmento que o casamento com o ativo acontece."""
    partes = str(asset.get("code") or "").split("-")
    if len(partes) >= 2 and partes[-2].strip():
        return partes[-2].strip()
    return str(asset.get("usina") or "").strip()


def montar_linha(aba: str, asset: dict, usina: str, quando, agora=None,
                 quantidade=None, nota="") -> dict:
    """{coluna: valor} da ocorrência nova. Só as colunas que a aba tem — o resto o
    `para_valores` completa vazio.

    `quantidade` é o número do card da tela (strings afetadas ou trackers parados). Vindo None,
    Strings conta da própria `nota` e Trackers fica em 1 — assim quem chamar sem tela continua
    tendo o comportamento antigo, só que com a contagem certa em vez do 1 fixo.
    `nota` é a observação daquele ativo, que vira a frase de "Comentários gerais"."""
    ag = agora or _dt.datetime.now()
    ini = quando or ag
    linha = {
        "Usina": str(usina or "").strip(),
        "Início da ocorrência": ini.strftime("%Y-%m-%d %H:%M:%S"),
        "Início do chamado pela Grid Co.": ag.strftime("%Y-%m-%d %H:%M:%S"),
        "Causa raiz": "",                       # é o técnico quem diz, no fim da atividade
        "Comentários gerais": observacao_ticket(aba, nota, quantidade, ini),
    }
    if aba == "Trackers":
        skid, num = _identificacao(asset)
        linha["Nº do SKID"] = skid
        linha["Nº do tracker / Identificação"] = num
        # 'Status' aqui é a coluna ANTIGA da aba, que separa ocorrência de check periódico.
        # Sem ela a linha nasceria como 'Em conformidade' — ou seja, invisível na tela.
        linha["Status"] = "Parado"
        linha["Quantidade de trackers parados"] = str(int(quantidade or 1))
    else:
        linha["Inversor"] = api._asset_short_name(asset) or ""
        # a coluna "no inversor" fica de fora de propósito: o app não sabe quantas strings o
        # inversor tem, e chutar ali estraga uma coluna que hoje é preenchida à mão.
        n = int(quantidade) if quantidade else contar_strings(nota)[0]
        linha["Quantidade de strings no afetadas"] = str(n)
    return linha


def criar(aba: str, asset: dict, usina: str, folio, quando=None, agora=None,
          escrever=None, registrar=None, quantidade=None, nota="", cabecalho=None) -> dict:
    """Acrescenta a ocorrência e o registro do diário. → {'ok', 'linha'|'erro', 'quantidade'}.

    `escrever`/`registrar` são injetáveis: teste de criação que bate na API acabaria escrevendo
    numa planilha real no dia em que alguém rodasse a suíte distraído."""
    if aba not in tickets_spec.ABAS:
        return {"ok": False, "erro": "aba desconhecida: %s" % aba}
    sheet_id = tickets_spec.ABAS[aba]["sheet_id"]
    # `cabecalho` injetável por causa do TESTE: sem ele, a linha abaixo vai à rede para descobrir
    # a ordem das colunas, e a suíte inteira passava a depender de `app.gridco.com.br` estar no
    # ar — o arquivo de teste dizia "nenhum teste toca a rede" e quatro deles tocavam. Descoberto
    # em 11/09, quando o servidor caiu e os testes começaram a falhar sem ninguém ter mexido neles.
    cabecalho = list(cabecalho or []) or tickets_api.cabecalho_de(sheet_id)
    if not cabecalho:
        # sem o cabeçalho não dá para saber a ORDEM das colunas, e mandar fora de ordem grava
        # cada valor na coluna do vizinho.
        try:
            # UMA linha, nao a aba inteira: o cabecalho vem em toda linha, e baixar as 2.781 da
            # Trackers so para ler nome de coluna foi o que estourou o timeout em 17/09.
            cabecalho = tickets_api.cabecalho_vivo(sheet_id)
        except Exception as e:                      # noqa: BLE001
            return {"ok": False, "erro": "não li o cabeçalho da aba (%s)" % str(e)[:80]}
    if not cabecalho:
        return {"ok": False, "erro": "não li o cabeçalho da aba de tickets"}

    dados = montar_linha(aba, asset, usina, quando, agora=agora,
                         quantidade=quantidade, nota=nota)
    # o que foi REALMENTE gravado, para a tela somar "6 strings" sem recontar por conta própria
    qtd_col = ("Quantidade de trackers parados" if aba == "Trackers"
               else "Quantidade de strings no afetadas")
    qtd = int(dados.get(qtd_col) or 1)
    try:
        criar_linha = escrever or tickets_escrita.criar_linha
        r = criar_linha(sheet_id, dados, cabecalho)
    except Exception as e:                          # noqa: BLE001
        return {"ok": False, "erro": "%s: %s" % (type(e).__name__, str(e)[:110])}

    linha = r.get("row_number") if isinstance(r, dict) else None
    oc = dict(dados)
    oc["_row"] = linha
    try:
        (registrar or tickets_diario.registrar)(
            aba, oc, {"OS": str(folio or "").strip(), "Status do ticket": "OS Programada",
                      "Início do chamado pela Grid Co.": dados["Início do chamado pela Grid Co."]})
    except Exception as e:                          # noqa: BLE001
        return {"ok": True, "linha": linha, "quantidade": qtd,
                "aviso": "linha criada, mas a OS não ficou vinculada (%s)" % str(e)[:80]}
    return {"ok": True, "linha": linha, "quantidade": qtd}

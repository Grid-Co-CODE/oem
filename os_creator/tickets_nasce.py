"""A OCORRÊNCIA NASCE COM A OS — o "pulo do gato" (Levi, 31/08).

Até aqui a ordem era ao contrário: alguém digitava a ocorrência na planilha e, dias depois,
abria a OS. O tempo entre as duas é justamente o que ninguém conseguia medir, e a linha só
existia se alguém lembrasse de criá-la. Agora, criar uma OS de "Recomposição de String" ou de
"Verificação de Tracker Parado" no Performance acrescenta a linha na aba de tickets na hora, já
com a OS vinculada.

O QUE ENTRA NA LINHA: usina, o ativo (inversor ou skid/tracker), o início da ocorrência (a data
do incidente que a pessoa escolheu na tela) e o "Início do chamado pela Grid Co." (agora, que é
quando a Grid abriu a OS). Causa raiz fica VAZIA de propósito — quem diz é o técnico, no fim.

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


def montar_linha(aba: str, asset: dict, usina: str, quando, agora=None) -> dict:
    """{coluna: valor} da ocorrência nova. Só as colunas que a aba tem — o resto o
    `para_valores` completa vazio."""
    ag = agora or _dt.datetime.now()
    ini = quando or ag
    linha = {
        "Usina": str(usina or "").strip(),
        "Início da ocorrência": ini.strftime("%Y-%m-%d %H:%M:%S"),
        "Início do chamado pela Grid Co.": ag.strftime("%Y-%m-%d %H:%M:%S"),
        "Causa raiz": "",                       # é o técnico quem diz, no fim da atividade
    }
    if aba == "Trackers":
        skid, num = _identificacao(asset)
        linha["Nº do SKID"] = skid
        linha["Nº do tracker / Identificação"] = num
        # 'Status' aqui é a coluna ANTIGA da aba, que separa ocorrência de check periódico.
        # Sem ela a linha nasceria como 'Em conformidade' — ou seja, invisível na tela.
        linha["Status"] = "Parado"
        linha["Quantidade de trackers parados"] = "1"
    else:
        linha["Inversor"] = api._asset_short_name(asset) or ""
        linha["Quantidade de strings no afetadas"] = "1"
    return linha


def criar(aba: str, asset: dict, usina: str, folio, quando=None, agora=None,
          escrever=None, registrar=None) -> dict:
    """Acrescenta a ocorrência e o registro do diário. → {'ok', 'linha'|'erro'}.

    `escrever`/`registrar` são injetáveis: teste de criação que bate na API acabaria escrevendo
    numa planilha real no dia em que alguém rodasse a suíte distraído."""
    if aba not in tickets_spec.ABAS:
        return {"ok": False, "erro": "aba desconhecida: %s" % aba}
    sheet_id = tickets_spec.ABAS[aba]["sheet_id"]
    cabecalho = tickets_api.cabecalho_de(sheet_id)
    if not cabecalho:
        # sem o cabeçalho não dá para saber a ORDEM das colunas, e mandar fora de ordem grava
        # cada valor na coluna do vizinho.
        try:
            tickets_api.listar_linhas(sheet_id)
            cabecalho = tickets_api.cabecalho_de(sheet_id)
        except Exception as e:                      # noqa: BLE001
            return {"ok": False, "erro": "não li o cabeçalho da aba (%s)" % str(e)[:80]}
    if not cabecalho:
        return {"ok": False, "erro": "não li o cabeçalho da aba de tickets"}

    dados = montar_linha(aba, asset, usina, quando, agora=agora)
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
        return {"ok": True, "linha": linha,
                "aviso": "linha criada, mas a OS não ficou vinculada (%s)" % str(e)[:80]}
    return {"ok": True, "linha": linha}

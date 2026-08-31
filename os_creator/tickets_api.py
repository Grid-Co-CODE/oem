"""Cliente de LEITURA da Gridco Performance API (espelho das planilhas).

Leitura é aberta: não usa credencial nenhuma. Escrita exigiria o GRIDCO_SQL_TOKEN e está fora
desta fase de propósito — enquanto o pipeline ainda subir o .xlsx com replace=true, qualquer
escrita daqui seria apagada no sync seguinte (ver spec §8)."""
import requests

from tickets_spec import linha_para_dict

BASE = "https://app.gridco.com.br/db_performace"
TETO = 1000          # teto da rota; a aba Trackers tem 2.781 linhas
TIMEOUT = 20


def _buscar(sheet_id, limit, offset):
    r = requests.get("%s/api/sheets/%s/rows" % (BASE, sheet_id),
                     params={"limit": limit, "offset": offset}, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else (d.get("rows") or d.get("items") or [])


def _paginar(sheet_id, buscar=None):
    """Junta as páginas até vir uma incompleta ou vazia.

    `buscar` é injetável para o teste rodar sem rede."""
    buscar = buscar or _buscar
    out, offset = [], 0
    while True:
        pagina = buscar(sheet_id, TETO, offset)
        if not pagina:
            break
        out.extend(pagina)
        if len(pagina) < TETO:
            break
        offset += TETO
    return out


_CABECALHOS = {}          # sheet_id -> colunas da última leitura


def cabecalho_de(sheet_id):
    """As colunas da aba, NA ORDEM em que a API as devolve — é assim que a escrita precisa
    mandá-las de volta. Sai da última leitura, então não custa requisição; vazio se ninguém
    leu a aba ainda (e aí a escrita não deve nem tentar: mandar ordem errada é gravar cada
    valor na coluna do vizinho)."""
    return list(_CABECALHOS.get(sheet_id) or [])


def listar_linhas(sheet_id, buscar=None):
    """Todas as linhas da aba, já como dicionários {coluna: valor}.

    Cada linha devolvida pela API carrega seu próprio array `headers` (metadado idêntico em todas).
    Não existe linha de cabeçalho especial — os nomes de coluna saem dos headers da primeira linha
    SEM que ela deixe de ser dado. O [1:] anterior descartava uma ocorrência real em silêncio."""
    cruas = _paginar(sheet_id, buscar)
    if not cruas:
        return []
    headers = cruas[0].get("headers") or []
    _CABECALHOS[sheet_id] = list(headers)
    out = []
    for r in cruas:
        d = linha_para_dict(headers, r.get("values") or [])
        d["_row"] = r.get("row_number")
        out.append(d)
    return out

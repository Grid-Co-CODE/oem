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


def listar_linhas(sheet_id):
    """Todas as linhas da aba, já como dicionários {coluna: valor}.

    A primeira linha devolvida pela API carrega o cabeçalho; é ela que dá os nomes de coluna."""
    cruas = _paginar(sheet_id)
    if not cruas:
        return []
    headers = cruas[0].get("headers") or []
    out = []
    for r in cruas[1:]:
        d = linha_para_dict(headers, r.get("values") or [])
        d["_row"] = r.get("row_number")
        out.append(d)
    return out

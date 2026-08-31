"""Escrita na Gridco Performance API — fase 2 dos tickets.

SEPARADO da leitura (`tickets_api.py`) de propósito. A leitura é aberta e roda o tempo todo; a
escrita exige credencial e só acontece por ação explícita. Deixar as duas no mesmo módulo faria
um `import` inocente carregar o token.

ONDE ISTO PODE ESCREVER — e por quê a restrição existe. Enquanto o pipeline de coleta subir o
`Tickets de Performance.xlsx` com `replace=true`, tudo que gravarmos numa aba que ele alimenta é
apagado no sync seguinte, em silêncio. Por isso `SHEETS_LIBERADAS` começa apontando para a aba de
TESTE: a produção só entra depois do corte no pipeline, e o corte só acontece depois de avisar
quem edita a planilha (Levi Maia, Gabriela Dias, Roger Lélis e Ana Patrícia).

Gravar numa aba fora dessa lista levanta erro em vez de tentar. É trava de código, não lembrete.
"""
import io
import os

import requests

BASE = "https://app.gridco.com.br/db_performace"
TIMEOUT = 30

# sheet_id → apelido. Só o que estiver aqui aceita escrita.
#   374 = zz_teste_claude_apagar / FASE2_Trackers  (23 colunas de Trackers + "Nº OS")
# Produção (123 Trackers, 128 Strings) entra AQUI quando o pipeline parar de subir essas abas.
SHEETS_LIBERADAS = {374: "teste/FASE2_Trackers"}

COL_OS = "Nº OS"          # a coluna nova da fase 2; não existe nas abas de produção ainda


class EscritaBloqueada(RuntimeError):
    """Tentativa de gravar numa aba que o pipeline ainda sobrescreve."""


class ConflitoDeEdicao(RuntimeError):
    """A linha mudou no banco entre a leitura da tela e o clique em salvar."""
    def __init__(self, campos):
        self.campos = campos        # {coluna: (valor_que_a_tela_tinha, valor_agora)}
        super().__init__("a linha mudou desde que a tela carregou: %s" % ", ".join(campos))


def _token() -> str:
    """Lê o GRIDCO_SQL_TOKEN do tokens.txt da raiz do repositório, ou do ambiente.

    O arquivo é o mesmo que a T.I. edita; nunca vai para o git. Sem token, a escrita nem tenta —
    a API devolveria 401 e o erro chegaria à pessoa como falha genérica de rede."""
    v = os.environ.get("GRIDCO_SQL_TOKEN", "").strip()
    if v:
        return v
    aqui = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(aqui, "tokens.txt"),
                 os.path.join(os.path.dirname(aqui), "tokens.txt"),
                 os.path.join(os.path.dirname(os.path.dirname(aqui)), "tokens.txt")):
        try:
            with io.open(cand, encoding="utf-8", errors="replace") as f:
                for linha in f:
                    if linha.strip().upper().startswith("GRIDCO_SQL_TOKEN"):
                        return linha.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def _cabecalho():
    tok = _token()
    if not tok:
        raise EscritaBloqueada(
            "GRIDCO_SQL_TOKEN não encontrado — a escrita precisa dele. "
            "Ele fica no tokens.txt da raiz do repositório.")
    return {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}


def _confere_liberada(sheet_id):
    if sheet_id not in SHEETS_LIBERADAS:
        raise EscritaBloqueada(
            "aba %s não está liberada para escrita: o pipeline ainda sobrescreve essa aba a "
            "partir do .xlsx, e o que gravássemos sumiria no próximo sync." % sheet_id)


def para_valores(dados: dict, headers: list) -> list:
    """{coluna: valor} → lista na ORDEM do cabeçalho, que é como a API espera.

    Coluna ausente vira string vazia, não None: `None` chega no banco como o texto 'None' em
    alguns caminhos, e texto 'None' numa célula é pior que célula vazia."""
    out = []
    for c in headers:
        v = dados.get(c, "")
        out.append("" if v is None else v)
    return out


def ler_linha(sheet_id: int, row_number: int, buscar=None) -> dict:
    """A linha como {coluna: valor}, direto do banco. É a releitura que antecede o salvar."""
    if buscar is not None:
        return buscar(sheet_id, row_number)
    r = requests.get("%s/api/sheets/%s/rows/%s" % (BASE, sheet_id, row_number), timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if isinstance(d, list):
        d = d[0] if d else {}
    headers = d.get("headers") or []
    valores = d.get("values") or []
    return {c: (valores[i] if i < len(valores) else None)
            for i, c in enumerate(headers) if str(c or "").strip()}


def gravar_linha(sheet_id: int, row_number: int, dados: dict, headers: list,
                 base: dict = None, enviar=None, ler=None) -> dict:
    """Grava a linha. Se `base` vier, confere antes se alguém mexeu nela nesse meio-tempo.

    A conferência é otimista de propósito: poucos analistas, raramente ao mesmo tempo (Levi,
    28/08), então travar a linha seria burocracia para um caso que quase não acontece. Mas
    gravar por cima sem olhar seria perder a edição do outro em silêncio, que é justamente a
    classe de erro que este projeto não aceita."""
    _confere_liberada(sheet_id)
    if base is not None:
        agora = (ler or ler_linha)(sheet_id, row_number)
        mudou = {}
        for c, antes in base.items():
            depois = agora.get(c)
            if str(antes or "").strip() != str(depois or "").strip():
                mudou[c] = (antes, depois)
        if mudou:
            raise ConflitoDeEdicao(mudou)
    corpo = {"values": para_valores(dados, headers), "headers": list(headers)}
    if enviar is not None:
        return enviar("PUT", sheet_id, row_number, corpo)
    r = requests.put("%s/api/sheets/%s/rows/%s" % (BASE, sheet_id, row_number),
                     headers=_cabecalho(), json=corpo, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def criar_linha(sheet_id: int, dados: dict, headers: list, enviar=None) -> dict:
    """Acrescenta uma linha. É o que roda quando uma OS é criada no Performance."""
    _confere_liberada(sheet_id)
    corpo = {"values": para_valores(dados, headers), "headers": list(headers)}
    if enviar is not None:
        return enviar("POST", sheet_id, None, corpo)
    r = requests.post("%s/api/sheets/%s/rows" % (BASE, sheet_id),
                      headers=_cabecalho(), json=corpo, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

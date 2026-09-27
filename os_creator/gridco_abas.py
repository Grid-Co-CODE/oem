# -*- coding: utf-8 -*-
"""Uma aba do banco da Gridco (a db_performace) lida e escrita DIRETO, com o GRIDCO_SQL_TOKEN.

É o caminho do `temas_store.py`, agora compartilhado pelas duas abas novas dos chamados (27/09/2026): os modelos do
Controle de fornecedores (`chamado_modelos`) e as observações do Acompanhamento (`chamados_obs`).

DIRETO, e não pelo relay da plataforma (`tickets_escrita._transporte`): o relay só aceita as abas de tickets, e quem
escreve estas é o os_web — um SERVIDOR, com o token no ambiente (`/etc/gridco/os-web.env` no Linux; na máquina do
Levi, o arquivo da pasta do usuário que o instalador grava). É o mesmo arranjo dos temas no app de mesa.

LEITURA É ABERTA, como em todo o banco. ESCRITA sem token nem tenta: a API responderia 401 e a tela diria "falha de
rede" para o que é falta de credencial.
"""
import json

import requests

BASE = "https://app.gridco.com.br/db_performace"
TIMEOUT = 20
LIMITE = 1000                 # o teto de `limit` da API


class SemCredencial(PermissionError):
    """Este processo não tem o GRIDCO_SQL_TOKEN: dá para ler, não para gravar."""


def token() -> str:
    """O mesmo token que os tickets usam — uma regra de busca só (ambiente → cofre → pasta do usuário → tokens.txt)."""
    try:
        from tickets_escrita import _token
        return _token()
    except Exception:                                    # noqa: BLE001
        return ""


def pode_gravar() -> bool:
    return bool(token())


def _get(caminho: str, params=None):
    r = requests.get(BASE + caminho, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def escrever(metodo: str, caminho: str, corpo) -> dict:
    tok = token()
    if not tok:
        raise SemCredencial("Este servidor não tem a credencial de escrita do banco da Gridco (GRIDCO_SQL_TOKEN): "
                            "dá para ver, mas não para salvar.")
    r = requests.request(metodo, BASE + caminho, timeout=TIMEOUT, data=json.dumps(corpo, ensure_ascii=False),
                         headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    r.raise_for_status()
    return r.json() if (r.content or b"").strip() else {}


class Aba:
    """Uma aba de um workbook, achada pelo NOME (o id sai do banco quando ela nasce; se o workbook for recriado, o
    número muda — perguntar custa uma requisição na primeira vez e evita gravar na aba de outra pessoa)."""

    def __init__(self, workbook: str, nome: str, colunas):
        self.workbook, self.nome, self.colunas = workbook, nome, list(colunas)
        self._id = None

    def id(self, criar: bool = False):
        if self._id:
            return self._id
        abas = _get("/api/sheets")
        abas = abas if isinstance(abas, list) else (abas or {}).get("sheets") or []
        for a in abas:
            if a.get("workbook_key") == self.workbook and a.get("sheet_name") == self.nome:
                self._id = int(a["id"])
                return self._id
        if not criar:
            return None
        # a largura nasce aqui e não muda mais: a API não sabe alargar aba (ver tickets_diario._conferir_largura)
        nova = escrever("POST", "/api/workbooks/%s/sheets" % self.workbook,
                        {"sheet_name": self.nome, "headers": self.colunas})
        self._id = int(nova["id"])
        return self._id

    def linhas(self) -> list:
        """As linhas cruas, todas as páginas. Aba que ainda não existe = nenhuma linha (não é erro)."""
        sid = self.id()
        if sid is None:
            return []
        out, offset = [], 0
        while True:
            d = _get("/api/sheets/%s/rows" % sid, {"limit": LIMITE, "offset": offset})
            pag = d if isinstance(d, list) else ((d or {}).get("rows") or (d or {}).get("items") or [])
            out += pag
            if len(pag) < LIMITE:
                return out
            offset += len(pag)

    def registro(self, linha: dict) -> dict:
        """Linha crua → {coluna: valor}. Pelos `headers` da própria linha quando vierem; senão, pela ordem da aba."""
        vals = linha.get("values") or []
        heads = [str(h or "").strip() for h in (linha.get("headers") or [])] or self.colunas
        out = {c: (vals[i] if i < len(vals) else None) for i, c in enumerate(heads) if c}
        out["_linha"] = linha.get("row_number")
        return out

    def _corpo(self, dados: dict) -> dict:
        # coluna ausente vira "", não None: None chega no banco como o texto 'None' em alguns caminhos
        return {"values": ["" if dados.get(c) is None else dados.get(c) for c in self.colunas],
                "headers": list(self.colunas)}

    def inserir(self, dados: dict) -> dict:
        return escrever("POST", "/api/sheets/%s/rows" % self.id(criar=True), self._corpo(dados))

    def trocar(self, row_number, dados: dict) -> dict:
        """PUT troca a LINHA INTEIRA (ver a memória do PUT): manda sempre o registro completo."""
        return escrever("PUT", "/api/sheets/%s/rows/%s" % (self.id(criar=True), row_number), self._corpo(dados))

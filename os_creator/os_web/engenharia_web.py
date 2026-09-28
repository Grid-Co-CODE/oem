# os_creator/os_web/engenharia_web.py
"""O supervisório da Engenharia na área Engenharia da web (Levi, 27/09/2026): "poderíamos trazer a visão de outro
supervisório do github? seria que nem o OS Creator web é atualmente, um supervisório público, sem exposição de nenhuma
chave, esse supervisório fica direto no servidor e atualiza a cada commit, só faríamos a ligação com o OS Creator Web".

É a ligação e nada mais — o conteúdo é da Engenharia (docs/ambiente-compartilhado-engenharia.md: "a área é dona do
conteúdo; a casa segura o layout"). O endereço vem do .env do servidor (`OS_WEB_SUPERVISORIO_URL`, e o nome em
`OS_WEB_SUPERVISORIO_NOME`), nunca do código: é deles, muda sem passar por aqui, e nenhuma chave passa por esta tela.
Sem endereço, a área fica como sempre foi (a moldura "em construção"). PURO: só lê o ambiente."""
from __future__ import annotations

import os
import re

NOME_PADRAO = "Supervisório da Engenharia"
_URL_OK = re.compile(r"^https?://[^\s\"'<>`]+$")


def supervisorio() -> dict:
    """{url, nome} do supervisório, ou {} sem endereço (ou com um que não é http/https — `javascript:` não vira quadro)."""
    url = (os.environ.get("OS_WEB_SUPERVISORIO_URL") or "").strip()
    if not _URL_OK.match(url):
        return {}
    return {"url": url, "nome": (os.environ.get("OS_WEB_SUPERVISORIO_NOME") or NOME_PADRAO).strip() or NOME_PADRAO}

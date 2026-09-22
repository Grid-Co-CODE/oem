# tests/test_os_web_tickets_filtro.py
"""Tickets: o filtro de status no navegador e o rótulo das colunas (Levi, 22/09/2026).

· "Esses cards de Todas, Abertas, OS Criada... não funcionam como filtros? atualmente eu clico e
  direciona para um link novo" — a página passa a trazer todos os status e o clique filtra na
  hora. Os CONTADORES passam a contar só o que os outros filtros deixaram (antes o "Aberta 627" era
  da aba inteira mesmo com um cliente escolhido, e o número não batia com a lista embaixo).
· "Mude a coluna Estado para Status" — e a que já se chamava "Status" vira "Status do ticket",
  senão a tabela teria duas colunas "Status".

O comportamento no navegador foi conferido com os dados reais (Strings, 309 ocorrências): cada
cartão bate com a lista (Aberta 82 = 82, Encerrada 227 = 227) e filtrar não recarrega a página.
"""
import os
import re

import pytest

import tickets_api
import tickets_diario
from os_web import criar_app, tickets_web as tw
from os_web import rotas_tickets as rt

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
_TPL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "os_creator", "os_web", "templates", "tickets.html")


def _l(row, usina, cliente, fim="", qtd=1):
    return {"_row": row, "Usina": usina, "Cliente": cliente, "Status": "Parado",
            "Início da ocorrência": "2026-09-01 08:00", "Fim da ocorrência": fim,
            "Quantidade de trackers parados": qtd}


@pytest.fixture
def cli(monkeypatch):
    linhas = [_l(1, "TIM100", "Athon", qtd=4), _l(2, "TIM100", "Athon", fim="2026-09-05 08:00", qtd=9),
              _l(3, "Tupi", "2C", qtd=2), _l(4, "Tupi", "2C", fim="2026-09-06 08:00")]
    monkeypatch.setattr(tickets_api, "listar_linhas", lambda sid: [dict(x) for x in linhas])
    monkeypatch.setattr(tickets_diario, "ler", lambda **k: [])
    monkeypatch.setattr(tickets_diario, "aplicar", lambda a, o, r: {"aplicados": 0})
    monkeypatch.setattr(rt, "_pode_gravar", lambda: False)
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "perfil": "ADMINISTRATOR"}
    return c


def _cartao(h, estado):
    m = re.search(r'data-estado="%s"[^>]*>\s*<span class="os-painel-n"[^>]*>(\d+)</span>' % estado, h)
    return int(m.group(1)) if m else None


# ── 5. o filtro ──────────────────────────────────────────────────────────────────────────────
def test_a_pagina_traz_TODOS_os_status_mesmo_com_estado_na_url(cli):
    """Senão o clique no navegador não teria as outras linhas para mostrar."""
    h = cli.get("/os/tickets?estado=aberta").get_data(as_text=True)
    estados = re.findall(r'class="tk-l tk-f"[^>]*data-estado="(\w+)"', h)
    assert sorted(estados) == ["aberta", "aberta", "encerrada", "encerrada"]


def test_o_estado_da_url_e_o_filtro_inicial_do_navegador(cli):
    h = cli.get("/os/tickets?estado=aberta").get_data(as_text=True)
    assert 'var estadoAtual = "aberta";' in h


def test_contadores_respeitam_o_filtro_de_cliente(cli):
    """O defeito de antes: com o cliente escolhido, o cartão ainda contava a aba inteira."""
    h = cli.get("/os/tickets?cliente=Athon").get_data(as_text=True)
    assert _cartao(h, "aberta") == 1 and _cartao(h, "encerrada") == 1
    h = cli.get("/os/tickets").get_data(as_text=True)
    assert _cartao(h, "aberta") == 2 and _cartao(h, "encerrada") == 2


def test_cada_linha_leva_status_e_quantidade_para_o_recontar(cli):
    h = cli.get("/os/tickets").get_data(as_text=True)
    assert re.search(r'data-estado="aberta" data-qtd="4"', h)
    assert re.search(r'data-estado="encerrada" data-qtd="9"', h)


def test_o_clique_nao_navega_e_o_segundo_clique_volta_para_todas():
    with open(_TPL, encoding="utf-8") as f:
        h = f.read()
    assert "ev.preventDefault();" in h and ".tk-filtro" in h
    assert 'aplicarEstado(c.classList.contains("on") && c.dataset.estado ? "" : c.dataset.estado);' in h
    # a URL acompanha sem empilhar histórico
    assert "history.replaceState" in h


def test_o_recontar_so_soma_equipamento_das_NAO_encerradas():
    with open(_TPL, encoding="utf-8") as f:
        h = f.read()
    assert 'if (l.dataset.estado !== "encerrada") { ab++; qtd += Number(l.dataset.qtd) || 0; }' in h


# ── 7. os rótulos ────────────────────────────────────────────────────────────────────────────
def test_estado_virou_status_e_status_virou_status_do_ticket(cli):
    h = cli.get("/os/tickets").get_data(as_text=True)
    cabecalhos = re.findall(r"<th[^>]*>([^<]+)</th>", h.split('id="tab_tk"')[1].split("</thead>")[0])
    assert cabecalhos[0] == "Status"
    assert "Status do ticket" in cabecalhos
    assert "Estado" not in cabecalhos
    assert cabecalhos.count("Status") == 1                   # nada de duas colunas "Status"


def test_o_nome_interno_da_coluna_NAO_mudou():
    """O rótulo é da tela; o nome interno é o do app de mesa, e o teste de fidelidade o compara."""
    assert tw.COL_STATUS == "Status"
    assert tw.ROTULO_COLUNA[tw.COL_STATUS] == "Status do ticket"


# ── 6 e 9. o CSS ─────────────────────────────────────────────────────────────────────────────
def test_todas_as_colunas_centralizadas_e_a_rolagem_escura():
    css = os.path.join(os.path.dirname(_TPL), "..", "static", "os.css")
    with open(css, encoding="utf-8") as f:
        c = f.read()
    assert "#tab_tk th,#tab_tk td{text-align:center}" in c
    assert "scrollbar-color:#2c3a5c" in c and "::-webkit-scrollbar-thumb{background:#2c3a5c" in c

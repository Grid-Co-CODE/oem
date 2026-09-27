# tests/test_os_web_fornecedores.py
"""Controle de fornecedores (27/09/2026): a tela, o salvar e — o que importa — a Inspeção de chamados passando a usar o
modelo salvo NA HORA, sem release."""
import json
import re

import pytest

import chamado_insp_spec as ci
import chamado_modelos_store as cms
import gridco_abas as ga
from chamado_garantia import spec as sp
from os_web import criar_app
from os_web import fornecedores_web as fw

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"


@pytest.fixture
def cli():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "analista@teste.invalid", "perfil": "ADMINISTRATOR"}
    return c


@pytest.fixture
def banco(monkeypatch):
    """A aba chamado_modelos de mentira: o que se grava volta na leitura seguinte."""
    linhas = []

    def inserir(dados):
        linhas.append({"row_number": len(linhas) + 2, "headers": ["chave", "valor"], "values": [dados["chave"], dados["valor"]]})

    def trocar(row, dados):
        for l in linhas:
            if l["row_number"] == row:
                l["values"] = [dados["chave"], dados["valor"]]
    monkeypatch.setattr(cms, "_linhas", lambda: [dict(l) for l in linhas])
    monkeypatch.setattr(cms.ABA, "inserir", inserir)
    monkeypatch.setattr(cms.ABA, "trocar", trocar)
    monkeypatch.setattr(ga, "pode_gravar", lambda: True)
    return linhas


def _dados_da_pagina(h):
    return json.loads(re.search(r'<script type="application/json" id="f_dados">(.*?)</script>', h, re.S).group(1))


# ── o desenho dos dados ───────────────────────────────────────────────────────────────────────────────────────
def test_as_abas_e_as_contas_sao_as_do_pacote():
    t = fw.tela(cms.efetivo({}))
    assert [a["nome"] for a in t["abas"]] == ["Inversor", "Tracker", "NCU", "RSU", "Estação meteorológica", "Cabine", "Skid"]
    trk = next(a for a in t["abas"] if a["tipo"] == "Estrutura Trackers")
    sti = next(f for f in trk["fornecedores"] if f["marca"] == "STI")
    assert sti["n_total"] == len(ci.subtarefas("Estrutura Trackers", "STI"))
    ncu = next(a for a in t["abas"] if a["tipo"] == "NCU")
    # na NCU as perguntas da STI são de tracker (so_para) e a de testes repete a do bloco da NCU: nenhuma própria
    assert next(f for f in ncu["fornecedores"] if f["marca"] == "STI")["n_proprias"] == 0
    assert next(f for f in trk["fornecedores"] if f["marca"] == "Brametal")["igual_a"] == "STI"
    inv = next(a for a in t["abas"] if a["tipo"] == "Inversor")
    assert "SolarEdge" in inv["sem_doc"] and trk["sem_doc"] == []
    assert next(a for a in t["abas"] if a["tipo"] == "Estação Meteorológica")["alias"] == ["FDL", "PRN", "SDT"]


def test_a_pagina(cli):
    h = cli.get("/os/chamados/fornecedores").get_data(as_text=True)
    d = _dados_da_pagina(h)
    assert "BASE" in d["blocos"] and "MARCA:Huawei" in d["blocos"] and d["blocos"]["BASE"]["origem"] == "codigo"
    assert "O App de Campo" in h and "/os/static/fornecedores.js" in h


def test_o_mesmo_visual_escuro_do_acompanhamento(cli, monkeypatch):
    """Levi, 27/09: "leva o mesmo visual escuro para o Controle de fornecedores". As três telas de chamados leem a MESMA
    folha — o 1B (chamados1b.css) saiu de vez."""
    import api
    monkeypatch.setattr(api, "list_chamados", lambda **k: [])              # o quadro sem ir ao Fracttal
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    for url in ("/os/chamados/fornecedores", "/os/chamados/acompanhamento"):
        h = cli.get(url).get_data(as_text=True)
        assert 'href="/os/static/chamados.css"' in h and "os-form cham" in h and "chamados1b" not in h, url
    assert cli.get("/os/static/chamados.css").status_code == 200
    assert cli.get("/os/static/chamados1b.css").status_code == 404


def test_sem_credencial_a_pagina_avisa(cli, monkeypatch):
    monkeypatch.setattr(ga, "pode_gravar", lambda: False)
    h = cli.get("/os/chamados/fornecedores").get_data(as_text=True)
    assert "não tem a credencial de escrita" in h and _dados_da_pagina(h)["pode_gravar"] is False


# ── salvar ────────────────────────────────────────────────────────────────────────────────────────────────────
NOVA = {"desc": "Print da tela de alarmes do SmartLogger", "tipo": "texto", "obrig": True, "anexo": True,
        "opcoes": [], "chave": "", "so_para": []}


def test_salvar_vale_na_hora_para_a_inspecao(cli, banco):
    antes = cli.get("/os/api/insp/subtarefas?tipo=Inversor&marca=Huawei").get_json()
    r = cli.post("/os/api/fornecedores/salvar", json={"chave": "MARCA:Huawei", "versao": "",
                                                      "dados": {"subtarefas": [NOVA], "atende": ["Inversor"],
                                                                "canal": "Portal Digital Power"}})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["tela"]["blocos"]["MARCA:Huawei"]["origem"] == "banco"
    assert j["tela"]["blocos"]["MARCA:Huawei"]["por"] == "Analista Teste"
    depois = cli.get("/os/api/insp/subtarefas?tipo=Inversor&marca=Huawei").get_json()
    assert depois != antes and NOVA["desc"] in json.dumps(depois, ensure_ascii=False)
    assert len(ci.subtarefas("Inversor", "Huawei")) == len(sp.BASE) + len(sp.POR_TIPO["Inversor"]) + 1


def test_salvar_por_cima_de_quem_salvou_antes_e_recusado(cli, banco):
    cli.post("/os/api/fornecedores/salvar", json={"chave": "MARCA:Huawei", "versao": "",
                                                  "dados": {"subtarefas": [NOVA], "atende": ["Inversor"]}})
    r = cli.post("/os/api/fornecedores/salvar", json={"chave": "MARCA:Huawei", "versao": "",      # a tela velha
                                                      "dados": {"subtarefas": [], "atende": ["Inversor"]}})
    assert r.status_code == 409 and r.get_json()["conflito"] is True and "Analista Teste" in r.get_json()["erro"]


def test_salvar_invalido_e_sem_credencial(cli, banco, monkeypatch):
    r = cli.post("/os/api/fornecedores/salvar", json={"chave": "BASE", "versao": "", "dados": {"subtarefas": []}})
    assert r.status_code == 400 and "pelo menos uma" in r.get_json()["erro"]
    monkeypatch.setattr(ga, "pode_gravar", lambda: False)
    r = cli.post("/os/api/fornecedores/salvar", json={"chave": "MARCA:Huawei", "versao": "",
                                                      "dados": {"subtarefas": [], "atende": ["Inversor"]}})
    assert r.status_code == 403 and banco == []


def test_fornecedor_novo_passa_a_ser_oferecido_na_inspecao(cli, banco):
    cli.post("/os/api/fornecedores/salvar", json={"chave": "MARCA:Fornecedor Teste", "versao": "",
                                                  "dados": {"subtarefas": [NOVA], "atende": ["Inversor"], "canal": "e-mail"}})
    assert "Fornecedor Teste" in ci.marcas_para("Inversor")
    t = fw.tela(cms.efetivo())
    inv = next(a for a in t["abas"] if a["tipo"] == "Inversor")
    assert any(f["marca"] == "Fornecedor Teste" and f["n_proprias"] == 1 for f in inv["fornecedores"])


def test_arquivar_tira_da_inspecao(cli, banco):
    cli.post("/os/api/fornecedores/salvar", json={"chave": "MARCA:Trina", "versao": "",
                                                  "dados": {"subtarefas": [], "atende": ["Estrutura Trackers"], "arquivado": True}})
    assert "Trina" not in ci.marcas_para("Estrutura Trackers")

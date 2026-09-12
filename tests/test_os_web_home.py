# tests/test_os_web_home.py
"""A tela que aparece depois do login na web e A MESMA do app (Levi, 12/09/2026: "após logar quero que apareça a
mesma coisa que aparece para quem loga no OS Creator"): cabecalho Grid Co. / Sistema de Ordens de Servico, avatar
com iniciais + nome + cargo, tres abas e o lancador de nove cards, na ordem e com os textos do `app.py`."""
import re

import pytest

import api
from os_web import criar_app

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"

CARDS = [
    ("Ativos", "Todo o catálogo do Fracttal — busca, histórico e atalhos"),
    ("Performance", "Inversores, Strings, Trackers e ETM"),
    ("COS", "Ocorrência de desligamento, religamento e inspeção"),
    ("PCM", "OS planejada por família de plano, vários ativos"),
    ("Chamados", "Nova OS ligada a uma OS pai, com a etiqueta CHAMADOS"),
    ("Inspeção de chamados", "OS de teste que fundamenta o chamado — subtarefas por ativo e marca"),
    ("Tradicional", "Criar OS do zero, passo a passo"),
    ("Clonar OS", "Duplicar uma OS existente pelo número"),
    ("Engenharia", "OS de ETM e as análises da Engenharia"),
]


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 3)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


def test_cabecalho_igual_ao_do_app(cli):
    html = cli.get("/os/").get_data(as_text=True)
    assert "Grid Co." in html and "Sistema de Ordens de Serviço" in html
    assert "Levi Maia" in html and "ADMINISTRATOR" in html
    assert ">LM<" in html                                            # iniciais no avatar (primeiro + ultimo nome)
    assert 'grid-icon.png' in html                                   # o simbolo do app, servido pela propria area


def test_tres_abas_na_ordem_do_app(cli):
    html = cli.get("/os/").get_data(as_text=True)
    ordem = [html.index(t) for t in ("Criar OS", "Solicitação / PCM", "Históricos de OS")]
    assert ordem == sorted(ordem)
    assert 'href="/os/historico"' in html


def test_os_nove_cards_com_os_textos_e_a_ordem_do_launcher(cli):
    html = cli.get("/os/").get_data(as_text=True)
    pos = []
    for titulo, sub in CARDS:
        assert sub in html, titulo
        pos.append(html.index(sub))
    assert pos == sorted(pos)                                        # mesma ordem da grade do app
    assert html.count('class="os-card') >= 9
    assert 'href="/os/performance"' in html                          # Performance abre o fluxo proprio


def test_selo_do_card_performance(cli, monkeypatch):
    html = cli.get("/os/").get_data(as_text=True)
    assert "3 atribuídas a você" in html
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 1)
    assert "1 atribuída a você" in cli.get("/os/").get_data(as_text=True)
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 0)
    assert "atribuída" not in cli.get("/os/").get_data(as_text=True)     # zero = some, sem ruido


def test_selo_que_falha_nao_derruba_a_tela(cli, monkeypatch):
    def _boom():
        raise api.FracttalError("fora")
    monkeypatch.setattr(api, "contar_minhas_analises", _boom)
    r = cli.get("/os/")
    assert r.status_code == 200 and "Performance" in r.get_data(as_text=True)


def test_card_ainda_so_no_app_explica_e_nao_quebra(cli):
    r = cli.get("/os/em-breve/cos")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "COS" in html and "app" in html.lower()


def test_sem_emoji_na_interface(cli):
    html = cli.get("/os/").get_data(as_text=True)
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", html)

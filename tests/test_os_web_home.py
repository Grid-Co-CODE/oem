# tests/test_os_web_home.py
"""A tela inicial da web (Levi, 27/09/2026): "parece que todo campo carrega o mesmo peso", e o PCM aparecia duas vezes
(a aba "Solicitação / PCM" e o card). A ordem pedida: CONSULTAR (Ativos, Histórico) → os SETORES (Performance, COS, PCM,
Chamados, Engenharia, mais o jeito tradicional de criar OS) → as SOLICITAÇÕES (a nova solicitação e o Clonar OS).
O cabeçalho continua o do app (12/09: "após logar quero que apareça a mesma coisa que aparece para quem loga no OS
Creator"); a grade de nove cards é que deixou de ser o molde."""
import datetime as dt
import re
import time

import pytest

import api
from os_web import criar_app, lancador, rotas

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"


def _cliente(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    rotas._MEMO.clear()
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 3)
    # o catálogo local tem 21 mil ativos: a tela inicial só lê o tamanho e a data dele — aqui, nenhum
    monkeypatch.setattr(api, "assets_cache_info", lambda: {"ts": 0, "n": 0, "idade_h": 0.0, "expirado": True})
    monkeypatch.setattr(api, "_read_asset_cache", lambda: None)


@pytest.fixture
def cli():
    return _cliente(criar_app(segredo="teste", testing=True))


def test_cabecalho_igual_ao_do_app(cli):
    html = cli.get("/os/").get_data(as_text=True)
    assert "Grid Co." in html and "Sistema de Ordens de Serviço" in html
    assert "Levi Maia" in html and "ADMINISTRATOR" in html
    assert ">LM<" in html                                            # iniciais no avatar (primeiro + ultimo nome)
    assert 'grid-icon.png' in html                                   # o simbolo do app, servido pela propria area


def test_a_faixa_comeca_so_com_o_inicio(cli):
    """Até 27/09 a faixa tinha duas abas fixas, Início e Histórico de OS. Desde 28/09 a tela inicial é a CASCA das abas
    abertas (tests/test_os_web_abas.py) e a faixa começa só com o Início (Levi: "comece só com início, se eu clicar em
    histórico abre uma aba de histórico"); o Histórico se abre pelo cartão dele, como os setores."""
    html = cli.get("/os/").get_data(as_text=True)
    nav = re.search(r'<nav class="os-tabs abas-faixa"[^>]*>(.*?)</nav>', html, re.S).group(1)
    assert nav.count('role="tab"') == 1 and ">Início<" in nav
    assert "Histórico de OS" not in nav and "Solicitação / PCM" not in nav
    assert re.search(r'class="os-tab aba-inicio on" id="aba_inicio" href="/os/"', nav)   # o Início aceso


def test_a_ordem_consultar_setores_solicitacoes(cli):
    html = cli.get("/os/").get_data(as_text=True)
    marcos = ['<h1>', '>Ativos<', '>Histórico de OS</a>', 'id="h_setores"', '>Performance<', '>COS<', '>PCM<',
              '>Chamados<', '>Engenharia<', 'Criar OS do zero', 'id="h_solic"', 'Nova solicitação', 'Clonar OS']
    corpo = html[html.index('id="inicio"'):]                                      # sem o menu do topo
    pos = [corpo.index(m) for m in marcos]
    assert pos == sorted(pos)


def test_as_portas_de_cada_setor(cli):
    html = cli.get("/os/").get_data(as_text=True)
    for href in ("/os/ativos", "/os/historico", "/os/historico?modo=cos", "/os/performance", "/os/tickets",
                 "/os/setor/pcm", "/os/solicitacao/fila", "/os/solicitacao/historico", "/os/chamados",
                 "/os/chamados/inspecao", "/os/chamados/acompanhamento", "/os/chamados/fornecedores",
                 "/os/engenharia", "/os/tradicional", "/os/solicitacao", "/os/clonar"):
        assert 'href="%s"' % href in html, href
    assert "/os/performance/criar?frase=" in html                                  # os planos da Performance
    assert html.count("data-carga") >= 4                                           # o Histórico com o círculo de carga


def test_o_cos_e_a_clonagem_nasceram_e_acenderam(cli):
    """O que ainda não nasceu na web fica apagado, sem link, dizendo onde mora. O COS (/os/cos, tests/test_os_web_cos.py)
    e a clonagem de planos (/os/pcm, tests/test_os_web_pcm.py) nasceram em 27/09: acenderam sozinhos, sem mexer no
    lançador — o card do COS deixa de ir ao "em breve" e as três pílulas viram link."""
    html = cli.get("/os/").get_data(as_text=True)
    cos = html[html.index('data-chave="cos"') - 40:html.index('data-chave="pcm"')]
    assert 'class="setor fora"' not in cos and "no app de mesa" not in cos and 'href="/os/em-breve/cos"' not in cos
    assert '<h3><a href="/os/cos">COS</a></h3>' in cos and '<a href="/os/cos">Religamento</a>' in cos
    pcm = html[html.index('data-chave="pcm"'):html.index('data-chave="chamados"')]
    assert '<a href="/os/pcm">Planos: Handover, MPS, MPA</a>' in pcm and "Planos: Handover, MPS, MPA</span>" not in pcm


def test_a_porta_acende_sozinha_quando_a_tela_nasce():
    """No dia em que /os/pcm existir (tests/test_os_web_pcm.py), a clonagem vira link — sem mexer no lançador."""
    app = criar_app(segredo="teste", testing=True)
    app.add_url_rule("/os/pcm", "pcm_de_mentira", lambda: "ok")
    c = _cliente(app)
    pcm = c.get("/os/").get_data(as_text=True)
    pcm = pcm[pcm.index('data-chave="pcm"'):pcm.index('data-chave="chamados"')]
    assert '<a href="/os/pcm">Planos: Handover, MPS, MPA</a>' in pcm
    setor = c.get("/os/setor/pcm").get_data(as_text=True)
    assert '<a class="porta" href="/os/pcm">' in setor and "no app de mesa" not in setor


def test_o_setor_pcm_separado_em_tres(cli):
    """Levi: "clonagem de Handover, MPS, MPA etc. - fila de PCM - histórico de solicitações"."""
    html = cli.get("/os/setor/pcm").get_data(as_text=True)
    pos = [html.index(t) for t in ("Clonagem de planos", "Fila do PCM", "Histórico de solicitações")]
    assert pos == sorted(pos)
    assert 'href="/os/solicitacao/fila"' in html and 'href="/os/solicitacao/historico"' in html
    assert '<a class="porta" href="/os/pcm">' in html and "no app de mesa" not in html   # a clonagem nasceu na web (27/09)
    assert all(f in html for f in ("Handover", "MPA", "MPS"))
    assert cli.get("/os/setor/nada").status_code == 404
    r = cli.get("/os/setor/chamados")
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/chamados")


def test_saudacao_pela_hora_de_brasilia(cli):
    assert [lancador.saudacao(h) for h in (3, 8, 12, 17, 18, 23)] == \
        ["Boa noite", "Bom dia", "Boa tarde", "Boa tarde", "Boa noite", "Boa noite"]
    assert re.search(r"<h1>(Bom dia|Boa tarde|Boa noite), Levi</h1>", cli.get("/os/").get_data(as_text=True))


@pytest.mark.parametrize("q,destino", [
    ("12875", "/os/os/folio/12875"),
    ("#12875", "/os/os/folio/12875"),
    (" Inversor  1.1 ", "/os/ativos?busca=Inversor+1.1"),
    ("", "/os/"),
])
def test_a_busca_numero_abre_a_os_e_texto_vai_aos_ativos(cli, q, destino):
    r = cli.get("/os/buscar", query_string={"q": q})
    assert r.status_code == 302 and r.headers["Location"].endswith(destino)


def test_as_pilulas_do_catalogo(cli, monkeypatch):
    """A conta é a da tela de Ativos (só ativo com código): o arquivo tinha 21.639 registros e a tela, 21.635."""
    uma_hora = time.time() - 3600
    monkeypatch.setattr(api, "assets_cache_info", lambda: {"ts": uma_hora, "n": 21639, "idade_h": 1.0, "expirado": False})
    monkeypatch.setattr(api, "_read_asset_cache", lambda: [{"code": "X"}] * 21635 + [{"code": ""}] * 4)
    html = cli.get("/os/").get_data(as_text=True)
    brt = dt.timezone(dt.timedelta(hours=-3))
    quando = dt.datetime.fromtimestamp(uma_hora, brt)
    dia = "hoje" if quando.date() == dt.datetime.now(brt).date() else quando.strftime("%d/%m")
    assert '<span class="pill">21.635 ativos</span>' in html
    assert ("catálogo de %s, %s" % (dia, quando.strftime("%H:%M"))) in html


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
    for url in ("/os/", "/os/setor/pcm", "/os/chamados"):
        html = cli.get(url).get_data(as_text=True)
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", html), url


def test_catalogo_vencido_fica_com_a_conta_do_arquivo_e_avisa(cli, monkeypatch):
    monkeypatch.setattr(api, "assets_cache_info", lambda: {"ts": time.time() - 3 * 86400, "n": 21639, "idade_h": 72.0,
                                                          "expirado": True})
    html = cli.get("/os/").get_data(as_text=True)
    assert "21.639 ativos" in html and "desatualizado" in html


def test_as_telas_da_solicitacao_acendem_o_inicio():
    """A aba "Solicitação / PCM" saiu (27/09); as telas dela seguem passando aba="solic" — e acendem o Início."""
    from flask import render_template_string
    app = criar_app(segredo="teste", testing=True)
    with app.test_request_context("/os/solicitacao"):
        h = render_template_string('{% extends "base.html" %}', conta={"nome": "Levi Maia"}, aba="solic")
    nav = re.search(r'<nav class="os-tabs">(.*?)</nav>', h, re.S).group(1)
    assert re.search(r'class="os-tab on" href="/os/"', nav) and nav.count("os-tab on") == 1

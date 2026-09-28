# tests/test_os_web_abas.py
"""As ABAS ABERTAS do OS Creator web (Levi, 28/09/2026): "comece só com início, se eu clicar em histórico abre uma aba de
histórico, se performance abre uma aba de performance e assim por diante". A tela inicial é a CASCA (data-casca): o
Início mora nela e cada outra tela abre numa aba viva (um <iframe>), com o comportamento no static/abas.js. As regras de
decisão do abas.js são puras e rodam aqui no node; o resto (a casca e as telas) é o HTML que o servidor manda."""
import json
import os
import re
import shutil
import subprocess

import pytest

import api
from os_web import criar_app, lancador, rotas

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira: {"email": "teste@exemplo.invalid"} (o oem é público)
_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "os_web")
_JS = os.path.join(_WEB, "static", "abas.js")


@pytest.fixture
def app(monkeypatch):
    rotas._MEMO.clear()
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 0)
    monkeypatch.setattr(api, "assets_cache_info", lambda: {"ts": 0, "n": 0, "idade_h": 0.0, "expirado": True})
    monkeypatch.setattr(api, "_read_asset_cache", lambda: None)
    return criar_app(segredo="teste", testing=True)


@pytest.fixture
def cli(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    return c


# ── a casca: a tela inicial ────────────────────────────────────────────────────────────────────────────
def test_a_tela_inicial_e_a_casca_e_comeca_so_com_o_inicio(cli):
    html = cli.get("/os/").get_data(as_text=True)
    assert '<html lang="pt-BR" data-casca="1">' in html
    faixa = re.search(r'<nav class="os-tabs abas-faixa"[^>]*>(.*?)</nav>', html, re.S).group(1)
    assert faixa.count('role="tab"') == 1 and 'id="aba_inicio"' in faixa and 'aria-selected="true"' in faixa
    assert '<div class="abas-paineis" id="abas_paineis">' in html
    assert re.search(r'<main class="os-main aba-painel" id="painel_inicio" role="tabpanel"', html)
    assert '/os/static/abas.js' in html and '/os/static/abas.css' in html


def test_a_casca_leva_a_tabela_dos_setores_e_os_icones(cli):
    """Uma fonte só: a tabela sai do lancador.py para o abas.js da casca (e as telas embutidas a leem dela)."""
    html = cli.get("/os/").get_data(as_text=True)
    tabela = json.loads(re.search(r'<script type="application/json" id="abas_secoes">(.*?)</script>', html, re.S).group(1))
    assert tabela == [list(p) for p in lancador.ABAS_SECOES]
    icones = re.search(r'<template id="abas_icones">(.*?)</template>', html, re.S).group(1)
    for secao in list(lancador.ICONE_SECAO) + ["outra"]:
        assert 'data-secao="%s"><svg' % secao in icones, secao


def test_todo_setor_tem_icone_que_existe():
    secoes = {s for _, s in lancador.ABAS_SECOES}
    assert secoes <= set(lancador.ICONE_SECAO), secoes - set(lancador.ICONE_SECAO)
    for nome in lancador.ICONE_SECAO.values():
        assert nome in lancador.ICONES, nome


# ── as outras telas ────────────────────────────────────────────────────────────────────────────────────
def test_tela_fora_da_casca_vai_para_ela_e_dentro_da_aba_perde_o_cabecalho(cli):
    """O <head> decide antes de pintar: dentro de uma aba → classe os-embutido (o abas.css esconde o cabeçalho e a faixa);
    sozinha no navegador → a casca com ela numa aba. A faixa fixa de antes fica para quem abre sem JavaScript."""
    html = cli.get("/os/setor/pcm").get_data(as_text=True)
    assert '<html lang="pt-BR">' in html                                      # nem casca nem login
    cabeca = html[:html.index("</head>")]
    assert 'h.classList.add("os-embutido")' in cabeca
    assert 'location.replace("/os/?aba=" + encodeURIComponent(location.pathname + location.search + location.hash))' in cabeca
    assert cabeca.index("os-embutido") < cabeca.index("/os/static/os.css")         # antes de qualquer pintura
    assert '<nav class="os-tabs">' in html and "/os/static/abas.js" in html
    css = open(os.path.join(_WEB, "static", "abas.css"), encoding="utf-8").read()
    assert "html.os-embutido .os-header,html.os-embutido .os-sep,html.os-embutido .os-tabs{display:none!important}" in css


def test_o_login_fica_fora_das_abas(cli):
    """A sessão que cai dentro de uma aba manda para o login — que tem de tomar a janela inteira, não abrir DENTRO da
    aba. E segue sem script na tela e sem location.replace (test_os_web_sso, test_os_web_oauth)."""
    with cli.session_transaction() as s:
        s.clear()
    html = cli.get("/os/login").get_data(as_text=True)
    assert 'data-sem-abas="1"' in html and "/os/static/abas.js" not in html
    assert "window.top.location.href = location.href" in html and "location.replace" not in html


def test_as_visoes_do_historico_tem_nome_proprio(cli, monkeypatch):
    """O rótulo da aba é o título da tela: duas visões do Histórico lado a lado não podem ter o mesmo nome."""
    monkeypatch.setattr(api, "list_minhas_os", lambda *a, **k: [])      # os dublês do test_os_web_historico_27_09
    monkeypatch.setattr(api, "get_labels", lambda: [])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda: {"pessoas": [], "eu": 77})
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "_read_asset_cache", lambda: [])
    for modo, nome in (("", "Histórico de OS"), ("criadas", "Histórico de OS"), ("atribuidas", "Atribuídas a mim"),
                       ("cos", "Visão COS")):
        html = cli.get("/os/historico" + ("?modo=" + modo if modo else "")).get_data(as_text=True)
        assert "<title>%s · Grid Co.</title>" % nome in html, modo


def test_a_os_aberta_numa_aba_diz_quem_ela_e_e_o_fechar_fecha_a_aba(cli, monkeypatch):
    """Aberta pelo nº (/os/os/folio/N) ou pelo id, é a MESMA OS: o canonical deixa a casca reaproveitar a aba já aberta."""
    d = {"folio": 9812, "descricao": "OS de teste", "subtarefas": [], "tarefas": [], "etiquetas": [], "notas": "",
         "ativo": "Inversor 1", "code": "TST-1", "tipo": "Corretiva", "classif": "", "criticidade": "", "event_date": None,
         "data_fim": None, "responsavel": "", "criado_por": "", "solicitacao": None, "os_pai": "", "os_pai_id": None,
         "cancel_motivo": "", "cancel_nota": ""}
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: d if wid == 501 else {})
    monkeypatch.setattr(api, "_wo_id_por_folio", lambda f: 501 if str(f) == "9812" else None)
    for url in ("/os/os/501", "/os/os/folio/9812"):
        html = cli.get(url).get_data(as_text=True)
        assert '<link rel="canonical" href="/os/os/501">' in html, url
        assert '<a class="det-b ghost" href="/os/historico" data-aba-fechar>Fechar</a>' in html, url


def test_a_busca_do_servidor_e_a_da_casca_dizem_a_mesma_coisa(cli, tmp_path):
    """A casca decide sozinha para onde vai a busca do Início (para achar a aba já aberta); a regra é a do /os/buscar."""
    casos = ["14500", "#14500", "  14500 ", "Usina Teste 2", "abc 123"]
    esperado = {}
    for q in casos:
        r = cli.get("/os/buscar", query_string={"q": q})
        assert r.status_code == 302, q
        esperado[q] = r.headers["Location"].replace("http://localhost", "")
    out = _node(tmp_path, {"busca": casos})
    assert {q: out["busca"][q]["url"] for q in casos} == esperado


# ── as regras do abas.js, no node ──────────────────────────────────────────────────────────────────────
_HARNESS = r"""
const fs = require('fs');
global.window = {};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const P = window.OsAbas.puro, E = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const B = 'http://127.0.0.1:5050/os/', T = E.tabela || [];
const out = {};
if (E.busca) { out.busca = {}; E.busca.forEach((q) => { out.busca[q] = P.destinoDaBusca(q); }); }
if (E.secoes) out.secoes = E.secoes.map((c) => P.secaoDe(c, T));
if (E.normalizar) out.normalizar = E.normalizar.map((h) => P.normalizar(h, B));
if (E.endereco) out.endereco = E.endereco.map((s) => P.abaDoEndereco(s, B));
if (E.destino) out.destino = E.destino.map((c) => P.destino(Object.assign({target: '', download: false, fechar: false, botao: 0, mod: false}, c.a),
                                                          c.pagina, T, 'http://127.0.0.1:5050' + c.pagina.pathname + (c.pagina.search || '')));
if (E.vizinha) out.vizinha = E.vizinha.map((c) => P.vizinha(c.abas.map((id) => ({id})), c.id));
if (E.achar) out.achar = E.achar.map((c) => (P.acharAba(c.abas, c.url) || {}).id || null);
out.rotulo = P.rotulo('Histórico de OS · Grid Co.');
console.log(JSON.stringify(out));
"""


def _node(tmp_path, entrada):
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    entrada = dict(entrada, tabela=[list(p) for p in lancador.ABAS_SECOES])
    (tmp_path / "h.js").write_text(_HARNESS, encoding="utf-8")
    (tmp_path / "e.json").write_text(json.dumps(entrada, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([node, str(tmp_path / "h.js"), _JS, str(tmp_path / "e.json")], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_toda_tela_do_os_creator_tem_setor(app, tmp_path):
    """Cada rota de TELA (GET, fora da API) cai num setor da tabela — tela nova sem linha no lancador.ABAS_SECOES viraria
    o setor do 1º pedaço do caminho, e aqui avisa para dar o dela."""
    amostra = {"int": "1", "default": "pcm", "path": "x"}
    telas = set()
    for regra in app.url_map.iter_rules():
        c = regra.rule
        if "GET" not in (regra.methods or set()) or not c.startswith("/os/") or c == "/os/":
            continue
        if re.match(r"^/os/(api|static|assets|login|logout)(/|$)", c) or c.startswith("/os/historico/progresso") \
                or c.startswith("/os/historico/meta") or c.endswith("/anexos") or c == "/os/solicitacao/atualizar":
            continue                                       # JSON e caminhos de login: nunca uma aba
        telas.add(re.sub(r"<(?:(\w+)(?:\([^)]*\))?:)?\w+>", lambda m: amostra.get(m.group(1) or "default", "x"), c))
    telas = sorted(telas)
    out = _node(tmp_path, {"secoes": telas})
    sem = [c for c, s in zip(telas, out["secoes"]) if s.startswith("outra")]
    assert not sem, sem
    assert dict(zip(telas, out["secoes"]))["/os/solicitacao/fila"] == "pcm"          # o prefixo mais comprido vence
    assert dict(zip(telas, out["secoes"]))["/os/solicitacao"] == "solic"


def test_regras_do_endereco_da_aba(tmp_path):
    out = _node(tmp_path, {
        "normalizar": ["/os/historico?modo=cos&p=abc123", "/os/historico?solo=1", "/os/", "/os/api/os/1/anexo",
                       "/os/static/os.css", "/os/login?next=/os/", "/os/logout", "https://outro.site/os/historico",
                       "javascript:alert(1)", "/os/os/folio/14500"],
        "endereco": ["?aba=%2Fos%2Fhistorico%3Fmodo%3Dcos", "?aba=//outro.site/os/x", "?aba=https://outro.site/os/x",
                     "?aba=javascript:alert(1)", "?aba=%2Fos%2Fapi%2Fos%2F1", "?aba=%2Fos%2F", "", "?outra=1"],
    })
    assert out["normalizar"] == ["/os/historico?modo=cos", "/os/historico", None, None, None, None, None, None, None,
                                 "/os/os/folio/14500"]
    # ?aba= só abre tela NOSSA: nunca outro site, javascript:, a API nem a própria casca
    assert out["endereco"] == ["/os/historico?modo=cos", None, None, None, None, None, None, None]
    assert out["rotulo"] == "Histórico de OS"


def test_regras_do_clique_dentro_de_uma_aba(tmp_path):
    hist = {"pathname": "/os/historico", "search": ""}
    casos = [
        ({"href": "/os/clonar?folio=9812"}, hist, "abrir"),                    # outro setor: aba nova (o Histórico fica)
        ({"href": "/os/chamados/inspecao?pai=9812"}, hist, "abrir"),
        ({"href": "/os/historico?modo=cos"}, hist, "seguir"),                  # mesmo setor: a aba segue o link
        ({"href": "/os/solicitacao/historico"}, {"pathname": "/os/setor/pcm", "search": ""}, "seguir"),
        ({"href": "/os/"}, hist, "inicio"),                                    # o "← Início": acende o Início
        ({"href": "/"}, hist, "topo"),                                         # a Plataforma: a janela inteira
        ({"href": "/os/logout"}, hist, "topo"),
        ({"href": "/os/historico", "fechar": True}, {"pathname": "/os/os/501", "search": ""}, "fechar"),
        ({"href": "/os/os/folio/1", "target": "_blank"}, {"pathname": "/os/tickets", "search": ""}, "abrir"),
        ({"href": "/os/os/folio/1", "mod": True}, hist, "seguir"),             # Ctrl: outra aba do navegador
        ({"href": "/os/clonar", "botao": 1}, hist, "seguir"),
        ({"href": "/os/api/os/1/anexo?value=x", "download": True}, hist, "seguir"),
        ({"href": "/os/api/os/1/anexo?value=x"}, hist, "seguir"),
        ({"href": "#topo"}, hist, "seguir"),
        ({"href": "https://supervisorio.exemplo/"}, {"pathname": "/os/engenharia", "search": ""}, "seguir"),
        ({"href": "mailto:alguem@exemplo.com"}, hist, "seguir"),
    ]
    out = _node(tmp_path, {"destino": [{"a": a, "pagina": p} for a, p, _ in casos]})
    assert out["destino"] == [e for _, _, e in casos]


def test_quem_acende_ao_fechar_e_quem_ja_esta_aberta(tmp_path):
    abas = [{"id": "a1", "origem": "/os/historico", "url": "/os/historico?modo=cos"},
            {"id": "a2", "origem": "/os/os/folio/14500", "url": "/os/os/900000"}]
    out = _node(tmp_path, {
        "vizinha": [{"abas": ["a1", "a2", "a3"], "id": "a2"}, {"abas": ["a1", "a2", "a3"], "id": "a3"},
                    {"abas": ["a1"], "id": "a1"}, {"abas": ["a1"], "id": "zz"}],
        "achar": [{"abas": abas, "url": "/os/historico"}, {"abas": abas, "url": "/os/historico?modo=cos"},
                  {"abas": abas, "url": "/os/os/900000"}, {"abas": abas, "url": "/os/os/folio/14500"},
                  {"abas": abas, "url": "/os/cos"}],
    })
    assert out["vizinha"] == ["a3", "a2", "inicio", "inicio"]                   # a da direita; na ponta, a da esquerda
    assert out["achar"] == ["a1", "a1", "a2", "a2", None]                       # pelo endereço de agora OU pelo que a abriu

# tests/test_os_web_tickets_painel.py
"""O painel de acompanhamento dos tickets (Levi, 22/09/2026: item 11) e o leitor que ele divide com
a tela de Tickets.

Conferido com dado real em 22/09 (só leitura), contra os números do mockup aprovado: total,
abertas, parados, +30 dias, mediana, fechadas em 30 dias, sem cliente, faixas, clientes e top 10
batem valor a valor. As diferenças são as do conserto do diário: 621 e não 627 abertas sem OS em
Trackers (6 tickets nasceram com OS), 77 e não 82 em Strings. Estes testes seguram as regras.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess

import pytest

import tickets_api
import tickets_diario
from os_web import criar_app, tickets_painel as tp, tickets_web as tw
from os_web import rotas_tickets as rt

_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator", "os_web")
JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
AGORA = dt.datetime(2026, 9, 22, 17, 0)
HOJE = AGORA.date()


def _oc(usina="TIM100", ini=None, fim=None, os_=None, cliente="Athon", qtd=1, **extra):
    o = {"Usina": usina, "Cliente": cliente, "Início da ocorrência": ini, "Fim da ocorrência": fim,
         "OS": os_, "Quantidade de trackers parados": qtd, "Status": "Parado"}
    o.update(extra)
    return o


def _prontas(linhas, aba="Trackers"):
    ocs, _ = tw.montar(linhas, AGORA)
    tw.preencher_cliente(ocs)
    tw.recalcular(ocs, AGORA)
    return ocs


def _dias_atras(n, hora="08:00:00"):
    return (HOJE - dt.timedelta(days=n)).strftime("%Y-%m-%d ") + hora


# ── 1. o estado depois do diário ─────────────────────────────────────────────────────────────
def test_recalcular_poe_a_OS_do_diario_no_estado():
    """O `montar` roda ANTES do diário. A OS vinculada pelo app mora só no diário — sem recalcular,
    a ocorrência seguia "Aberta" com o número da OS na coluna ao lado (6 em Trackers em 22/09)."""
    ocs, _ = tw.montar([_oc(ini=_dias_atras(40))], AGORA)
    assert ocs[0]["_estado"] == "aberta"
    ocs[0]["OS"] = "13637"                                   # = o diário aplicado
    tw.recalcular(ocs, AGORA)
    assert ocs[0]["_estado"] == "com_os"
    ocs[0]["Fim da ocorrência"] = _dias_atras(1)
    tw.recalcular(ocs, AGORA)
    assert ocs[0]["_estado"] == "encerrada" and ocs[0]["_dias"] == 39


def test_a_lista_e_o_painel_leem_pelo_MESMO_caminho(monkeypatch):
    """Diário com a OS de uma ocorrência: a tela de Tickets e o painel têm de contá-la igual."""
    linha = dict(_oc(ini=_dias_atras(40)), _row=7, **{"Nº do SKID": "01", "Nº do tracker / Identificação": "3"})
    monkeypatch.setattr(tickets_api, "listar_linhas", lambda sid, **k: [dict(linha)] if sid == 123 else [])
    reg = {"linha": 7, "aba": "Trackers", "quando": "2026-09-15 12:00:00", "quem": "Gabriela",
           "impressao": tickets_diario.impressao("Trackers", linha)}
    for c in tickets_diario.CAMPOS:
        reg[c] = ""
    reg.update({"OS": "13637", "Status do ticket": "OS Programada"})
    monkeypatch.setattr(tickets_diario, "ler", lambda **k: [reg])
    ocs, _o, placar = rt._carregar("Trackers")
    assert ocs[0]["_estado"] == "com_os"
    assert ocs[0]["Início da ocorrência"] == _dias_atras(40)          # o "" do registro não apagou
    r = tp.resumo(ocs, "Trackers", AGORA)
    assert r["sem_os"] == 0 and r["estados"]["com_os"] == 1 and r["abertas"] == 1


# ── 2. semanas ───────────────────────────────────────────────────────────────────────────────
def test_a_semana_termina_HOJE_e_a_de_7_dias_atras_e_a_anterior():
    ocs = [_oc(ini=_dias_atras(0)), _oc(ini=_dias_atras(6)), _oc(ini=_dias_atras(7)),
           _oc(ini=_dias_atras(83)), _oc(ini=_dias_atras(84)),              # 84 = fora das 12 semanas
           _oc(ini=(HOJE + dt.timedelta(days=2)).strftime("%Y-%m-%d")),     # futuro: não conta
           _oc(ini=_dias_atras(20), fim=_dias_atras(3))]
    sem = tp.semanas(ocs, HOJE)
    assert len(sem) == tp.SEMANAS
    assert sem[-1]["ate"] == "22/09" and sem[-1]["de"] == "16/09"
    assert sem[-1]["abertas"] == 2 and sem[-2]["abertas"] == 1
    assert sem[0]["abertas"] == 1                            # o de 83 dias; o de 84 ficou de fora
    assert sem[-1]["fechadas"] == 1 and sum(w["fechadas"] for w in sem) == 1


# ── 3. faixas ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dias, faixa", [(0, "0-7"), (7, "0-7"), (8, "8-30"), (30, "8-30"),
                                         (31, "31-90"), (365, "181-365"), (366, ">365")])
def test_faixas_nas_bordas(dias, faixa):
    fx = tp.faixas([{"_dias": dias}])
    assert [f["rotulo"] for f in fx if f["n"]] == [faixa]


def test_o_vermelho_da_faixa_e_o_alarme_da_tela():
    fx = {f["rotulo"]: f["alarme"] for f in tp.faixas([])}
    assert fx == {"0-7": False, "8-30": False, "31-90": True, "91-180": True, "181-365": True, ">365": True}
    assert tw.ALARME_DIAS == 30


# ── 4. alerta ────────────────────────────────────────────────────────────────────────────────
def _sem(fechadas, abertas=None):
    abertas = abertas or [10] * len(fechadas)
    return [{"de": "", "ate": "%02d/09" % (i + 1), "abertas": a, "fechadas": f}
            for i, (a, f) in enumerate(zip(abertas, fechadas))]


def test_sem_alerta_quando_a_ultima_semana_fechou():
    assert tp.alerta(_sem([5, 5, 5, 5, 0, 3])) is None


def test_uma_semana_sem_fechar_ainda_nao_e_alerta():
    assert tp.alerta(_sem([5, 5, 5, 5, 5, 0])) is None


def test_alerta_compara_com_a_MEDIA_das_4_anteriores():
    a = tp.alerta(_sem([100, 154, 137, 109, 156, 0, 0], abertas=[120, 164, 117, 137, 134, 96, 2]))
    assert a["titulo"].startswith("Nenhuma ocorrência fechada há 2 semanas")
    assert "terminou em 05/09" in a["titulo"]
    assert "média 139 por semana" in a["texto"]               # (154+137+109+156)/4, não a última
    assert "só entraram 2 (a média era 121)" in a["texto"]    # (117+137+134+96)/4: as 4 antes da última
    assert tp.TEXTO_CAUSA in a["texto"]


def test_sem_alerta_se_ja_nao_fechava_nada():
    assert tp.alerta(_sem([0, 0, 0, 1, 0, 0])) is None                # média 0,25 antes do buraco
    assert tp.alerta(_sem([0, 0, 0, 0, 0, 0], [0] * 6)) is None       # aba parada dos dois lados


def test_doze_semanas_sem_fechar_nenhuma_tem_alerta_proprio():
    a = tp.alerta(_sem([0] * 12, [3] * 12))
    assert a["titulo"] == "Nenhuma ocorrência fechada nas últimas 12 semanas"


# ── 5. clientes, grafias e qualidade ─────────────────────────────────────────────────────────
def test_clientes_ordenados_por_equipamento_e_o_resto_vira_outros():
    ab = [dict(_cliente="C%d" % i, **{"Quantidade de trackers parados": i + 1}) for i in range(10)]
    lst = tp.clientes(ab, "Trackers")
    assert len(lst) == tp.MAX_CLIENTES
    assert lst[0] == ["C9", 1, 10]
    assert lst[-1] == ["outros (3)", 3, 6]                    # C0, C1 e C2: 1 + 2 + 3


def test_qtd_em_branco_conta_um_equipamento():
    lst = tp.clientes([{"_cliente": "X", "Quantidade de trackers parados": ""}], "Trackers")
    assert lst == [["X", 1, 1]]


def test_grafias_acha_as_duplicadas_reais_e_nao_as_usinas_irmas():
    nomes = ["Macaiba 1", "Macaíba", "Santarem 1 e 2", "Santarém 1 e 2", "Ibaté 1", "Ibaté 2",
             "Coração 1", "Coração 2", "Araçoiaba da Serra 1", "Araçoiaba da Serra 2", "Santarém 1",
             "Santarém 2", "Barretos"]
    pares = tp.grafias_duplicadas([{"Usina": n, "Quantidade de trackers parados": 2} for n in nomes], "Trackers")
    achados = sorted(tuple(sorted((p[0], p[2]))) for p in pares)
    assert ("Macaiba 1", "Macaíba") in achados
    assert ("Santarem 1 e 2", "Santarém 1 e 2") in achados
    for irmas in (("Ibaté 1", "Ibaté 2"), ("Coração 1", "Coração 2"),
                  ("Araçoiaba da Serra 1", "Araçoiaba da Serra 2"), ("Santarém 1", "Santarém 2")):
        assert irmas not in achados, irmas


def test_qualidade_no_singular_e_com_o_filtro_certo():
    ocs = _prontas([_oc(usina="Barretos", cliente="", ini=None)])
    r = tp.resumo(ocs, "Trackers", AGORA)
    textos = [q["destaque"] + q["texto"] for q in r["qualidade"]]
    assert textos[0].startswith("A única aberta não tem OS vinculada")
    assert "1 aberta, em 1 usina, sem cliente em lugar nenhum da planilha." in textos
    assert any(t.startswith("1 aberta sem data de início") for t in textos)
    filtros = [q["filtro"] for q in r["qualidade"] if q["filtro"]]
    assert {"estado": "aberta"} in filtros and {"cliente": tw.SEM_CLIENTE} in filtros


def test_qualidade_no_plural():
    ocs = _prontas([_oc(usina="Barretos", cliente="", ini=None), _oc(usina="PRM100", cliente="", ini=None),
                    _oc(ini=_dias_atras(3), os_="100")])
    textos = [q["destaque"] + q["texto"] for q in tp.resumo(ocs, "Trackers", AGORA)["qualidade"]]
    assert textos[0].startswith("2 de 3 abertas sem OS vinculada")
    assert "2 abertas, em 2 usinas, sem cliente em lugar nenhum da planilha." in textos


# ── 6. o resumo fecha as contas ──────────────────────────────────────────────────────────────
def test_resumo_fecha_as_contas():
    ocs = _prontas([
        _oc(ini=_dias_atras(3), qtd=6), _oc(ini=_dias_atras(45)), _oc(ini=_dias_atras(400), os_="9208"),
        _oc(ini=None), _oc(ini=(HOJE + dt.timedelta(days=5)).strftime("%Y-%m-%d")),
        _oc(ini=_dias_atras(60), fim=_dias_atras(10)),
        _oc(ini=_dias_atras(20), fim=_dias_atras(40)),         # Fim antes do Início: encerrada, sem dias
        dict(_oc(ini=_dias_atras(5)), Status="Em conformidade"),   # check periódico: não é ocorrência
    ])
    r = tp.resumo(ocs, "Trackers", AGORA)
    assert r["total"] == 7 and r["abertas"] == 5
    assert r["qtd"] == 10                                     # 6 + 1 + 1 + 1 + 1
    assert r["sem_os"] == r["estados"]["aberta"] == 4         # "Aberta" É "sem OS e sem Fim"
    assert r["estados"]["com_os"] == 1 and r["estados"]["encerrada"] == 2
    assert r["mais_30"] == 2 == sum(f["n"] for f in r["faixas"] if f["alarme"])
    assert r["sem_inicio"] == 1 and r["inicio_futuro"] == 1
    assert sum(f["n"] for f in r["faixas"]) + r["sem_inicio"] + r["inicio_futuro"] == r["abertas"]
    assert r["mediana_dias"] == 45                            # 3, 45, 400
    assert r["fechadas_30d"] == 1                             # a de 10 dias; a de 40 ficou fora
    assert r["top"][0][:3] == ["TIM100", "Athon", 10]


# ── 7. a rota e a página ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    linhas = {123: [dict(_oc(ini=_dias_atras(40), qtd=3), _row=5, **{"Nº do SKID": "1", "Nº do tracker / Identificação": "2"})],
              128: [dict(_oc(usina="Crateus", cliente="Renogrid", ini=_dias_atras(10)), _row=9,
                         **{"Quantidade de strings no afetadas": 12, "Inversor": "INV-3"})]}
    monkeypatch.setattr(tickets_api, "listar_linhas", lambda sid, **k: [dict(l) for l in linhas.get(sid, [])])
    monkeypatch.setattr(tickets_diario, "ler", lambda **k: [])
    monkeypatch.setattr(rt, "_pode_gravar", lambda: False)
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Ana Souza", "email": "ana@gridco.com.br", "perfil": "ANALISTA"}
    c.linhas = linhas
    return c


def _dados(html):
    m = re.search(r'<script type="application/json" id="tp_dados">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_painel_traz_as_DUAS_abas_calculadas(cli):
    r = cli.get("/os/tickets/painel?aba=Strings")
    assert r.status_code == 200
    j = _dados(r.get_data(as_text=True))
    assert j["aba"] == "Strings"
    assert j["dados"]["Trackers"]["qtd"] == 3 and j["dados"]["Trackers"]["mais_30"] == 1
    assert j["dados"]["Strings"]["qtd"] == 12 and j["dados"]["Strings"]["top"][0][0] == "Crateus"
    assert [e[0] for e in j["estados"]] == ["aberta", "com_os", "verificando", "a_fechar", "encerrada"]


def test_aba_que_falha_vira_aviso_so_nela(cli, monkeypatch):
    def listar(sid, **k):
        if sid == 128:
            raise RuntimeError("timeout")
        return [dict(l) for l in cli.linhas[sid]]
    monkeypatch.setattr(tickets_api, "listar_linhas", listar)
    j = _dados(cli.get("/os/tickets/painel").get_data(as_text=True))
    assert "timeout" in j["dados"]["Strings"]["erro"]
    assert j["dados"]["Trackers"]["qtd"] == 3


def test_o_menu_do_topo_nao_quebra_nem_no_painel_nem_na_lista(cli):
    """`abas` é a variável global das abas do topo. A tela de Tickets passava a sua lista
    Trackers/Strings com esse nome e o menu saía com dois links vazios (visto em 22/09)."""
    for url in ("/os/tickets", "/os/tickets/painel"):
        h = cli.get(url).get_data(as_text=True)
        nav = re.search(r'<nav class="os-tabs">(.*?)</nav>', h, re.S).group(1)
        assert "Criar OS" in nav and 'href=""' not in nav, url
        assert re.search(r'class="os-tab on" href="/os/"', nav), url    # "Criar OS" aceso


def test_a_lista_tem_o_botao_do_painel(cli):
    h = cli.get("/os/tickets?aba=Strings").get_data(as_text=True)
    assert 'href="/os/tickets/painel?aba=Strings"' in h


def test_sem_emoji_no_painel(cli):
    h = cli.get("/os/tickets/painel").get_data(as_text=True)
    js = open(os.path.join(_WEB, "static", "tickets_painel.js"), encoding="utf-8").read()
    for texto in (h, js):
        assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", texto)


def test_o_js_do_painel_e_javascript_valido():
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    r = subprocess.run([node, "--check", os.path.join(_WEB, "static", "tickets_painel.js")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


_HARNESS = r"""
const fs = require('fs');
const dados = fs.readFileSync(process.argv[2], 'utf8');
function no(tag) {
  return {tag, attrs: {}, children: [], style: {}, textContent: '', innerHTML: '', hidden: false, dataset: {},
    classList: {toggle() {}, add() {}, remove() {}},
    setAttribute(k, v) { this.attrs[k] = v; }, appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { this.children.splice(this.children.indexOf(c), 1); },
    get firstChild() { return this.children[0] || null; },
    addEventListener(t, f) { (this._ev = this._ev || {})[t] = f; },
    getBoundingClientRect() { return {left: 0, top: 0, width: 560, height: 230}; }};
}
const els = {};
const abas = ['Trackers', 'Strings'].map((a) => { const n = no('a'); n.dataset.aba = a; return n; });
global.document = {
  getElementById(id) { return id === 'tp_dados' ? {textContent: dados} : (els[id] || (els[id] = no(id))); },
  createElementNS(ns, tag) { return no(tag); },
  querySelectorAll(sel) { return sel.indexOf('data-aba') >= 0 ? abas : []; },
};
global.location = {href: ''}; global.history = {replaceState() {}}; global.innerWidth = 1366;
eval(fs.readFileSync(process.argv[3], 'utf8'));
const tags = (id, t) => els[id].children.filter((c) => c.tag === t).length;
const conta = () => ({linhas: tags('g_fluxo', 'path'), barras: tags('g_idade', 'path'), clientes: tags('g_cli', 'path'),
                      sub: els.tp_sub.textContent, erro: els.tp_erro.hidden});
const antes = conta();
abas[1]._ev.click({preventDefault() {}});                       // troca de aba, como a pessoa faz
['g_fluxo', 'g_idade', 'g_cli'].forEach((id) => els[id].children.forEach((c) => {
  if (c._ev && c._ev.mousemove) c._ev.mousemove({clientX: 100, clientY: 100});
  if (c._ev && c._ev.mouseleave) c._ev.mouseleave({});
}));
console.log(JSON.stringify({antes, depois: conta(), voltar: els.tp_voltar.href, tip: els.tp_tip.innerHTML}));
"""


def test_o_js_RODA_nas_duas_abas_com_dado_de_verdade(tmp_path):
    """A classe da "função fantasma" (22/09, plataforma): apagar uma função e deixar a chamada. O
    `node --check` não pega — a chamada só quebra quando RODA. Aqui o script roda de verdade, com
    um DOM de mentira: desenha Trackers, troca para Strings pelo clique e passa o mouse em tudo."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    trk = _prontas([_oc(ini=_dias_atras(3), qtd=6), _oc(ini=_dias_atras(45)), _oc(usina="Barretos", cliente="", ini=None),
                    _oc(ini=_dias_atras(60), fim=_dias_atras(10))])
    stg = _prontas([dict(_oc(usina="Crateus", cliente="Renogrid", ini=_dias_atras(10)),
                         **{"Quantidade de strings no afetadas": 12})], "Strings")
    j = {"dados": {"Trackers": tp.resumo(trk, "Trackers", AGORA), "Strings": tp.resumo(stg, "Strings", AGORA)},
         "estados": tp.estados_def(), "aba": "Trackers", "lido": "22/09/2026 às 17:00", "sem_cliente": tw.SEM_CLIENTE}
    (tmp_path / "dados.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "harness.js").write_text(_HARNESS, encoding="utf-8")
    r = subprocess.run([node, str(tmp_path / "harness.js"), str(tmp_path / "dados.json"),
                        os.path.join(_WEB, "static", "tickets_painel.js")], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    fx_t = sum(1 for f in j["dados"]["Trackers"]["faixas"] if f["n"])
    assert out["antes"] == dict(out["antes"], linhas=2, barras=fx_t, clientes=len(j["dados"]["Trackers"]["clientes"]))
    assert out["depois"]["linhas"] == 2 and out["depois"]["clientes"] == 1        # Strings: 1 cliente
    assert "aba Trackers" in out["antes"]["sub"] and "aba Strings" in out["depois"]["sub"]
    assert out["antes"]["erro"] is True                      # sem erro de leitura: o aviso fica escondido
    assert out["voltar"] == "/os/tickets?aba=Strings"
    assert out["tip"]                                        # o tooltip foi montado

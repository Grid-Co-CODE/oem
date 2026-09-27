# tests/test_os_web_insp.py
"""A Inspeção de chamados na web (Levi, 27/09/2026) — o card único de Chamados, a tela clonada do app
(`steps/insp_chamado.py`) e o "Abrir chamado" do card da OS, que leva a ela com o ativo, a data do incidente e o
responsável da OS de referência.

As REGRAS vêm do app, uma por uma (insp_web.py); estes testes seguram as que não aparecem na tela e a fidelidade de
texto com o app — que lê o código-fonte dele, como os outros testes de porte."""
import ast
import datetime as dt
import json
import os
import re
import shutil
import subprocess

import pytest

import api
import chamado_insp_spec as ci
from os_web import criar_app, insp_web as iw, lancador

_OSC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator")
_WEB = os.path.join(_OSC, "os_web")
JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
BRT = iw.BRT


def _app_src() -> str:
    return open(os.path.join(_OSC, "steps", "insp_chamado.py"), encoding="utf-8").read()


# ── 1. fidelidade de texto com o app ────────────────────────────────────────────────────────────
def test_os_textos_dos_combos_sao_os_do_app():
    tree = ast.parse(_app_src())
    do_app = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name) and t.id.startswith("SEM_")}
    for nome in ("SEM_CLI", "SEM_USI", "SEM_TIPO", "SEM_ATIVO", "SEM_MARCA"):
        assert getattr(iw, nome) == do_app[nome], nome


def test_frases_da_tela_sao_as_do_app():
    src = _app_src()
    tpl = open(os.path.join(_WEB, "templates", "insp.html"), encoding="utf-8").read()
    assert iw.SEM_PAI in src and iw.SEM_PREVIA in src
    for frase in ("Equipamento com falha", "Origem e datas", "Execução", "Subtarefas que a OS vai levar",
                  "Marca do ativo", "(vem preenchida quando o cadastro do ativo diz a marca)", "OS pai",
                  "(a data do incidente passa a ser a dela)", "nº da OS que originou (opcional)", "Últimas OS",
                  "Data do incidente", "Data programada", "(quando o técnico vai a campo)", "Responsável em campo",
                  "contexto para o técnico (opcional)", "Criar OS de inspeção", "ÚLTIMAS OS DESTE ATIVO",
                  "clique para usar como OS pai"):
        assert frase in src, "o app não tem mais: %s" % frase
        assert frase in tpl, "a tela web não tem: %s" % frase


def test_cores_de_status_sao_as_do_app():
    src = _app_src()
    for st, cor in iw.COR_STATUS.items():
        if st != "Concluída":                    # a do app é o GREEN do steps/ui
            assert '"%s": "%s"' % (st, cor) in src, st


# ── 2. datas ────────────────────────────────────────────────────────────────────────────────────
AGORA = dt.datetime(2026, 9, 27, 15, 20, tzinfo=BRT)


def test_programada_e_amanha_8h_quando_o_incidente_e_passado():
    inc = dt.datetime(2026, 9, 20, 3, 10, tzinfo=BRT)
    assert iw.prog_apos(inc, AGORA) == dt.datetime(2026, 9, 28, 8, 0, tzinfo=BRT)


def test_programada_vai_para_o_dia_seguinte_ao_incidente_futuro():
    inc = dt.datetime(2026, 9, 30, 14, 0, tzinfo=BRT)
    assert iw.prog_apos(inc, AGORA) == dt.datetime(2026, 10, 1, 8, 0, tzinfo=BRT)


def test_incidente_de_hoje_programa_amanha_8h():
    assert iw.prog_apos(AGORA, AGORA) == dt.datetime(2026, 9, 28, 8, 0, tzinfo=BRT)


@pytest.mark.parametrize("iso", ["2026-09-10T11:00:00", "2026-09-10 11:00:00", "2026-09-10T11:00:00Z",
                                 "2026-09-10T11:00:00.123+00:00", "2026-09-10T11:00"])
def test_event_date_do_fracttal_e_utc_e_vira_brasilia(iso):
    """A OS 10391: incidente 08:00 em Brasília, 11:00 no ISO do Fracttal."""
    assert iw.iso_para_brt(iso) == dt.datetime(2026, 9, 10, 8, 0, tzinfo=BRT)


def test_data_invalida_vira_none():
    assert iw.iso_para_brt("") is None and iw.iso_para_brt("ontem") is None


# ── 3. a OS pai ─────────────────────────────────────────────────────────────────────────────────
PESSOAS = [{"id_personnel": 10, "name": "Pedro  Alfa"}, {"id_personnel": 20, "name": "Pedro  Beta"},
           {"id_personnel": 30, "name": "Analista  Teste"}]


def test_responsavel_com_espaco_duplo_casa_a_pessoa_certa():
    """O cadastro grava 'Pedro  Beta'; a OS traz 'Pedro Beta'. Pelo 1º nome, o app pegaria o Pedro Alfa."""
    assert iw.casar_responsavel("Pedro Beta", PESSOAS) == (20, "Pedro  Beta")


def test_responsavel_exato_e_pelo_primeiro_nome():
    assert iw.casar_responsavel("Analista  Teste", PESSOAS) == (30, "Analista  Teste")
    assert iw.casar_responsavel("Analista T.", PESSOAS) == (30, "Analista  Teste")        # o recuo do app
    assert iw.casar_responsavel("Fulano", PESSOAS) == (None, "")
    assert iw.casar_responsavel("", PESSOAS) == (None, "")


def test_herda_data_com_hora_e_responsavel_da_os_pai():
    pai = {"folio": 9812, "descricao": "[INV 2.18] Religamento", "event_date": "2026-09-20T11:30:00",
           "responsavel": "Pedro Beta", "code": "BAR-INV2.18", "id_work_order": 501}
    h = iw.herdar_do_pai(pai, PESSOAS, AGORA)
    assert h["inc"] == "2026-09-20T08:30" and h["prog"] == "2026-09-28T08:00"
    assert h["resp_id"] == 20 and h["id_work_order"] == 501 and h["code"] == "BAR-INV2.18"
    assert h["texto"] == ("OS 9812 · [INV 2.18] Religamento  ·  herdado: incidente 20/09/2026 08:30, "
                          "responsável Pedro Beta")


def test_responsavel_fora_da_lista_e_dito_e_nao_chutado():
    h = iw.herdar_do_pai({"folio": 1, "responsavel": "Fulano de Tal"}, PESSOAS, AGORA)
    assert h["resp_id"] is None and "responsável da OS pai é Fulano de Tal, que não está na lista" in h["texto"]


def test_sem_event_date_usa_a_data_que_o_painel_mostrou():
    """A 6647 não tem event_date no detalhe; a linha clicada no painel mostrava 20/05."""
    h = iw.herdar_do_pai({"folio": 6647}, PESSOAS, AGORA, data_painel="2026-05-20T13:00:00")
    assert h["inc"] == "2026-05-20T10:00"


# ── 4. catálogo e marca ─────────────────────────────────────────────────────────────────────────
def _cat():
    return [
        {"id": 1, "code": "BAR-INV1", "description": "Inversor 1.1 Huawei SUN2000 { BAR-INV1 }", "tipo": "Inversor",
         "usina": "Alfa", "cliente": "Acme"},
        {"id": 2, "code": "BAR-INV2", "description": "Inversor 1.2 { BAR-INV2 }", "tipo": "Inversor",
         "usina": "Alfa", "cliente": "Acme"},
        {"id": 3, "code": "BAR-TRF", "description": "Transformador 1", "tipo": "Transformador", "usina": "Alfa",
         "cliente": "Acme"},
        {"id": 4, "code": "X-INV1", "description": "Inversor SMA { X-INV1 }", "tipo": "Inversor", "usina": "",
         "cliente": "Acme"},
    ]


def test_catalogo_so_leva_tipo_com_modelo_e_com_usina():
    cat = iw.catalogo(_cat())
    assert [a["id"] for a in cat] == [1, 2]              # o transformador não tem modelo; o SMA não tem usina
    assert not ci.aceita("Transformador")


def test_ativos_em_ordem_e_sem_o_code_no_nome():
    cat = iw.catalogo(_cat())
    nomes = [a["nome"] for a in iw.ativos(cat, "Alfa", "Inversor")]
    assert nomes == ["Inversor 1.1 Huawei SUN2000", "Inversor 1.2"]


def test_marca_sugerida_pelo_cadastro_e_pelos_irmaos():
    cat = iw.catalogo(_cat())
    m = iw.marcas(cat[0], "Inversor", cat)
    assert m["sugerida"] == "Huawei" and m["aviso"] == ""
    # o Inversor 1.2 não diz a marca; o irmão da mesma usina diz Huawei
    assert iw.marcas(cat[1], "Inversor", cat)["sugerida"] == "Huawei"


def test_duas_marcas_nos_irmaos_viram_campo_vazio():
    cat = iw.catalogo(_cat()) + [{"id": 9, "code": "BAR-INV9", "description": "Inversor 1.9 Sungrow",
                                  "tipo": "Inversor", "usina": "Alfa", "cliente": "Acme"}]
    assert iw.marca_pelos_irmaos(cat[1], cat, ci.marcas_para("Inversor")) == ""


def test_marca_sem_processo_vira_aviso_e_nao_selecao(monkeypatch):
    monkeypatch.setattr(ci, "marca_do_ativo", lambda a: "SolarEdge")
    m = iw.marcas({"usina": "X"}, "Inversor", [])
    assert m["sugerida"] == "" and "SolarEdge, que ainda não tem processo de chamado documentado" in m["aviso"]


def test_previa_e_a_do_spec():
    p = iw.previa("Inversor", "Huawei")
    assert p["resumo"] == ci.resumo("Inversor", "Huawei")
    assert [l["texto"] for l in p["linhas"]] == [s["description"] for s in ci.subtarefas("Inversor", "Huawei")]
    assert iw.previa("", "Huawei") == {"resumo": iw.SEM_PREVIA, "linhas": []}


# ── 5. criar ────────────────────────────────────────────────────────────────────────────────────
def _corpo(**k):
    c = {"ativo": 1, "marca": "Huawei", "resp_id": "30", "resp_nome": "Analista  Teste", "inc": "2026-09-20T08:30",
         "prog": "2026-09-28T08:00", "pai_id": 501, "obs": "  ver string 3  "}
    c.update(k)
    return c


def test_validar_criar_monta_o_que_o_app_manda():
    kw, erro = iw.validar_criar(_corpo(), iw.catalogo(_cat()))
    assert erro == ""
    assert kw["asset"]["id"] == 1 and kw["fabricante"] == "Huawei" and kw["id_responsible"] == 30
    assert kw["event_date"] == dt.datetime(2026, 9, 20, 8, 30, tzinfo=BRT)       # carimbado em Brasília
    assert kw["prog_date"] == dt.datetime(2026, 9, 28, 8, 0, tzinfo=BRT)
    assert kw["id_parent"] == 501 and kw["note"] == "ver string 3"


@pytest.mark.parametrize("muda, erro", [({"ativo": 999}, iw.ERRO_ATIVO), ({"marca": ""}, iw.ERRO_MARCA),
                                        ({"marca": "Marca Inventada"}, iw.ERRO_MARCA), ({"resp_id": ""}, iw.ERRO_RESP)])
def test_travas_do_criar(muda, erro):
    assert iw.validar_criar(_corpo(**muda), iw.catalogo(_cat())) == (None, erro)


def test_confirmacao_nao_manda_abrir_chamado_na_propria_inspecao():
    """Na web o "Abrir chamado" do card leva à inspeção; a frase do app pediria uma inspeção da inspeção."""
    t = iw.confirmacao(8, _cat()[0], "Huawei", "Aguardando Garantia")
    assert t.startswith("Criar a OS de inspeção com 8 subtarefas?") and "Abrir chamado" not in t


# ── 6. o card único e as rotas ──────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: _cat())
    monkeypatch.setattr(api, "get_responsaveis", lambda: PESSOAS)
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Dois", "email": "analista2@teste.invalid", "perfil": "ANALISTA"}
    return c


def test_um_card_de_chamados_na_home(cli, monkeypatch):
    monkeypatch.setattr(api, "contar_minhas_analises", lambda *a, **k: 0)     # o selo da Performance, sem rede
    h = cli.get("/os/").get_data(as_text=True)
    assert h.count(">Chamados<") == 1 and "Inspeção de chamados" not in h
    assert 'href="/os/chamados"' in h and lancador.SUB_CHAMADOS in h


def test_o_card_abre_as_duas_portas(cli):
    h = cli.get("/os/chamados").get_data(as_text=True)
    assert "Acompanhamento de chamados" in h and "Inspeção de chamados" in h
    assert 'href="/os/chamados/inspecao"' in h


def test_a_tela_nasce_com_a_os_de_referencia(cli):
    h = cli.get("/os/chamados/inspecao?pai=9812").get_data(as_text=True)
    assert 'data-pai="9812"' in h and 'value="9812"' in h


def test_o_login_devolve_a_tela_com_a_os_de_referencia():
    """Sessão vencida no meio do "Abrir chamado": o login tem de voltar COM o ?pai=, senão a inspeção abre vazia."""
    app = criar_app(segredo="teste", testing=True)
    r = app.test_client().get("/os/chamados/inspecao?pai=9812")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/os/login?next=%2Fos%2Fchamados%2Finspecao%3Fpai%3D9812")


def test_enderecos_antigos_redirecionam(cli):
    r = cli.get("/os/inspecao?ativo=5")
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/chamados/inspecao?ativo=5")
    r = cli.get("/os/chamados/abrir?folio=9812")
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/chamados/inspecao?pai=9812")


def test_api_pai_passa_ativo_data_e_responsavel(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes_por_folio", lambda f: {
        "folio": 9812, "descricao": "Religamento", "event_date": "2026-09-20T11:30:00", "responsavel": "Pedro Beta",
        "code": "BAR-INV1", "ativo": "Inversor 1.1", "id_work_order": 501})
    j = cli.get("/os/api/insp/pai?folio=9812").get_json()
    assert j["inc"] == "2026-09-20T08:30" and j["resp_id"] == 20 and j["id_work_order"] == 501
    assert j["ativo"] == {"cliente": "Acme", "usina": "Alfa", "tipo": "Inversor", "id": 1, "code": "BAR-INV1",
                          "nome": "Inversor 1.1 Huawei SUN2000"}
    assert j["aviso_ativo"] == ""


def test_api_pai_com_ativo_sem_modelo_avisa(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes_por_folio", lambda f: {
        "folio": 77, "descricao": "Trafo", "event_date": "", "responsavel": "", "code": "BAR-TRF", "ativo": "Transformador 1",
        "id_work_order": 9})
    j = cli.get("/os/api/insp/pai?folio=77").get_json()
    assert j["ativo"] is None and "não tem modelo de inspeção" in j["aviso_ativo"]


def test_api_pai_inexistente_e_404(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes_por_folio", lambda f: None)
    r = cli.get("/os/api/insp/pai?folio=1")
    assert r.status_code == 404 and "não encontrada" in r.get_json()["erro"]


def test_api_criar_chama_a_funcao_do_app(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_inspecao_chamado",
                        lambda **k: visto.update(k) or {"wo_folio": 14501, "n_subtarefas": 8, "etiqueta_erro": ""})
    r = cli.post("/os/api/insp/criar", json=_corpo())
    assert r.status_code == 200 and r.get_json()["texto"] == "OS 14501 criada com 8 subtarefas."
    assert visto["asset"]["code"] == "BAR-INV1" and visto["id_parent"] == 501 and visto["id_responsible"] == 30


def test_api_criar_recusa_sem_ativo(cli, monkeypatch):
    monkeypatch.setattr(api, "create_inspecao_chamado", lambda **k: pytest.fail("não podia criar"))
    r = cli.post("/os/api/insp/criar", json=_corpo(ativo=None))
    assert r.status_code == 400 and r.get_json()["erro"] == iw.ERRO_ATIVO


def test_catalogo_em_cascata(cli):
    assert cli.get("/os/api/insp/catalogo").get_json() == {"clientes": ["Acme"]}
    assert cli.get("/os/api/insp/catalogo?cliente=Acme").get_json() == {"usinas": ["Alfa"]}
    j = cli.get("/os/api/insp/catalogo?usina=Alfa").get_json()
    assert "Inversor" in j["tipos"] and [a["id"] for a in j["ativos"] if a["tipo"] == "Inversor"] == [1, 2]


# ── 7. o JS: o caminho do "Abrir chamado", rodado de verdade ────────────────────────────────────
_HARNESS = r"""
const fs = require('fs');
const respostas = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const unesc = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
function el(id) {
  const o = {id, value: '', textContent: '', hidden: false, disabled: false, title: '', dataset: {}, _ev: {},
    className: '', style: {},
    addEventListener(t, f) { (this._ev[t] = this._ev[t] || []).push(f); },
    dispatchEvent(e) { (this._ev[e.type] || []).forEach((f) => f(e)); return true; },
    closest() { return null; }, blur() {}};
  return o;
}
function sel(id, vazio) {
  const s = el(id); s.options = []; s.selectedIndex = -1;
  Object.defineProperty(s, 'innerHTML', {set(h) {
    s.options = [...h.matchAll(/<option value="([^"]*)">([^<]*)<\/option>/g)].map((m) => ({value: unesc(m[1]), text: unesc(m[2])}));
    s.selectedIndex = s.options.length ? 0 : -1; }, get() { return ''; }});
  Object.defineProperty(s, 'value', {get() { return s.selectedIndex >= 0 ? s.options[s.selectedIndex].value : ''; },
    set(v) { s.selectedIndex = s.options.findIndex((o) => o.value === String(v)); }});
  s.innerHTML = '<option value="">' + vazio + '</option>';
  return s;
}
const els = {};
['cb_cli', 'cb_usi', 'cb_tipo', 'cb_ativo', 'cb_marca', 'cb_resp'].forEach((k) => { els[k] = sel(k, 'vazio ' + k); });
['ed_pai', 'lb_pai', 'b_hist', 'dt_inc', 'dt_prog', 'ed_obs', 'lb_resumo', 'lb_subs', 'hint', 'b_criar', 'res',
 'modal_hist', 'hist_lista', 'hist_nome', 'hist_dica', 'hist_rod'].forEach((k) => { els[k] = el(k); });
const R = el('insp'); R.dataset = {pai: '9812', ativo: '', semPai: 'Sem OS pai', semPrevia: 'Escolha o ativo e a marca'};
els.insp = R; els.ed_pai.value = '9812';
global.document = {getElementById: (id) => els[id] || null, addEventListener() {}};
global.history = {replaceState() {}}; global.alert = () => {}; global.confirm = () => true;
global.fetch = async (url) => {
  const chave = Object.keys(respostas).find((k) => url.startsWith(k));
  if (!chave) throw new Error('URL inesperada: ' + url);
  return {ok: true, status: 200, json: async () => respostas[chave]};
};
eval(fs.readFileSync(process.argv[3], 'utf8'));
const fim = Date.now() + 3000;
(function espera() {
  const pronto = els.lb_pai.textContent.startsWith('OS 9812') && els.lb_resumo.textContent &&
                 els.lb_resumo.textContent !== R.dataset.semPrevia;       // a prévia chega em segundo plano
  if (pronto || Date.now() > fim) {
    console.log(JSON.stringify({cli: els.cb_cli.value, usi: els.cb_usi.value, tipo: els.cb_tipo.value, ativo: els.cb_ativo.value,
      marca: els.cb_marca.value, resp: els.cb_resp.value, inc: els.dt_inc.value, prog: els.dt_prog.value,
      pai: els.lb_pai.textContent, resumo: els.lb_resumo.textContent, hist_visivel: !els.b_hist.hidden}));
  } else setTimeout(espera, 10);
})();
"""


def test_abrir_chamado_preenche_ativo_data_e_responsavel_no_js(tmp_path):
    """O pedido do Levi, ponta a ponta no JS: a tela aberta com ?pai=9812 termina com a cascata inteira no ativo da OS,
    a marca sugerida, a data do incidente e o responsável dela."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    cat = iw.catalogo(_cat())
    pai = iw.herdar_do_pai({"folio": 9812, "descricao": "Religamento", "event_date": "2026-09-20T11:30:00",
                            "responsavel": "Pedro Beta", "code": "BAR-INV1", "id_work_order": 501}, PESSOAS, AGORA)
    pai["ativo"] = iw.cascata(cat[0])
    pai["aviso_ativo"] = ""
    respostas = {
        "/os/api/insp/catalogo?cliente=": {"usinas": iw.usinas(cat, "Acme")},
        "/os/api/insp/catalogo?usina=": {"tipos": iw.tipos(cat, "Alfa"), "ativos": iw.ativos(cat, "Alfa")},
        "/os/api/insp/catalogo": {"clientes": iw.clientes(cat)},
        "/os/api/responsaveis": {"pessoas": PESSOAS},
        "/os/api/insp/pai": pai,
        "/os/api/insp/marcas": iw.marcas(cat[0], "Inversor", cat),
        "/os/api/insp/subtarefas": iw.previa("Inversor", "Huawei"),
        "/os/api/insp/ultimas-os": {"linhas": []},
    }
    (tmp_path / "resp.json").write_text(json.dumps(respostas, ensure_ascii=False, default=str), encoding="utf-8")
    (tmp_path / "h.js").write_text(_HARNESS, encoding="utf-8")
    r = subprocess.run([node, str(tmp_path / "h.js"), str(tmp_path / "resp.json"), os.path.join(_WEB, "static", "insp.js")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out == dict(out, cli="Acme", usi="Alfa", tipo="Inversor", ativo="1", marca="Huawei", resp="20",
                       inc="2026-09-20T08:30", prog="2026-09-28T08:00", hist_visivel=True), out
    assert out["pai"].startswith("OS 9812 · Religamento  ·  herdado: incidente 20/09/2026 08:30")
    assert out["resumo"] == ci.resumo("Inversor", "Huawei")

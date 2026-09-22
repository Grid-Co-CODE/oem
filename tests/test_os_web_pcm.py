# tests/test_os_web_pcm.py
"""PCM na web (o card "PCM" do lançador — NÃO a aba "Solicitação / PCM"): a mesma tela da `PcmTab` (steps/pcm.py) —
cascata Cliente → Usina → Tipo, ativos marcáveis, família do plano + "Carregar planos" (api.get_plans_for_assets +
api.get_subtask_counts), data/hora por linha com a programação em massa, observação, "Requerido por" e OS pai.
A escrita é `api.create_planned_os_multi` (com plano) ou `api.create_os_sem_plano` (sem plano), com os MESMOS
argumentos que o `_criar`/`_criar_sem_plano` do app montam. A API do Fracttal é um dublê: o que se testa é o contrato."""
# ESPECIFICACAO ADIANTADA: este arquivo descreve a tela ANTES de ela existir, e o modulo que ele
# importa ainda nao foi escrito. Sem o `importorskip` o pytest nem CHEGA a coletar a bateria — um
# ImportError na coleta derruba a suite inteira, e nao so este arquivo. Enquanto o modulo nao
# nascer, os testes ficam como "skipped" (visiveis, contados, na fila); no dia em que ele nascer,
# passam a valer sozinhos, sem ninguem lembrar de reativa-los.
import pytest as _pytest

_pytest.importorskip("os_web.pcm_web", reason="a tela PCM (OS planejada por familia de plano) ainda nao foi portada para a web")

import datetime as dt
import os

import pytest

import api
import os_web
from os_web import criar_app, pcm_web

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
BRT = dt.timezone(dt.timedelta(hours=-3))

# registros como o catálogo (`api._build_records`) devolve; id_group_task é o que o get_plans_for_assets usa
CATALOGO = [
    {"id": 11, "code": "TNB200-INVR2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "description": "Inversor 2.18",
     "tipo": "Inversor", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_group_task": 9},
    {"id": 12, "code": "TNB200-INVR2.19", "label": "TNB200-INVR2.19 — Inversor 2.19", "description": "Inversor 2.19",
     "tipo": "Inversor", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_group_task": 9},
    {"id": 13, "code": "TNB200-ESTM1", "label": "TNB200-ESTM1 — Estação Meteorológica", "description": "Estação Meteorológica",
     "tipo": "Estação Meteorológica", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_group_task": 9},
    {"id": 14, "code": "TNB200-TRK", "label": "TNB200-TRK — Estrutura Trackers", "description": "Estrutura Trackers",
     "tipo": "Estrutura Trackers", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_group_task": 9},
    {"id": 15, "code": "TNB200-TRK5.100", "label": "TNB200-TRK5.100 — Tracker 5.100", "description": "Tracker 5.100",
     "tipo": "Estrutura Trackers", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_group_task": 9},
    {"id": 16, "code": "TNB200-X", "label": "TNB200-X — sem tipo", "description": "sem tipo",
     "tipo": "", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP"},
    {"id": 21, "code": "TNB100-INVR1.1", "label": "TNB100-INVR1.1 — Inversor 1.1", "description": "Inversor 1.1",
     "tipo": "Inversor", "cliente": "Thopen", "usina": "Thopen - Tanabi 1 - SP", "id_group_task": 9},
    {"id": 33, "code": "ARA100-INVR1.1", "label": "ARA100-INVR1.1 — Inversor 1.1", "description": "Inversor 1.1",
     "tipo": "Inversor", "cliente": "2C", "usina": "2C - Araputanga 1 - MT", "id_group_task": 9},
]
PESSOAS = [{"code": "LM", "name": "Levi Maia", "id_personnel": 77}, {"code": "AP", "name": "Ana Patrícia", "id_personnel": 88}]


def _plano(idt, desc, fam, asset):
    return {"id_task": idt, "description": desc, "family": fam, "asset": asset, "asset_label": asset["label"]}


# o que `api.get_plans_for_assets` devolve para os ativos 11 e 12 (o 905 é PERFORMANCE: o PCM esconde essa família)
PLANOS = [
    _plano(901, "MPM - Manutenção preventiva mensal", "MPM", CATALOGO[0]),
    _plano(902, "[Grid Co.] MPM - Preventiva mensal do inversor", "MPM", CATALOGO[0]),
    _plano(903, "MPA - Preventiva anual", "MPA", CATALOGO[0]),
    _plano(904, "Handover - Recebimento", "Handover", CATALOGO[0]),
    _plano(905, "PERFORMANCE - Recomposição de String", "PERFORMANCE", CATALOGO[0]),
    _plano(906, "MPM - Preventiva mensal", "MPM", CATALOGO[1]),
]


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"})
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: CATALOGO)
    monkeypatch.setattr(api, "get_responsaveis", lambda: PESSOAS)
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


# ── a tela ────────────────────────────────────────────────────────────────────
def test_a_tela_tem_a_estrutura_da_pcmtab_do_app(cli):
    html = cli.get("/os/pcm").get_data(as_text=True)
    # Card 1 Ativo → Card 2 Plano de tarefas → Card 3 Detalhes e responsável → botão, com os rótulos do steps/pcm.py
    for txt in ("PCM — OS por plano de tarefas", "Ativo", "Cliente", "Usina", "Tipo de equipamento", "Filtrar ativo por código ou nome…",
                "— Selecione o cliente —", "— Selecione a usina —", "Todos os tipos",
                "Plano de tarefas", "Sem plano de tarefas", "Descrição da tarefa", "opcional (vale p/ todas) — vazio = 'Procedimento'",
                "Família do plano", "(carregue os planos)", "Carregar planos", "Só com plano", "Selecionar todos", "Limpar",
                "Ativos", "(marque um ou vários — o plano aparece após carregar)",
                "Plano de tarefa", "Subt.", "Data/hora programada", "0 marcado(s)",
                "Programação em massa", "(aplica a todas as linhas marcadas)", "Aplicar data", "Manhã (07:00)", "Tarde (13:00)", "Avançar 1 mês",
                "Detalhes e responsável", "Observação", "(opcional)", "Requerido por", "(digite p/ pesquisar)", "Recarregar responsáveis",
                "Ela depende de outra OS?", "(opcional — OS pai)", "Selecione a OS pai (nº) — opcional", "Criar OS (PCM)"):
        assert txt in html, txt
    # as dicas (tooltips) do app viram title
    assert 'title="Marca apenas os ativos que têm plano nesta família (desmarca os demais)"' in html
    assert 'title="Define a DATA (dia/mês/ano) de todas as linhas; mantém o horário de cada uma"' in html
    # clientes: TODOS os que têm o campo (o PCM não filtra por carteira, diferente da Performance), ordenados
    assert "<option>2C</option>" in html and "<option>Thopen</option>" in html
    assert html.index("<option>2C</option>") < html.index("<option>Thopen</option>")
    assert 'href="/os/static/pcm.css"' in html and 'src="/os/static/pcm.js"' in html
    assert "alert(" not in html


def test_js_tem_as_frases_do_app_confirma_antes_de_criar_e_nao_usa_alert():
    js = open(os.path.join(os.path.dirname(os_web.__file__), "static", "pcm.js"), encoding="utf-8").read()
    assert "confirm(" in js and "alert(" not in js
    for frase in ("Vou criar UMA OS com ", "tarefa(s) — uma por ativo marcado.", "Ficam de FORA (sem plano nesta família):",
                  "SEM plano — uma por ativo, subtarefa 'Procedimento'", "Marque ao menos um ativo primeiro.",
                  "Carregue os planos primeiro (marque os ativos → Carregar planos).", "Carregue os planos e marque ao menos um ativo com plano.",
                  "Marque ao menos um ativo.", "Escolha o responsável.", "clique em “Carregar planos”", "— sem plano nesta família —",
                  "Procedimento  (sem plano de tarefas)", "Nenhum plano encontrado p/ os ativos marcados.", "com plano", "SEM plano nesta família",
                  "(todas)", "— selecione —", "T08:00", "07:00", "13:00"):
        assert frase in js, frase


# ── cascata e ativos (espelho de _fill_clientes / _on_cli / _on_usi / _refresh) ──
def test_cascata_cliente_usina_tipo_e_ativos_como_o_app(cli):
    assert cli.get("/os/api/pcm/usinas?cliente=Thopen").get_json()["usinas"] == ["Thopen - Tanabi 1 - SP", "Thopen - Tanabi 2 - SP"]
    assert cli.get("/os/api/pcm/usinas").get_json()["usinas"] == []                  # sem cliente, sem usina (a cascata do app)
    j = cli.get("/os/api/pcm/ativos?cliente=Thopen&usina=Thopen - Tanabi 2 - SP").get_json()
    # PCM: SEM restrição de tipo — todos os tipos da usina (o 16, sem tipo, não conta)
    assert j["tipos"] == ["Estação Meteorológica", "Estrutura Trackers", "Inversor"]
    # o 15 (tracker individual) fica de fora: em Estrutura Trackers só entra o ativo generalizado; o 16 não tem tipo
    assert [a["id"] for a in j["ativos"]] == [11, 12, 13, 14]
    assert j["ativos"][0] == {"id": 11, "code": "TNB200-INVR2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "tipo": "Inversor"}
    assert cli.get("/os/api/pcm/ativos?cliente=Thopen&usina=").get_json()["ativos"] == []


def test_carregar_planos_chama_get_plans_e_get_subtask_counts_como_o_app(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "get_plans_for_assets", lambda assets: visto.update(assets=assets) or PLANOS)
    monkeypatch.setattr(api, "get_subtask_counts", lambda pares: visto.update(pares=pares) or {904: 7})
    j = cli.get("/os/api/pcm/planos?ativos=11,12,999").get_json()
    # o app manda o registro INTEIRO do catálogo (id_group_task vai junto); o 999 não existe e cai fora
    assert [a["id"] for a in visto["assets"]] == [11, 12] and visto["assets"][0] is CATALOGO[0]
    assert j["familias"] == ["Handover", "MPM", "MPA"]                 # _FAM_ORDER; PERFORMANCE fica de fora (performance=False)
    assert j["n_planos"] == 5
    assert [p["id_task"] for p in j["por_ativo"]["11"]] == [901, 902, 903, 904]
    assert [p["id_task"] for p in j["por_ativo"]["12"]] == [906]
    assert "asset" not in j["por_ativo"]["11"][0]                      # a tela não precisa do ativo repetido em cada plano
    # contagens: a família inicial é a PRIMEIRA (o app seleciona o índice 1); o 12 não tem plano nela → só o 11
    assert visto["pares"] == [(904, 11)]
    assert j["subt"] == {"904": 7}
    # com a família pedida: o plano padrão é o "[Grid Co.]" quando há mais de um (a regra do _fill_row)
    j = cli.get("/os/api/pcm/planos?ativos=11,12&familia=MPM").get_json()
    assert visto["pares"] == [(902, 11), (906, 12)]
    # sob demanda (o _fetch_counts_visiveis quando a pessoa troca o plano de uma linha)
    monkeypatch.setattr(api, "get_subtask_counts", lambda pares: visto.update(pares=pares) or {901: 3})
    j = cli.get("/os/api/pcm/subtarefas?pares=901:11, 906:12,lixo,7").get_json()
    assert visto["pares"] == [(901, 11), (906, 12)] and j["subt"] == {"901": 3}
    r = cli.get("/os/api/pcm/planos?ativos=")
    assert r.status_code == 400 and r.get_json()["erro"] == "Marque ao menos um ativo primeiro."


# ── criar (espelho de _criar / _criar_sem_plano / _criou) ─────────────────────
def test_criar_com_plano_chama_create_planned_os_multi_como_o_app(cli, monkeypatch):
    visto = {}
    def _criar(selecoes, id_responsible, responsible_name="", event_date=None, id_parent=None):
        visto.update(sel=selecoes, idp=id_responsible, nome=responsible_name, evt=event_date, id_parent=id_parent)
        return {"ok": True, "os": {"id_work_order": 900, "wo_folio": 12345, "id_tasks": [1, 2]}, "n_tarefas": 2, "n_criadas": 2,
                "erros": ["TNB200-INVR2.19: plano sem subtarefas"], "aviso": ""}
    monkeypatch.setattr(api, "create_planned_os_multi", _criar)
    monkeypatch.setattr(api, "create_os_sem_plano", lambda *a, **k: pytest.fail("com plano não passa pelo caminho sem plano"))
    corpo = {"sem_plano": False,
             "selecoes": [{"asset_id": 11, "id_task": 902, "event_date": "2026-09-15T07:00"},
                          {"asset_id": 12, "id_task": 906, "event_date": "2026-10-15T13:00"},
                          {"asset_id": 13, "id_task": None, "event_date": "2026-09-15T08:00"}],   # sem plano nesta família: fica de fora
             "responsavel": {"id_personnel": 77, "name": "Levi Maia"}, "descricao": "",
             "note": "observação que o app NÃO manda no caminho com plano", "id_parent": 4321}
    r = cli.post("/os/api/pcm/criar", json=corpo)
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j["ok"] and j["mensagem"].startswith("OS criada — Nº 12345 com 2 tarefa(s).")
    assert "Algumas tarefas falharam:\n- TNB200-INVR2.19: plano sem subtarefas" in j["mensagem"]
    assert j["id_work_order"] == 900 and j["folio"] == 12345
    # o payload do `_criar` do app: [{asset, id_task, event_date}], id_personnel, name, event_date geral None, id_parent
    assert len(visto["sel"]) == 2
    assert visto["sel"][0]["asset"] is CATALOGO[0] and visto["sel"][0]["id_task"] == 902
    assert visto["sel"][0]["event_date"] == dt.datetime(2026, 9, 15, 7, 0, tzinfo=BRT)        # Brasília, como o app
    assert visto["sel"][1]["asset"] is CATALOGO[1] and visto["sel"][1]["id_task"] == 906
    assert visto["sel"][1]["event_date"] == dt.datetime(2026, 10, 15, 13, 0, tzinfo=BRT)
    assert (visto["idp"], visto["nome"], visto["evt"], visto["id_parent"]) == (77, "Levi Maia", None, 4321)


def test_criar_sem_plano_chama_create_os_sem_plano_como_o_app(cli, monkeypatch):
    visto = {}
    def _criar(selecoes, id_responsible, responsible_name="", descricao="", note="", tipo_task="Corretiva", id_parent=None):
        visto.update(sel=selecoes, idp=id_responsible, nome=responsible_name, desc=descricao, note=note, tipo=tipo_task, id_parent=id_parent)
        return {"ok": True, "os": {"id_work_order": 901, "wo_folio": 12346}, "n_tarefas": 2, "n_criadas": 2, "erros": [],
                "aviso": "tarefas criadas; não gerei a OS numerada (x)."}
    monkeypatch.setattr(api, "create_os_sem_plano", _criar)
    monkeypatch.setattr(api, "create_planned_os_multi", lambda *a, **k: pytest.fail("sem plano não passa pelo caminho com plano"))
    corpo = {"sem_plano": True,
             "selecoes": [{"asset_id": 11, "event_date": "2026-09-15T08:00"}, {"asset_id": 33, "event_date": "2026-09-16T13:00"}],
             "responsavel": {"id_personnel": 88, "name": "Ana Patrícia"}, "descricao": "  Limpeza dos módulos  ", "note": "  obs geral  ",
             "id_parent": None}
    r = cli.post("/os/api/pcm/criar", json=corpo)
    j = r.get_json()
    assert r.status_code == 200 and j["ok"]
    assert j["mensagem"] == "OS criada — Nº 12346 com 2 tarefa(s).\n\nObs.: tarefas criadas; não gerei a OS numerada (x)."
    assert [s["asset"]["id"] for s in visto["sel"]] == [11, 33] and all("id_task" not in s for s in visto["sel"])
    assert visto["sel"][1]["event_date"] == dt.datetime(2026, 9, 16, 13, 0, tzinfo=BRT)
    # descrição e observação com .strip(), como o app; tipo_task não é mexido (fica o padrão Corretiva)
    assert (visto["idp"], visto["nome"], visto["desc"], visto["note"]) == (88, "Ana Patrícia", "Limpeza dos módulos", "obs geral")
    assert visto["tipo"] == "Corretiva" and visto["id_parent"] is None


def test_validacoes_com_as_frases_do_app_e_nada_chega_na_api(cli, monkeypatch):
    monkeypatch.setattr(api, "create_planned_os_multi", lambda *a, **k: pytest.fail("não podia chamar a API"))
    monkeypatch.setattr(api, "create_os_sem_plano", lambda *a, **k: pytest.fail("não podia chamar a API"))
    resp = {"id_personnel": 77, "name": "Levi Maia"}
    r = cli.post("/os/api/pcm/criar", json={"sem_plano": False, "selecoes": [], "responsavel": resp})
    assert r.status_code == 400 and r.get_json()["erro"] == "Carregue os planos e marque ao menos um ativo com plano."
    r = cli.post("/os/api/pcm/criar", json={"sem_plano": False, "selecoes": [{"asset_id": 11, "id_task": None}], "responsavel": resp})
    assert r.status_code == 400 and r.get_json()["erro"] == "Carregue os planos e marque ao menos um ativo com plano."
    r = cli.post("/os/api/pcm/criar", json={"sem_plano": True, "selecoes": [], "responsavel": resp})
    assert r.status_code == 400 and r.get_json()["erro"] == "Marque ao menos um ativo."
    r = cli.post("/os/api/pcm/criar", json={"sem_plano": True, "selecoes": [{"asset_id": 999}], "responsavel": resp})
    assert r.status_code == 400 and r.get_json()["erro"] == "Marque ao menos um ativo."          # fora do catálogo não vira tarefa
    r = cli.post("/os/api/pcm/criar", json={"sem_plano": False, "selecoes": [{"asset_id": 11, "id_task": 902}], "responsavel": {}})
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o responsável."
    r = cli.post("/os/api/pcm/criar", json={"sem_plano": False, "selecoes": [{"asset_id": 11, "id_task": 902, "event_date": "ontem"}], "responsavel": resp})
    assert r.status_code == 400 and r.get_json()["erro"] == "Data inválida."


def test_falha_do_fracttal_vira_a_frase_do_app_e_nao_500(cli, monkeypatch):
    monkeypatch.setattr(api, "create_planned_os_multi",
                        lambda *a, **k: {"ok": False, "erro": "Falha ao criar as tarefas: x", "n_tarefas": 1, "n_criadas": 0})
    r = cli.post("/os/api/pcm/criar", json={"selecoes": [{"asset_id": 11, "id_task": 902}], "responsavel": {"id_personnel": 77, "name": "L"}})
    assert r.status_code == 200 and r.get_json() == {"ok": False, "mensagem": "Falha ao criar as tarefas: x"}
    assert pcm_web.mensagem_resultado({"ok": False})["mensagem"] == "Falha ao criar a OS planejada."
    assert pcm_web.mensagem_resultado(None)["mensagem"] == "Falha ao criar a OS planejada."


# ── OS pai (o OsPaiPicker) e sessão ──────────────────────────────────────────
def test_os_pai_busca_pelo_numero_como_o_picker_do_app(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "buscar_os_pai", lambda termo="", limit=50: visto.update(termo=termo) or
                        [{"id": 555, "folio": "9812", "descricao": "Troca de string", "responsavel": "Levi", "data": "12/09/2026", "criada": ""}])
    j = cli.get("/os/api/pcm/os-pai?termo=98").get_json()
    assert visto["termo"] == "98" and j["resultados"][0]["id"] == 555 and j["resultados"][0]["folio"] == "9812"
    assert cli.get("/os/api/pcm/os-pai?termo=").get_json() == {"resultados": []}        # vazio não busca (o _buscar do picker)


def test_sem_sessao_a_api_pede_login_e_a_tela_redireciona(monkeypatch):
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: CATALOGO)
    c = criar_app(segredo="teste", testing=True).test_client()
    r = c.get("/os/api/pcm/ativos?usina=x")
    assert r.status_code == 401 and r.get_json()["login"] is True
    assert c.get("/os/pcm").status_code == 302


# ── helper puro (as regras do _fill_row / _set_planos, sem Flask) ────────────
def test_helper_puro_regras_do_fill_row_e_do_set_planos():
    por_ativo, familias = pcm_web.indexar(pcm_web.so_pcm(PLANOS))
    assert familias == ["Handover", "MPM", "MPA"]
    assert pcm_web.plano_padrao(por_ativo[11], "MPM") == 902           # "[Grid Co.]" ganha do alfabético
    assert pcm_web.plano_padrao(por_ativo[11], "MPA") == 903
    assert pcm_web.plano_padrao(por_ativo[11], "MPS") is None          # sem plano nesta família
    assert pcm_web.plano_padrao(por_ativo[11], None) == 902            # "(todas)": qualquer família, ainda prefere o Grid
    assert pcm_web.familias_ordenadas({"MPT", "XPTO", "MPM", "Handover"}) == ["Handover", "MPM", "MPT", "XPTO"]
    assert pcm_web.familia_inicial(None, familias) == "Handover" and pcm_web.familia_inicial("MPA", familias) == "MPA"
    assert pcm_web.familia_inicial("todas", familias) is None and pcm_web.familia_inicial("XPTO", familias) == "Handover"
    assert pcm_web.parse_pares("901:11, 906:12,lixo,7") == [(901, 11), (906, 12)]
    assert pcm_web.parse_ids("11, 12,x,11") == [11, 12]

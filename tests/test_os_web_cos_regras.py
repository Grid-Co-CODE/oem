# tests/test_os_web_cos_regras.py
"""COS na web — o que a especificação adiantada (tests/test_os_web_cos.py) não cobre porque só existe na web.

No app de mesa estes estados são impossíveis: o QDateTimeEdit trava o evento no passado (`travar_no_passado`), o
`_on_prot` não deixa código e "Sem trip" juntos, o combo só guarda opção da lista e o `_codigos` lê os chips na ordem da
grade. Na web o pedido pode chegar de qualquer jeito — e o que não passaria pela tela do app não pode virar OS. Também
ficam aqui a prévia e a cascata por POST (o jeito que a tela usa, para os ids marcados não irem na URL) e a guarda do
clonador contra OS sem código de ativo. Dados fictícios: o repositório é público."""
import datetime as dt
import json

import pytest

import api
from os_web import cos_web, criar_app

JWT = "aaa.eyJlbWFpbCI6InBlc3NvYUBleGVtcGxvLmNvbSIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # {"email": "pessoa@exemplo.com"}
BRT = dt.timezone(dt.timedelta(hours=-3))
UM, DOIS = "Alfa - Usina Um - XX", "Alfa - Usina Dois - XX"
ASSETS = [
    {"id": 1, "code": "AUM100-INVR1.1", "description": "Inversor 1.1", "label": "AUM100-INVR1.1 — Inversor 1.1", "tipo": "Inversor",
     "cliente": "Alfa", "usina": UM, "id_parent": 5, "id_type_item": 2, "id_group_task": 9},
    {"id": 2, "code": "AUM100-INVR1.2", "description": "Inversor 1.2", "label": "AUM100-INVR1.2 — Inversor 1.2", "tipo": "Inversor",
     "cliente": "Alfa", "usina": UM, "id_parent": 5, "id_type_item": 2, "id_group_task": 9},
    {"id": 3, "code": "ADO100-INVR1.1", "description": "Inversor 1.1", "label": "ADO100-INVR1.1 — Inversor 1.1", "tipo": "Inversor",
     "cliente": "Alfa", "usina": DOIS, "id_parent": 6, "id_type_item": 2, "id_group_task": 9},
    {"id": 4, "code": "", "description": "Registro sem código", "label": "Registro sem código", "tipo": "Inversor",
     "cliente": "Alfa", "usina": UM},
]
CLASSIF = {"tipos": [{"id": 101, "description": "Religamento Remoto"}, {"id": 102, "description": "Religamento"},
                     {"id": 103, "description": "Corretiva Emergencial"}, {"id": 104, "description": "Corretiva"}],
           "c1": [{"id": 201, "description": "Religamento"}, {"id": 202, "description": "Emergencial"}],
           "c2": [{"id": 301, "description": "Elétrica"}]}
FALHAS = {"tipos": [{"id": 1, "description": "Desligamento"}], "causas": [{"id": 11, "description": "Queda de energia"}],
          "metodos": [{"id": 21, "description": "Monitoramento de Condição Online (MCO)"}]}
PESSOA = {"code": "P1", "name": "Pessoa Um", "id_personnel": 501}


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: ASSETS)
    monkeypatch.setattr(api, "get_tipos_classif", lambda: CLASSIF)
    monkeypatch.setattr(api, "get_falha_listas", lambda: FALHAS)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Um", "email": "pessoa@exemplo.com", "perfil": ""}
    return c


def _corpo(**k):
    base = {"tipo": 0, "cat": "A", "remoto": True, "modo": 0, "codigos": ["27"], "onde": "Disjuntor Geral", "obs": "", "ids": [1],
            "terceiros": False, "cliente": "", "usina": "", "ovr": {}, "realizada": True, "em_verificacao": False,
            "responsavel": PESSOA, "falha": {"marcado": False}, "evento": "2026-09-12T14:00", "conclusao": "2026-09-12T14:10",
            "datas": []}
    base.update(k)
    return base


def _post(cli, url, corpo):
    return cli.post(url, data=json.dumps(corpo), content_type="application/json")


def _nada_no_fracttal(monkeypatch):
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda *a, **k: pytest.fail("escreveu no Fracttal"))
    monkeypatch.setattr(api, "create_work_orders_datas", lambda *a, **k: pytest.fail("escreveu no Fracttal"))


def _gravar(monkeypatch, nome):
    visto = {}
    monkeypatch.setattr(api, nome, lambda *a, **k: visto.update(args=a, kwargs=k) or [])
    return visto


# ── a prévia e a cascata por POST dizem o mesmo que por GET ────────────────────────────────────────────────────────
def test_previa_por_post_e_a_mesma_da_query(cli):
    get = cli.get("/os/api/cos/preview?tipo=0&cat=A&remoto=1&codigos=27&codigos=59&onde=Inversor&ids=1,2&obs=nota&realizada=0").get_json()
    post = _post(cli, "/os/api/cos/preview", _corpo(codigos=["27", "59"], onde="Inversor", ids=[1, 2], obs="nota", realizada=False)).get_json()
    assert post == get
    assert post["titulo"].endswith("(cada OS usa o seu ativo)") and post["observacao"].endswith("\nnota")


def test_ativos_por_post_podam_os_marcados_como_o_on_usi(cli):
    """O marcado é sempre um subconjunto do que a tabela pode mostrar: trocar de usina tira o da outra."""
    j = _post(cli, "/os/api/cos/ativos", {"usina": UM, "cliente": "", "multi": False, "marcados": [1, 3]}).get_json()
    assert j["cliente"] == "Alfa" and j["marcados"] == [1] and [a["id"] for a in j["ativos"]] == [1, 2, 4]
    j = _post(cli, "/os/api/cos/ativos", {"usina": UM, "cliente": "Alfa", "multi": True, "marcados": [1, 3]}).get_json()
    assert j["marcados"] == [1, 3] and {a["usina"] for a in j["ativos"]} == {UM, DOIS}   # várias usinas: os dois ficam
    assert j == cli.get("/os/api/cos/ativos?usina=%s&cliente=Alfa&multi=1&marcados=1,3" % UM).get_json()


# ── o que a tela do app não deixa acontecer ────────────────────────────────────────────────────────────────────────
def test_a_ordem_das_protecoes_e_a_da_grade_e_nao_a_do_clique(cli, monkeypatch):
    visto = _gravar(monkeypatch, "create_work_orders_bulk")
    assert _post(cli, "/os/api/cos/criar", _corpo(codigos=["59", "27", "59"])).status_code == 200
    assert visto["args"][15]["AUM100-INVR1.1"]["note"].startswith("UFV: Usina Um | Proteção: 27 e 59 |")
    assert visto["args"][11]["respostas"][0] == "Proteção atuou — 27 e 59"


def test_evento_no_futuro_nao_vira_os(cli, monkeypatch):
    _nada_no_fracttal(monkeypatch)
    amanha = (dt.datetime.now(BRT) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    r = _post(cli, "/os/api/cos/criar", _corpo(evento=amanha, conclusao=amanha))
    assert r.status_code == 400 and r.get_json()["erro"] == cos_web.ERRO_FUTURO
    r = _post(cli, "/os/api/cos/criar", _corpo(modo=1, datas=[{"evento": amanha, "conclusao": amanha}]))
    assert r.status_code == 400 and r.get_json()["erro"] == cos_web.ERRO_FUTURO


def test_folga_para_o_relogio_do_navegador_adiantado():
    """Quem lança "agora" num PC com o relógio alguns minutos na frente não é barrado (a folga do Tradicional)."""
    agora = dt.datetime(2026, 9, 12, 14, 0, tzinfo=BRT)
    base = dict(assets=ASSETS, classif=CLASSIF, falhas={})
    trilho, _args, erro = cos_web.criacao(_corpo(evento="2026-09-12T14:05", conclusao="2026-09-12T14:06"), agora=agora, **base)
    assert (trilho, erro) == (cos_web.TRILHO_BULK, "")
    assert cos_web.criacao(_corpo(evento="2026-09-12T14:30", conclusao="2026-09-12T14:40"), agora=agora, **base)[2] == cos_web.ERRO_FUTURO


def test_codigo_e_sem_trip_juntos_nao_viram_os(cli, monkeypatch):
    _nada_no_fracttal(monkeypatch)
    r = _post(cli, "/os/api/cos/criar", _corpo(codigos=["27", cos_web.cs.SEM_TRIP]))
    assert r.status_code == 400 and r.get_json()["erro"] == cos_web.ERRO_SEM_TRIP_JUNTO


@pytest.mark.parametrize("campo, valor", [("onde", "Transformador"), ("cat", "D"), ("tipo", 7), ("modo", "x")])
def test_valor_fora_das_opcoes_da_tela_e_recusado(cli, monkeypatch, campo, valor):
    _nada_no_fracttal(monkeypatch)
    r = _post(cli, "/os/api/cos/criar", _corpo(**{campo: valor}))
    assert r.status_code == 400 and "inválid" in r.get_json()["erro"]
    assert _post(cli, "/os/api/cos/preview", _corpo(**{campo: valor})).status_code == 400


def test_combo_de_outra_categoria_nao_e_lido(cli, monkeypatch):
    """O app só lê o combo da categoria ativa: na A, uma falha B qualquer não barra nem entra na OS."""
    visto = _gravar(monkeypatch, "create_work_orders_bulk")
    assert _post(cli, "/os/api/cos/criar", _corpo(falha_b="qualquer coisa", causa_c="outra")).status_code == 200
    assert "qualquer" not in visto["args"][15]["AUM100-INVR1.1"]["note"]


def test_bloco_de_falha_resolve_os_ids_do_select_e_barra_o_que_nao_existe(cli, monkeypatch):
    visto = _gravar(monkeypatch, "create_work_orders_bulk")
    falha = {"marcado": True, "id_type": "1", "id_cause": "11", "id_detection": "21", "id_severity": "4", "id_damage": "3"}
    assert _post(cli, "/os/api/cos/criar", _corpo(falha=falha)).status_code == 200
    f = visto["args"][16]
    assert (f["id_type"], f["id_cause"], f["id_detection"]) == (1, 11, 21)                 # o id da lista, não o texto
    assert (f["id_severity"], f["severity_desc"], f["id_damage"], f["damage_desc"]) == ("4", "Alto", 3, "Danos nas Instalações")
    _nada_no_fracttal(monkeypatch)
    r = _post(cli, "/os/api/cos/criar", _corpo(falha=dict(falha, id_type="999")))
    assert r.status_code == 400 and r.get_json()["erro"] == cos_web.ERRO_FALHA
    r = _post(cli, "/os/api/cos/criar", _corpo(falha=dict(falha, id_severity="9")))
    assert r.status_code == 400 and r.get_json()["erro"] == cos_web.ERRO_SEV_DANO


def test_inspecao_ja_realizada_responde_so_o_equipamento_e_sintoma(cli, monkeypatch):
    visto = _gravar(monkeypatch, "create_work_orders_bulk")
    r = _post(cli, "/os/api/cos/criar", _corpo(tipo=1, cat="C", remoto=False, causa_c="Falta de internet"))
    assert r.status_code == 200
    assert visto["args"][11]["respostas"] == ["Usina ligada, mas em falha de comunicação devido falta de internet.", "", "", ""]


def test_erro_que_nao_e_do_fracttal_vira_502_em_json(cli, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("conexão caiu no meio")
    monkeypatch.setattr(api, "create_work_orders_bulk", _boom)
    r = _post(cli, "/os/api/cos/criar", _corpo())
    assert r.status_code == 502 and r.get_json() == {"erro": "conexão caiu no meio"}


# ── o clonador ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_clone_de_os_sem_codigo_nao_escolhe_ativo_nenhum(cli, monkeypatch):
    """O `next(...)` do app, com o código vazio, pegaria o primeiro registro do catálogo que também não tem código."""
    os_ = {"folio": 70, "descricao": "[Inversor 1.1] - Religamento do Inversor 1.1", "code": "",
           "notas": "UFV: Usina Um | Proteção: 27 | Ação: Religamento Remoto | Falha: Inversor desligado, relé com proteções 27 ativas."}
    monkeypatch.setattr(api, "get_os_detalhes_por_folio", lambda folio: os_)
    j = cli.get("/os/api/cos/os-modelo?folio=70").get_json()
    assert j["ativo"] is None and (j["cat"], j["codigos"], j["remoto"]) == ("A", ["27"], True)


def test_clone_devolve_a_carteira_pelo_prefixo_da_usina(cli, monkeypatch):
    os_ = {"folio": 71, "descricao": "[Inversor 1.1] - Religamento do Inversor 1.1", "code": "ADO100-INVR1.1",
           "notas": 'UFV: Usina Dois | Proteção: --/-- | Ação: Religamento Local | Falha: Inversor 1.1 desligado devido a falha: "Outro erro".'}
    monkeypatch.setattr(api, "get_os_detalhes_por_folio", lambda folio: os_)
    j = cli.get("/os/api/cos/os-modelo?folio=71").get_json()
    assert (j["cat"], j["falha_b"], j["remoto"], j["ativo"]["id"], j["ativo"]["carteira"]) == ("B", "Outro erro", False, 3, "Alfa")


# ── a página ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_pagina_abre_com_a_previa_do_estado_inicial_ja_montada(cli):
    html = cli.get("/os/cos").get_data(as_text=True)
    ini = html.index('id="cos_dados">') + len('id="cos_dados">')
    dados = json.loads(html[ini:html.index("</script>", ini)])
    assert dados["preview"]["titulo"] == "[Disjuntor Geral] - Religamento do Disjuntor Geral"
    assert dados["preview"]["meta"]["tarefa"] == "Religamento Remoto" and dados["sev_padrao"] == "5"
    assert dados["tipo_da_cat"] == {"A": 0, "B": 0, "C": 1}
    assert 'value="Alfa - Usina Um - XX"' in html and "Registro sem código" not in html

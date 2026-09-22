# tests/test_os_web_tradicional.py
"""Card Tradicional na web — Criar OS do zero, passo a passo — com a MESMA lógica do wizard do app (steps/step1.py,
step2.py + tipo_tarefa.py, step3.py e o Step 4 `ResponsavelDialog` do app.py, com finalizar.py e ospai.py).

O que se testa é o contrato da tela: os rótulos são os do app; a cascata Cliente → Usina → Tipo → Ativos segue o Step1
(clientes ocultos, tipo vazio fora); o POST monta o payload IGUAL ao que `ResponsavelDialog._gerar` manda para
`api.create_work_orders_bulk` / `api.create_work_orders_agrupada` (campo a campo); as validações usam as frases do app;
e quando a validação falha NADA chega à API. A API do Fracttal é um dublê que grava o que recebeu."""
import ast
import datetime as dt
import io
import json
import os

import pytest

import api
from os_web import criar_app, tradicional_web as trad

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
BRT = dt.timezone(dt.timedelta(hours=-3))
_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator")

# registros como o catálogo (`api._build_records`) devolve — inclui os campos que o create_os_rpc exige do ativo
ASSETS = [
    {"id": 11, "code": "TNB200-INVR2.18", "description": "Inversor 2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "tipo": "Inversor",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 5, "id_type_item": 1, "id_group_task": 9},
    {"id": 12, "code": "TNB200-INVR2.17", "description": "Inversor 2.17", "label": "TNB200-INVR2.17 — Inversor 2.17", "tipo": "Inversor",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 5, "id_type_item": 1, "id_group_task": 9},
    {"id": 13, "code": "TNB200-ESTM1", "description": "Estação Meteorológica", "label": "TNB200-ESTM1 — Estação Meteorológica",
     "tipo": "Estação Meteorológica", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 5, "id_type_item": 1, "id_group_task": 9},
    {"id": 21, "code": "IBR100-INVR1.1", "description": "Inversor 1.1", "label": "IBR100-INVR1.1 — Inversor 1.1", "tipo": "Inversor",
     "cliente": "Ultragaz", "usina": "Utragaz - Ibirapuã 1 e 2 - BA", "id_parent": 7, "id_type_item": 1, "id_group_task": 9},
    {"id": 31, "code": "ALM-DJ1", "description": "Disjuntor", "label": "ALM-DJ1 — Disjuntor", "tipo": "Disjuntor",
     "cliente": "Almoxarifado", "usina": "Depósito"},
    {"id": 41, "code": "TST-INV1", "description": "Inversor 1", "label": "TST-INV1 — Inversor 1", "tipo": "Inversor",
     "cliente": "TESTE - PA", "usina": "TESTE - PA - Usina 1"},
    {"id": 51, "code": "TNB200-X", "description": "Sem tipo", "label": "TNB200-X — Sem tipo", "tipo": "",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP"},
]

TIPOS = {"tipos": [{"id": 5, "description": "Corretiva"}, {"id": 6, "description": "Inspeção"}, {"id": 9, "description": "Religamento"}],
         "c1": [{"id": 12, "description": "Elétrica"}, {"id": 13, "description": "Mecânica"}],
         "c2": [{"id": 21, "description": "Strings"}]}
LABELS = [{"id": 4660, "description": "PERFORMANCE", "color": "#8fce3f"}, {"id": 12, "description": "CHAMADOS", "color": "#57B6F5"}]

# o corpo que a tela manda quando tudo está preenchido (dois ativos, duas etiquetas, OS pai escolhida)
CORPO = {"ativos": [12, 11], "desc": "Verificar strings sem corrente", "obs": "Levar multímetro",
         "tipo": {"id_main": 5, "desc_main": "Corretiva", "id_priorities": 2, "id_c1": 12, "desc_c1": "Elétrica", "id_c2": None, "desc_c2": ""},
         "etiquetas": [{"id": 4660, "description": "PERFORMANCE"}, {"id": 12, "description": "CHAMADOS"}],
         "subs": ["Medir tensão das strings", "  ", "Fotografar o quadro"],
         "event": "2026-09-12T01:10", "prog": "2026-09-13T08:00",
         "responsavel": {"id_personnel": 1414413, "name": "Levi Maia", "code": "L1"},
         "os_pai": {"id": 400, "folio": "9786"}, "agrupar": False, "finalizar": None}

TIPO_DICT = {"id_main": 5, "id_priorities": 2, "id_c1": 12, "desc_c1": "Elétrica", "id_c2": None, "desc_c2": ""}


def _nunca(*a, **k):
    raise AssertionError("a API do Fracttal não pode ser chamada quando a validação falha")


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: ASSETS)
    monkeypatch.setattr(api, "create_work_orders_bulk", _nunca)
    monkeypatch.setattr(api, "create_work_orders_agrupada", _nunca)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


def _post(cli, corpo):
    return cli.post("/os/api/tradicional/criar", data=json.dumps(corpo), content_type="application/json")


def _dublê_bulk(visto, resposta):
    """A assinatura REAL de `api.create_work_orders_bulk`: grava cada argumento pelo nome, venha posicional ou nomeado."""
    def _bulk(assets, description, task_type, subtasks, etiqueta="", responsible_code="", responsible_name="", id_responsible=None,
              etiqueta_ids=None, note="", tipo=None, finalizar=None, event_date=None, id_parent=None, imagens_por_ativo=None,
              por_ativo=None, falha=None, prog_date=None):
        visto.update(assets=assets, description=description, task_type=task_type, subtasks=subtasks, etiqueta=etiqueta,
                     responsible_code=responsible_code, responsible_name=responsible_name, id_responsible=id_responsible,
                     etiqueta_ids=etiqueta_ids, note=note, tipo=tipo, finalizar=finalizar, event_date=event_date, id_parent=id_parent,
                     imagens_por_ativo=imagens_por_ativo, por_ativo=por_ativo, falha=falha, prog_date=prog_date)
        return resposta
    return _bulk


def _dublê_agrupada(visto, resposta):
    def _agr(assets, description, task_type, subtasks, etiqueta="", responsible_name="", id_responsible=None, etiqueta_ids=None,
             note="", tipo=None, event_date=None, id_parent=None, imagens_por_ativo=None, por_ativo=None, falha=None, prog_date=None):
        visto.update(assets=assets, description=description, task_type=task_type, subtasks=subtasks, etiqueta=etiqueta,
                     responsible_name=responsible_name, id_responsible=id_responsible, etiqueta_ids=etiqueta_ids, note=note, tipo=tipo,
                     event_date=event_date, id_parent=id_parent, imagens_por_ativo=imagens_por_ativo, por_ativo=por_ativo, falha=falha,
                     prog_date=prog_date)
        return resposta
    return _agr


# ── fidelidade com o código do app (ast, sem Qt) ─────────────────────────────────────────────────
def _literal(rel, nome):
    with open(os.path.join(_APP, rel), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == nome for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{nome} não encontrado em {rel}")


def test_constantes_iguais_as_do_app():
    assert trad.STEP_LABELS == _literal("app.py", "STEP_LABELS")                       # "Passo N de 4 · rótulo"
    assert trad.CLIENTES_OCULTOS == _literal("steps/step1.py", "CLIENTES_OCULTOS")     # almoxarifado e ambiente de teste fora
    assert trad.TODOS_USINA == _literal("steps/step1.py", "TODOS_USINA")
    assert trad.TODOS_TIPO == _literal("steps/step1.py", "TODOS_TIPO")
    assert trad.NENHUMA == _literal("steps/tipo_tarefa.py", "_NENHUMA")


# ── a cascata do Step 1, pura ────────────────────────────────────────────────────────────────────
def test_cascata_cliente_usina_tipo_ativos_como_o_step1():
    assert trad.clientes(ASSETS) == ["Thopen", "Ultragaz"]                              # Almoxarifado e TESTE - PA ocultos
    assert trad.usinas_de(ASSETS, "Thopen") == ["Thopen - Tanabi 2 - SP"]
    assert trad.usinas_de(ASSETS, "") == []
    assert trad.tipos_de(ASSETS, "Thopen", "Thopen - Tanabi 2 - SP") == ["Estação Meteorológica", "Inversor"]   # tipo vazio fora
    ativos = trad.ativos_de(ASSETS, "Thopen", "Thopen - Tanabi 2 - SP")
    assert [a["id"] for a in ativos] == [11, 12, 13]                                    # ordem do catálogo; o sem tipo (51) fora
    assert ativos[0] == {"id": 11, "code": "TNB200-INVR2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "tipo": "Inversor"}
    assert [a["id"] for a in trad.ativos_de(ASSETS, "Thopen", "Thopen - Tanabi 2 - SP", tipo="Inversor", busca="2.17")] == [12]
    assert trad.ativos_de(ASSETS, "Thopen", "") == []


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────
def test_tela_abre_com_os_rotulos_e_a_ordem_do_wizard(cli):
    r = cli.get("/os/tradicional")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    # os 4 passos, na ordem (STEP_LABELS do app.py)
    for rot in ("Ativo + Data", "Detalhes da Tarefa", "Sub tarefas", "Responsável"):
        assert rot in html, rot
    assert html.index("Ativo + Data") < html.index("Detalhes da Tarefa") < html.index("Sub tarefas") < html.index("Responsável")
    # barra de clonar (app.py ~310) vira link para a tela de clonagem
    assert "Clonar OS nº" in html and 'placeholder="ex.: 8125"' in html and "/os/clonar" in html
    # Step 1 (steps/step1.py)
    for txt in ("Cliente", "Usina", "Tipo de equipamento", "Refinar por código ou nome…", "— Selecione o cliente —", "— Selecione a usina —",
                "Todos os tipos", "Ativos", "marque um ou vários — no fim você escolhe uma OS por ativo ou uma OS só com várias tarefas; "
                "anexe imagens por ativo", "Anexos", "Selecione cliente e usina para ver os ativos.", "Data do incidente", "(Brasília)",
                "Agora", "Data programada", "(quando executar)", "Recarregar ativos do Fracttal", "Próximo ›››"):
        assert txt in html, txt
    assert "Thopen" in html and "Ultragaz" in html                                      # clientes do catálogo
    assert "TESTE - PA" not in html and "Almoxarifado" not in html                       # CLIENTES_OCULTOS
    # Step 2 (steps/step2.py + tipo_tarefa.py)
    for txt in ("Detalhes da OS", "Descrição da tarefa", "Somente uma ação", "Observação", "Observações da OS (opcional)", "Etiquetas",
                "(opcional — marque as que quiser)", "Classificação", "Tipo de tarefa", "Criticidade", "Classificação 1", "Classificação 2",
                "— nenhuma —", "‹‹‹ Voltar"):
        assert txt in html, txt
    for nome, _ in api.CRITICIDADES:                                                     # 5 níveis, default Médio
        assert nome in html
    assert 'value="3" selected' in html
    # Step 3 (steps/step3.py)
    for txt in ("Subtarefas", "Passos", "(mínimo 1)", "+ Adicionar subtarefa", "Concluir e Gerar OS"):
        assert txt in html, txt
    # Step 4 (app.py::ResponsavelDialog + finalizar.py + ospai.py)
    for txt in ("Filtrar responsável…", "Esta tarefa já foi realizada?", "Enviar para OS:", "Verificação", "Finalizados", "Data inicial",
                "(= evento)", "Data final", "Respostas das subtarefas", "Agrupar em UMA OS com várias tarefas", "Ela depende de outra OS?",
                "Selecione a OS pai (nº) — opcional", "Cancelar", "Gerar OS"):
        assert txt in html, txt
    # diálogo de imagens por ativo (PerfAnexoDialog, reaproveitado pelo Step 1)
    for txt in ("Adicionar arquivo…", "Colar (Ctrl+V)", "Nenhuma imagem ainda.", "Concluir"):
        assert txt in html, txt
    assert '/os/static/tradicional.css' in html and '/os/static/tradicional.js' in html


def test_sem_sessao_vai_para_o_login_e_a_api_responde_401(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    r = c.get("/os/tradicional")
    assert r.status_code == 302 and "/os/login" in r.headers["Location"]
    r = c.post("/os/api/tradicional/criar", data="{}", content_type="application/json")
    assert r.status_code == 401 and r.get_json()["login"] is True


# ── JSON de apoio ────────────────────────────────────────────────────────────────────────────────
def test_api_catalogo_tres_niveis_e_recarregar(cli, monkeypatch):
    j = cli.get("/os/api/tradicional/catalogo").get_json()
    assert j["clientes"] == ["Thopen", "Ultragaz"]
    j = cli.get("/os/api/tradicional/catalogo?cliente=Thopen").get_json()
    assert j == {"cliente": "Thopen", "usinas": ["Thopen - Tanabi 2 - SP"]}
    j = cli.get("/os/api/tradicional/catalogo?cliente=Thopen&usina=Thopen - Tanabi 2 - SP").get_json()
    assert j["tipos"] == ["Estação Meteorológica", "Inversor"]
    assert [a["id"] for a in j["ativos"]] == [11, 12, 13] and j["ativos"][0]["code"] == "TNB200-INVR2.18"
    visto = {}
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: visto.update(force=force) or ASSETS)
    cli.get("/os/api/tradicional/catalogo?recarregar=1")                                  # o botão ↻ do Step 1
    assert visto["force"] is True
    cli.get("/os/api/tradicional/catalogo")
    assert visto["force"] is False


def test_api_tipos_etiquetas_e_os_pai(cli, monkeypatch):
    monkeypatch.setattr(api, "get_tipos_classif", lambda: TIPOS)
    j = cli.get("/os/api/tradicional/tipos").get_json()
    assert j["tipos"] == TIPOS["tipos"] and j["c1"] == TIPOS["c1"] and j["c2"] == TIPOS["c2"]
    assert j["criticidades"] == [{"id": i, "description": n} for n, i in api.CRITICIDADES] and j["crit_default"] == 3
    monkeypatch.setattr(api, "get_labels", lambda: LABELS)
    assert cli.get("/os/api/tradicional/etiquetas").get_json() == {"etiquetas": LABELS}
    visto = {}
    monkeypatch.setattr(api, "buscar_os_pai", lambda termo="", limit=50: visto.update(termo=termo) or
                        [{"id": 400, "folio": "9786", "descricao": "Troca de fusível", "responsavel": "X", "data": "", "criada": ""}])
    j = cli.get("/os/api/tradicional/os-pai?q=978").get_json()
    assert visto["termo"] == "978" and j["resultados"][0]["id"] == 400 and j["resultados"][0]["folio"] == "9786"
    visto.clear()
    assert cli.get("/os/api/tradicional/os-pai?q=").get_json() == {"resultados": []} and visto == {}   # vazio não busca (OsPaiPicker._buscar)


# ── a escrita: o MESMO payload do ResponsavelDialog._gerar ───────────────────────────────────────
def test_criar_uma_os_por_ativo_com_o_payload_do_app(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_bulk", _dublê_bulk(visto, [
        {"code": "TNB200-INVR2.18", "ok": True, "os": {"id_task": 1, "id_work_order": 501, "wo_folio": 9812}},
        {"code": "TNB200-INVR2.17", "ok": True, "os": {"id_task": 2, "id_work_order": 502, "wo_folio": 9813}}]))
    r = _post(cli, CORPO)
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] is True and j["mensagem"] == "2 OS criada(s) — Nº 9812, 9813."
    # os 10 posicionais do app.py:1009-1011, campo a campo
    assert visto["assets"] == [ASSETS[0], ASSETS[1]]                     # registro INTEIRO do catálogo, na ordem do catálogo
    assert visto["description"] == "Verificar strings sem corrente"      # d["desc"]
    assert visto["task_type"] == "Corretiva"                             # d["tipo"] (texto do tipo)
    assert visto["subtasks"] == ["Medir tensão das strings", "Fotografar o quadro"]   # d["subs"] (vazias fora, como Step3.subtarefas)
    assert visto["etiqueta"] == "PERFORMANCE, CHAMADOS"                  # d["etiqueta"] (nomes, Step2.etiqueta)
    assert visto["responsible_code"] == "L1"                             # p["code"]
    assert visto["responsible_name"] == "Levi Maia"                      # p["name"]
    assert visto["id_responsible"] == 1414413                            # p.get("id_personnel")
    assert visto["etiqueta_ids"] == [4660, 12]                           # d.get("etiqueta_ids")
    assert visto["note"] == "Levar multímetro"                           # d.get("obs", "")
    # os kwargs do app.py:1011-1014
    assert visto["tipo"] == TIPO_DICT                                    # tipo=d.get("tipo_dict") (TipoTarefaBox.tipo_dict)
    assert visto["finalizar"] is None                                    # painel "já realizada" desmarcado
    assert visto["event_date"] == dt.datetime(2026, 9, 12, 1, 10, tzinfo=BRT)      # data do incidente com o fuso de Brasília
    assert visto["id_parent"] == 400                                     # self.os_pai.id_parent() — o id, não o nº
    assert visto["imagens_por_ativo"] == {}                              # Step1.selected_images() sem anexo
    assert visto["prog_date"] == dt.datetime(2026, 9, 13, 8, 0, tzinfo=BRT)        # data programada
    assert visto["por_ativo"] is None and visto["falha"] is None         # o Tradicional não passa (só COS)


def test_agrupar_em_uma_os_chama_create_work_orders_agrupada_como_o_app(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_agrupada", _dublê_agrupada(visto, {
        "ok": True, "os": {"id_tasks": [1, 2], "id_work_order": 600, "wo_folio": 9900}, "n_tarefas": 2, "n_criadas": 2, "erros": []}))
    r = _post(cli, {**CORPO, "agrupar": True})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] is True and j["mensagem"] == "OS 9900 criada com 2 tarefa(s)."
    # os 9 posicionais do app.py:999-1001 (sem responsible_code) e os kwargs de 1001-1003 (sem finalizar)
    assert visto["assets"] == [ASSETS[0], ASSETS[1]] and visto["description"] == "Verificar strings sem corrente"
    assert visto["task_type"] == "Corretiva" and visto["subtasks"] == ["Medir tensão das strings", "Fotografar o quadro"]
    assert visto["etiqueta"] == "PERFORMANCE, CHAMADOS" and visto["responsible_name"] == "Levi Maia" and visto["id_responsible"] == 1414413
    assert visto["etiqueta_ids"] == [4660, 12] and visto["note"] == "Levar multímetro"
    assert visto["tipo"] == TIPO_DICT and visto["event_date"] == dt.datetime(2026, 9, 12, 1, 10, tzinfo=BRT)
    assert visto["id_parent"] == 400 and visto["imagens_por_ativo"] == {} and visto["prog_date"] == dt.datetime(2026, 9, 13, 8, 0, tzinfo=BRT)
    assert "finalizar" not in visto and visto["por_ativo"] is None and visto["falha"] is None


def test_agrupar_com_um_ativo_so_nao_agrupa(cli, monkeypatch):
    """No app o checkbox 'Agrupar' só existe com mais de um ativo (n > 1)."""
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_bulk", _dublê_bulk(visto, [{"code": "TNB200-INVR2.18", "ok": True, "os": {"wo_folio": 1}}]))
    r = _post(cli, {**CORPO, "ativos": [11], "agrupar": True})
    assert r.status_code == 200 and visto["assets"] == [ASSETS[0]]


def test_ja_realizada_monta_finalizar_e_a_data_inicial_vira_o_evento(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_bulk", _dublê_bulk(visto, [{"code": "TNB200-INVR2.18", "ok": True, "os": {"wo_folio": 9814}}]))
    fin = {"to_in_review": True, "ini": "2026-09-12T09:00", "fim": "2026-09-12T11:30", "respostas": ["612"]}
    r = _post(cli, {**CORPO, "ativos": [11], "finalizar": fin})
    assert r.status_code == 200
    assert visto["event_date"] == dt.datetime(2026, 9, 12, 9, 0, tzinfo=BRT)          # app.py:988 — finalizada usa a data inicial
    assert visto["finalizar"] == {"to_in_review": True, "final_date": dt.datetime(2026, 9, 12, 11, 30, tzinfo=BRT),
                                  "id_assigned_user": 1414413, "name": "Levi Maia",
                                  "respostas": ["612", ""]}                               # uma resposta por subtarefa (FinalizarPanel)
    assert visto["prog_date"] == dt.datetime(2026, 9, 13, 8, 0, tzinfo=BRT)             # a programada não muda


def test_ja_realizada_com_data_final_antes_da_inicial_e_400_e_nada_vai_a_api(cli):
    fin = {"to_in_review": False, "ini": "2026-09-12T09:00", "fim": "2026-09-12T08:59", "respostas": []}
    r = _post(cli, {**CORPO, "finalizar": fin})
    assert r.status_code == 400 and r.get_json()["erro"] == "A Data final não pode ser anterior à Data inicial."


@pytest.mark.parametrize("muda, frase", [
    ({"ativos": []}, "Marque ao menos um ativo no Passo 1."),                                    # app.py:840
    ({"ativos": [999]}, "Marque ao menos um ativo no Passo 1."),                                 # id fora do catálogo = nada marcado
    ({"tipo": {"id_main": None, "desc_main": "carregando…"}},
     "O tipo de tarefa ainda não carregou (ou a sessão expirou). Aguarde um instante ou relogue antes de gerar."),   # app.py:844
    ({"desc": "   "}, "Preencha a Descrição da tarefa no Passo 2."),                             # no app o botão fica desabilitado
    ({"subs": ["", "  "]}, "Adicione ao menos uma subtarefa no Passo 3."),                      # idem (Step3: mínimo 1)
    ({"responsavel": {}}, "Escolha o responsável."),                                            # idem (b_ok só habilita com seleção)
    ({"event": "2099-01-01T00:00"}, "Data do evento não aceita futuro — é quando aconteceu."),  # steps/ui.py::travar_no_passado
    ({"event": "ontem"}, "Data inválida."),
])
def test_validacoes_com_as_frases_do_app_e_nada_chega_a_api(cli, muda, frase):
    r = _post(cli, {**CORPO, **muda})
    assert r.status_code == 400 and r.get_json() == {"erro": frase}


def test_imagens_por_ativo_chegam_como_bytes_no_multipart(cli, monkeypatch):
    """Step1.selected_images(): {code: [{'bytes','nome'}]} SÓ dos ativos marcados — o app repassa em `imagens_por_ativo`."""
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_bulk", _dublê_bulk(visto, [{"code": "TNB200-INVR2.18", "ok": True, "os": {"wo_folio": 1}}]))
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    dados = {"payload": json.dumps({**CORPO, "ativos": [11]}),
             "imagens:TNB200-INVR2.18": [(io.BytesIO(png), "foto.png"), (io.BytesIO(b"JPEG"), "captura_1.jpg")],
             "imagens:TNB200-INVR2.17": (io.BytesIO(b"fora"), "nao-marcado.png")}
    r = cli.post("/os/api/tradicional/criar", data=dados, content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert visto["imagens_por_ativo"] == {"TNB200-INVR2.18": [{"bytes": png, "nome": "foto.png"}, {"bytes": b"JPEG", "nome": "captura_1.jpg"}]}
    assert visto["description"] == "Verificar strings sem corrente"    # o resto do payload veio junto, no campo `payload`


def test_upload_acima_de_4mb_e_recusado_com_mensagem(cli):
    grande = io.BytesIO(b"\x00" * (4 * 1024 * 1024 + 1024))
    r = cli.post("/os/api/tradicional/criar", data={"payload": json.dumps(CORPO), "imagens:TNB200-INVR2.18": (grande, "g.png")},
                 content_type="multipart/form-data")
    assert r.status_code == 413 and "4 MB" in r.get_json()["erro"]


def test_erro_do_fracttal_vira_json_502(cli, monkeypatch):
    def _boom(*a, **k):
        raise api.FracttalError("Sua conta do Fracttal não tem permissão para criar OS.")
    monkeypatch.setattr(api, "create_work_orders_bulk", _boom)
    r = _post(cli, CORPO)
    assert r.status_code == 502 and "não tem permissão" in r.get_json()["erro"]


# ── as mensagens de resultado, iguais às do app (ResponsavelDialog._pronto / _pronto_agrupada) ───
def test_mensagens_de_resultado_iguais_as_do_app():
    res = [{"code": "A", "ok": True, "os": {"wo_folio": 9812}},
           {"code": "B", "ok": True, "os": {"id_work_order": 77, "aviso": "tarefa criada, mas não a achei no kanban p/ virar WO."}},
           {"code": "C", "ok": False, "erro": "RPC recusou"}]
    m = trad.mensagem_bulk(res)
    assert m["ok"] is True
    assert m["mensagem"] == ("2 OS criada(s) — Nº 9812, 77.\n\n⚠ 1 com ressalva:\n• B: tarefa criada, mas não a achei no kanban p/ virar WO."
                             "\n\n1 falharam:\n• C: RPC recusou")
    m = trad.mensagem_bulk([{"code": "A", "ok": False, "erro": "sem id_item"}])
    assert m["ok"] is False and m["mensagem"] == "Nenhuma OS criada.\n• A: sem id_item"
    m = trad.mensagem_agrupada({"ok": True, "os": {"wo_folio": 9900}, "n_criadas": 3, "erros": ["X: ativo não encontrado."], "aviso": "a etiqueta falhou"})
    assert m["ok"] is True and m["mensagem"] == "OS 9900 criada com 3 tarefa(s).\n\n⚠ a etiqueta falhou\n\n1 ativo(s) ficaram de fora:\n• X: ativo não encontrado."
    m = trad.mensagem_agrupada({"ok": False, "erro": "Falha ao criar as tarefas: x"})
    assert m["ok"] is False and m["mensagem"] == "Falha ao criar as tarefas: x"
    assert trad.mensagem_agrupada({"ok": False})["mensagem"] == "Não consegui criar a OS."


def test_nenhuma_os_criada_volta_200_com_a_frase_do_app(cli, monkeypatch):
    monkeypatch.setattr(api, "create_work_orders_bulk", _dublê_bulk({}, [{"code": "TNB200-INVR2.18", "ok": False, "erro": "RPC recusou"}]))
    r = _post(cli, {**CORPO, "ativos": [11]})
    assert r.status_code == 200 and r.get_json() == {"ok": False, "mensagem": "Nenhuma OS criada.\n• TNB200-INVR2.18: RPC recusou", "folios": []}

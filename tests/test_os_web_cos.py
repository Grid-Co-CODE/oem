# tests/test_os_web_cos.py
"""COS na web (card "COS"): a tela do `steps/varias_os.py` (VariasOSsDialog) em etapas, com os MESMOS rótulos, e o
título '[Equip] - Motivo' + observação-pipe montados pela MESMA regra do `cos_spec` (o preview vem do servidor, que
usa o módulo). A criação chama as duas funções que o app já usa — `api.create_work_orders_bulk` (Vários ativos ·
1 data) e `api.create_work_orders_datas` (Mesmo ativo · várias datas) — com os argumentos POSICIONAIS do `_criar`,
comparados aqui campo a campo. A API do Fracttal é um dublê: o que se testa é o contrato da tela."""
# ESPECIFICACAO ADIANTADA: este arquivo descreve a tela ANTES de ela existir, e o modulo que ele
# importa ainda nao foi escrito. Sem o `importorskip` o pytest nem CHEGA a coletar a bateria — um
# ImportError na coleta derruba a suite inteira, e nao so este arquivo. Enquanto o modulo nao
# nascer, os testes ficam como "skipped" (visiveis, contados, na fila); no dia em que ele nascer,
# passam a valer sozinhos, sem ninguem lembrar de reativa-los.
import pytest as _pytest

_pytest.importorskip("os_web.cos_web", reason="a tela COS ainda nao foi portada para a web")

import ast
import datetime as dt
import json
import os
import re
from urllib.parse import quote_plus

import pytest

import api
import cos_spec as cs
from os_web import cos_web, criar_app

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
BRT = dt.timezone(dt.timedelta(hours=-3))
_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator")

# registros como o catálogo (`api._build_records`) devolve; id_parent/id_type_item/id_group_task são o que o create_os_rpc exige
ASSETS = [
    {"id": 11, "code": "TNB200-INVR2.18", "description": "Inversor 2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "tipo": "Inversor",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 5, "id_type_item": 2, "id_group_task": 9},
    {"id": 12, "code": "TNB200-INVR2.17", "description": "Inversor 2.17", "label": "TNB200-INVR2.17 — Inversor 2.17", "tipo": "Inversor",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 5, "id_type_item": 2, "id_group_task": 9},
    {"id": 13, "code": "TNB200-CAB1", "description": "Cabine de Medição", "label": "TNB200-CAB1 — Cabine de Medição", "tipo": "Cabine",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 5, "id_type_item": 2, "id_group_task": 9},
    {"id": 14, "code": "TNB200-ESTM1", "description": "Estação Meteorológica", "label": "TNB200-ESTM1 — Estação Meteorológica",
     "tipo": "Estação Meteorológica", "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "id_parent": 5, "id_type_item": 2, "id_group_task": 9},
    {"id": 21, "code": "TNB100-INVR1.1", "description": "Inversor 1.1", "label": "TNB100-INVR1.1 — Inversor 1.1", "tipo": "Inversor",
     "cliente": "Thopen", "usina": "Thopen - Tanabi 1 - SP", "id_parent": 4, "id_type_item": 2, "id_group_task": 9},
    {"id": 31, "code": "IBR100-INVR1.1", "description": "Inversor 1.1", "label": "IBR100-INVR1.1 — Inversor 1.1", "tipo": "Inversor",
     "cliente": "Ultragaz", "usina": "Utragaz - Ibirapuã 1 e 2 - BA", "id_parent": 7, "id_type_item": 2, "id_group_task": 9},
    {"id": 41, "code": "ALM-DJ1", "description": "Disjuntor", "label": "ALM-DJ1 — Disjuntor", "tipo": "Disjuntor", "cliente": "Almoxarifado", "usina": "Depósito"},
]
CLASSIF = {"tipos": [{"id": 101, "description": "Religamento Remoto"}, {"id": 102, "description": "Religamento"},
                     {"id": 103, "description": "Corretiva Emergencial"}, {"id": 104, "description": "Corretiva"}],
           "c1": [{"id": 201, "description": "Religamento"}, {"id": 202, "description": "Emergencial"}, {"id": 203, "description": "Programada"}],
           "c2": [{"id": 301, "description": "Elétrica"}, {"id": 302, "description": "Mecânica"}]}
FALHAS = {"tipos": [{"id": 1, "description": "Desligamento"}, {"id": 2, "description": "Desligamento Inversor"},
                    {"id": 3, "description": "Conectividade/Comunicação"}],
          "causas": [{"id": 11, "description": "Queda de energia"}, {"id": 12, "description": "Perda de sinal em redes de comunicação"}],
          "metodos": [{"id": 21, "description": "Monitoramento de Condição Online (MCO)"}]}
PESSOAS = [{"code": "L1", "name": "Levi Maia", "id_personnel": 1414413}, {"code": "A1", "name": "Ana Patrícia", "id_personnel": 77}]
LEVI = PESSOAS[0]


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: ASSETS)
    monkeypatch.setattr(api, "get_tipos_classif", lambda: CLASSIF)
    monkeypatch.setattr(api, "get_falha_listas", lambda: FALHAS)
    monkeypatch.setattr(api, "get_responsaveis", lambda: PESSOAS)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


def _post(cli, corpo):
    return cli.post("/os/api/cos/criar", data=json.dumps(corpo), content_type="application/json")


def _corpo(**k):
    """Estado da tela como o cos.js manda: defaults iguais aos da tela recém-aberta (Religamento · A · Remoto · realizada)."""
    base = {"tipo": 0, "cat": "A", "remoto": True, "modo": 0, "codigos": ["27", "59"], "onde": "Disjuntor Geral", "falha_b": cs.FALHAS_B[0],
            "causa_c": cs.CAUSAS_C[0], "obs": "", "ids": [11], "terceiros": False, "cliente": "", "usina": "",
            "ovr": {"tipo": None, "c1": None, "c2": None, "crit": None}, "realizada": True, "em_verificacao": False,
            "responsavel": LEVI, "falha": {"marcado": False}, "evento": "2026-09-12T14:00", "conclusao": "2026-09-12T14:10", "datas": []}
    base.update(k)
    return base


# ── fidelidade com o widget (constantes copiadas, porque o módulo de lá é Qt) ──────────────────────────────────────
def _fonte_widget():
    with open(os.path.join(_APP, "steps", "varias_os.py"), encoding="utf-8") as f:
        return f.read()


def _literal(tree, nome):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == nome for t in node.targets):
            return node.value
    raise AssertionError(f"{nome} não encontrado no widget")


def test_constantes_copiadas_do_widget_iguais_ao_fonte():
    tree = ast.parse(_fonte_widget())
    assert cos_web.GENERICO_ID == _literal(tree, "GENERICO_ID").value
    assert cos_web.GENERICO_DESC == _literal(tree, "GENERICO_DESC").value
    assert cos_web.PREENCHER == _literal(tree, "_PREENCHER").value
    conj = _literal(tree, "_CARTEIRA_EQUIP")
    conj = conj.args[0] if isinstance(conj, ast.Call) else conj
    assert cos_web.CARTEIRA_EQUIP == frozenset(e.value for e in conj.elts)


def test_rotulos_da_tela_existem_no_widget():
    """Os textos dos segmentados, do marcador multi-usina e dos cards são os do app, letra por letra."""
    fonte = _fonte_widget()
    for txt in cos_web.MODOS + cos_web.CATEGORIAS_ROTULO + cos_web.ACOES_ROTULO + (
            "Ativos de mais de uma usina deste cliente", "Como vai ficar (montado sozinho)", "Ação e permissivo de segurança",
            "Registrada no Fracttal como", "Usina de terceiros", "Datas/horas do evento (uma OS por linha)"):
        assert txt in fonte, txt


# ── a tela ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_tela_abre_com_as_etapas_e_os_rotulos_do_app(cli):
    r = cli.get("/os/cos")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    # barra de tipo + clonador
    for txt in ("Tipo:", cs.TIPO_RELIGAMENTO, cs.TIPO_INSPECAO, "Clonar OS nº", "ex.: 9184", ">Clonar<"):
        assert txt in html, txt
    # Card 1 Ativo
    for txt in ("Usina de terceiros", "O&amp;M de usina que não é ativo cadastrado — Cliente/Usina livres + ativo genérico",
                "Vários ativos · 1 data", "Mesmo ativo · várias datas", "— Selecione o cliente —", "— Selecione a usina —",
                "Ativos de mais de uma usina deste cliente", "Tipo de equipamento", "Todos os tipos", "Filtrar ativo por código ou nome…",
                "Selecionar todos", ">Limpar<", "0 ativo(s) marcado(s)", "Grid Co. — Emergências e outros pontos",
                "ativo genérico · usado quando a usina não é cadastrada no Fracttal"):
        assert txt in html, txt
    assert "Thopen" in html and "Ultragaz" in html and "Almoxarifado" not in html     # clientes reais, sem inventário
    # Card 2 Categoria
    for txt in ("Categoria da ocorrência", "A · Proteções", "B · Inversores", "C · Comunicação", "Proteção(ões) que atuaram", "Onde atuou",
                "Falha do equipamento", "(o equipamento é o próprio ativo marcado — inversor, cabine, etc.)", "Causa da comunicação"):
        assert txt in html, txt
    for cod in cs.PROTECOES + [cs.SEM_TRIP] + cs.ONDE + cs.FALHAS_B + cs.CAUSAS_C:
        assert cod in html, cod
    assert "Relé Auxiliar de Bloqueio" in html                                        # a tabela ANSI da "!"
    # Cards 3 e 4
    for txt in ("Ação e permissivo de segurança", "Remoto — resolvo agora", "Local — equipe em campo", "Responsável", "Requerido por",
                "(digite p/ pesquisar)", "carregando…"):
        assert txt in html, txt
    # Card 5 O ativo falhou?
    for txt in ("O ativo falhou?", "Tipo de falha", "Causa da falha", "Método de detecção", "Severidade", "Tipo de dano", "Fora de serviço",
                "Registrada no Fracttal como", "(clique no verde para trocar)"):
        assert txt in html, txt
    for nome, _ in api.FALHA_SEVERIDADES + api.FALHA_DANOS:
        assert nome in html, nome
    assert 'value="5" selected' in html                                               # Severidade nasce em "Muito alto" (Levi, 30/07)
    # Card 6 preview e Card 7 Evento
    for txt in ("Como vai ficar (montado sozinho)", "Incluir alguma observação", "comentário do operador — entra numa nova linha no fim da observação",
                ">Título<", ">Observação<", ">Evento<", "Data/hora do evento", "Data/hora da conclusão", "(quando resolvido)", ">Agora<",
                "Datas/horas do evento (uma OS por linha)", "+ Adicionar data", "Esta tarefa já foi realizada?", "Enviar para OS:",
                "Verificação", "Finalizados", "Respostas das subtarefas", "Procedimento"):
        assert txt in html, txt
    # rodapé
    for txt in (">Cancelar<", ">Recomeçar<", ">Criar OSs<"):
        assert txt in html, txt
    assert 'href="/os/static/cos.css"' in html and 'src="/os/static/cos.js"' in html
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", html)                          # sem emoji na interface


def test_sem_sessao_vai_para_o_login_e_a_api_devolve_401():
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    r = c.get("/os/cos")
    assert r.status_code == 302 and "/os/login" in r.headers["Location"]
    r = c.get("/os/api/cos/preview?cat=A")
    assert r.status_code == 401 and r.get_json()["login"] is True


def test_blueprint_proprio_registrado_sozinho():
    app = criar_app(segredo="teste", testing=True)
    assert "os_web_cos" in app.blueprints


# ── cascata e ativos (espelho de _fill_usinas / _on_usi / _cands / _usinas_alvo) ───────────────────────────────────
def test_api_usinas_filtra_pela_carteira(cli):
    j = cli.get("/os/api/cos/usinas?cliente=Thopen").get_json()
    assert j["usinas"] == ["Thopen - Tanabi 1 - SP", "Thopen - Tanabi 2 - SP"]
    j = cli.get("/os/api/cos/usinas").get_json()
    assert j["usinas"] == ["Thopen - Tanabi 1 - SP", "Thopen - Tanabi 2 - SP", "Utragaz - Ibirapuã 1 e 2 - BA"]


def test_api_ativos_da_usina_todos_os_tipos_e_o_filtro_de_tipo_so_com_equipamento_do_cos(cli):
    j = cli.get("/os/api/cos/ativos?usina=Thopen - Tanabi 2 - SP").get_json()
    assert [a["id"] for a in j["ativos"]] == [13, 14, 12, 11]                # ALLOWED_TIPOS = todos; ordem por rótulo
    assert j["tipos"] == ["Cabine", "Inversor"]                                # só os de cs.COS_EQUIP (a estação fica fora do filtro)
    assert j["cliente"] == "Thopen"                                            # a usina escolhida preenche o Cliente
    a = j["ativos"][3]
    assert a == {"id": 11, "code": "TNB200-INVR2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "tipo": "Inversor",
                 "usina": "Thopen - Tanabi 2 - SP", "usina_curta": "Tanabi 2", "cliente": "Thopen"}


def test_api_ativos_de_todas_as_usinas_do_cliente(cli):
    j = cli.get("/os/api/cos/ativos?cliente=Thopen&multi=1").get_json()
    assert [a["id"] for a in j["ativos"]] == [21, 13, 14, 12, 11]           # Tanabi 1 antes de Tanabi 2 (agrupa por usina)
    assert {a["usina_curta"] for a in j["ativos"]} == {"Tanabi 1", "Tanabi 2"}
    assert cli.get("/os/api/cos/ativos").get_json()["ativos"] == []


# ── preview: a MESMA regra do cos_spec ─────────────────────────────────────────────────────────────────────────────
def _prev(cli, q):
    r = cli.get("/os/api/cos/preview?" + q)
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def test_preview_categoria_a_titulo_observacao_meta_e_permissivo(cli):
    j = _prev(cli, "tipo=0&cat=A&remoto=1&codigos=27&codigos=59&onde=Disjuntor+Geral&ids=11&obs=chuva+forte&realizada=1")
    assert j["titulo"] == api.perf_os_nome(ASSETS[0], cs.motivo_titulo(cs.TIPO_RELIGAMENTO, "Inversor 2.18", cs.ACAO_REMOTO))
    assert j["titulo"] == "[Inversor 2.18] - Religamento do Inversor 2.18"
    assert j["observacao"] == cs.observacao("Tanabi 2", ["27", "59"], cs.ACAO_REMOTO, cs.falha_texto(cs.CAT_A, "Disjuntor Geral", ["27", "59"])) + "\nchuva forte"
    assert j["observacao"] == ("UFV: Tanabi 2 | Proteção: 27 e 59 | Ação: Religamento Remoto | Falha: Disjuntor Geral desligado, "
                               "relé com proteções 27 e 59 ativas.\nchuva forte")
    assert j["meta"] == {"tarefa": "Religamento Remoto", "c1": "Religamento", "c2": "Elétrica", "crit": "Muito alto", "c1_preencher": False}
    assert j["permissivo"] == {"texto": "Sem impedimento — pode ser resolvido remoto.", "nivel": "ok"}
    assert j["oos"] == {"ativo": False, "texto": "Não — OS já tem conclusão, o ativo voltou", "curto": "Fora de Serviço: Não"}
    # 86 → permissivo bloqueia o remoto; Local → tipo de tarefa 'Religamento'
    j = _prev(cli, "tipo=0&cat=A&remoto=1&codigos=86&onde=Disjuntor+Geral&ids=11")
    assert j["permissivo"]["texto"].startswith("Impedimento ativo (86) — religamento remoto não autorizado.") and j["permissivo"]["nivel"] == "alerta"
    j = _prev(cli, "tipo=0&cat=A&remoto=0&codigos=27&onde=Inversor&ids=11&realizada=0")
    assert j["meta"]["tarefa"] == "Religamento" and "| Ação: Religamento Local |" in j["observacao"]
    assert j["permissivo"] == {"texto": "Local — a OS abre para a equipe em campo resolver.", "nivel": "info"}
    assert j["oos"] == {"ativo": True, "texto": "Sim — ativo segue fora de serviço (desde a data do evento)", "curto": "Fora de Serviço: Sim"}
    # Sem trip
    j = _prev(cli, "tipo=0&cat=A&remoto=1&codigos=" + quote_plus(cs.SEM_TRIP) + "&onde=Disjuntor+Cabine&ids=11")
    assert "| Proteção: Sem proteção/trip ativo |" in j["observacao"] and "sem atuação de proteção (sem trip)." in j["observacao"]


def test_preview_categoria_b_com_varios_ativos_avisa_que_cada_os_usa_o_seu(cli):
    j = _prev(cli, "tipo=0&cat=B&remoto=0&codigos=27&falha_b=Baixa+irradi%C3%A2ncia&ids=11,12")
    assert j["titulo"] == "[Inversor 2.18] - Religamento do Inversor 2.18   (cada OS usa o seu ativo)"
    assert j["observacao"] == 'UFV: Tanabi 2 | Proteção: --/-- | Ação: Religamento Local | Falha: Inversor 2.18 desligado devido a falha: "Baixa irradiância".'
    assert j["meta"] == {"tarefa": "Corretiva Emergencial", "c1": "Emergencial", "c2": "Elétrica", "crit": "Muito alto", "c1_preencher": False}


def test_preview_inspecao_categoria_c(cli):
    j = _prev(cli, "tipo=1&cat=C&remoto=0&causa_c=Fibra+rompida+na+regi%C3%A3o&ids=13")
    assert j["titulo"] == "[Cabine de Medição] - Inspeção e normalização da Cabine de Medição"
    assert j["observacao"] == ("UFV: Tanabi 2 | Proteção: --/-- | Ação: Inspeção Local | Falha: Usina ligada, mas em falha de comunicação "
                               "devido fibra rompida na região.")
    assert j["meta"]["tarefa"] == "Corretiva Emergencial" and j["meta"]["c1"] == "Emergencial"
    j = _prev(cli, "tipo=1&cat=C&remoto=1&causa_c=Falha+de+comunica%C3%A7%C3%A3o+com+o+supervis%C3%B3rio&ids=13")
    assert j["permissivo"] == {"texto": "Falha de comunicação — verificação remota.", "nivel": "ok"}
    # Religamento + C só existe fora da tela (a sincronia impede) — o PCM deixou 'Preencher' e a linha fica em vermelho
    j = _prev(cli, "tipo=0&cat=C&remoto=0&causa_c=Falta+de+internet&ids=13")
    assert j["meta"]["tarefa"] == "Corretiva" and j["meta"]["c1"] == "Preencher" and j["meta"]["c1_preencher"] is True


def test_preview_sem_ativo_e_de_usina_de_terceiros(cli):
    j = _prev(cli, "tipo=0&cat=A&remoto=1&codigos=27&onde=Disjuntor+Cabine")
    assert j["titulo"] == "[Disjuntor Cabine] - Religamento do Disjuntor Cabine"      # montado à mão, mesmo padrão do perf_os_nome
    assert j["observacao"].startswith("UFV: {usina} | Proteção: 27 |")
    gen = cos_web.ativo_generico("Fulano Energia", "Sítio X")
    j = _prev(cli, "tipo=0&cat=A&remoto=1&codigos=27&onde=Disjuntor+Geral&terceiros=1&cliente=Fulano+Energia&usina=S%C3%ADtio+X")
    assert j["titulo"] == api.perf_os_nome(gen, cs.motivo_titulo(cs.TIPO_RELIGAMENTO, api._asset_short_name(gen), cs.ACAO_REMOTO))
    assert j["observacao"].startswith("UFV: Sítio X |")


def test_preview_respeita_as_trocas_manuais_da_linha_registrada_como(cli):
    j = _prev(cli, "tipo=0&cat=A&remoto=1&codigos=27&onde=Inversor&ids=11&ovr_tipo=Corretiva&ovr_c1=Programada&ovr_c2=Mec%C3%A2nica&ovr_crit=2")
    assert j["meta"] == {"tarefa": "Corretiva", "c1": "Programada", "c2": "Mecânica", "crit": "Alto", "c1_preencher": False}


# ── listas (classificações, falhas, responsáveis) ──────────────────────────────────────────────────────────────────
def test_listas_juntam_classificacoes_falhas_responsaveis_e_a_sugestao_da_falha(cli):
    j = cli.get("/os/api/cos/listas").get_json()
    assert j["classif"] == CLASSIF and j["falhas"] == FALHAS and j["erros"] == {}
    assert [p["name"] for p in j["responsaveis"]] == ["Ana Patrícia", "Levi Maia"]
    assert j["severidade_padrao"] == "5"                                          # 'Muito alto' da api.FALHA_SEVERIDADES
    # _sugerir_falha: Inspeção e C têm tipo/causa próprios; A = Desligamento/Queda de energia; B só o tipo; detecção SEMPRE MCO
    assert j["sugestoes"] == {"A": {"id_type": 1, "id_cause": 11, "id_detection": 21},
                              "B": {"id_type": 2, "id_cause": None, "id_detection": 21},
                              "C": {"id_type": 3, "id_cause": 12, "id_detection": 21},
                              "insp": {"id_type": 2, "id_cause": 12, "id_detection": 21}}
    j = cli.get("/os/api/cos/listas?so=responsaveis").get_json()
    assert set(j) == {"responsaveis", "erros"}


def test_uma_lista_que_falha_nao_derruba_as_outras(cli, monkeypatch):
    def _boom():
        raise api.FracttalError("RPC indisponível")
    monkeypatch.setattr(api, "get_responsaveis", _boom)
    j = cli.get("/os/api/cos/listas").get_json()
    assert j["classif"] == CLASSIF and j["responsaveis"] == [] and j["erros"] == {"responsaveis": "RPC indisponível"}


def test_escolher_desc_e_o_sel_desc_do_widget():
    itens = FALHAS["tipos"]
    assert cos_web.escolher_desc(itens, "desligamento")["id"] == 1                  # igual sem diferença de caixa
    assert cos_web.escolher_desc(itens, "Desligamento Inversor (MCO)")["id"] == 2   # prefixo: o MAIS LONGO vence
    assert cos_web.escolher_desc(itens, "Xyz") is None


# ── criar: Vários ativos · 1 data → api.create_work_orders_bulk, argumentos do _criar ─────────────────────────────
def test_criar_varios_ativos_uma_data_chama_o_bulk_com_o_payload_do_app(cli, monkeypatch):
    visto = {}
    def _bulk(*args, **kwargs):
        visto["args"], visto["kwargs"] = args, kwargs
        return [{"code": "TNB200-INVR2.18", "ok": True, "os": {"id_work_order": 1, "wo_folio": 9184}},
                {"code": "TNB200-INVR2.17", "ok": False, "erro": "kanban não achou a tarefa"}]
    monkeypatch.setattr(api, "create_work_orders_bulk", _bulk)
    monkeypatch.setattr(api, "create_work_orders_datas", lambda *a, **k: pytest.fail("trilho errado"))
    r = _post(cli, _corpo(ids=[12, 11], obs="chuva forte",
                          falha={"marcado": True, "id_type": 1, "id_cause": 11, "id_detection": 21, "id_severity": "5", "id_damage": 1}))
    j = r.get_json()
    assert r.status_code == 200, j
    assert j["ok"] == 1 and j["falhas"] == 1 and j["folios"] == [9184]
    assert j["mensagem"] == "1 OS criada(s) — Nº 9184.\n\nFalhas:\n- TNB200-INVR2.17: kanban não achou a tarefa"
    a = visto["args"]
    assert visto["kwargs"] == {} and len(a) == 17
    assert a[0] == [ASSETS[0], ASSETS[1]]                                        # ativos INTEIROS do catálogo, na ordem dele
    assert a[1] == "Religamento" and a[2] == "Religamento Remoto"
    assert a[3] == [{"description": "Categoria e proteção", "id_task_form_item_type": 1, "is_required": True},
                    {"description": "Onde atuou", "id_task_form_item_type": 1, "is_required": True},
                    {"description": "Foi necessário religamento?", "id_task_form_item_type": 7, "is_required": True,
                     "dropdown_options": [{"description": "Sim"}, {"description": "Não — já normalizado"}]},
                    {"description": "Resultado", "id_task_form_item_type": 7, "is_required": True,
                     "dropdown_options": [{"description": "Normalizado"}, {"description": "Persistiu"}, {"description": "Parcial"}]}]
    assert a[4] == "" and a[5:8] == ("L1", "Levi Maia", 1414413) and a[8] is None and a[9] == ""
    assert a[10] == {"id_main": 101, "id_priorities": api.CRITICIDADE_MUITO_ALTO, "id_c1": 201, "desc_c1": "Religamento", "id_c2": 301, "desc_c2": "Elétrica"}
    assert a[11] == {"to_in_review": False, "final_date": dt.datetime(2026, 9, 12, 14, 10, tzinfo=BRT), "id_assigned_user": 1414413,
                     "name": "Levi Maia", "respostas": ["Proteção atuou — 27 e 59", "Disjuntor Geral", "Sim", "Normalizado"]}
    assert a[12] == dt.datetime(2026, 9, 12, 14, 0, tzinfo=BRT) and a[13] is None and a[14] is None
    obs = "UFV: Tanabi 2 | Proteção: 27 e 59 | Ação: Religamento Remoto | Falha: Disjuntor Geral desligado, relé com proteções 27 e 59 ativas.\nchuva forte"
    assert a[15] == {"TNB200-INVR2.18": {"description": "[Inversor 2.18] - Religamento do Inversor 2.18", "note": obs},
                     "TNB200-INVR2.17": {"description": "[Inversor 2.17] - Religamento do Inversor 2.17", "note": obs}}
    assert a[16] == {"id_type": 1, "type_desc": "Desligamento", "id_cause": 11, "cause_desc": "Queda de energia",
                     "id_detection": 21, "detection_desc": "Monitoramento de Condição Online (MCO)",
                     "id_severity": "5", "severity_desc": "Muito alto", "id_damage": 1, "damage_desc": "Nenhum",
                     "out_of_service": False}                                        # já realizada → tem conclusão → não está fora de serviço


def test_criar_inspecao_nasce_aberta_com_as_subtarefas_de_inspecao(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda *a, **k: visto.update(args=a) or [{"code": "TNB200-CAB1", "ok": True, "os": {"wo_folio": 1}}])
    r = _post(cli, _corpo(tipo=1, cat="C", remoto=False, causa_c="Falta de internet", ids=[13], realizada=False, em_verificacao=False,
                          falha={"marcado": True, "id_type": 2, "id_cause": 12, "id_detection": 21, "id_severity": "5", "id_damage": 1}))
    assert r.status_code == 200, r.get_json()
    a = visto["args"]
    assert a[2] == "Corretiva Emergencial"
    assert a[3] == [{"description": "Equipamento e sintoma", "id_task_form_item_type": 1, "is_required": True},
                    {"description": "Diagnóstico", "id_task_form_item_type": 7, "is_required": True,
                     "dropdown_options": [{"description": "Desligado"}, {"description": "Só sem comunicação (segue gerando)"}]},
                    {"description": "Ação", "id_task_form_item_type": 7, "is_required": True,
                     "dropdown_options": [{"description": "Religamento local"}, {"description": "Operador avisado"}]},
                    {"description": "Normalizado?", "id_task_form_item_type": 7, "is_required": True,
                     "dropdown_options": [{"description": "Sim"}, {"description": "Não"}, {"description": "Parcial"}]}]
    assert a[10] == {"id_main": 103, "id_priorities": 1, "id_c1": 202, "desc_c1": "Emergencial", "id_c2": 301, "desc_c2": "Elétrica"}
    assert a[11] is None                                                              # não realizada → sem finalizar
    assert a[15]["TNB200-CAB1"] == {"description": "[Cabine de Medição] - Inspeção e normalização da Cabine de Medição",
                                    "note": "UFV: Tanabi 2 | Proteção: --/-- | Ação: Inspeção Local | Falha: Usina ligada, mas em falha de comunicação devido falta de internet."}
    assert a[16]["out_of_service"] is True                                            # sem conclusão → fora de serviço


def test_criar_em_usina_de_terceiros_usa_o_ativo_generico(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda *a, **k: visto.update(args=a) or [{"code": "GRID", "ok": True, "os": {"wo_folio": 2}}])
    r = _post(cli, _corpo(ids=[], terceiros=True, cliente="Fulano Energia", usina="Sítio X"))
    assert r.status_code == 200, r.get_json()
    gen = cos_web.ativo_generico("Fulano Energia", "Sítio X")
    assert visto["args"][0] == [gen] and gen["id"] == cos_web.GENERICO_ID and gen["code"] == "GRID"
    assert visto["args"][15]["GRID"]["note"].startswith("UFV: Sítio X |")


# ── criar: Mesmo ativo · várias datas → api.create_work_orders_datas ──────────────────────────────────────────────
def test_criar_mesmo_ativo_varias_datas_chama_o_datas_com_o_payload_do_app(cli, monkeypatch):
    visto = {}
    def _datas(*args, **kwargs):
        visto["args"], visto["kwargs"] = args, kwargs
        return [{"data": "10/09 08:00", "ok": True, "os": {"wo_folio": 9001, "aviso": "WO 9001 criada, mas etiqueta falhou: x"}},
                {"data": "11/09 09:00", "ok": True, "os": {"wo_folio": 9002}}]
    monkeypatch.setattr(api, "create_work_orders_datas", _datas)
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda *a, **k: pytest.fail("trilho errado"))
    r = _post(cli, _corpo(modo=1, cat="B", remoto=False, falha_b="Perda da rede elétrica", ids=[11], em_verificacao=True,
                          datas=[{"evento": "2026-09-10T08:00", "conclusao": "2026-09-10T08:10"}, {"evento": "2026-09-11T09:00", "conclusao": "2026-09-11T09:30"}]))
    j = r.get_json()
    assert r.status_code == 200, j
    assert j["mensagem"] == "2 OS criada(s) — Nº 9001, 9002.\n\nAvisos:\n- WO 9001 criada, mas etiqueta falhou: x"
    a = visto["args"]
    assert visto["kwargs"] == {} and len(a) == 14
    assert a[0] == ASSETS[0] and a[1] == "[Inversor 2.18] - Religamento do Inversor 2.18" and a[2] == "Corretiva Emergencial"
    assert [s["description"] for s in a[3]] == ["Categoria e proteção", "Onde atuou", "Foi necessário religamento?", "Resultado"]
    assert a[4] == [(dt.datetime(2026, 9, 10, 8, 0, tzinfo=BRT), dt.datetime(2026, 9, 10, 8, 10, tzinfo=BRT)),
                    (dt.datetime(2026, 9, 11, 9, 0, tzinfo=BRT), dt.datetime(2026, 9, 11, 9, 30, tzinfo=BRT))]
    assert a[5:8] == ("L1", "Levi Maia", 1414413) and a[8] is None
    assert a[9] == 'UFV: Tanabi 2 | Proteção: --/-- | Ação: Religamento Local | Falha: Inversor 2.18 desligado devido a falha: "Perda da rede elétrica".'
    assert a[10] == {"id_main": 103, "id_priorities": 1, "id_c1": 202, "desc_c1": "Emergencial", "id_c2": 301, "desc_c2": "Elétrica"}
    assert a[11] == {"to_in_review": True, "id_assigned_user": 1414413, "name": "Levi Maia",
                     "respostas": ["Inversor desligado — Perda da rede elétrica", "—", "Sim", "Normalizado"]}   # sem final_date: vai por data
    assert a[12] is None and a[13] is None                                          # sem OS pai; 'O ativo falhou?' desmarcado


def test_varias_datas_sem_realizar_manda_so_o_evento_de_cada_linha(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_work_orders_datas", lambda *a, **k: visto.update(args=a) or [])
    r = _post(cli, _corpo(modo=1, ids=[11, 12], realizada=False, datas=[{"evento": "2026-09-10T08:00", "conclusao": ""}]))
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] == 0 and j["mensagem"] == "0 OS criada(s)."
    a = visto["args"]
    assert a[0] == ASSETS[0]                                                        # mesmo ativo: só o primeiro marcado
    assert a[4] == [dt.datetime(2026, 9, 10, 8, 0, tzinfo=BRT)] and a[11] is None


# ── validações: a frase do app, 400, e nada chega ao Fracttal ─────────────────────────────────────────────────────
@pytest.mark.parametrize("corpo, frase", [
    (_corpo(ids=[]), "Marque ao menos um ativo."),
    (_corpo(ids=[], terceiros=True, cliente="Fulano", usina=""), "Preencha o Cliente e a Usina (texto livre)."),
    (_corpo(responsavel={}), "Escolha o responsável (requerido por)."),
    (_corpo(tipo=0, cat="C", remoto=False, causa_c="Falta de internet"),
     "Escolha a Classificação 1 — clique no 'Preencher' em vermelho na linha 'Registrada no Fracttal como'."),
    (_corpo(codigos=[]), "Marque ao menos uma proteção que atuou (categoria A · Proteções)."),
    (_corpo(falha={"marcado": True, "id_type": 1, "id_cause": None, "id_detection": 21}),
     "Preencha Tipo de falha, Causa e Método de detecção (ou desmarque 'O ativo falhou?')."),
    (_corpo(modo=1, datas=[]), "Adicione ao menos uma data."),
    (_corpo(modo=1, datas=[{"evento": "2026-09-10T08:00", "conclusao": "2026-09-10T07:00"}]), "Conclusão anterior ao evento (linha 10/09 08:00)."),
    (_corpo(conclusao="2026-09-12T13:00"), "A conclusão não pode ser anterior ao evento."),
    (_corpo(evento="ontem"), "Data inválida."),
])
def test_validacao_vira_400_com_a_frase_do_app(cli, monkeypatch, corpo, frase):
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda *a, **k: pytest.fail("escreveu no Fracttal com validação falhando"))
    monkeypatch.setattr(api, "create_work_orders_datas", lambda *a, **k: pytest.fail("escreveu no Fracttal com validação falhando"))
    r = _post(cli, corpo)
    assert r.status_code == 400 and r.get_json()["erro"] == frase


def test_tipos_que_nao_carregaram_barram_a_criacao(cli, monkeypatch):
    monkeypatch.setattr(api, "get_tipos_classif", lambda: {"tipos": [], "c1": [], "c2": []})
    monkeypatch.setattr(api, "create_work_orders_bulk", lambda *a, **k: pytest.fail("escreveu sem tipo de tarefa"))
    r = _post(cli, _corpo())
    assert r.status_code == 400
    assert r.get_json()["erro"] == "Os tipos ainda não carregaram (ou a sessão expirou). Aguarde um instante ou relogue e tente de novo."


def test_erro_do_fracttal_na_criacao_vira_502_json_e_nao_500(cli, monkeypatch):
    def _boom(*a, **k):
        raise api.FracttalError("RPC recusou")
    monkeypatch.setattr(api, "create_work_orders_bulk", _boom)
    r = _post(cli, _corpo())
    assert r.status_code == 502 and r.get_json() == {"erro": "RPC recusou"}


def test_mensagem_de_resultado_e_a_do_ok_do_widget():
    res = [{"code": "A", "ok": True, "os": {"wo_folio": 1}}, {"code": "B", "ok": True, "os": {"wo_folio": 2, "aviso": "tarefa criada, mas falhou virar WO: x"}},
           {"data": "10/09 08:00", "ok": False, "erro": "boom"}]
    j = cos_web.mensagem_resultado(res)
    assert j["mensagem"] == "2 OS criada(s) — Nº 1, 2.\n\nAvisos:\n- tarefa criada, mas falhou virar WO: x\n\nFalhas:\n- 10/09 08:00: boom"
    assert (j["ok"], j["falhas"], j["folios"]) == (2, 1, [1, 2])
    assert cos_web.mensagem_resultado([])["mensagem"] == "0 OS criada(s)."        # o `_ok` do widget: a frase nasce do len(ok)


# ── clonar: uma OS do COS remonta o formulário (parse_observacao + categoria_de) ───────────────────────────────────
def _os(folio, descricao, notas, code):
    return {"folio": folio, "descricao": descricao, "notas": notas, "code": code, "id_work_order": 500 + folio}


def test_clonar_os_do_cos_remonta_tipo_categoria_protecoes_acao_e_ativo(cli, monkeypatch):
    oss = {"9184": _os(9184, "[Inversor 2.18] - Religamento do Inversor 2.18",
                        "UFV: Tanabi 2 | Proteção: 27 e 59 | Ação: Religamento Remoto | Falha: Disjuntor Geral desligado, relé com proteções 27 e 59 ativas.\nchuva",
                        "TNB200-INVR2.18"),
           "9185": _os(9185, "[Inversor 2.17] - Religamento do Inversor 2.17",
                        'UFV: Tanabi 2 | Proteção: --/-- | Ação: Religamento Local | Falha: Inversor 2.17 desligado devido a falha: "Perda da rede elétrica".',
                        "TNB200-INVR2.17"),
           "9186": _os(9186, "[Cabine de Medição] - Inspeção e normalização da Cabine de Medição",
                        "UFV: Tanabi 2 | Proteção: --/-- | Ação: Inspeção Local | Falha: Usina ligada, mas em falha de comunicação devido fibra rompida na região.",
                        "TNB200-CAB1"),
           "9187": _os(9187, "[Inversor 1.1] - Recomposição de String", "verificar strings", "IBR100-INVR1.1")}
    monkeypatch.setattr(api, "get_os_detalhes_por_folio", lambda folio: oss.get(str(folio)))
    j = cli.get("/os/api/cos/os-modelo?folio=9184").get_json()
    assert j == {"folio": 9184, "tipo": 0, "cat": "A", "codigos": ["27", "59"], "falha_b": "", "causa_c": "", "remoto": True,
                 "ativo": {"id": 11, "code": "TNB200-INVR2.18", "label": "TNB200-INVR2.18 — Inversor 2.18", "tipo": "Inversor",
                           "usina": "Thopen - Tanabi 2 - SP", "usina_curta": "Tanabi 2", "cliente": "Thopen", "carteira": "Thopen"},
                 "mensagem": "Formulário preenchido a partir da OS 9184.\nConfira o ativo, a data do evento e o responsável antes de criar."}
    j = cli.get("/os/api/cos/os-modelo?folio=9185").get_json()
    assert (j["tipo"], j["cat"], j["codigos"], j["falha_b"], j["remoto"]) == (0, "B", [], "Perda da rede elétrica", False)
    j = cli.get("/os/api/cos/os-modelo?folio=9186").get_json()
    assert (j["tipo"], j["cat"], j["causa_c"], j["remoto"], j["ativo"]["id"]) == (1, "C", "Fibra rompida na região", False, 13)
    r = cli.get("/os/api/cos/os-modelo?folio=9187")
    assert r.status_code == 400 and r.get_json()["erro"].startswith("A OS 9187 não segue o padrão do COS na observação (UFV | Proteção | Ação | Falha)")
    r = cli.get("/os/api/cos/os-modelo?folio=1")
    assert r.status_code == 404 and r.get_json()["erro"] == "Não achei nenhuma OS com esse número."
    r = cli.get("/os/api/cos/os-modelo?folio=")
    assert r.status_code == 400 and r.get_json()["erro"] == "Digite o número da OS que quer clonar."

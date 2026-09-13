# tests/test_os_web_historico.py
"""Historicos de OS na web: as mesmas visoes (criadas por mim / atribuidas a mim), o mesmo filtro de periodo, as
mesmas colunas e cores de status do `steps/historico.py`; o numero abre o detalhe da OS (`api.get_os_detalhes`)."""
import json

import pytest

import api
from os_web import criar_app

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"

LINHAS = [
    {"id": 501, "folio": 9812, "cliente": "Thopen", "usina": "Thopen - Tanabi 2 - SP", "ativo": "Inversor 2.18", "tipo": "Inversor",
     "descricao": "[Inversor 2.18] - Recomposição de String", "criado_por": "Levi Maia", "atribuido_a": "Luiz Silva",
     "etiquetas": [{"id": 4660, "nome": "PERFORMANCE"}], "data": "2026-09-12T01:12:00", "event_date": "2026-09-12T01:10:00",
     "data_fim": "", "status_id": 1, "status": "Em Processo"},
    {"id": 502, "folio": 9773, "cliente": "2C", "usina": "2C - Araputanga 1 - MT", "ativo": "Inversor 1.5", "tipo": "Inversor",
     "descricao": "[Inversor 1.5] - Verificação de Tracker Parado", "criado_por": "Levi Maia", "atribuido_a": "Luiz Silva",
     "etiquetas": [], "data": "2026-09-09T12:32:00", "event_date": "", "data_fim": "2026-09-10T18:00:00", "status_id": 3, "status": "Concluída"},
]


LABELS = [{"id": 4660, "description": "PERFORMANCE", "color": "#8fce3f"}, {"id": 12, "description": "CHAMADOS", "color": "#57B6F5"}]
PESSOAS = {"pessoas": [{"id_account": 77, "nome": "Levi Maia"}, {"id_account": 88, "nome": "Luiz Silva"}], "eu": 77}


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    """Os filtros do historico buscam etiquetas, pessoas e o catalogo no Fracttal: aqui sao dubles fixos."""
    monkeypatch.setattr(api, "get_labels", lambda: LABELS)
    monkeypatch.setattr(api, "get_pessoas_contas", lambda: PESSOAS)
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "meta_tarefas_por_os", lambda ids: {})


@pytest.fixture
def cli(monkeypatch):
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    return c


def test_lista_criadas_por_mim_com_as_colunas_do_app(cli, monkeypatch):
    visto = {}
    def _lista(modo="criadas", id_account=None, id_label=None, de=None, ate=None, status_ids=None, cap=2000):
        visto.update(modo=modo, de=de, ate=ate, id_account=id_account)
        return LINHAS
    monkeypatch.setattr(api, "list_minhas_os", _lista)
    r = cli.get("/os/historico?de=2026-09-01&ate=2026-09-12")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and visto == {"modo": "criadas", "de": "2026-09-01", "ate": "2026-09-12", "id_account": None}
    for col in ("Nº", "Cliente", "Usina", "Ativo", "Descrição", "Data de Criação", "Data do Evento", "Data Fim", "Status", "Etiqueta"):
        assert col in html
    assert "9812" in html and "Tanabi 2" in html and "Em Processo" in html and "Concluída" in html
    assert 'href="/os/os/501' in html                                  # o numero abre o detalhe (leva o status junto)
    assert "#F5A623" in html and "#48D07A" in html                    # cores vivas de status do app
    assert "PERFORMANCE" in html
    assert "11/09/2026 22:12" in html                                 # data em horario de Brasilia (api.fmt_data_br)


def test_lista_atribuidas_a_mim(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "list_minhas_os", lambda modo="criadas", **k: visto.update(modo=modo) or [])
    html = cli.get("/os/historico?modo=atribuidas&de=2026-09-01&ate=2026-09-12").get_data(as_text=True)
    assert visto["modo"] == "atribuidas" and "Nenhuma OS" in html


def test_periodo_padrao_e_os_ultimos_30_dias(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "list_minhas_os", lambda **k: visto.update(k) or [])
    cli.get("/os/historico")
    import datetime as dt
    assert visto["ate"] == dt.date.today().isoformat()
    assert visto["de"] == (dt.date.today() - dt.timedelta(days=30)).isoformat()


def test_falha_do_fracttal_vira_aviso_e_nao_500(cli, monkeypatch):
    def _boom(**k):
        raise api.FracttalError("Não consegui identificar seu usuário no Fracttal (e-mail não bate no cadastro).")
    monkeypatch.setattr(api, "list_minhas_os", _boom)
    r = cli.get("/os/historico")
    assert r.status_code == 200 and "Não consegui identificar seu usuário" in r.get_data(as_text=True)


def test_detalhe_da_os_com_os_campos_do_card_do_app(cli, monkeypatch):
    det = {"folio": 9812, "descricao": "[Inversor 2.18] - Recomposição de String", "tipo": "Corretiva", "classif": "Elétrica / Strings",
           "criticidade": "Alto", "event_date": "2026-09-12T01:10:00", "data_fim": None, "responsavel": "Luiz Silva",
           "criado_por": "Levi Maia", "solicitacao": None, "os_pai": "9786", "os_pai_id": 400,
           "notas": "Strings Ipv10 e Ipv17 com corrente nula, verificar e normalizar",
           "subtarefas": [{"descricao": "Medir tensão das strings", "feito": True, "tipo": "Número", "resposta": "612", "id_tarefa": 1},
                          {"descricao": "Foto da string normalizada", "feito": False, "tipo": "Texto", "resposta": "", "id_tarefa": 1}],
           "tarefas": [{"id": 1, "titulo": "[Inversor 2.18] - Recomposição de String", "ativo": "Inversor 2.18", "tipo": "Corretiva",
                        "classif": "Elétrica", "criticidade": "Alto", "programada": "2026-09-12T08:00:00", "inicio": "", "fim": "",
                        "duracao": "5400", "gatilho": "Sem agendamento", "nota": ""}],
           "etiquetas": [{"id": 4660, "nome": "PERFORMANCE", "cor": "#8fce3f"}], "code": "TNB200-INVR2.18", "ativo": "Inversor 2.18",
           "cancel_motivo": "", "cancel_nota": ""}
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: det if wid == 501 else {})
    r = cli.get("/os/os/501")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    for txt in ("9812", "Recomposição de String", "Corretiva", "Elétrica / Strings", "Alto", "Luiz Silva", "Levi Maia",
                "9786", "Strings Ipv10 e Ipv17", "Medir tensão das strings", "612", "Foto da string normalizada", "PERFORMANCE",
                "TNB200-INVR2.18"):
        assert txt in html, txt
    assert 'href="/os/historico' in html                              # voltar


def test_detalhe_inexistente_e_404_amigavel(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {})
    r = cli.get("/os/os/999")
    assert r.status_code == 404 and "não achei" in r.get_data(as_text=True).lower()


def test_detalhe_parcial_devolve_so_o_fragmento_para_o_card(cli, monkeypatch):
    """Levi (13/09/2026): clicar no numero abre um CARD grande na propria pagina (nao uma aba/pagina nova). A rota devolve
    so o fragmento do detalhe (?parcial=1), sem o cabecalho/base, para injetar no card; e sem o 'Voltar' (o card tem o X)."""
    det = {"folio": 9812, "descricao": "[Inversor 2.18] - Recomposicao de String", "tipo": "Corretiva", "classif": "Eletrica",
           "criticidade": "Alto", "event_date": "2026-09-12T01:10:00", "data_fim": None, "responsavel": "Luiz Silva",
           "criado_por": "Levi Maia", "notas": "verificar strings", "subtarefas": [], "tarefas": [],
           "etiquetas": [{"id": 1, "nome": "PERFORMANCE", "cor": "#8fce3f"}], "code": "TNB200-INVR2.18", "ativo": "Inversor 2.18"}
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: det if wid == 501 else {})
    r = cli.get("/os/os/501?parcial=1")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "9812" in html and "Recomposicao de String" in html and "TNB200-INVR2.18" in html    # tem o conteudo do detalhe
    assert "<!doctype" not in html.lower() and "Sistema de Ordens" not in html                   # SEM o chrome do base
    assert "os-topo-voltar" not in html and "/os/historico" not in html                          # sem 'Voltar' no card


def test_historico_abre_a_os_em_card_e_nao_em_nova_aba(cli, monkeypatch):
    monkeypatch.setattr(api, "list_minhas_os", lambda modo="criadas", **k: LINHAS)
    html = cli.get("/os/historico?de=2026-09-01&ate=2026-09-12").get_data(as_text=True)
    assert "target=\"_blank\"" not in html                        # nao abre aba
    assert "id=\"os_card\"" in html and "parcial=1" in html        # o card existe e busca o fragmento
    assert "href=\"/os/os/501" in html                             # link cheio continua (fallback sem JS)


def test_card_da_os_copia_a_estrutura_do_detalhe_original(cli, monkeypatch):
    """Levi (13/09/2026, prints do app): o card tem de ser o detalhe ORIGINAL -- cabecalho com Nº + badge do tipo + pilula
    da Solicitacao; banner do ativo; datas/pessoas com avatar ao lado de DURACAO TOTAL + etiqueta; TITULO e NOTAS em caixa;
    SUBTAREFAS com barra e 'X de N concluidas'; ANEXOS DA OS em dois cards (verde/azul); REGISTRO NO FRACTTAL; rodape com
    Clonar/Fluxo/Abrir chamado/Concluir/Cancelar/Fechar."""
    det = {"folio": 13448, "descricao": "[Estrutura Trackers] - Verificacao de Tracker Parado", "tipo": "Corretiva",
           "classif": "Programada / Eletrica", "criticidade": "Alto", "event_date": "2026-09-09T09:00:00", "data_fim": None,
           "responsavel": "Marcos Duarte", "criado_por": "Levi Maia", "solicitacao": None, "os_pai": None, "notas": "",
           "subtarefas": [{"descricao": "O tracker encontra-se parado?", "feito": True, "tipo": "Sim/Nao", "resposta": "Sim"},
                          {"descricao": "Reset realizado?", "feito": False, "tipo": "Sim/Nao", "resposta": ""}],
           "tarefas": [], "etiquetas": [{"id": 1, "nome": "PERFORMANCE", "cor": "#8fce3f"}],
           "code": "SMT-TRK-B", "ativo": "Estrutura Trackers BR 101 KM 80 Sao Mateus Espirito Santo B",
           "cancel_motivo": "", "cancel_nota": ""}
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: det if wid == 777 else {})
    monkeypatch.setattr(api, "get_os_subtarefa_anexos", lambda wid: [{"value": "a.jpg"}, {"value": "b.jpg"}, {"value": "c.jpg"}])
    monkeypatch.setattr(api, "get_os_anexos", lambda wid: [{"value": "a.jpg"}, {"value": "z.pdf"}])   # a.jpg repete a subtarefa
    html = cli.get("/os/os/777?parcial=1&status=Em+Processo").get_data(as_text=True)
    # cabecalho
    assert "OS 13448" in html and 'class="det-badge"' in html and "Corretiva" in html and "criada sem solicita" in html
    # banner + duas colunas
    assert "Estrutura Trackers BR 101" in html and "DURA" in html and "OS ainda sem data de fim" in html
    assert "MD" in html and "Marcos Duarte" in html and "LM" in html and "Levi Maia" in html         # avatares (iniciais)
    assert "ETIQUETA" in html and "PERFORMANCE" in html
    # caixas, subtarefas com barra e contagem
    assert "TULO" in html and "NOTAS" in html and "SUBTAREFAS" in html and "1 de 2 conclu" in html
    assert 'style="width:50%"' in html and "O tracker encontra-se parado?" in html and "Sim/Nao" in html
    # anexos: 3 das subtarefas e 1 da OS (a.jpg deduplicado), verde e azul
    assert "ANEXOS DA OS" in html and "Anexos das subtarefas" in html and "Anexos da OS" in html
    assert 'data-anexos="/os/os/777/anexos"' in html                            # o card busca a contagem depois
    assert cli.get("/os/os/777/anexos").get_json() == {"sub": 3, "os": 1}
    # registro e rodape
    assert "REGISTRO NO FRACTTAL" in html and "Programada / Eletrica" in html and "Alto" in html
    for b in ("Clonar esta OS", "Fluxo", "Abrir chamado", "Concluir OS", "Cancelar OS", "Fechar"):
        assert b in html, b
    assert "2 subtarefa(s)" in html
    # no card (parcial) nada aponta para a pagina cheia; na pagina cheia o Fechar volta ao historico
    assert "/os/historico" not in html
    cheia = cli.get("/os/os/777").get_data(as_text=True)
    assert 'href="/os/historico"' in cheia and "Sistema de Ordens" in cheia


# ── os filtros do Historico do app (steps/historico.py), na web ─────────────────────────────────────
def test_historico_tem_os_filtros_do_app(cli, monkeypatch):
    """Levi (13/09/2026): "estou sentindo falta de todos os filtros que ja temos no historico do OS Creator". Sao eles, na
    ordem do app: as tres visoes (Historico Geral / Atribuidas a mim / Visao COS), Buscar OS pelo nº (direto), Buscar (local),
    Limpar filtros; e a grade Criado por, Etiqueta, Status, Cliente, Usina, Tipo de ativo, Tipo de tarefa, Periodo."""
    monkeypatch.setattr(api, "list_minhas_os", lambda modo="criadas", **k: LINHAS)
    html = cli.get("/os/historico?de=2026-09-01&ate=2026-09-12").get_data(as_text=True)
    for txt in ("Histórico Geral", "Atribuídas a mim", "Visão COS", "Buscar OS pelo nº", "Limpar filtros",
                "Criado por", "Etiqueta", "Status", "Cliente", "Usina", "Tipo de ativo", "Tipo de tarefa", "Período"):
        assert txt in html, txt
    assert "Todos os usuários" in html and "Luiz Silva" in html                  # pessoas (Criado por)
    assert "Todas as etiquetas" in html and "CHAMADOS" in html                     # etiquetas do catalogo
    for st in ("Em Processo", "Em Verificação", "Concluída", "Cancelada"):          # api.WO_STATUS, todos
        assert st in html
    assert "Thopen" in html and "2C" in html and "Inversor" in html                # Cliente/Usina/Tipo de ativo vem das linhas
    # cada linha leva o que os filtros locais precisam
    assert 'data-cliente="Thopen"' in html and 'data-usina="Thopen - Tanabi 2 - SP"' in html
    assert 'data-tipo="Inversor"' in html and 'data-status="Em Processo"' in html and 'data-id="501"' in html


def test_filtros_do_servidor_vao_para_a_api_como_no_app(cli, monkeypatch):
    visto = {}
    def _lista(modo="criadas", id_account=None, id_label=None, de=None, ate=None, status_ids=None, cap=2000):
        visto.update(modo=modo, id_account=id_account, id_label=id_label, status_ids=status_ids)
        return LINHAS
    monkeypatch.setattr(api, "list_minhas_os", _lista)
    cli.get("/os/historico?pessoa=88&etiqueta=12&status=Em+Processo&status=Conclu%C3%ADda&de=2026-09-01&ate=2026-09-12")
    assert visto == {"modo": "criadas", "id_account": 88, "id_label": 12, "status_ids": [1, 3]}
    cli.get("/os/historico?pessoa=TODOS")
    assert visto["id_account"] == "TODOS" and visto["id_label"] is None and visto["status_ids"] is None
    cli.get("/os/historico")                                                       # padrao do app: o usuario logado
    assert visto["id_account"] is None
    cli.get("/os/historico?modo=atribuidas&pessoa=88")                             # em Atribuidas, Criado por nao existe
    assert visto["modo"] == "atribuidas" and visto["id_account"] is None


def test_visao_cos_usa_todos_os_usuarios_e_as_colunas_do_power_bi(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "list_minhas_os", lambda modo="criadas", **k: visto.update(modo=modo, **k) or LINHAS)
    html = cli.get("/os/historico?modo=cos").get_data(as_text=True)
    assert visto["modo"] == "criadas" and visto["id_account"] == "TODOS"          # visao de EQUIPE
    for col in ("Data da programação", "Tipo de tarefa", "Equipe", "Data Início da OS", "Descrição gatilho",
                "Descrição EQP", "Nº Da OS", "Criado por"):
        assert col in html, col
    assert "Data de Criação" not in html                                            # coluna da visao padrao
    for t in api.TIPOS_COS:                                                         # tipos do COS ja marcados no filtro
        assert 'value="%s" checked' % t in html, t


def test_meta_das_tarefas_vem_depois_por_rota_json(cli, monkeypatch):
    """Como no app: tipo de tarefa/datas da tarefa chegam DEPOIS da lista (3,5 s por 60 ids no servidor)."""
    monkeypatch.setattr(api, "meta_tarefas_por_os", lambda ids: {501: {"tipo_tarefa": "Corretiva / Religamento", "inicio": "2026-09-12T08:12:00"}} if 501 in ids else {})
    r = cli.get("/os/historico/meta?ids=501,502,x")
    assert r.status_code == 200 and r.get_json() == {"501": {"tipo_tarefa": "Corretiva / Religamento", "inicio": "2026-09-12T08:12:00"}}


def test_buscar_os_pelo_numero_abre_o_detalhe_direto(cli, monkeypatch):
    det = {"folio": 9812, "descricao": "[Inversor 2.18] - Recomposicao de String", "tipo": "Corretiva", "classif": "", "criticidade": "",
           "event_date": "", "data_fim": None, "responsavel": "", "criado_por": "", "notas": "", "subtarefas": [], "tarefas": [],
           "etiquetas": [], "code": "", "ativo": "Inversor 2.18"}
    monkeypatch.setattr(api, "_wo_id_por_folio", lambda folio: 501 if str(folio) == "9812" else None)
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: det if wid == 501 else {})
    html = cli.get("/os/os/folio/9812?parcial=1").get_data(as_text=True)
    assert "OS 9812" in html and "<!doctype" not in html.lower()
    r = cli.get("/os/os/folio/1?parcial=1")
    assert r.status_code == 404 and "9812" not in r.get_data(as_text=True) and "não achei" in r.get_data(as_text=True).lower()

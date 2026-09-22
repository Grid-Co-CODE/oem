# tests/test_os_web_tickets_tela.py
"""A TELA de Tickets na web (Levi, 22/09/2026: "mas tem uma visão só para tickets que nem no OS
Creator Desktop??").

Não confundir com `test_os_web_tickets_perf.py`, que cobre a GERAÇÃO de ticket ao criar a OS.
Esta é a tela de consulta e edição — o 5º card da Performance.

FIDELIDADE: `os_web/tickets_web.py` copia as listas de apresentação do `steps/tickets.py`, que é
Qt e o servidor não pode importar. Os testes abaixo leem o código-fonte do app e falham se um lado
mudar sem o outro.

COMPORTAMENTO: o que esta tela escreve vai para planilha de produção. As recusas — campo que não
é editável, campo que não mudou, linha sem número — acontecem ANTES de qualquer chamada.
"""
import ast
import datetime as dt
import os

import pytest

import tickets_diario
import tickets_spec
from os_web import criar_app, tickets_web as tw

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator")
AGORA = dt.datetime(2026, 9, 22, 12, 0)


def _constantes(arquivo="steps/tickets.py"):
    """As constantes de modulo do app, com os NOMES resolvidos.

    `_FIXAS_DEPOIS` e `_CAMPO_DA_COLUNA` referenciam `_COL_ATIVO` e companhia em vez de repetir a
    string, entao um `literal_eval` seco falha neles. Aqui as atribuicoes sao lidas em ordem e
    cada Name ja conhecido vira o seu valor — e um Name DESCONHECIDO levanta, em vez de a trava
    de fidelidade passar a comparar com o vazio sem ninguem notar.
    """
    with open(os.path.join(_APP, arquivo), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    vals = {}

    def resolver(no):
        if isinstance(no, ast.Name):
            if no.id not in vals:
                raise AssertionError("nome nao resolvido na constante: %s" % no.id)
            return vals[no.id]
        if isinstance(no, ast.Constant):
            return no.value
        if isinstance(no, (ast.List, ast.Tuple)):
            itens = [resolver(x) for x in no.elts]
            return itens if isinstance(no, ast.List) else tuple(itens)
        if isinstance(no, ast.Dict):
            return {resolver(k): resolver(v) for k, v in zip(no.keys, no.values)}
        raise ValueError(no)

    corpo = list(arvore.body)
    corpo += [x for c in arvore.body if isinstance(c, ast.ClassDef) for x in c.body]
    for no in corpo:                            # topo do modulo e, depois, o corpo das classes
        if not isinstance(no, ast.Assign) or len(no.targets) != 1:
            continue
        alvo = no.targets[0]
        if not isinstance(alvo, ast.Name):
            continue
        try:
            vals[alvo.id] = resolver(no.value)
        except (ValueError, AssertionError):
            continue                            # lambda, f-string, chamada: nao e constante
    return vals


def _constante(nome, arquivo="steps/tickets.py"):
    vals = _constantes(arquivo)
    assert nome in vals, "%s nao encontrado em %s" % (nome, arquivo)
    return vals[nome]


# ── 1. fidelidade com o app ──────────────────────────────────────────────────────────────────
def test_colunas_iguais_as_do_app():
    assert tw.FIXAS_ANTES == _constante("_FIXAS_ANTES")
    assert tw.FIXAS_DEPOIS == _constante("_FIXAS_DEPOIS")
    assert tw.ROTULO_CAUSA == _constante("_ROTULO_CAUSA")
    assert tw.COL_ATIVO == _constante("_COL_ATIVO")
    assert tw.COL_STATUS == _constante("_COL_STATUS")


def test_status_do_ticket_iguais_aos_do_app():
    """A lista do Levi (31/08). Um status a mais de um lado e a planilha ganha valor que a outra
    tela não sabe ler."""
    assert tw.STATUS == _constante("STATUS")


def test_de_para_das_colunas_igual_ao_do_app():
    """'Status do ticket', nunca 'Status': a aba Trackers já tem uma coluna com esse nome
    ('Parado'/'Em conformidade') e escrever por cima dela apaga o filtro que separa ocorrência de
    check periódico."""
    assert tw.CAMPO_DA_COLUNA == _constante("_CAMPO_DA_COLUNA")
    assert tw.CAMPO_DA_COLUNA[tw.COL_STATUS] == "Status do ticket"


def test_campos_editaveis_iguais_aos_do_app():
    do_app = _constante("_CAMPOS_EDITAVEIS")
    assert tw.CAMPOS_EDITAVEIS == tuple(do_app)


def test_colunas_da_aba():
    assert tw.colunas_da_aba("Trackers") == ["Usina", "Cabine", "Tracker", "Ativo vinculado", "OS",
                                             "Status", "Resumo incidente", "Início da ocorrência", "Período"]
    assert tw.colunas_da_aba("Strings") == ["Usina", "Inversor", "Ativo vinculado", "OS",
                                            "Status", "Resumo incidente", "Início da ocorrência", "Período"]


# ── 2. as réguas de apresentação ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dias, texto", [
    (0, "0 dias"), (1, "1 dia"), (45, "45 dias"),
    (59, "59 dias"), (60, "2 meses"), (70, "2 meses"),
    (364, "1 ano"), (400, "1 ano e 1 mês"), (470, "1 ano e 3 meses"),
    (None, "—"), (-3, "—"),
])
def test_periodo_em_unidade_que_se_le(dias, texto):
    """O corte em 60, e não em 30: 30 é o limiar do alarme vermelho, e mudar a unidade ali faria
    "31 dias" virar "1 mês" no mesmo ponto em que a linha fica vermelha."""
    assert tw.periodo_txt(dias) == texto


def test_364_dias_nao_vira_12_meses_ao_lado_de_1_ano():
    """Uma escada só, em meses: contar o ano à parte dava "12 meses" e "1 ano" na mesma tela."""
    assert tw.periodo_txt(364) == "1 ano" and tw.periodo_txt(365) == "1 ano"


def test_so_numero_da_cabine():
    assert tw.so_numero("02") == "2"          # zero à esquerda é formatação de quem digitou
    assert tw.so_numero("01A") == "01A"       # texto passa inteiro: existe cabine "1A"
    assert tw.so_numero("") == "—"


def test_em_conformidade_nao_e_ocorrencia():
    """734 de 999 linhas da amostra são 'Em conformidade'. Sem este filtro, a régua 'Sem OS'
    contaria ~654 em vez das 236 ocorrências reais."""
    ocs, ocultas = tw.montar([{"_row": 1, "Status": "Em conformidade"},
                              {"_row": 2, "Status": "Parado", "Início da ocorrência": "2026-09-01 08:00"}])
    assert [o["_row"] for o in ocs] == [2]
    assert len(ocultas) == 1                  # guardadas, não descartadas


def test_estado_e_alarme():
    ocs, _ = tw.montar([
        {"_row": 1, "Início da ocorrência": "2026-06-05 08:00", "Status": "Parado"},
        {"_row": 2, "Início da ocorrência": "2026-09-20 08:00", "Status": "Parado"},
        {"_row": 3, "Início da ocorrência": "2026-08-01 08:00", "Fim da ocorrência": "2026-08-02 08:00"},
    ], agora=AGORA)
    e = {o["_row"]: o for o in ocs}
    assert e[1]["_estado"] == "aberta" and tw.alarme(e[1]) is True       # 109 dias
    assert e[2]["_estado"] == "aberta" and tw.alarme(e[2]) is False      # 2 dias
    assert e[3]["_estado"] == "encerrada" and tw.alarme(e[3]) is False   # encerrada nunca alarma


def test_sem_os_e_o_texto_da_celula():
    """"Sem OS" e não um traço: a ausência de OS é o estado que a tela existe para caçar."""
    ocs, _ = tw.montar([{"_row": 1, "OS": "", "Status": "Parado"}])
    assert tw.celula(ocs[0], "OS", "Trackers") == "Sem OS"
    ocs, _ = tw.montar([{"_row": 2, "OS": "13801", "Status": "Parado"}])
    assert tw.celula(ocs[0], "OS", "Trackers") == "13801"


def test_ordem_poe_a_mais_antiga_na_frente_e_a_encerrada_no_fim():
    ocs, _ = tw.montar([
        {"_row": 1, "Início da ocorrência": "2026-09-20 08:00", "Status": "Parado"},
        {"_row": 2, "Início da ocorrência": "2026-06-05 08:00", "Status": "Parado"},
        {"_row": 3, "Início da ocorrência": "2026-01-01 08:00", "Fim da ocorrência": "2026-01-02 08:00"},
    ], agora=AGORA)
    assert [o["_row"] for o in tw.ordenar(ocs)] == [2, 1, 3]


def test_filtrar_por_estado_texto_e_alarme():
    ocs, _ = tw.montar([
        {"_row": 1, "Usina": "Tupi", "Início da ocorrência": "2026-06-05 08:00", "Status": "Parado"},
        {"_row": 2, "Usina": "Araputanga", "Início da ocorrência": "2026-09-21 08:00", "Status": "Parado"},
    ], agora=AGORA)
    assert [o["_row"] for o in tw.filtrar(ocs, estado="aberta")] == [1, 2]
    assert [o["_row"] for o in tw.filtrar(ocs, busca="araputanga")] == [2]
    assert [o["_row"] for o in tw.filtrar(ocs, so_alarme=True)] == [1]
    assert tw.filtrar(ocs, busca="nada disso") == []


def test_busca_ignora_os_campos_internos():
    """`_estado`, `_dias` e afins não são dado da ocorrência: buscar "aberta" não pode casar com
    o estado calculado e devolver a lista inteira."""
    ocs, _ = tw.montar([{"_row": 1, "Usina": "Tupi", "Início da ocorrência": "2026-09-01 08:00",
                         "Status": "Parado"}], agora=AGORA)
    assert tw.filtrar(ocs, busca="aberta") == []


def test_placar_conta_os_cinco_estados():
    p = tw.placar([{"_estado": "aberta"}, {"_estado": "aberta"}, {"_estado": "encerrada"}])
    assert p == {"aberta": 2, "com_os": 0, "verificando": 0, "a_fechar": 0, "encerrada": 1}
    assert set(p) == {k for k, _r, _c in tickets_spec.ESTADOS}


# ── 3. a escrita: tudo que recusa, recusa ANTES ──────────────────────────────────────────────
def test_campo_fora_da_lista_recusa():
    oc = {"_row": 10, "Usina": "Tupi"}
    _d, erro = tw.validar_edicao("Trackers", oc, {"Usina": "Outra"})
    assert erro == tw.ERRO_CAMPO % "Usina"


def test_so_vai_o_que_mudou():
    """Reescrever o que já estava lá transforma uma edição de dois campos num carimbo sobre a
    linha inteira — inclusive sobre o que outra pessoa mudou no meio tempo."""
    oc = {"_row": 10, "Causa raiz": "fim de curso", "OS": "13801"}
    dados, erro = tw.validar_edicao("Trackers", oc, {"Causa raiz": "fim de curso", "OS": "13900"})
    assert erro == "" and dados == {"OS": "13900"}


def test_nada_mudou_recusa():
    oc = {"_row": 10, "OS": "13801"}
    _d, erro = tw.validar_edicao("Trackers", oc, {"OS": "13801"})
    assert erro == tw.ERRO_NADA_MUDOU


def test_linha_sem_numero_recusa():
    _d, erro = tw.validar_edicao("Trackers", {"OS": ""}, {"OS": "1"})
    assert erro == tw.ERRO_SEM_LINHA


def test_aba_desconhecida_recusa():
    _d, erro = tw.validar_edicao("Inversores", {"_row": 1}, {"OS": "1"})
    assert erro == tw.ERRO_ABA % "Inversores"


# ── 4. as rotas ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    import tickets_api
    import tickets_diario
    import tickets_escrita
    from os_web import rotas_tickets as rt
    app = criar_app(segredo="teste", testing=True)
    diario = []
    linha = {"Usina": "Tupi", "Nº do SKID": "02", "Nº do tracker / Identificação": "93",
             "Início da ocorrência": "2026-06-05 08:00", "Fim da ocorrência": "", "OS": "",
             "Causa raiz": "fim de curso", "Status": "Parado", "Status do ticket": "Triagem"}
    monkeypatch.setattr(tickets_api, "listar_linhas", lambda sid: [dict(linha, _row=101)])
    monkeypatch.setattr(tickets_api, "cabecalho_vivo", lambda sid, **k: list(linha))
    monkeypatch.setattr(tickets_escrita, "ler_linha", lambda sid, row, **k: dict(linha))
    monkeypatch.setattr(tickets_escrita, "gravar_linha",
                        lambda sid, row, dados, cab, **k: diario.append(("gravar", row, dados)))
    monkeypatch.setattr(tickets_diario, "ler", lambda **k: [])
    monkeypatch.setattr(tickets_diario, "aplicar", lambda a, o, r: {"aplicados": 0})
    monkeypatch.setattr(tickets_diario, "registrar",
                        lambda aba, oc, dados, **k: diario.append(("diario", oc.get("_row"), dados)))
    monkeypatch.setattr(rt, "_pode_gravar", lambda: True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Levi Maia", "email": "levi@gridco.com.br", "perfil": "ADMINISTRATOR"}
    c.diario = diario
    return c


def test_tela_abre_e_lista(cli):
    r = cli.get("/os/tickets")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert "Santa" not in h and "Tupi" in h
    assert "Sem OS" in h                        # a ocorrência sem OS aparece como tal


def test_aba_desconhecida_cai_na_padrao(cli):
    r = cli.get("/os/tickets?aba=Inversores")
    assert r.status_code == 200                 # não 500: cai em Trackers


def test_salvar_grava_e_registra_no_diario_NESTA_ordem(cli):
    """Diário depois da planilha: registrá-lo antes de saber se a gravação passou criaria um
    "restaurado" para algo que nunca chegou a existir.

    ESTE TESTE AFIRMAVA O DEFEITO até 22/09: esperava o PUT com `{"OS": "13900"}` — a linha
    PARCIAL que apagaria as outras colunas. Agora a Causa raiz (coluna de verdade) vai no PUT com a
    linha inteira; a bateria completa está em test_os_web_tickets_salvar.py."""
    r = cli.post("/os/api/tickets/Trackers/101/salvar",
                 json={"valores": {"Causa raiz": "motor queimado"}})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert [x[0] for x in cli.diario] == ["gravar", "diario"]
    linha = cli.diario[0][2]
    assert linha["Causa raiz"] == "motor queimado"
    assert linha["Usina"] == "Tupi"                        # o resto da linha NÃO foi apagado


def test_salvar_so_a_OS_vai_so_para_o_diario(cli):
    """A OS não tem coluna na planilha: regravar a linha inteira só por ela seria um PUT à toa."""
    r = cli.post("/os/api/tickets/Trackers/101/salvar", json={"valores": {"OS": "13900"}})
    assert r.status_code == 200
    assert [x[0] for x in cli.diario] == ["diario"]
    # o registro é o RETRATO inteiro (22/09): dos registros de uma linha só o mais novo vale
    reg = cli.diario[0][2]
    assert reg["OS"] == "13900" and sorted(reg) == sorted(tickets_diario.CAMPOS)


def test_salvar_campo_proibido_nao_chega_no_fracttal(cli):
    r = cli.post("/os/api/tickets/Trackers/101/salvar", json={"valores": {"Usina": "Outra"}})
    assert r.status_code == 400
    assert cli.diario == []


def test_salvar_sem_credencial_recusa(cli, monkeypatch):
    from os_web import rotas_tickets as rt
    monkeypatch.setattr(rt, "_pode_gravar", lambda: False)
    r = cli.post("/os/api/tickets/Trackers/101/salvar", json={"valores": {"OS": "13900"}})
    assert r.status_code == 403 and "leitura" in r.get_json()["erro"]
    assert cli.diario == []


def test_detalhe_traz_o_valor_CRU_e_nao_o_rotulo_da_tabela(cli):
    """A armadilha do app (steps/tickets.py:3028): a célula mostra "Sem OS"/"—"/causa truncada, e
    quem edita a partir disso grava o próprio rótulo. Foi assim que "Sem OS" virou número de OS no
    diário. O painel lê a linha CRUA."""
    r = cli.get("/os/api/tickets/Trackers/101")
    assert r.status_code == 200
    campos = {c["campo"]: c["valor"] for c in r.get_json()["campos"]}
    assert campos["OS"] == ""                   # vazio, NÃO "Sem OS"
    assert campos["Causa raiz"] == "fim de curso"

# tests/test_os_web_tickets_salvar.py
"""O Salvar da tela de Tickets na web — a correção de 22/09/2026.

A PRIMEIRA VERSÃO APAGAVA A LINHA. O `gravar_linha` faz PUT, que substitui a linha inteira, e o
`para_valores` põe "" em toda coluna que não veio. A web mandava só o que mudou. Um único Salvar
teria apagado Usina, Cliente, Supervisor e as datas da ocorrência — no banco de produção.

Não chegou a acontecer: conferido no histórico da API em 22/09 (as duas linhas suspeitas eram uma
criação e uma operação `postgres` de 09/09, antes de a tela existir). Estes testes existem para
que não aconteça depois.

O `gravar_linha` e o `para_valores` rodam DE VERDADE aqui — só o transporte HTTP é dublado. É de
propósito: o defeito morava na combinação dos dois com a rota, e dublar o `gravar_linha` inteiro
(como a primeira bateria fazia) deixava justamente o defeito de fora.
"""
import pytest

import tickets_api
import tickets_diario
import tickets_escrita
from os_web import criar_app, tickets_web as tw
from os_web import rotas_tickets as rt

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"

# o cabeçalho REAL da aba Trackers (lido em 22/09), na ordem da planilha
CABECALHO = ["Usina", "Código da usina", "Cliente", "UF", "Supervisor(a)", "Fonte", "Equipamento",
             "Status", "Responsável", "Nº do SKID", "Quantidade de trackers parados",
             "Nº do tracker / Identificação", "Inversor", "Causa raiz", "Plano de ação",
             "Responsabilidade da Grid Co.?", "Início da ocorrência",
             "Início do chamado pela Grid Co.", "Fim da ocorrência", "Indisponibilidade (horas)",
             "Indisponibilidade da Grid Co. (horas)", "Comentários para os clientes",
             "Comentários gerais"]

LINHA = {"Usina": "TIM100", "Código da usina": "TIM100", "Cliente": "Athon", "UF": "MA",
         "Supervisor(a)": "Supervisor X", "Fonte": "API PV", "Equipamento": "Tracker",
         "Status": "Parado", "Responsável": "", "Nº do SKID": "02",
         "Quantidade de trackers parados": 3, "Nº do tracker / Identificação": "93",
         "Inversor": "", "Causa raiz": "fim de curso", "Plano de ação": "",
         "Responsabilidade da Grid Co.?": "Não", "Início da ocorrência": "2026-09-01 08:00:00",
         "Início do chamado pela Grid Co.": "", "Fim da ocorrência": "",
         "Indisponibilidade (horas)": 12, "Indisponibilidade da Grid Co. (horas)": 0,
         "Comentários para os clientes": "texto para o cliente", "Comentários gerais": "nota"}


@pytest.fixture
def banco(monkeypatch):
    """Um banco de mentira com UMA linha, que o `gravar_linha` de verdade escreve por PUT."""
    estado = {"linha": dict(LINHA), "puts": [], "diario": []}

    def ler_linha(sid, row, buscar=None):
        return dict(estado["linha"])

    def transporte():
        def enviar(metodo, sid, row, corpo):
            assert metodo == "PUT"
            estado["puts"].append(corpo)
            # o PUT SUBSTITUI a linha: é exatamente o que a API faz
            estado["linha"] = dict(zip(corpo["headers"], corpo["values"]))
            return {"ok": True}
        return enviar

    monkeypatch.setattr(tickets_escrita, "ler_linha", ler_linha)
    monkeypatch.setattr(tickets_escrita, "_transporte", transporte)
    monkeypatch.setattr(tickets_escrita, "_confere_liberada", lambda sid: None)
    monkeypatch.setattr(tickets_api, "cabecalho_vivo", lambda sid, **k: list(CABECALHO))
    monkeypatch.setattr(tickets_diario, "ler", lambda **k: [])
    monkeypatch.setattr(tickets_diario, "aplicar", lambda a, o, r: {"aplicados": 0})
    monkeypatch.setattr(tickets_diario, "registrar",
                        lambda aba, oc, dados, autor=None, **k: estado["diario"].append((dados, autor)))
    monkeypatch.setattr(rt, "_pode_gravar", lambda: True)
    return estado


@pytest.fixture
def cli(banco):
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Ana Souza", "email": "ana@gridco.com.br", "perfil": "ANALISTA"}
    return c


def _originais(**muda):
    """O que o painel MOSTROU ao abrir: os valores da linha, com as datas no formato do input."""
    o = {c: ("" if LINHA.get(c) is None else str(LINHA.get(c))) for c in tw.EDITAVEIS}
    o["Início da ocorrência"] = "2026-09-01T08:00"          # datetime-local, como o navegador guarda
    o.update(muda)
    return o


def _post(cli, valores, originais=None):
    return cli.post("/os/api/tickets/Trackers/101/salvar",
                    json={"valores": valores, "originais": originais if originais is not None else _originais()})


# ── 1. o defeito: a linha inteira tem de voltar ──────────────────────────────────────────────
def test_salvar_UM_campo_preserva_TODAS_as_outras_colunas(cli, banco):
    """O teste que pegaria o defeito original: muda-se a Causa raiz e nada mais pode sumir."""
    r = _post(cli, dict(_originais(), **{"Causa raiz": "motor queimado"}))
    assert r.status_code == 200, r.get_json()
    depois = banco["linha"]
    assert depois["Causa raiz"] == "motor queimado"
    for c in ("Usina", "Cliente", "Supervisor(a)", "Início da ocorrência", "Comentários para os clientes",
              "Quantidade de trackers parados", "Nº do SKID", "Status"):
        assert str(depois[c]) == str(LINHA[c]), "a coluna %r foi apagada pelo PUT" % c


def test_o_put_leva_o_cabecalho_inteiro(cli, banco):
    _post(cli, dict(_originais(), **{"Causa raiz": "x"}))
    corpo = banco["puts"][0]
    assert corpo["headers"] == CABECALHO
    assert len(corpo["values"]) == len(CABECALHO)
    assert sum(1 for v in corpo["values"] if str(v).strip()) >= 15   # a linha veio cheia, não 1 campo


# ── 2. datas: formato do navegador × formato da planilha ─────────────────────────────────────
def test_data_nao_tocada_nao_conta_como_mudanca(cli, banco):
    """O painel devolve "2026-09-01T08:00" e a planilha guarda "2026-09-01 08:00:00". Comparando
    texto, a data parecia mudada — e seria regravada em outro formato."""
    r = _post(cli, _originais())                 # tudo exatamente como veio
    assert r.status_code == 400 and r.get_json()["erro"] == tw.ERRO_NADA_MUDOU
    assert banco["puts"] == []


def test_data_mudada_e_gravada_em_ISO(cli, banco):
    _post(cli, dict(_originais(), **{"Fim da ocorrência": "2026-09-22T17:30"}))
    assert banco["linha"]["Fim da ocorrência"] == "2026-09-22 17:30:00"
    assert banco["linha"]["Início da ocorrência"] == "2026-09-01 08:00:00"   # a outra ficou intacta


# ── 3. campos que só existem no diário ───────────────────────────────────────────────────────
def test_OS_sozinha_nao_regrava_a_linha(cli, banco):
    r = _post(cli, dict(_originais(), **{"OS": "13900", "Status do ticket": "OS Programada"}))
    assert r.status_code == 200
    assert banco["puts"] == []                                  # nenhum PUT
    reg = banco["diario"][0][0]
    assert reg["OS"] == "13900" and reg["Status do ticket"] == "OS Programada"


def test_OS_junto_com_coluna_real_nao_entra_no_put(cli, banco):
    _post(cli, dict(_originais(), **{"OS": "13900", "Causa raiz": "x"}))
    corpo = banco["puts"][0]
    assert "OS" not in corpo["headers"]                         # não existe na planilha
    reg = banco["diario"][0][0]
    assert reg["OS"] == "13900" and reg["Causa raiz"] == "x"


def test_o_registro_do_diario_e_o_RETRATO_inteiro(cli, banco):
    """Como o app de mesa (`_digitado`): todos os campos do diário, não só o que mudou. Dos
    registros de uma linha só o mais novo vale — um registro parcial apagaria da tela o resto."""
    _post(cli, dict(_originais(), **{"Causa raiz": "motor queimado"}))
    reg = banco["diario"][0][0]
    assert sorted(reg) == sorted(tickets_diario.CAMPOS)
    assert reg["Causa raiz"] == "motor queimado"
    assert reg["Início da ocorrência"] == "2026-09-01 08:00:00"    # o que não mudou vai junto
    assert reg["Comentários gerais"] == "nota"
    assert reg["Responsabilidade da Grid Co.?"] == "Não"


def test_a_OS_vinculada_antes_SOBREVIVE_a_edicao_de_outro_campo(cli, banco):
    """O caso que o registro parcial quebrava: a OS 13637 veio do diário (o ticket nasceu com ela);
    depois alguém corrige a Causa raiz. Se o registro novo não levasse a OS, ele viraria o mais
    novo da linha e a OS sumiria da tela — ela não tem coluna na planilha para voltar de lá."""
    banco["linha"].update({"OS": "13637", "Status do ticket": "OS Programada"})   # = diário aplicado
    orig = _originais(**{"OS": "13637", "Status do ticket": "OS Programada"})
    r = _post(cli, dict(orig, **{"Causa raiz": "fusível"}), originais=orig)
    assert r.status_code == 200, r.get_json()
    reg = banco["diario"][0][0]
    assert reg["OS"] == "13637" and reg["Status do ticket"] == "OS Programada"
    assert reg["Causa raiz"] == "fusível"


def test_retrato_para_diario_normaliza_as_datas():
    atual = {"Início da ocorrência": "01/09/2026 08:00", "Fim da ocorrência": None, "OS": 13637}
    r = tw.retrato_para_diario(atual, {"Causa raiz": "x"}, ["Início da ocorrência", "Fim da ocorrência",
                                                             "OS", "Causa raiz"])
    assert r == {"Início da ocorrência": "2026-09-01 08:00:00", "Fim da ocorrência": "", "OS": "13637",
                 "Causa raiz": "x"}


# ── 4. duas pessoas ──────────────────────────────────────────────────────────────────────────
def test_outra_pessoa_mudou_O_MESMO_campo_e_conflito(cli, banco):
    """Nada é gravado: o trabalho do outro sumiria sem ninguém perceber."""
    banco["linha"]["Causa raiz"] = "o outro escreveu isto"      # mudou depois que o painel abriu
    r = _post(cli, dict(_originais(), **{"Causa raiz": "eu escrevi isto"}))
    assert r.status_code == 409 and r.get_json()["conflito"] == ["Causa raiz"]
    assert banco["puts"] == [] and banco["diario"] == []
    assert banco["linha"]["Causa raiz"] == "o outro escreveu isto"


def test_outra_pessoa_mudou_OUTRO_campo_e_a_edicao_dela_FICA(cli, banco):
    """O caso que comparar com o banco de agora errava: o painel ainda mostra o comentário velho,
    e isso parecia uma edição — que sobrescreveria o comentário novo do outro com o velho."""
    banco["linha"]["Comentários gerais"] = "comentário novo do outro"
    r = _post(cli, dict(_originais(), **{"Causa raiz": "motor queimado"}))
    assert r.status_code == 200
    assert banco["linha"]["Causa raiz"] == "motor queimado"
    assert banco["linha"]["Comentários gerais"] == "comentário novo do outro"   # NÃO voltou ao velho


# ── 5. o autor no diário ─────────────────────────────────────────────────────────────────────
def test_o_diario_registra_QUEM_ESTA_LOGADO_e_nao_o_usuario_do_windows(cli, banco):
    """Na web o processo é um só para todo mundo: o usuário do Windows diria "Levi Maia" para a
    edição de qualquer pessoa, e no servidor diria o usuário do serviço."""
    _post(cli, dict(_originais(), **{"Causa raiz": "x"}))
    assert banco["diario"][0][1] == "Ana Souza"


def test_registrar_sem_autor_continua_usando_o_windows(monkeypatch):
    """O app de mesa não passa autor — e tem de seguir exatamente como antes."""
    visto = {}
    monkeypatch.setattr(tickets_diario, "garantir_aba", lambda **k: 387)
    monkeypatch.setattr(tickets_diario, "quem", lambda: "Levi Maia")

    class Esc:
        @staticmethod
        def criar_linha(sid, dados, cols, enviar=None):
            visto.update(dados)
            return {}
    monkeypatch.setattr(tickets_diario, "_esc", Esc)
    tickets_diario.registrar("Trackers", {"_row": 5, "Usina": "X"}, {"OS": "1"})
    assert visto["quem"] == "Levi Maia"
    tickets_diario.registrar("Trackers", {"_row": 5, "Usina": "X"}, {"OS": "1"}, autor="Ana Souza")
    assert visto["quem"] == "Ana Souza"


# ── 6. as regras puras ───────────────────────────────────────────────────────────────────────
def test_linha_inteira_so_poe_colunas_que_existem():
    atual = {"Usina": "A", "Causa raiz": "velha", "OS": "1"}
    linha = tw.linha_inteira(atual, {"Causa raiz": "nova", "OS": "2"}, ["Usina", "Causa raiz"])
    assert linha == {"Usina": "A", "Causa raiz": "nova"}


def test_muda_a_planilha():
    assert tw.muda_a_planilha({"Causa raiz": "x"}, CABECALHO) is True
    assert tw.muda_a_planilha({"OS": "1", "Status do ticket": "x"}, CABECALHO) is False


def test_para_iso():
    assert tw.para_iso("2026-09-21T14:30") == "2026-09-21 14:30:00"
    assert tw.para_iso("21/09/2026 14:30") == "2026-09-21 14:30:00"
    assert tw.para_iso("não é data") == "não é data"

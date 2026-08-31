"""A ocorrência que nasce junto com a OS.

Nenhum teste toca a rede: `criar` aceita `escrever` e `registrar` injetáveis. É de propósito —
teste de criação que batesse na API acabaria acrescentando linha numa planilha real no dia em
que alguém rodasse a suíte distraído.
"""
import datetime

import tickets_nasce as nasce


def _asset(nome, code="TIM100-ETKR02.129"):
    return {"id": 1, "code": code, "description": nome, "tipo": "Estrutura Trackers"}


AGORA = datetime.datetime(2026, 8, 31, 15, 30, 0)
INCIDENTE = datetime.datetime(2026, 8, 30, 8, 0, 0)


# ── de que plano nasce ocorrência ──────────────────────────────────────────────────────────
def test_reconhece_os_dois_planos():
    assert nasce.aba_do_plano("[Grid Co.] - Recomposição de String") == "Strings"
    assert nasce.aba_do_plano("[Grid Co.] - Verificação de Tracker Parado") == "Trackers"


def test_plano_que_nao_gera_ocorrencia():
    # inspeção e coleta de geração não são ocorrência de tracker nem de string
    assert nasce.aba_do_plano("[Grid Co.] - Inspeção Geral do Inversor") == ""
    assert nasce.aba_do_plano("") == ""


# ── o que vai na linha ─────────────────────────────────────────────────────────────────────
def test_tracker_separa_skid_e_numero():
    l = nasce.montar_linha("Trackers", _asset("Tracker 02.129"), "TIM100", INCIDENTE, agora=AGORA)
    assert l["Nº do SKID"] == "02"
    assert l["Nº do tracker / Identificação"] == "02.129"
    assert l["Usina"] == "TIM100"


def test_tracker_nasce_como_PARADO():
    # a coluna 'Status' da aba separa ocorrência de check periódico; sem ela a linha nasceria
    # como 'Em conformidade' e a tela nem a mostraria.
    l = nasce.montar_linha("Trackers", _asset("Tracker 02.129"), "TIM100", INCIDENTE, agora=AGORA)
    assert l["Status"] == "Parado"


def test_string_leva_o_nome_do_inversor():
    l = nasce.montar_linha("Strings", _asset("Inversor 1.1"), "PEII", INCIDENTE, agora=AGORA)
    assert l["Inversor"] == "Inversor 1.1"
    assert l["Quantidade de strings no afetadas"] == "1"


def test_a_causa_raiz_nasce_vazia():
    # quem diz a causa é o técnico, no fim da atividade — preencher aqui seria inventar
    for aba, a in (("Trackers", _asset("Tracker 02.129")), ("Strings", _asset("Inversor 1.1"))):
        assert nasce.montar_linha(aba, a, "X", INCIDENTE, agora=AGORA)["Causa raiz"] == ""


def test_as_duas_datas_sao_diferentes():
    # o incidente é quando quebrou; o chamado é agora, quando a Grid abriu a OS
    l = nasce.montar_linha("Trackers", _asset("Tracker 1.1"), "X", INCIDENTE, agora=AGORA)
    assert l["Início da ocorrência"] == "2026-08-30 08:00:00"
    assert l["Início do chamado pela Grid Co."] == "2026-08-31 15:30:00"


def test_sem_data_de_incidente_usa_agora():
    l = nasce.montar_linha("Trackers", _asset("Tracker 1.1"), "X", None, agora=AGORA)
    assert l["Início da ocorrência"] == "2026-08-31 15:30:00"


# ── a criação ──────────────────────────────────────────────────────────────────────────────
def test_cria_a_linha_e_vincula_a_OS_no_diario():
    escritas, registros = [], []
    r = nasce.criar("Trackers", _asset("Tracker 02.129"), "TIM100", "12345",
                    quando=INCIDENTE, agora=AGORA,
                    escrever=lambda sid, dados, cab: escritas.append((sid, dados)) or {"row_number": 77},
                    registrar=lambda aba, oc, vals: registros.append((aba, oc, vals)))
    assert r["ok"] and r["linha"] == 77
    assert escritas and escritas[0][0] == 123           # a aba Trackers
    aba, oc, vals = registros[0]
    assert oc["_row"] == 77
    assert vals["OS"] == "12345"
    assert vals["Status do ticket"] == "OS Programada"


def test_erro_ao_gravar_volta_como_resultado_e_nao_explode():
    # a OS é o que a equipe precisa; a linha de ticket é registro. Uma exceção aqui não pode
    # derrubar a criação da OS que já foi feita.
    def explode(*a, **k):
        raise RuntimeError("API fora do ar")
    r = nasce.criar("Trackers", _asset("Tracker 1.1"), "X", "1", agora=AGORA,
                    escrever=explode, registrar=lambda *a: None)
    assert r["ok"] is False and "API fora do ar" in r["erro"]


def test_linha_criada_mas_diario_falhou_avisa_sem_perder_a_linha():
    def explode(*a, **k):
        raise RuntimeError("sem token")
    r = nasce.criar("Strings", _asset("Inversor 1.1"), "X", "9", agora=AGORA,
                    escrever=lambda *a: {"row_number": 5}, registrar=explode)
    assert r["ok"] is True and r["linha"] == 5
    assert "não ficou vinculada" in r["aviso"]


def test_aba_desconhecida_e_recusada():
    r = nasce.criar("Inventada", _asset("x"), "X", "1", escrever=lambda *a: {}, registrar=lambda *a: None)
    assert r["ok"] is False

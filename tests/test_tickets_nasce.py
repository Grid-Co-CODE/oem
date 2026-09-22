"""A ocorrência que nasce junto com a OS.

Nenhum teste toca a rede: `criar` aceita `escrever` e `registrar` injetáveis. É de propósito —
teste de criação que batesse na API acabaria acrescentando linha numa planilha real no dia em
que alguém rodasse a suíte distraído.
"""
import datetime

import tickets_nasce as nasce
import tickets_spec


def _cab(aba):
    """A ordem das colunas, injetada. Sem ela o `criar` vai a REDE descobrir o cabecalho da aba,
    e a suite passa a depender de `app.gridco.com.br` estar no ar — foi o que aconteceu em
    11/09, com quatro testes falhando sem ninguem ter mexido neles."""
    e = tickets_spec.ABAS[aba]
    return list(tickets_spec.NUCLEO) + list(e["extras"])


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
def test_o_numero_do_tracker_e_o_NOME_INTEIRO():
    """Premissa virada em 09/09. Antes o primeiro pedaço virava skid: de 'Tracker 02.129' saía
    skid '02'. Errado — em Diamantino esse primeiro pedaço é o TRACKER e o segundo é a CABINE, e
    o índice de `steps.tickets` descartava o sufixo, então a ocorrência que o app criava nunca
    achava o próprio ativo. Agora vai o nome inteiro, que casa exato."""
    l = nasce.montar_linha("Trackers", _asset("Tracker 02.129"), "TIM100", INCIDENTE, agora=AGORA)
    assert l["Nº do tracker / Identificação"] == "02.129"
    assert l["Nº do SKID"] == "", "com duas partes não dá para saber se a 2ª é cabine ou número"
    assert l["Usina"] == "TIM100"


def test_o_skid_so_sai_quando_o_nome_tem_TRES_partes():
    """'Tracker 1.5.101' em Boa Esperança: aí o primeiro pedaço é de fato a sub-usina."""
    l = nasce.montar_linha("Trackers", _asset("Tracker 1.5.101"), "BES100", INCIDENTE, agora=AGORA)
    assert l["Nº do SKID"] == "1"
    assert l["Nº do tracker / Identificação"] == "1.5.101"


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
                    quando=INCIDENTE, agora=AGORA, cabecalho=_cab("Trackers"),
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
                    cabecalho=_cab("Trackers"), escrever=explode, registrar=lambda *a: None)
    assert r["ok"] is False and "API fora do ar" in r["erro"]


def test_linha_criada_mas_diario_falhou_avisa_sem_perder_a_linha():
    def explode(*a, **k):
        raise RuntimeError("sem token")
    r = nasce.criar("Strings", _asset("Inversor 1.1"), "X", "9", agora=AGORA,
                    cabecalho=_cab("Strings"),
                    escrever=lambda *a: {"row_number": 5}, registrar=explode)
    assert r["ok"] is True and r["linha"] == 5
    assert "não ficou vinculada" in r["aviso"]


def test_aba_desconhecida_e_recusada():
    r = nasce.criar("Inventada", _asset("x"), "X", "1", escrever=lambda *a: {}, registrar=lambda *a: None)
    assert r["ok"] is False


# ── a régua das strings (Levi, 10/09/2026) ─────────────────────────────────────────────────
# "a palavra isolada tem que vir com um número colado ou um número logo após o space".
# Os casos abaixo são os do pré-visual aprovado — os dois primeiros são os textos que a
# plataforma gera de verdade no deep link, e são justamente onde a régua ao pé da letra erra.
def test_conta_os_nomes_do_texto_da_plataforma():
    n, via, nomes = nasce.contar_strings(
        "Strings Ipv10, Ipv11 e Ipv12 com corrente nula, verificar e normalizar")
    assert (n, via) == (3, "tokens"), "a palavra 'Strings' do texto corrido não pode contar"
    assert nomes == ["Ipv10", "Ipv11", "Ipv12"], "o nome volta como foi escrito, com o prefixo"


def test_uma_string_so():
    assert nasce.contar_strings("String Ipv4 com corrente nula, verificar e normalizar")[0] == 1


def test_numero_colado_e_numero_apos_espaco_valem_igual():
    assert nasce.contar_strings("STR2 e STR7 sem corrente")[0] == 2
    assert nasce.contar_strings("String 4 e String 9 sem corrente")[0] == 2
    assert nasce.contar_strings("PV 10 apagada")[0] == 1


def test_palavra_sozinha_nao_conta():
    # sem número junto não é nome de string, é texto — cai na saída de emergência (presumido)
    assert nasce.contar_strings("strings sem corrente")[1] == "presumido"


def test_nome_repetido_conta_uma_vez():
    assert nasce.contar_strings("Ipv10 e Ipv10 de novo")[0] == 1


def test_numero_antes_da_palavra():
    n, via, _ = nasce.contar_strings("3 strings sem corrente no inversor")
    assert (n, via) == (3, "antes")


def test_sem_nada_reconhecido_fica_1_e_avisa_que_presumiu():
    # zero não pode ir para a planilha: se a OS está sendo aberta, ao menos uma string caiu
    for t in ("", "verificar o inversor amanhã", "Strings 1 a 12 sem corrente"):
        n, via, _ = nasce.contar_strings(t)
        assert (n, via) == (1, "presumido"), t


def test_o_nome_do_inversor_nao_vira_string():
    # "Inversor 2.18" no meio da observação não pode virar contagem
    assert nasce.contar_strings("Inversor 2.18 desligado")[1] == "presumido"


# ── a quantidade e a observação na linha ───────────────────────────────────────────────────
def test_quantidade_de_strings_vem_do_card_da_tela():
    l = nasce.montar_linha("Strings", _asset("Inversor 2.18"), "TNB200", INCIDENTE,
                           agora=AGORA, quantidade=6, nota="Strings Ipv10 e Ipv11")
    assert l["Quantidade de strings no afetadas"] == "6", "o card manda, não a contagem"
    assert "Quantidade de strings no inversor" not in l, "o app não sabe esse número"


def test_sem_card_a_quantidade_sai_da_observacao():
    l = nasce.montar_linha("Strings", _asset("Inversor 2.18"), "TNB200", INCIDENTE, agora=AGORA,
                           nota="Strings Ipv10, Ipv11 e Ipv12 com corrente nula")
    assert l["Quantidade de strings no afetadas"] == "3"


def test_quantidade_de_trackers_parados_e_editavel():
    l = nasce.montar_linha("Trackers", _asset("Tracker 02.129"), "TIM100", INCIDENTE,
                           agora=AGORA, quantidade=3)
    assert l["Quantidade de trackers parados"] == "3"


def test_observacao_do_ticket_cita_os_nomes_e_a_data_do_incidente():
    l = nasce.montar_linha("Strings", _asset("Inversor 2.18"), "TNB200", INCIDENTE, agora=AGORA,
                           nota="Strings Ipv10, Ipv11 e Ipv12 com corrente nula, verificar")
    assert l["Comentários gerais"] == "Ipv10, Ipv11 e Ipv12 com corrente nula em 30/08/2026 08:00"


def test_observacao_livre_vai_inteira_com_a_data():
    l = nasce.montar_linha("Trackers", _asset("Tracker 1.1"), "X", INCIDENTE, agora=AGORA,
                           nota="Travado em fim de curso")
    assert l["Comentários gerais"] == "Travado em fim de curso — em 30/08/2026 08:00"


def test_sem_observacao_a_frase_ainda_se_sustenta_sozinha():
    ls = nasce.montar_linha("Strings", _asset("Inversor 1.1"), "X", INCIDENTE, agora=AGORA,
                            quantidade=4)
    assert ls["Comentários gerais"] == "4 strings sem corrente em 30/08/2026 08:00"
    lt = nasce.montar_linha("Trackers", _asset("Tracker 1.1"), "X", INCIDENTE, agora=AGORA)
    assert lt["Comentários gerais"] == "Tracker parado em 30/08/2026 08:00"


def test_criar_devolve_a_quantidade_gravada_para_a_tela_somar():
    r = nasce.criar("Strings", _asset("Inversor 1.1"), "X", "9", quando=INCIDENTE, agora=AGORA,
                    quantidade=5, nota="", cabecalho=_cab("Strings"),
                    escrever=lambda *a: {"row_number": 5}, registrar=lambda *a: None)
    assert r["quantidade"] == 5

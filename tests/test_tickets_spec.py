"""Declaração das abas e o estado do ticket."""
from tickets_spec import ABAS, NUCLEO, ESTADOS, estado_do_ticket, linha_para_dict


def test_as_duas_abas_declaradas_com_o_sheet_id_certo():
    assert ABAS["Trackers"]["sheet_id"] == 123
    assert ABAS["Strings"]["sheet_id"] == 128


def test_nucleo_tem_as_quinze_colunas_compartilhadas():
    assert len(NUCLEO) == 15
    assert "Início da ocorrência" in NUCLEO
    assert "Fim da ocorrência" in NUCLEO
    assert "Responsabilidade da Grid Co.?" in NUCLEO


def test_extras_nao_repetem_o_nucleo():
    for aba in ABAS.values():
        assert not (set(aba["extras"]) & set(NUCLEO))


def test_linha_para_dict_casa_cabecalho_com_valor():
    d = linha_para_dict(["Usina", "Status"], ["Araputanga", "Parado"])
    assert d["Usina"] == "Araputanga"
    assert d["Status"] == "Parado"


def test_linha_para_dict_tolera_valores_a_menos():
    # a API devolve linhas curtas quando as últimas células estão vazias
    d = linha_para_dict(["Usina", "Status", "Fim da ocorrência"], ["Araputanga"])
    assert d["Usina"] == "Araputanga"
    assert d["Status"] is None
    assert d["Fim da ocorrência"] is None


def test_linha_para_dict_ignora_cabecalho_vazio():
    # a coluna A da planilha é vazia — o cabeçalho começa em B
    d = linha_para_dict(["", "Usina"], ["lixo", "Araputanga"])
    assert d == {"Usina": "Araputanga"}


def test_estado_sem_os_e_aberta():
    assert estado_do_ticket("", "", None) == "aberta"
    assert estado_do_ticket(None, None, None) == "aberta"


def test_estado_com_os_em_processo():
    assert estado_do_ticket("10847", "Em Processo", None) == "com_os"


def test_estado_em_verificacao():
    # o estado que o Levi pediu em azul: o técnico fechou, ninguém confirmou
    assert estado_do_ticket("10847", "Em Verificação", None) == "verificando"


def test_estado_concluida_sem_fim_fica_a_fechar():
    # OS concluída mas o Fim ainda não foi gravado. Na fase de leitura isso é o passivo que a
    # fase de escrita vai resolver — precisa aparecer, não ser confundido com encerrada.
    assert estado_do_ticket("10847", "Concluída", None) == "a_fechar"


def test_estado_encerrada_exige_fim_preenchido():
    assert estado_do_ticket("10847", "Concluída", "2026-08-03T11:57:43") == "encerrada"


def test_fim_preenchido_encerra_mesmo_sem_os():
    # linha antiga, de antes da integração: tem fim e nunca teve OS
    assert estado_do_ticket("", "", "2026-08-03T11:57:43") == "encerrada"


def test_fim_com_espaco_invisivel_nao_encerra():
    # célula de planilha editada à mão vem com tab ou espaço duplo. Antes isso classificava a
    # ocorrência como encerrada em silêncio: sumia da lista E da ronda do WhatsApp.
    assert estado_do_ticket("10847", "Em Processo", "   ") == "com_os"
    assert estado_do_ticket("10847", "Em Processo", "\t") == "com_os"


def test_cada_estado_tem_cor_propria():
    # com_os e a_fechar nasceram com a mesma cor e renderizariam idênticos na tela, apagando
    # justamente a distinção que faz a_fechar existir.
    cores = [c for _, _, c in ESTADOS]
    assert len(cores) == len(set(cores))

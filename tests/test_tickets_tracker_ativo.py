"""A régua que casa o tracker do ticket com o ativo do Fracttal.

O nome do ativo é "Tracker <identificação>.<sufixo de 3 dígitos>", e o sufixo é da nomenclatura
do cadastro — não faz parte da identificação (Levi, 31/08: "é normal o .101 ou .100 no fim").
Foi por não tirar esse sufixo que a primeira tentativa casou ZERO de 1.094; com ele fora, casa
540. As que sobram não são falha da régua: usina sem tracker cadastrado, ticket com texto no
lugar do número, ou número que não existe naquele cadastro.
"""
import steps.tickets as tk


def _ativo(code, nome, usina="TIM100"):
    return {"id": abs(hash(code)) % 10**7, "code": code, "description": nome,
            "tipo": "Estrutura Trackers", "usina": usina}


def _oc(trk, skid="", usina="TIM100"):
    return {"Usina": usina, "Nº do SKID": skid, "Nº do tracker / Identificação": trk}


CAT = [_ativo("TIM100-ETKR129.100", "Tracker 129.100"),
       _ativo("TIM100-ETKR01.100", "Tracker 01.100"),
       _ativo("TIM100-ETKR02.100", "Tracker 02.100"),
       _ativo("BES100-ETKR1.2.101", "Tracker 1.2.101", usina="BES100"),
       _ativo("TIM100-INVR1.1", "Inversor 1.1")]
CAT[-1]["tipo"] = "Inversor"


def _limpa():
    tk._CACHE_TRK.clear()


def test_casa_ignorando_o_sufixo_do_cadastro():
    _limpa()
    a = tk._achar_tracker(_oc("129"), CAT)
    assert a is not None and a["code"] == "TIM100-ETKR129.100"


def test_casa_mesmo_com_zero_a_esquerda_no_cadastro():
    # o cadastro escreve "Tracker 01", a planilha escreve "1"
    _limpa()
    a = tk._achar_tracker(_oc("1"), CAT)
    assert a is not None and a["code"] == "TIM100-ETKR01.100"


def test_numero_composto_do_ticket_casa_inteiro():
    # em Boa Esperança o número do ticket já vem com o skid ("1.2") e o ativo é "Tracker 1.2.101"
    _limpa()
    a = tk._achar_tracker(_oc("1.2", usina="BES100"), CAT)
    assert a is not None and a["code"] == "BES100-ETKR1.2.101"


def test_tenta_skid_mais_numero_quando_o_ticket_traz_so_o_numero():
    _limpa()
    cat = CAT + [_ativo("BES100-ETKR2.32.101", "Tracker 2.32.101", usina="BES100")]
    a = tk._achar_tracker(_oc("32", skid="2", usina="BES100"), cat)
    assert a is not None and a["code"] == "BES100-ETKR2.32.101"


def test_numero_que_nao_existe_no_cadastro_devolve_none():
    # é o caso de 483 das 1.094: fica para o vínculo manual, não vira vínculo errado
    _limpa()
    assert tk._achar_tracker(_oc("9999"), CAT) is None


def test_texto_no_lugar_do_numero_nao_casa_nada():
    # "A ser verificado" aparece de verdade na planilha
    _limpa()
    assert tk._achar_tracker(_oc("A ser verificado"), CAT) is None


def test_sem_numero_nao_casa():
    _limpa()
    assert tk._achar_tracker(_oc(""), CAT) is None
    assert tk._achar_tracker(_oc(None), CAT) is None


def test_usina_sem_tracker_cadastrado_devolve_none():
    _limpa()
    assert tk._achar_tracker(_oc("129", usina="PEIII"), CAT) is None


def test_nao_casa_com_ativo_que_nao_e_tracker():
    # o inversor do catálogo tem nome parecido e não pode entrar no índice de trackers
    _limpa()
    assert tk._achar_tracker(_oc("1.1"), CAT) is None


def test_ativo_vinculado_a_mao_vence_o_automatico():
    _limpa()
    oc = _oc("129")
    oc["Ativo"] = "TIM100-ETKR01.100"
    a = tk.ativo_da_ocorrencia("Trackers", oc, CAT)
    assert a["code"] == "TIM100-ETKR01.100"

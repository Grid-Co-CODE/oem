# tests/test_os_web_ativo_curto.py
"""O nome curto do ativo na coluna Ativo do Histórico (Levi, 27/09/2026: "algo direto, por exemplo 'Inversor 1.1',
'Tracker 1.100', 'Estação Meteorológica', 'Relé de Proteção'"). Os nomes seguem os padrões medidos no catálogo inteiro
(21.639 ativos); cidades e endereços aqui são INVENTADOS — o repositório é público."""
import pytest

from os_web import ativo_curto as ac


@pytest.mark.parametrize("nome,esperado", [
    ("Inversor 1.10 Sungrow SG125HV", "Inversor 1.10"),                 # o número fecha o nome
    ("Inversor 1.2 Huawei SUN2000-250KTL-H1", "Inversor 1.2"),
    ("Inversor 6.2 CANANDIAN SOLAR", "Inversor 6.2"),                    # até com a marca escrita errada
    ("Tracker 40.100 STI Norland STI-H250 V05", "Tracker 40.100"),
    ("Tracker 35.100 AXIALtracker", "Tracker 35.100"),                   # marca colada no nome do produto
    ("Estrutura Trackers  Cidade Teste  Estado Brasil", "Estrutura Trackers"),   # endereço depois de dois espaços
    ("Cabine 1 Rua das Flores, S/N, Centro  Estado Brasil", "Cabine 1"),
    ("Sala de O&M FZ. Boa Vista, S/N, Zona Rural", "Sala de O&M"),       # "FZ." abre o endereço; "O&M" não é modelo
    ("Sistema Supervisório SITIO BOA ESPERANÇA, CEP:00.000-000", "Sistema Supervisório"),
    ("Infraestrutura Elétrica BR 101 KM 80 Cidade Teste", "Infraestrutura Elétrica"),
    ("Módulo Fotovoltaico Risen RSM132-8-700 725BHDG", "Módulo Fotovoltaico"),
    ("Disjuntor circuito auxiliar - Ub 115 V In 6A Icu 5 kA", "Disjuntor circuito auxiliar"),
    ("Relé de Proteção Pextron URP 6000", "Relé de Proteção"),
    ("Relé da Cabine 1", "Relé da Cabine 1"),
    ("Transformador 1 WEG", "Transformador 1"),
    ("Disjuntor do Inversor (P.E.) 18.4", "Disjuntor do Inversor (P.E.) 18.4"),
    ("Estação Meteorológica", "Estação Meteorológica"),
    ("Tracker 8.9.101", "Tracker 8.9.101"),
    ("Inversor 1.1 Huawei  {TST100-INVR1.1}", "Inversor 1.1"),
    ("—", "—"), ("", "—"), (None, "—"),
])
def test_o_nome_curto(nome, esperado):
    assert ac.curto(nome) == esperado


def test_a_frase_do_tipo_corta_o_endereco_sem_marcador():
    """"Infraestrutura Civil Recanto Teste" não tem número, marca nem marcador de endereço: quem diz onde o tipo termina
    é o cadastro — ≥ 3 ativos do mesmo tipo com o nome curto "Infraestrutura Civil"."""
    cat = [{"tipo": "Infraestrutura Civil", "description": "Infraestrutura Civil  Cidade %d  Estado Brasil" % i} for i in range(4)]
    cat += [{"tipo": "Inversor", "description": "Inversor 1.%d Huawei" % i} for i in range(9)]     # número não vira frase
    fr = ac.frases(cat)
    assert fr["Infraestrutura Civil"] == ["Infraestrutura Civil"] and not fr.get("Inversor")
    assert ac.curto("Infraestrutura Civil Recanto Teste, s/n", fr["Infraestrutura Civil"]) == "Infraestrutura Civil"
    assert ac.curto("Infraestrutura Civil Recanto Teste") == "Infraestrutura Civil Recanto Teste"      # sem a frase, fica


def test_frase_rara_nao_vale():
    fr = ac.frases([{"tipo": "X", "description": "Painel Antigo"}] * 2)
    assert fr["X"] == []

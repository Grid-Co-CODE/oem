"""Ordem da lista: primeiro o que precisa de gente.

Sem isto a tela mostraria as 2.781 linhas na ordem da planilha, e as ocorrências que exigem ação
ficariam enterradas no meio das 734 'Em conformidade'."""
from steps.tickets import ordenar_ocorrencias


def _oc(estado, dias):
    return {"_estado": estado, "_dias": dias}


def test_verificando_vem_antes_de_tudo():
    r = ordenar_ocorrencias([_oc("com_os", 90), _oc("verificando", 1)])
    assert r[0]["_estado"] == "verificando"


def test_sem_os_vem_logo_depois():
    r = ordenar_ocorrencias([_oc("com_os", 90), _oc("aberta", 1), _oc("verificando", 1)])
    assert [x["_estado"] for x in r] == ["verificando", "aberta", "com_os"]


def test_dentro_do_mesmo_estado_a_mais_velha_primeiro():
    r = ordenar_ocorrencias([_oc("aberta", 3), _oc("aberta", 40), _oc("aberta", 10)])
    assert [x["_dias"] for x in r] == [40, 10, 3]


def test_encerradas_por_ultimo():
    r = ordenar_ocorrencias([_oc("encerrada", 99), _oc("com_os", 1)])
    assert r[0]["_estado"] == "com_os"

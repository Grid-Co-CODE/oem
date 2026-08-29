"""Resolução de ativo, SKID e cabine pelo catálogo do Fracttal.

Cadeias medidas no cadastro em 28/08:
  tracker  : Tracker 1.100 -> Estrutura Trackers -> Usina        (NÃO passa por cabine, sem SKID)
  inversor : Inversor 1.1 -> QGBT 1 -> SKID 1 -> Cabine 1 -> Usina

Portanto cabine e SKID existem para Strings e não existem para Trackers. Isso é o cadastro, não uma
limitação do app — e a tela precisa dizer 'não se aplica' em vez de mentir um valor."""
from tickets_ativo import cabine_de, cadeia_de_pais, indexar, skid_de

USINA = {"id": 1, "id_parent": None, "code": "2C-APG100", "tipo": "Usina",
         "description": "2C - Araputanga 1 - MT"}
ESTRUT = {"id": 2, "id_parent": 1, "code": "APG100-ETKR1", "tipo": "Estrutura Trackers",
          "description": "Estrutura Trackers Araputanga"}
TRACKER = {"id": 3, "id_parent": 2, "code": "APG100-ETKR1.100", "tipo": "Estrutura Trackers",
           "description": "Tracker 1.100 STI STI-H250"}
CABINE = {"id": 4, "id_parent": 1, "code": "APG100-CABN1", "tipo": "Cabine",
          "description": "Cabine 1 Araputanga"}
SKID = {"id": 5, "id_parent": 4, "code": "APG100-SKID1", "tipo": "Skid",
        "description": "SKID 1 Araputanga"}
QGBT = {"id": 6, "id_parent": 5, "code": "APG100-QGBT1", "tipo": "QGBT",
        "description": "QGBT 1 Araputanga"}
INVERSOR = {"id": 7, "id_parent": 6, "code": "APG100-INV1.1", "tipo": "Inversor",
            "description": "Inversor 1.1 Huawei SUN2000"}

TODOS = [USINA, ESTRUT, TRACKER, CABINE, SKID, QGBT, INVERSOR]


def test_cadeia_do_tracker_sobe_ate_a_usina():
    por_id = indexar(TODOS)
    codes = [a["code"] for a in cadeia_de_pais(TRACKER, por_id)]
    assert codes == ["APG100-ETKR1.100", "APG100-ETKR1", "2C-APG100"]


def test_tracker_nao_tem_cabine():
    # não é falha: no cadastro do Fracttal o tracker não pendura em cabine
    assert cabine_de(TRACKER, indexar(TODOS)) is None


def test_inversor_tem_cabine():
    c = cabine_de(INVERSOR, indexar(TODOS))
    assert c is not None
    assert c["code"] == "APG100-CABN1"


def test_ciclo_no_id_parent_nao_trava():
    # defensivo: cadastro com pai apontando para si mesmo não pode congelar a tela
    louco = {"id": 9, "id_parent": 9, "code": "X", "tipo": "Inversor", "description": "X"}
    assert len(cadeia_de_pais(louco, indexar([louco]))) == 1


def test_pai_inexistente_encerra_a_cadeia():
    orfao = {"id": 10, "id_parent": 999, "code": "Y", "tipo": "Inversor", "description": "Y"}
    assert [a["code"] for a in cadeia_de_pais(orfao, indexar([orfao]))] == ["Y"]


def test_ciclo_entre_dois_ativos_nao_trava():
    # cadastro de 16.289 ativos preenchido à mão: A apontando para B e B para A é possível.
    # O self-loop já tinha teste; o ciclo de dois não tinha.
    a = {"id": 20, "id_parent": 21, "code": "A", "tipo": "Inversor", "description": "A"}
    b = {"id": 21, "id_parent": 20, "code": "B", "tipo": "Inversor", "description": "B"}
    codes = [x["code"] for x in cadeia_de_pais(a, indexar([a, b]))]
    assert codes == ["A", "B"]


def test_tipo_com_caixa_e_espaco_ainda_casa():
    # o tipo é preenchido à mão. Se a comparação fosse literal, a tela diria "não se aplica"
    # para um ativo que TEM cabine — mentira pior que ausência.
    cab = {"id": 30, "id_parent": None, "code": "C", "tipo": "  CABINE  ", "description": "C"}
    inv = {"id": 31, "id_parent": 30, "code": "I", "tipo": "Inversor", "description": "I"}
    assert cabine_de(inv, indexar([cab, inv]))["code"] == "C"


def test_inversor_tem_skid():
    assert skid_de(INVERSOR, indexar(TODOS))["code"] == "APG100-SKID1"


def test_tracker_nao_tem_skid():
    # mesma razão de não ter cabine: a cadeia do tracker é Tracker -> Estrutura -> Usina
    assert skid_de(TRACKER, indexar(TODOS)) is None

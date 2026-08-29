"""Resolução de ativo e cabine pelo catálogo do Fracttal.

Cadeias medidas no cadastro em 28/08:
  tracker  : Tracker 1.100 -> Estrutura Trackers -> Usina        (NÃO passa por cabine)
  inversor : Inversor 1.1 -> QGBT 1 -> SKID 1 -> Cabine 1 -> Usina

Portanto cabine existe para Strings e não existe para Trackers. Isso é o cadastro, não uma
limitação do app — e a tela precisa dizer 'não se aplica' em vez de mentir um valor."""
from tickets_ativo import cabine_de, cadeia_de_pais, indexar

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

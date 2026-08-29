"""Casamento do nome da coluna 'Inversor' (aba Strings) com o ativo do catálogo.

Fixture montada à mão a partir de três padrões medidos no `assets_cache.json` real (16.289
ativos, rodada de revisão da Tarefa 7, 29/08):

1. JCD100: usina "limpa" (code sem prefixo de cliente) com dois inversores cujos números
   colidem por substring — 'Inversor 2.1' e 'Inversor 2.18' na MESMA usina. 250 colisões
   deste tipo em 103 usinas do catálogo real; um `in` ingênuo casaria sempre o primeiro da
   lista.
2. THPN-TNB100: usina com prefixo de cliente no code ('THPN-TNB100-INVR2.1'), formato de
   26% dos 1.710 inversores reais. A coluna 'Usina' da planilha traz o código NU ('TNB100'),
   sem o prefixo — como visto nas usinas Athon (JCD100, TIM100...) da aba Strings ao vivo.
3. Boa Esperança do Sul: usina identificada por NOME na coluna 'Usina' (não por código) —
   medido em 56 das 233 linhas reais de Strings ('Demerval Lobao', 'Santarém 1',
   'Boa Esperança do Sul 1 e 2' etc.)."""
from steps.tickets import _achar_inversor, _numero

# usina 1: JCD100, sem prefixo de cliente, com a colisão numérica 2.1 / 2.18
JCD_21 = {"id": 1, "tipo": "Inversor", "code": "JCD100-INVR2.1",
          "description": "Inversor 2.1 Sungrow { JCD100-INVR2.1 }",
          "usina": "Athon - Jacundá 1 - PA"}
JCD_218 = {"id": 2, "tipo": "Inversor", "code": "JCD100-INVR2.18",
           "description": "Inversor 2.18 Sungrow { JCD100-INVR2.18 }",
           "usina": "Athon - Jacundá 1 - PA"}
JCD_210 = {"id": 3, "tipo": "Inversor", "code": "JCD100-INVR2.10",
           "description": "Inversor 2.10 Sungrow { JCD100-INVR2.10 }",
           "usina": "Athon - Jacundá 1 - PA"}

# usina 2: THPN-TNB100, code com prefixo de cliente (THPN-) -- mesmo número (2.1) que JCD100,
# de propósito, para provar que o escopo por usina não deixa cruzar as duas
TNB_21 = {"id": 4, "tipo": "Inversor", "code": "THPN-TNB100-INVR2.1",
          "description": "Inversor 2.1 WEG { THPN-TNB100-INVR2.1 }",
          "usina": "Thopen - Tanabi 1 - SP"}

# usina 3: identificada por NOME na planilha, não por código -- o code do ativo nem contém
# "boa esperanca" em nenhum segmento
BES_11 = {"id": 5, "tipo": "Inversor", "code": "BES100-INVR1.1",
          "description": "Inversor 1.1 Growatt { BES100-INVR1.1 }",
          "usina": "Thopen - Boa Esperança do Sul 1 e 2 - SP"}

TODOS = [JCD_21, JCD_218, JCD_210, TNB_21, BES_11]


# ── _numero ──────────────────────────────────────────────────────────────────────────────
def test_numero_extrai_sequencia_com_ponto():
    assert _numero("Inversor 2.18") == "2.18"


def test_numero_sem_digito_devolve_vazio():
    assert _numero("sem número nenhum") == ""
    assert _numero(None) == ""


def test_numero_2_1_diferente_de_2_18():
    assert _numero("Inversor 2.1") != _numero("Inversor 2.18")


# ── _achar_inversor: a colisão numérica (item 1 do docstring) ──────────────────────────────
def test_achar_inversor_nao_confunde_2_1_com_2_18():
    a = _achar_inversor("Inversor 2.1", "JCD100", TODOS)
    assert a is not None and a["code"] == "JCD100-INVR2.1"


def test_achar_inversor_nao_confunde_2_18_com_2_1():
    a = _achar_inversor("Inversor 2.18", "JCD100", TODOS)
    assert a is not None and a["code"] == "JCD100-INVR2.18"


def test_achar_inversor_2_10_nao_casa_com_2_1():
    a = _achar_inversor("Inversor 2.10", "JCD100", TODOS)
    assert a is not None and a["code"] == "JCD100-INVR2.10"


# ── código com prefixo de cliente (item 2) ─────────────────────────────────────────────────
def test_achar_inversor_usina_com_prefixo_de_cliente():
    # a planilha manda o código NU ('TNB100'), sem o prefixo 'THPN-' que o code do ativo tem
    a = _achar_inversor("Inversor 2.1", "TNB100", TODOS)
    assert a is not None and a["code"] == "THPN-TNB100-INVR2.1"


def test_achar_inversor_prefixo_de_cliente_nao_cruza_usina():
    # mesmo número (2.1) existe em JCD100 (sem prefixo) -- pedir TNB100 não pode devolver o
    # inversor de JCD100
    a = _achar_inversor("Inversor 2.1", "TNB100", TODOS)
    assert a["code"] != "JCD100-INVR2.1"


# ── usina por nome, não por código (item 3) ─────────────────────────────────────────────────
def test_achar_inversor_usina_por_nome_quando_nao_e_codigo():
    a = _achar_inversor("Inversor 1.1", "Boa Esperança do Sul 1 e 2", TODOS)
    assert a is not None and a["code"] == "BES100-INVR1.1"


def test_achar_inversor_nome_parcial_tambem_casa():
    # como em steps/performance.py::_aplicar_sug_pendente: substring basta, não precisa ser
    # igual ao nome inteiro do catálogo
    a = _achar_inversor("Inversor 1.1", "Boa Esperança", TODOS)
    assert a is not None and a["code"] == "BES100-INVR1.1"


# ── casos degenerados ────────────────────────────────────────────────────────────────────
def test_achar_inversor_numero_inexistente_devolve_none():
    # JCD100 existe, mas não tem Inversor 9.9 -- 'não encontrado' é a resposta certa, não
    # um número inventado
    assert _achar_inversor("Inversor 9.9", "JCD100", TODOS) is None


def test_achar_inversor_usina_inexistente_devolve_none():
    assert _achar_inversor("Inversor 1.1", "USINA-QUE-NAO-EXISTE", TODOS) is None


def test_achar_inversor_sem_nome_devolve_none():
    assert _achar_inversor("", "JCD100", TODOS) is None


def test_achar_inversor_sem_catalogo_devolve_none():
    assert _achar_inversor("Inversor 2.1", "JCD100", []) is None

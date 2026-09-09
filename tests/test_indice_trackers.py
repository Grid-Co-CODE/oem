# -*- coding: utf-8 -*-
"""Como um ticket acha o tracker no cadastro do Fracttal.

Levi, 09/09: "essa relação entre Fracttal e supervisórios tem está na plataforma, pesquisa
direito". Estava — `plataforma/trackers_depara.xlsx`, 4.745 linhas, com a coluna
'Cabine (Fracttal)'. Ela derrubou a premissa de 31/08 ("é normal o .101 ou .100 no fim", tratado
como enfeite do cadastro e descartado antes de comparar):

- **Diamantino 1**: 'Tracker 3.100' e 'Tracker 3.101' são o tracker 3 nas CABINES 100 e 101 —
  51 trackers, duas cabines, 102 ativos. Descartando o sufixo, os dois viravam a mesma chave e o
  casamento ficava com o primeiro da lista. 21 das 91 usinas com tracker têm essa colisão.
- **MAB100**: 'Tracker 1.101', 'Tracker 1.102', 'Tracker 1.103' são o SKID 1 e os trackers 101,
  102, 103. Aqui o sufixo É a identificação, e descartá-lo perdia o casamento.

Os dois significados convivem no mesmo catálogo, então não há régua fixa para o sufixo. A saída
foi parar de interpretá-lo: o índice guarda o NOME INTEIRO, e quem decide é a forma que o ticket
usa. O miolo fica como último recurso, para a linha antiga que só traz o número.

Medido contra as 1.364 ocorrências visíveis: 670 casamentos idênticos, 6 novos, ZERO perdidos,
ZERO trocando de ativo.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from steps.tickets import _achar_tracker, _indice_trackers


def _trk(usina, nome, code):
    return {"id": abs(hash(code)) % 10**6, "code": code, "description": nome,
            "usina": usina, "cliente": "Thopen", "tipo": "Estrutura Trackers"}


# Diamantino: o sufixo é a CABINE — 3 trackers em duas cabines
DIAMANTINO = [_trk("Thopen - Diamantino 1 - MT", "Tracker %d.%d" % (n, cab),
                   "THPN-DMT100-ETKR%d.%d" % (n, cab))
              for n in (3, 10, 44) for cab in (100, 101)]

# MAB100: o sufixo é o NÚMERO do tracker, e o 1 é o skid
MAB = [_trk("Thopen - Mairi Bahia 2 - BA", "Tracker 1.%d" % n, "MAB100-ETKR1.%d" % n)
       for n in (101, 102, 103)]

# Boa Esperança: três partes — skid 1, tracker 5, cabine 101
BOA = [_trk("Thopen - Boa Esperança do Sul 1 - SP", "Tracker 1.%d.101" % n,
            "BES100-ETKR1.%d.101" % n) for n in (5, 6)]


def _oc(usina, num, skid=""):
    return {"Usina": usina, "Nº do tracker / Identificação": num, "Nº do SKID": skid}


# ── o sufixo como CABINE ──────────────────────────────────────────────────────────────────
def test_ticket_que_diz_a_cabine_casa_exato():
    """O caso que motivou tudo: a OS 13311 criou ocorrências '3.101' e elas não achavam nada."""
    for n in (3, 10, 44):
        oc = _oc("Diamantino 1", "%d.101" % n)
        achado = _achar_tracker(oc, DIAMANTINO)
        assert achado and achado["code"] == "THPN-DMT100-ETKR%d.101" % n


def test_a_outra_cabine_tambem_casa_exato():
    achado = _achar_tracker(_oc("Diamantino 1", "3.100"), DIAMANTINO)
    assert achado and achado["code"] == "THPN-DMT100-ETKR3.100"


def test_ticket_sem_cabine_cai_na_MENOR_e_nao_no_acaso():
    """A linha antiga só traz '3'. Não dá para saber a cabine — mas a escolha tem de ser sempre a
    mesma, e não "o primeiro que a lista trouxer"."""
    achado = _achar_tracker(_oc("Diamantino 1", "3"), DIAMANTINO)
    assert achado and achado["code"] == "THPN-DMT100-ETKR3.100"
    invertido = _achar_tracker(_oc("Diamantino 1", "3"), list(reversed(DIAMANTINO)))
    assert invertido["code"] == achado["code"], "a ordem da lista mudou o resultado"


# ── o sufixo como NÚMERO do tracker ───────────────────────────────────────────────────────
def test_MAB100_o_sufixo_e_o_numero_e_o_1_e_o_skid():
    """Aqui a régua antiga descartava '.102' e perdia o casamento inteiro."""
    achado = _achar_tracker(_oc("Mairi Bahia 2", "102", skid="1"), MAB)
    assert achado and achado["code"] == "MAB100-ETKR1.102"


def test_MAB100_tambem_casa_pelo_nome_inteiro():
    achado = _achar_tracker(_oc("Mairi Bahia 2", "1.102"), MAB)
    assert achado and achado["code"] == "MAB100-ETKR1.102"


# ── três partes ───────────────────────────────────────────────────────────────────────────
def test_tres_partes_casa_pelo_nome_inteiro():
    achado = _achar_tracker(_oc("Boa Esperança do Sul 1", "1.5.101"), BOA)
    assert achado and achado["code"] == "BES100-ETKR1.5.101"


def test_tres_partes_ainda_casa_por_skid_mais_numero():
    """A linha antiga escreve skid 1 e número 5 em colunas separadas."""
    achado = _achar_tracker(_oc("Boa Esperança do Sul 1", "5", skid="1"), BOA)
    assert achado and achado["code"] == "BES100-ETKR1.5.101"


# ── o índice ──────────────────────────────────────────────────────────────────────────────
def test_o_indice_guarda_o_nome_inteiro_E_o_miolo():
    idx = _indice_trackers("Diamantino 1", DIAMANTINO)
    assert "tracker 3.101" in idx, "sem o nome inteiro, quem diz a cabine não casa"
    assert "tracker 3" in idx, "sem o miolo, a linha antiga para de casar"


def test_zero_a_esquerda_do_cadastro_nao_atrapalha():
    ativos = [_trk("Usina X", "Tracker 07.100", "X-ETKR07.100")]
    for num in ("7", "07", "7.100", "07.100"):
        assert _achar_tracker(_oc("Usina X", num), ativos), "não casou com %r" % num


def test_sem_numero_no_ticket_nao_inventa():
    assert _achar_tracker(_oc("Diamantino 1", ""), DIAMANTINO) is None
    assert _achar_tracker(_oc("Diamantino 1", "A ser verificado"), DIAMANTINO) is None


def test_usina_sem_tracker_cadastrado_devolve_nada():
    assert _achar_tracker(_oc("Usina Fantasma", "3.101"), DIAMANTINO) is None

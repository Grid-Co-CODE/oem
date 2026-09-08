# -*- coding: utf-8 -*-
"""Quem é a 'Estrutura Trackers' da usina — o ativo-pai que carrega o plano.

Levi, 08/09: "não está carregando os trackers de Salto do Pirapora em performance > análise de
tracker parado mesmo tendo esses ativos criados". Estavam criados mesmo: 15 ativos, 14 trackers
individuais. O que faltava era o PAI — a régua exigia 'estrutura trackers' coladas e o ativo de
lá se chama 'Estrutura DE Trackers'. Sem o pai, `get_performance_alvos` devolve erro e a lista
abre vazia.

O outro lado da régua importa tanto quanto: quatro usinas têm 'Estrutura FIXA' e NÃO têm tracker.
Afrouxar para "tem a palavra estrutura" faria elas ganharem um pai que não existe, e a tela
ofereceria trackers de uma planta que não os tem.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import api


def _ativo(desc, tipo="Estrutura Trackers", code="X-ETKR1"):
    return {"tipo": tipo, "code": code, "label": "%s · %s" % (code, desc), "description": desc}


# ── quem É o pai ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("desc", [
    "Estrutura Trackers  Irecê  Bahia Brasil { IRC100-ETKR1 }",
    "Estrutura de Trackers      { SPP300-ETKR1 }",        # Salto Pirapora 3 — o caso do Levi
    "Estrutura de Trackers      { THPN-FZL100-ETKR1 }",   # Fazenda Limão 1
    "ESTRUTURA DE TRACKERS",
])
def test_reconhece_o_generalizado(desc):
    assert api._eh_tracker_generalizado(_ativo(desc))


# ── quem NÃO é ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("desc", [
    "Tracker 1.100 Valmont Solar TRJHT28PDR    { IRC100-ETKR1.100 }",
    "Tracker 10.100 { SPP300-ETKR10.100 }",
])
def test_tracker_individual_nao_e_o_pai(desc):
    """Se um individual passasse por pai, ele sairia da lista de alvos — o `indiv` do
    `get_performance_alvos` é justamente "todos menos o generalizado"."""
    assert not api._eh_tracker_generalizado(_ativo(desc))


@pytest.mark.parametrize("desc", [
    "Estrutura Fixa Fotovoltaica { THPN-ORB100-ETKR1 }",     # Ouro Branco 1
    "Estrutura Fixa a { THPN-SCB100-ETKR1 }",                # Sorocaba 1
    "Estrutura Fixa p { THPN-SDI100-ETKR1 }",                # Santana do Ipanema 1
])
def test_estrutura_FIXA_nao_e_tracker(desc):
    """Usina de estrutura fixa não tem tracker. Ganhar um pai aqui faria a tela oferecer
    trackers de uma planta que não os tem."""
    assert not api._eh_tracker_generalizado(_ativo(desc))


def test_tipo_errado_nunca_passa():
    assert not api._eh_tracker_generalizado(_ativo("Estrutura de Trackers", tipo="Inversor"))
    assert not api._eh_tracker_generalizado({"tipo": "Estrutura Trackers"})


# ── o efeito no fluxo ─────────────────────────────────────────────────────────────────────
def test_salto_pirapora_passa_a_listar_os_trackers(monkeypatch):
    """Ponta a ponta do `get_performance_alvos`, com o plano do Fracttal dublado: o que estava
    quebrado era achar o PAI, e é isso que se prova aqui."""
    pai = _ativo("Estrutura de Trackers      { SPP300-ETKR1 }", code="SPP300-ETKR1")
    pai["id"] = 999
    indiv = [_ativo("Tracker %d.100 { SPP300-ETKR%d.100 }" % (n, n),
                    code="SPP300-ETKR%d.100" % n) for n in range(1, 15)]
    monkeypatch.setattr(api, "get_plans_for_assets",
                        lambda alvos: [{"id_task": 7, "asset": alvos[0],
                                        "description": "[Grid Co.] - Verificação de Tracker Parado"}])
    res = api.get_performance_alvos([pai] + indiv, "verificacao de tracker parado")
    assert res.get("erro") is None, res.get("erro")
    assert res["is_tracker"] is True
    assert len(res["ativos"]) == 14, "o pai devia ficar fora da lista de alvos"
    assert all(al["plano_id_item"] == 999 for al in res["ativos"]), "o plano vem do pai"
    assert all(al["linkar"] is False for al in res["ativos"]), "tracker individual é OS avulsa"


def test_usina_de_estrutura_fixa_continua_dizendo_que_nao_achou(monkeypatch):
    monkeypatch.setattr(api, "get_plans_for_assets", lambda alvos: [])
    res = api.get_performance_alvos([_ativo("Estrutura Fixa Fotovoltaica")],
                                    "verificacao de tracker parado")
    assert res["ativos"] == [] and "Estrutura Trackers" in res["erro"]

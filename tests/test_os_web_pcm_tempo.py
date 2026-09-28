# tests/test_os_web_pcm_tempo.py
"""O que a especificação da tela PCM (tests/test_os_web_pcm.py) não cobre porque nasceu antes: o TEMPO de cada tarefa.

Desde 14–15/09 a PcmTab (steps/pcm.py) tem a coluna "Tempo" — a duração da tarefa, que vem do plano, anda de 30 em 30
min na seta e pode ser editada por linha — e o `_criar` manda `duracao` em cada seleção: None quando a pessoa não mexeu
(vale a do plano), os segundos quando mexeu. É esse número que fecha a janela da OS na agenda do técnico no Fracttal;
se a web o perdesse, a OS nasceria com outra duração e ninguém veria. Mais as regras de leitura que evitam pedir ao
Fracttal o que o app não pediria (as contagens só das linhas da tabela e só do que a tela ainda não tem)."""
import os

import pytest

import api
import os_web
from os_web import criar_app, pcm_web

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uY29tIiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"
CATALOGO = [
    {"id": 1, "code": "UA-INV1", "label": "UA-INV1 — Inversor 1", "description": "Inversor 1", "tipo": "Inversor",
     "cliente": "Cliente A", "usina": "Cliente A - Usina A - UF", "id_group_task": 5},
    {"id": 2, "code": "UA-INV2", "label": "UA-INV2 — Inversor 2", "description": "Inversor 2", "tipo": "Inversor",
     "cliente": "Cliente A", "usina": "Cliente A - Usina A - UF", "id_group_task": 5},
]


def _plano(idt, desc, fam, a):
    return {"id_task": idt, "description": desc, "family": fam, "asset": a, "asset_label": a["label"]}


PLANOS = [_plano(71, "MPM - Mensal", "MPM", CATALOGO[0]), _plano(72, "MPM - Mensal", "MPM", CATALOGO[1]),
          _plano(73, "MPA - Anual", "MPA", CATALOGO[1])]


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Pessoa Teste", "email": "teste@exemplo.com", "perfil": ""})
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: CATALOGO)
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.com", "perfil": ""}
    return c


def test_o_tempo_editado_vai_na_selecao_e_o_intocado_vai_none(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "create_planned_os_multi", lambda sel, *a, **k: visto.update(sel=sel) or {"ok": True, "os": {}, "n_criadas": 2})
    r = cli.post("/os/api/pcm/criar", json={"selecoes": [{"asset_id": 1, "id_task": 71, "event_date": "2026-09-15T07:00", "duracao": 9000},
                                                         {"asset_id": 2, "id_task": 72, "event_date": "2026-09-15T07:00", "duracao": None}],
                                            "responsavel": {"id_personnel": 5, "name": "Pessoa Teste"}})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert [s["duracao"] for s in visto["sel"]] == [9000, None]            # o `_dur_by_asset.get(aid)` do app


@pytest.mark.parametrize("dur", [-60, 86400, "1h", True])
def test_tempo_fora_do_que_o_campo_aceita_e_recusado(cli, monkeypatch, dur):
    monkeypatch.setattr(api, "create_planned_os_multi", lambda *a, **k: pytest.fail("não podia chamar a API"))
    r = cli.post("/os/api/pcm/criar", json={"selecoes": [{"asset_id": 1, "id_task": 71, "event_date": "2026-09-15T07:00", "duracao": dur}],
                                            "responsavel": {"id_personnel": 5, "name": "x"}})
    assert r.status_code == 400 and r.get_json()["erro"] == "Tempo inválido."


def test_data_com_fuso_nao_e_reinterpretada_como_brasilia():
    """'2026-09-15T07:00Z' viraria 07:00 de BRASÍLIA (três horas de diferença) se o fuso fosse trocado em silêncio."""
    _m, _a, _k, erro = pcm_web.montar_criacao({"selecoes": [{"asset_id": 1, "id_task": 71, "event_date": "2026-09-15T07:00Z"}],
                                               "responsavel": {"id_personnel": 5}}, CATALOGO)
    assert erro == "Data inválida."


def test_contagem_so_das_linhas_da_tabela_e_do_que_a_tela_nao_tem(cli, monkeypatch):
    visto = {}
    monkeypatch.setattr(api, "get_plans_for_assets", lambda assets: PLANOS)
    monkeypatch.setattr(api, "get_subtask_counts", lambda pares: visto.update(pares=pares) or {72: 4})
    monkeypatch.setattr(api, "duracao_do_plano", lambda idt, padrao=900: {72: 5400}.get(idt, padrao))
    j = cli.get("/os/api/pcm/planos?ativos=1,2&visiveis=2&conhecidos=").get_json()
    assert visto["pares"] == [(72, 2)]                                     # o 1 está marcado mas fora da tabela
    assert j["subt"] == {"72": 4} and j["dur"] == {"72": 5400}             # a duração do plano: o tempo que a linha mostra
    visto.clear()
    j = cli.get("/os/api/pcm/planos?ativos=1,2&visiveis=1,2&conhecidos=71,72").get_json()
    assert "pares" not in visto and j["subt"] == {}                        # a tela já tem: não pede de novo
    assert j["familia"] == "MPM" and j["familias"] == ["MPM", "MPA"]


def test_a_tela_tem_a_coluna_tempo_e_o_passo_de_30_minutos(cli):
    html = cli.get("/os/pcm").get_data(as_text=True)
    assert "<th class=\"c-tempo\">Tempo</th>" in html
    js = open(os.path.join(os.path.dirname(os_web.__file__), "static", "pcm.js"), encoding="utf-8").read()
    assert "const PASSO = 30, TETO = 23 * 60 + 30;" in js                  # _TempoTarefa.PASSO / TETO
    assert "A seta anda de 30 em 30 minutos." in js                        # a dica do app

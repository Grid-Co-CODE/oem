# -*- coding: utf-8 -*-
"""O JWT da pessoa não atravessava para as threads do ThreadPoolExecutor (17/09).

Sintoma em campo: na web, escolher a usina no card "Inspeção Geral do Inversor" não trazia ativo
nenhum — só o aviso "Nenhum ativo desta usina tem esse plano", sem erro.

Causa: o os_web guarda o JWT de quem está logado num `contextvars.ContextVar` (é o que permite
duas pessoas usarem o serviço ao mesmo tempo sem misturar sessão). ContextVar NÃO atravessa para
as threads de um ThreadPoolExecutor: cada worker começa num contexto vazio, `em_requisicao()`
devolve False e `_read_jwt` cai no arquivo do app de mesa — que no servidor não existe. Aí cada
chamada morre em FracttalError, que `get_plans_for_assets` engole com `return []`.

Ou seja: a lista vinha vazia e a tela dizia, com toda a calma, que a usina não tinha o plano."""
import contextvars

import pytest


@pytest.fixture
def web(monkeypatch):
    """`api` com a sessão do os_web instalada e o RPC trocado por um espião."""
    import api
    from os_web import sessao
    sessao.instalar(api)
    vistos = []

    def _rpc_falso(metodo, params=None, **kw):
        # é ISTO que o worker precisa enxergar: o token de quem abriu a requisição
        jwt = api._read_jwt()
        vistos.append(jwt)
        if not jwt:
            raise api.FracttalError("Você não está logado no Fracttal.")
        return {"data": [{"id_task": 900 + (params or {}).get("id_item", 0),
                          "task_description": "[Grid Co.] - Inspeção Geral do Inversor"}]}

    monkeypatch.setattr(api, "_rpc_call", _rpc_falso)
    return api, sessao, vistos


def test_o_jwt_da_requisicao_chega_nas_threads(web):
    """O teste que reproduz o defeito: dois ativos, duas threads, um token."""
    api, sessao, vistos = web
    ativos = [{"id": 1, "id_group_task": 1, "label": "Inversor 1"},
              {"id": 2, "id_group_task": 1, "label": "Inversor 2"}]
    with sessao.contexto("jwt-da-laura"):
        planos = api.get_plans_for_assets(ativos)
    assert vistos == ["jwt-da-laura", "jwt-da-laura"], (
        "as threads leram %r — o contexto não atravessou" % (vistos,))
    assert len(planos) == 2, "sem o token, o FracttalError é engolido e a lista volta vazia"


def test_a_tela_de_performance_acha_os_ativos_com_o_plano(web):
    """O caminho inteiro, como a rota `/api/performance/alvos` o percorre."""
    api, sessao, _ = web
    ativos = [{"id": 1, "id_group_task": 1, "tipo": "Inversor", "code": "INV1",
               "label": "INV1 — Inversor 1", "description": "Inversor 1"},
              {"id": 2, "id_group_task": 1, "tipo": "Inversor", "code": "INV2",
               "label": "INV2 — Inversor 2", "description": "Inversor 2"}]
    with sessao.contexto("jwt-da-laura"):
        res = api.get_performance_alvos(ativos, "inspecao geral do inversor")
    assert not res.get("erro"), res.get("erro")
    assert len(res.get("ativos") or []) == 2, "era este o 'Nenhum ativo desta usina tem esse plano'"


def test_fora_de_requisicao_nada_muda(web):
    """O app de mesa não tem contexto nenhum e continua lendo o token do arquivo, como sempre."""
    api, sessao, _ = web
    assert contextvars.copy_context() is not None      # só para deixar claro de onde vem o assunto
    assert not sessao.em_requisicao()

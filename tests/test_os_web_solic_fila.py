# tests/test_os_web_solic_fila.py
"""A Fila do PCM (/os/solicitacao/fila) com a lista de responsáveis no formato REAL do `api.get_responsaveis`
({code, name, id_personnel}). Até 02/10/2026 o template pedia `p.id_account` — o campo da lista de CONTAS do Histórico
(`api.get_pessoas_contas`) — e a página caía em "Internal Server Error" toda vez que o Fracttal devolvia alguém. Os
testes passavam porque todos os dublês devolviam a lista VAZIA. O id que vai ao aprovar é o `id_personnel`
(= id_responsible da OS), como no app (steps/solic_pcm.py: `cb_resp.addItem(name, id_personnel)`)."""
import re

import pytest

import api
from os_web import criar_app, rotas

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira (o oem é público)
PESSOAS = [{"code": "T1", "name": "Pessoa Teste", "id_personnel": 1414001},
           {"code": "T2", "name": "Outra Pessoa", "id_personnel": 1414002}]


@pytest.fixture
def cli(monkeypatch):
    rotas._MEMO.clear()
    monkeypatch.setattr(api, "list_minhas_solicitacoes", lambda *a, **k: [])
    monkeypatch.setattr(api, "get_responsaveis", lambda *a, **k: [dict(p) for p in PESSOAS])
    monkeypatch.setattr(api, "get_tipos_classif", lambda *a, **k: {})
    monkeypatch.setattr(api, "get_labels", lambda *a, **k: [])
    monkeypatch.setattr(api, "status_solicitacao_catalogo", lambda *a, **k: [])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    return c


def test_a_fila_abre_com_os_responsaveis_como_o_fracttal_manda(cli):
    r = cli.get("/os/solicitacao/fila")
    assert r.status_code == 200
    pessoas = re.search(r"var PESSOAS = \[(.*?)\];", r.get_data(as_text=True), re.S).group(1)
    # o id do responsável é o id_personnel, na ordem do nome
    assert pessoas == '{id: 1414002, nome: "Outra Pessoa"},{id: 1414001, nome: "Pessoa Teste"}'


def test_responsavel_sem_id_nao_derruba_a_fila(cli, monkeypatch):
    """Pessoa sem id no Fracttal fica de fora da lista (não dá para atribuir OS a ela) — a página abre."""
    monkeypatch.setattr(api, "get_responsaveis", lambda *a, **k: [dict(PESSOAS[0]), {"code": "X", "name": "Sem Id"}])
    r = cli.get("/os/solicitacao/fila")
    assert r.status_code == 200
    pessoas = re.search(r"var PESSOAS = \[(.*?)\];", r.get_data(as_text=True), re.S).group(1)
    assert pessoas == '{id: 1414001, nome: "Pessoa Teste"}'

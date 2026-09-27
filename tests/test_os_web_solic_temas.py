# -*- coding: utf-8 -*-
"""A Solicitação do OS Creator web com os temas do BANCO (27/09/2026).

O mesmo defeito do app de mesa, do lado do servidor: o `solic_web` lia só o `sp.TEMAS` do código, e o tema salvo pela
tela de Temas não chegava aqui. Na aprovação era pior que visual: um tema que só o banco tem não "existia", e a OS nascia
só com as 3 subtarefas da base, sem erro nenhum.

O servidor não tem "abertura": ele relê o banco antes das rotas da Solicitação quando o TTL vence
(`temas_store.garantir`, o mesmo desenho do `chamado_modelos_store.garantir`). Nenhum teste vai à rede: o banco é o
`_linhas` de mentira. Dado SINTÉTICO: o oem é público."""
import copy
import json
import types

import pytest

import api
import solic_spec as sp
import temas_store as ts
from os_web import criar_app

MOTIVO_NOVO = "Motivo do tema de teste"


def _tema(n, chave, **kw):
    d = {"nome": chave, "motivo": "", "classif1": "", "tipo_os": "", "tipo_equipamento": "",
         "solicitacoes": 0, "arquivado": False, "subtarefas": []}
    d.update(kw)
    return {"row_number": n, "headers": ["chave", "valor"], "values": [chave, json.dumps(d, ensure_ascii=False)]}


# o que o PCM teria salvo no app: a Vegetação com outro nome e um tema que só o banco tem
TEMAS_DO_BANCO = [
    _tema(2, "vegetacao", nome="Vegetação — nome do banco", motivo="Roçagem", solicitacoes=83,
          subtarefas=[{"desc": "Pergunta da vegetação no banco", "tipo": "texto", "anexo": False}]),
    _tema(3, "tema_teste_abertura", nome="Tema de teste da abertura", motivo=MOTIVO_NOVO, solicitacoes=5,
          subtarefas=[{"desc": "Pergunta do tema de teste", "tipo": "texto", "anexo": True}]),
]


@pytest.fixture(autouse=True)
def _temas_do_codigo():
    """Aplicar mexe no `sp.TEMAS` do processo inteiro: o tema de mentira não pode sobrar para o teste seguinte."""
    t, p = copy.deepcopy(sp.TEMAS), copy.deepcopy(sp.POR_TEMA)
    yield
    sp.TEMAS.clear()
    sp.TEMAS.update(t)
    sp.POR_TEMA.clear()
    sp.POR_TEMA.update(p)


@pytest.fixture
def banco(monkeypatch):
    """A aba `temas`, contando quantas vezes foi lida. O teste troca as linhas por uma exceção (banco fora) ou por []."""
    estado = {"linhas": list(TEMAS_DO_BANCO), "leituras": 0}

    def _linhas(buscar=None):
        estado["leituras"] += 1
        v = estado["linhas"]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(ts, "_linhas", _linhas)
    return estado


@pytest.fixture
def relogio(monkeypatch):
    """O relógio do `temas_store` e só dele: trocar o `time.time` do processo mexeria no Flask e no requests juntos."""
    agora = [1000.0]
    monkeypatch.setattr(ts, "time", types.SimpleNamespace(time=lambda: agora[0]))
    return agora


@pytest.fixture
def cli(monkeypatch):
    # o Fracttal da tela de Solicitação — catálogo, classificações e técnicos — não faz parte do que se testa aqui
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [])
    monkeypatch.setattr(api, "get_request_types", lambda *a, **k: {})
    monkeypatch.setattr(api, "get_responsaveis", lambda *a, **k: [])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = "jwt-de-teste"
        s["conta"] = {"nome": "Pessoa Teste", "email": "pessoa.teste@exemplo.com", "perfil": "ADMINISTRATOR"}
    return c


# ── a tela e a aprovação passam a ver o banco ─────────────────────────────────────────────────────────────────────
def test_a_solicitacao_web_oferece_os_temas_do_banco(cli, banco):
    html = cli.get("/os/solicitacao").get_data(as_text=True)
    assert 'value="tema_teste_abertura"' in html
    assert "Vegetação — nome do banco" in html


def test_tema_que_so_o_banco_tem_leva_as_subtarefas_dele_e_nao_so_as_da_base(cli, banco):
    """É o caminho da aprovação: sem edição do supervisor, o `api_aprovar` usa o `subtarefas_do_tema`, o mesmo desta
    rota. Antes, `sp.existe` respondia que o tema não existia e a OS nascia só com as 3 da base."""
    subs = cli.get("/os/api/solic/subtarefas?tema=tema_teste_abertura").get_json()["subtarefas"]
    assert subs[0] == {"tipo": "texto", "desc": "Pergunta do tema de teste", "anexo": True}


# ── banco fora do ar, TTL e a troca sem buraco ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("resposta", [ConnectionError("banco fora de teste"), []], ids=["fora", "vazio"])
def test_sem_banco_a_solicitacao_web_abre_com_o_codigo_intacto(cli, banco, resposta):
    """Sem reaplicar a semente, que não guarda o `obrig`: a opcional da Vegetação não vira obrigatória por uma queda."""
    banco["linhas"] = resposta
    temas, passos = copy.deepcopy(sp.TEMAS), copy.deepcopy(sp.POR_TEMA)
    assert cli.get("/os/solicitacao").status_code == 200
    assert sp.TEMAS == temas and sp.POR_TEMA == passos


def test_o_servidor_rele_o_banco_so_quando_o_ttl_vence(cli, banco, relogio):
    for _ in range(3):
        cli.get("/os/api/solic/subtarefas")
    assert banco["leituras"] == 1                    # dentro do TTL: uma leitura para todas as requisições
    relogio[0] += ts.TTL + 1
    cli.get("/os/api/solic/subtarefas")
    assert banco["leituras"] == 2                    # e a edição feita no app chega sem reiniciar o servidor


def test_banco_fora_custa_uma_espera_por_janela_e_nao_uma_por_requisicao(cli, banco, relogio):
    banco["linhas"] = ConnectionError("banco fora de teste")
    for _ in range(3):
        cli.get("/os/api/solic/subtarefas")
    assert banco["leituras"] == 1
    relogio[0] += ts.TTL_ERRO + 1                    # e volta a tentar antes do TTL cheio
    cli.get("/os/api/solic/subtarefas")
    assert banco["leituras"] == 2


def test_trocar_os_temas_nunca_mostra_a_lista_vazia_nem_tema_sem_subtarefas(monkeypatch):
    """O os_web lê `sp.TEMAS` de várias threads. Quem lê pega a chave em `TEMAS` e depois vai ao `POR_TEMA`; um
    `clear()` antes do `update()` deixava um instante com a lista vazia — a página sairia sem tema nenhum, ou o
    `sp.subtarefas(tema)` levantaria "tema desconhecido" no meio de uma aprovação."""
    vistos = []

    class Vigia(dict):
        """Anota, a cada mudança, o que uma requisição lendo em paralelo veria naquele instante."""
        def _ver(self):
            vistos.append((len(sp.TEMAS), set(sp.TEMAS) <= set(sp.POR_TEMA)))

        def update(self, *a, **k):
            super().update(*a, **k)
            self._ver()

        def clear(self):
            super().clear()
            self._ver()

        def __setitem__(self, k, v):
            super().__setitem__(k, v)
            self._ver()

        def __delitem__(self, k):
            super().__delitem__(k)
            self._ver()

        def pop(self, *a):
            v = super().pop(*a)
            self._ver()
            return v
    monkeypatch.setattr(sp, "TEMAS", Vigia(sp.TEMAS))
    monkeypatch.setattr(sp, "POR_TEMA", Vigia(sp.POR_TEMA))
    # o banco tira os dez do código (só a Vegetação volta, arquivada) e traz um novo: entra um, saem dez
    itens = ts.carregar(buscar=lambda: [TEMAS_DO_BANCO[1], _tema(2, "vegetacao", arquivado=True)])
    assert ts.aplicar_no_spec(itens)
    assert list(sp.TEMAS) == ["tema_teste_abertura"]
    assert vistos and all(n > 0 and cabe for n, cabe in vistos), vistos

# tests/test_chamados_obs_store.py
"""As observações da equipe de chamados no banco (27/09/2026): uma linha por observação, só POST, com a data e a hora
do SERVIDOR — "essas observações vão salvar o dia que a Singrid escreveu"."""
import datetime as dt
import json

import pytest

import chamados_obs_store as cos
import gridco_abas as ga

BRT = dt.timezone(dt.timedelta(hours=-3))
# a escrita real, guardada na coleta — o conftest troca `ga.escrever` por uma que falha durante cada teste
ESCREVER_REAL = ga.escrever


@pytest.fixture
def banco(monkeypatch):
    """A aba já existe (id 900); guarda o que foi escrito e devolve na leitura."""
    estado = {"escritas": [], "linhas": []}

    def _get(caminho, params=None):
        assert caminho == "/api/sheets"
        return [{"id": 900, "workbook_key": "os_creator", "sheet_name": "chamados_obs"}]

    def _escrever(metodo, caminho, corpo):
        estado["escritas"].append((metodo, caminho, corpo))
        estado["linhas"].append({"row_number": len(estado["linhas"]) + 2, "headers": corpo["headers"],
                                 "values": corpo["values"]})
        return {}
    monkeypatch.setattr(ga, "_get", _get)
    monkeypatch.setattr(ga, "escrever", _escrever)
    monkeypatch.setattr(cos, "_linhas", lambda: list(estado["linhas"]))
    return estado


def test_a_observacao_leva_a_data_do_servidor_e_o_autor(banco):
    agora = dt.datetime(2026, 9, 27, 10, 32, 5, tzinfo=BRT)
    reg = cos.adicionar(13926, "  Aberto no portal; a Huawei pediu o log.  ", ativo="THPN-STA100-INVR1.4",
                        quem="Analista Teste", email="analista@teste.invalid", agora=agora)
    metodo, caminho, corpo = banco["escritas"][0]
    assert (metodo, caminho) == ("POST", "/api/sheets/900/rows")
    assert corpo["headers"] == cos.COLUNAS
    linha = dict(zip(corpo["headers"], corpo["values"]))
    assert linha["quando"] == "2026-09-27T10:32:05-03:00" and linha["os"] == "13926" and linha["tipo"] == "obs"
    assert linha["texto"] == "Aberto no portal; a Huawei pediu o log." and linha["quem"] == "Analista Teste"
    assert json.loads(linha["extra"]) == {} and len(linha["id"]) == 12 and reg["id"] == linha["id"]


def test_sem_hora_informada_a_hora_e_a_de_brasilia(banco):
    reg = cos.adicionar(1, "x")
    assert reg["quando"].endswith("-03:00")


@pytest.mark.parametrize("texto,tipo,erro", [("", "obs", "Escreva"), ("   ", "obs", "Escreva"),
                                             ("x" * 2001, "obs", "2000"), ("ok", "status", "desconhecido")])
def test_recusa_sem_ir_ao_banco(banco, texto, tipo, erro):
    with pytest.raises(ValueError) as e:
        cos.adicionar(1, texto, tipo)
    assert erro in str(e.value) and banco["escritas"] == []


def test_sem_credencial_diz_o_que_e(monkeypatch):
    """Sem token a escrita NEM TENTA — a API responderia 401 e a tela diria "falha de rede"."""
    monkeypatch.setattr(ga, "_get", lambda c, params=None: [{"id": 900, "workbook_key": "os_creator", "sheet_name": "chamados_obs"}])
    monkeypatch.setattr(ga, "escrever", ESCREVER_REAL)          # a de verdade: tem de parar antes da rede
    monkeypatch.setattr(ga, "token", lambda: "")
    with pytest.raises(ga.SemCredencial):
        cos.adicionar(1, "x")


def test_a_leitura_ordena_tira_duplicata_e_separa_por_os(banco, monkeypatch):
    L = [{"row_number": 2, "headers": cos.COLUNAS, "values": ["b", "2026-09-26T09:15:00-03:00", "13926", "", "obs", "segunda", "S", "", "{}"]},
         {"row_number": 3, "headers": cos.COLUNAS, "values": ["a", "2026-09-26T09:12:00-03:00", "13926", "", "ticket", "Ticket registrado: 1", "S", "", ""]},
         {"row_number": 4, "headers": cos.COLUNAS, "values": ["a", "2026-09-26T09:12:00-03:00", "13926", "", "ticket", "dup", "S", "", ""]},
         {"row_number": 5, "headers": cos.COLUNAS, "values": ["c", "2026-09-20T08:00:00-03:00", "13732", "", "finalizado", "Chamado finalizado", "S", "", ""]},
         {"row_number": 6, "headers": cos.COLUNAS, "values": ["", "2026-09-20T08:00:00-03:00", "1", "", "obs", "sem id", "", "", ""]}]
    monkeypatch.setattr(cos, "_linhas", lambda: L)
    lista = cos.listar(forcar=True)
    assert [x["id"] for x in lista] == ["c", "a", "b"]
    assert [x["texto"] for x in cos.do_os(13926)] == ["Ticket registrado: 1", "segunda"]
    assert cos.ultima_por_os() == {"13926": "2026-09-26T09:15:00-03:00", "13732": "2026-09-20T08:00:00-03:00"}
    assert cos.finalizado_por_os() == {"13732": "2026-09-20T08:00:00-03:00"}


def test_a_propria_escrita_entra_na_leitura_sem_ir_ao_banco(banco, monkeypatch):
    cos.listar(forcar=True)
    monkeypatch.setattr(cos, "_linhas", lambda: (_ for _ in ()).throw(AssertionError("não devia reler")))
    cos.adicionar(5, "nova")
    assert [x["texto"] for x in cos.do_os(5)] == ["nova"]

# tests/test_chamado_modelos_store.py
"""Os modelos da inspeção de chamado no banco (Controle de fornecedores, 27/09/2026).

O que se trava aqui: o código é a semente e a rede de segurança; o bloco do banco vale POR CIMA, em memória e NO LUGAR
(o `chamado_insp_spec` segura as mesmas listas); o clone segue o original até ser salvo sozinho; arquivar tira da
escolha; salvar relê e confere a versão antes de gravar. O conftest devolve o pacote ao código em volta de cada teste."""
import json

import pytest

import chamado_insp_spec as ci
import chamado_modelos_store as cms
import chamado_spec as cs
import gridco_abas as ga
from chamado_garantia import spec as sp


def _sub(desc, tipo="texto", **k):
    return dict({"desc": desc, "tipo": tipo, "obrig": True, "anexo": False, "opcoes": [], "chave": "", "so_para": []}, **k)


def _n_codigo(tipo, marca):
    return len(ci.subtarefas(tipo, marca))


# ── a semente ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_semente_e_o_codigo():
    s = cms.semente()
    assert [x["desc"] for x in s["BASE"]["subtarefas"]] == [x["desc"] for x in sp.BASE]
    assert set(k[5:] for k in s if k.startswith("TIPO:")) == set(sp.POR_TIPO)
    assert s["MARCA:STI"]["atende"] == sorted(sp.TIPOS_DA_MARCA["STI"])
    assert s["MARCA:Huawei"]["canal"] == cs.CANAL["Huawei"]
    assert s["MARCA:Brametal"]["igual_a"] == "STI" and s["MARCA:STI"]["igual_a"] == ""
    # so_para sai como lista (JSON não tem set) e volta como set para o pacote
    assert s["MARCA:STI"]["subtarefas"][0]["so_para"] == ["Estrutura Trackers"]
    assert cms.de_json(s["MARCA:STI"]["subtarefas"][0])["so_para"] == {"Estrutura Trackers"}


def test_sem_banco_a_inspecao_e_a_do_codigo():
    esperado = len(sp.BASE) + len(sp.POR_TIPO["Inversor"]) + len(sp.POR_FABRICANTE["Canadian Solar"])
    cms.aplicar({})
    assert _n_codigo("Inversor", "Canadian Solar") == esperado


# ── o banco por cima ──────────────────────────────────────────────────────────────────────────────────────────
def test_o_bloco_do_banco_vale_por_cima_e_no_lugar():
    lista_antes, canal_antes = ci.POR_FABRICANTE, cs.CANAL
    base = len(sp.BASE) + len(sp.POR_TIPO["Inversor"])
    cms.aplicar({"MARCA:Canadian Solar": {"subtarefas": [_sub("Foto do QR do datalogger", anexo=True)],
                                          "canal": "portal novo", "atende": ["Inversor"]}})
    assert _n_codigo("Inversor", "Canadian Solar") == base + 1
    assert ci.subtarefas("Inversor", "Canadian Solar")[-1]["attachments_required"] is True
    assert cs.CANAL["Canadian Solar"] == "portal novo"
    # os nomes que a ponte importou continuam apontando para os MESMOS objetos
    assert ci.POR_FABRICANTE is lista_antes is sp.POR_FABRICANTE and cs.CANAL is canal_antes


def test_a_base_do_banco_muda_toda_inspecao():
    cms.aplicar({"BASE": {"subtarefas": [_sub("Pergunta única da base")]}})
    for tipo, marca in (("Inversor", "Huawei"), ("Estrutura Trackers", "STI"), ("NCU", "STI")):
        assert ci.subtarefas(tipo, marca)[0]["description"] == "Pergunta única da base"


def test_arquivar_tira_da_escolha():
    assert "Trina" in ci.marcas_para("Estrutura Trackers")
    cms.aplicar({"MARCA:Trina": {"subtarefas": [], "atende": ["Estrutura Trackers"], "arquivado": True}})
    assert "Trina" not in ci.marcas_para("Estrutura Trackers")


def test_fornecedor_novo_aparece_para_o_tipo_e_e_reconhecido_no_texto():
    cms.aplicar({"MARCA:Fornecedor Teste": {"subtarefas": [_sub("Código do teste")], "atende": ["Inversor"],
                                            "canal": "e-mail de teste"}})
    assert "Fornecedor Teste" in ci.marcas_para("Inversor")
    assert "Fornecedor Teste" not in ci.marcas_para("NCU")
    assert ci.marca_do_ativo({"description": "Inversor 9.9 Fornecedor Teste X1"}) == "Fornecedor Teste"
    assert ci.subtarefas("Inversor", "Fornecedor Teste")[-1]["description"] == "Código do teste"


def test_o_clone_segue_o_original_ate_ser_salvo_sozinho():
    banco = {"MARCA:STI": {"subtarefas": [_sub("Só da STI")], "atende": ["Estrutura Trackers", "NCU", "RSU"]}}
    cms.aplicar(banco)
    assert ci.subtarefas("Estrutura Trackers", "Brametal") == ci.subtarefas("Estrutura Trackers", "STI")
    banco["MARCA:Brametal"] = {"subtarefas": [_sub("Só da Brametal")], "atende": ["Estrutura Trackers"]}
    cms.aplicar(banco)
    assert ci.subtarefas("Estrutura Trackers", "Brametal")[-1]["description"] == "Só da Brametal"
    assert ci.subtarefas("Estrutura Trackers", "STI")[-1]["description"] == "Só da STI"
    assert cms.efetivo(banco)["MARCA:Brametal"]["igual_a"] == ""


def test_voltar_ao_codigo_desfaz_tudo():
    antes = {(t, m): _n_codigo(t, m) for t in sp.POR_TIPO for m in ci.marcas_para(t)}
    cms.aplicar({"BASE": {"subtarefas": [_sub("x")]}, "MARCA:STI": {"subtarefas": [], "atende": ["NCU"]}})
    cms.aplicar({})
    assert {(t, m): _n_codigo(t, m) for t in sp.POR_TIPO for m in ci.marcas_para(t)} == antes


# ── leitura ───────────────────────────────────────────────────────────────────────────────────────────────────
def _linha(n, chave, valor):
    return {"row_number": n, "headers": ["chave", "valor"],
            "values": [chave, valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)]}


def test_linha_ilegivel_e_chave_estranha_sao_puladas(monkeypatch):
    monkeypatch.setattr(cms, "_linhas", lambda: [_linha(2, "MARCA:STI", "{quebrado"), _linha(3, "LIXO", {"subtarefas": []}),
                                                 _linha(4, "TIPO:Inexistente", {"subtarefas": []}),
                                                 _linha(5, "MARCA:Huawei", {"subtarefas": [], "versao": "v1"})])
    banco = cms.carregar(forcar=True)
    assert list(banco) == ["MARCA:Huawei"] and banco["MARCA:Huawei"]["_linha"] == 5


def test_garantir_nao_levanta_com_o_banco_fora(monkeypatch):
    def _fora():
        raise ConnectionError("banco fora")
    monkeypatch.setattr(cms, "_linhas", _fora)
    antes = _n_codigo("Inversor", "Huawei")
    cms.garantir()
    assert "banco fora" in cms._estado["erro"] and _n_codigo("Inversor", "Huawei") == antes


def test_garantir_so_rele_depois_do_ttl(monkeypatch):
    chamadas = []
    monkeypatch.setattr(cms, "_linhas", lambda: chamadas.append(1) or [])
    cms.garantir()
    cms.garantir()
    assert len(chamadas) == 1


# ── validação ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("chave,dados,trecho", [
    ("MARCA:X", {"subtarefas": [_sub("  ")], "atende": ["Inversor"]}, "vazia"),
    ("MARCA:X", {"subtarefas": [_sub("Cor", "lista", opcoes=["Azul"])], "atende": ["Inversor"]}, "duas opções"),
    ("MARCA:X", {"subtarefas": [_sub("A"), _sub("a")], "atende": ["Inversor"]}, "duas vezes"),
    ("MARCA:X", {"subtarefas": [_sub("A", "data")], "atende": ["Inversor"]}, "Tipo desconhecido"),
    ("MARCA:X", {"subtarefas": [], "atende": []}, "tipo de ativo"),
    ("MARCA:X", {"subtarefas": [_sub("A", so_para=["NCU"])], "atende": ["Inversor"]}, "não atende"),
    ("BASE", {"subtarefas": []}, "pelo menos uma"),
    ("TIPO:Tracker", {"subtarefas": []}, "desconhecido"),
    ("MARCA:A:B", {"subtarefas": [], "atende": ["Inversor"]}, "desconhecido"),
])
def test_a_regua_recusa(chave, dados, trecho):
    valor, erro = cms.normalizar(chave, dados)
    assert valor is None and trecho in erro


def test_a_regua_limpa_o_que_aceita():
    valor, erro = cms.normalizar("TIPO:Inversor", {"subtarefas": [
        _sub("  Nº   de série ", chave="Serial!", so_para=["Inversor"]),
        _sub("Cor", "lista", opcoes=[" Azul", "azul", "Verde", ""])]})
    assert erro == ""
    s0, s1 = valor["subtarefas"]
    assert s0["desc"] == "Nº de série" and s0["chave"] == "serial" and s0["so_para"] == []   # só fornecedor tem so_para
    assert s1["opcoes"] == ["Azul", "Verde"]


# ── escrita ───────────────────────────────────────────────────────────────────────────────────────────────────
class _BancoFalso:
    """Uma aba de mentira: o que `inserir`/`trocar` gravam, `_linhas` devolve na próxima leitura."""

    def __init__(self, monkeypatch, linhas=None):
        self.linhas, self.escritas = list(linhas or []), []
        monkeypatch.setattr(cms, "_linhas", lambda: [dict(l) for l in self.linhas])
        monkeypatch.setattr(cms.ABA, "inserir", self.inserir)
        monkeypatch.setattr(cms.ABA, "trocar", self.trocar)
        monkeypatch.setattr(ga, "pode_gravar", lambda: True)

    def inserir(self, dados):
        self.escritas.append(("POST", None, dados))
        self.linhas.append(_linha(len(self.linhas) + 2, dados["chave"], dados["valor"]))

    def trocar(self, row, dados):
        self.escritas.append(("PUT", row, dados))
        self.linhas = [(_linha(row, dados["chave"], dados["valor"]) if l["row_number"] == row else l) for l in self.linhas]


def test_salvar_bloco_novo_insere_e_vale_na_hora(monkeypatch):
    db = _BancoFalso(monkeypatch)
    valor = cms.salvar("MARCA:Huawei", {"subtarefas": [_sub("Print do SmartLogger", anexo=True)], "atende": ["Inversor"],
                                        "canal": "Portal"}, "", "Levi Maia")
    assert db.escritas[0][0] == "POST" and db.escritas[0][2]["chave"] == "MARCA:Huawei"
    gravado = json.loads(db.escritas[0][2]["valor"])
    assert gravado["por"] == "Levi Maia" and gravado["versao"] == valor["versao"] and gravado["canal"] == "Portal"
    assert ci.subtarefas("Inversor", "Huawei")[-1]["description"] == "Print do SmartLogger"


def test_salvar_confere_a_versao_e_troca_a_linha_certa(monkeypatch):
    db = _BancoFalso(monkeypatch, [_linha(7, "MARCA:Huawei", {"subtarefas": [], "atende": ["Inversor"],
                                                              "versao": "2026-09-27T10:00:00-03:00", "por": "Ana"})])
    with pytest.raises(cms.Conflito) as e:
        cms.salvar("MARCA:Huawei", {"subtarefas": [], "atende": ["Inversor"]}, "", "Levi Maia")
    assert "Ana" in str(e.value) and db.escritas == []
    cms.salvar("MARCA:Huawei", {"subtarefas": [], "atende": ["Inversor"]}, "2026-09-27T10:00:00-03:00", "Levi Maia")
    assert db.escritas[0][:2] == ("PUT", 7)


def test_salvar_sem_credencial_nem_tenta(monkeypatch):
    db = _BancoFalso(monkeypatch)
    monkeypatch.setattr(ga, "pode_gravar", lambda: False)
    with pytest.raises(cms.SemCredencial):
        cms.salvar("MARCA:Huawei", {"subtarefas": [], "atende": ["Inversor"]}, "", "x")
    assert db.escritas == []


def test_salvar_recusa_o_invalido_antes_de_ir_ao_banco(monkeypatch):
    db = _BancoFalso(monkeypatch)
    with pytest.raises(ValueError):
        cms.salvar("BASE", {"subtarefas": []}, "", "x")
    assert db.escritas == []


def test_a_aba_nasce_com_as_colunas_certas(monkeypatch):
    """Sem a aba no banco, a primeira escrita cria — com a largura que ela vai ter para sempre."""
    feitas = []
    monkeypatch.setattr(ga, "_get", lambda caminho, params=None: [])
    monkeypatch.setattr(ga, "token", lambda: "tok")
    monkeypatch.setattr(ga, "escrever", lambda m, c, corpo: feitas.append((m, c, corpo)) or {"id": 812})
    cms.ABA.inserir({"chave": "BASE", "valor": "{}"})
    assert feitas[0] == ("POST", "/api/workbooks/os_creator/sheets", {"sheet_name": "chamado_modelos", "headers": ["chave", "valor"]})
    assert feitas[1][:2] == ("POST", "/api/sheets/812/rows") and feitas[1][2]["values"] == ["BASE", "{}"]

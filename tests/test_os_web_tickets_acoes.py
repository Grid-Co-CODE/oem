# tests/test_os_web_tickets_acoes.py
"""Tickets: EXCLUIR, VINCULAR OS e TROCAR A USINA (Levi, 22/09/2026).

Os três escrevem em produção, e cada um tem uma trava que a tela sozinha não dá:

· EXCLUIR confere a IMPRESSÃO da linha (usina + ativo) antes de apagar. Se alguém apagou uma linha
  acima nesse meio-tempo, os números descem — e "apagar a 101" apagaria a ocorrência de baixo.
· VINCULAR busca a OS inteira para ter a data de CRIAÇÃO e o status: a busca por número não traz
  nenhum dos dois (traz a data do SERVIÇO — 5 dias de diferença na OS 9208).
· TROCAR A USINA só aceita um nome que EXISTA no cadastro do Fracttal, grava a linha INTEIRA com
  só a Usina trocada, e pula (contando) a linha que já não tem o nome antigo.

O transporte HTTP é dublado; `gravar_linha`, `para_valores` e as regras rodam de verdade.
"""
import pytest

import api
import tickets_api
import tickets_diario
import tickets_escrita
from os_web import criar_app, tickets_web as tw
from os_web import rotas_tickets as rt

JWT = "aaa.eyJlbWFpbCI6ImxldmlAZ3JpZGNvLmNvbS5iciIsImV4cCI6OTk5OTk5OTk5OX0.sig"
CAB = ["Usina", "Cliente", "Status", "Nº do SKID", "Nº do tracker / Identificação", "Causa raiz",
       "Início da ocorrência", "Fim da ocorrência"]


def _linha(row, usina="PEIII", skid="02", trk="14", status="Parado"):
    return {"_row": row, "Usina": usina, "Cliente": "Axis", "Status": status, "Nº do SKID": skid,
            "Nº do tracker / Identificação": trk, "Causa raiz": "fim de curso",
            "Início da ocorrência": "2025-06-01 00:00:00", "Fim da ocorrência": ""}


CATALOGO = [{"usina": "Axis - Petrolina 2 - PE", "cliente": "Axis", "code": "AXS-PTL200-TRK1"},
            {"usina": "Axis - Petrolina 3 - PE", "cliente": "Axis", "code": "AXS-PTL300-TRK1"}]


@pytest.fixture
def banco(monkeypatch):
    estado = {"linhas": {101: _linha(101), 102: _linha(102, trk="15"),
                         103: _linha(103, trk="16", status="Em conformidade"),
                         104: _linha(104, usina="Tupi")},
              "puts": [], "deletes": []}

    def listar(sid, buscar=None):
        return [dict(l) for l in estado["linhas"].values()]

    def ler_linha(sid, row, buscar=None):
        return {k: v for k, v in estado["linhas"].get(row, {}).items() if k != "_row"}

    def transporte():
        def enviar(metodo, sid, row, corpo):
            if metodo == "PUT":
                estado["puts"].append((row, corpo))
                novo = dict(zip(corpo["headers"], corpo["values"]))
                novo["_row"] = row
                estado["linhas"][row] = novo
            elif metodo == "DELETE":
                estado["deletes"].append(row)
                estado["linhas"].pop(row, None)
            return {}
        return enviar

    monkeypatch.setattr(tickets_api, "listar_linhas", listar)
    monkeypatch.setattr(tickets_api, "cabecalho_vivo", lambda sid, **k: list(CAB))
    monkeypatch.setattr(tickets_escrita, "ler_linha", ler_linha)
    monkeypatch.setattr(tickets_escrita, "_transporte", transporte)
    monkeypatch.setattr(tickets_escrita, "_confere_liberada", lambda sid: None)
    monkeypatch.setattr(tickets_diario, "ler", lambda **k: [])
    monkeypatch.setattr(tickets_diario, "aplicar", lambda a, o, r: {"aplicados": 0})
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: list(CATALOGO))
    monkeypatch.setattr(rt, "_pode_gravar", lambda: True)
    return estado


@pytest.fixture
def cli(banco):
    app = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Ana Souza", "perfil": "ANALISTA"}
    return c


def _impressao(row, banco):
    return tickets_diario.impressao("Trackers", banco["linhas"][row])


# ── EXCLUIR ──────────────────────────────────────────────────────────────────────────────────
def test_o_painel_traz_as_duas_perguntas_e_a_impressao(cli, banco):
    j = cli.get("/os/api/tickets/Trackers/101").get_json()
    assert j["impressao"] == _impressao(101, banco)
    assert "PEIII" in j["confirma_1"] and "linha 101 do banco" in j["confirma_1"]
    assert j["confirma_2"].startswith("Não tem desfazer.")
    assert j["confirma_1"] != j["confirma_2"]                  # duas perguntas, não uma repetida


def test_excluir_com_a_impressao_certa_apaga(cli, banco):
    r = cli.post("/os/api/tickets/Trackers/101/excluir", json={"impressao": _impressao(101, banco)})
    assert r.status_code == 200 and banco["deletes"] == [101]


def test_excluir_quando_a_linha_MUDOU_nao_apaga_nada(cli, banco):
    """O caso que a trava existe para pegar: as linhas desceram e a 101 agora é OUTRA ocorrência."""
    imp = _impressao(101, banco)
    banco["linhas"][101] = _linha(101, trk="99")           # outra ocorrência caiu na linha 101
    r = cli.post("/os/api/tickets/Trackers/101/excluir", json={"impressao": imp})
    assert r.status_code == 409 and banco["deletes"] == []


def test_excluir_sem_impressao_recusa(cli, banco):
    r = cli.post("/os/api/tickets/Trackers/101/excluir", json={})
    assert r.status_code == 400 and banco["deletes"] == []


def test_excluir_sem_credencial_recusa(cli, banco, monkeypatch):
    monkeypatch.setattr(rt, "_pode_gravar", lambda: False)
    r = cli.post("/os/api/tickets/Trackers/101/excluir", json={"impressao": _impressao(101, banco)})
    assert r.status_code == 403 and banco["deletes"] == []


# ── VINCULAR OS ──────────────────────────────────────────────────────────────────────────────
def test_status_ao_vincular():
    """Só preenche VAZIO — status escolhido à mão não é sobrescrito."""
    assert tw.status_ao_vincular("", "Em Processo") == "OS Programada"
    assert tw.status_ao_vincular("", "Em Verificação") == "OS em Verificação"
    assert tw.status_ao_vincular("", "Concluída") == "OS em Verificação"
    assert tw.status_ao_vincular("Aguardando Fabricante", "Concluída") == "Aguardando Fabricante"


def test_pode_vincular_so_sem_os_e_aberta():
    assert tw.pode_vincular({"OS": "", "_estado": "aberta"}) is True
    assert tw.pode_vincular({"OS": "13801", "_estado": "com_os"}) is False
    assert tw.pode_vincular({"OS": "", "_estado": "encerrada"}) is False


def test_os_escolhida_traz_criacao_e_status(cli, monkeypatch):
    monkeypatch.setattr(api, "os_por_folio", lambda f: {"wo_folio": str(f), "id_status_work_order": 2,
                                                        "creation_date": "2026-09-18T13:05:00+00:00"})
    monkeypatch.setattr(api, "fmt_data_br", lambda v, *a, **k: "18/09/2026 10:05")
    j = cli.get("/os/api/tickets/os/13801").get_json()
    assert j["status"] == "Em Verificação"
    assert j["criada"] == "2026-09-18 10:05:00" and j["criada_input"] == "2026-09-18T10:05"
    assert j["status_ticket_padrao"] == "OS em Verificação"


def test_os_que_nao_existe_e_404(cli, monkeypatch):
    monkeypatch.setattr(api, "os_por_folio", lambda f: None)
    assert cli.get("/os/api/tickets/os/99999").status_code == 404


def test_buscar_os_exige_dois_digitos(cli, monkeypatch):
    chamado = []
    monkeypatch.setattr(api, "buscar_os_pai", lambda q, limit=12: chamado.append(q) or [])
    assert cli.get("/os/api/tickets/buscar-os?q=1").get_json() == {"resultados": []}
    assert chamado == []                                   # uma letra não vai ao Fracttal


@pytest.mark.parametrize("celula, numero", [("13801", "13801"), ("OS 13801", "13801"),
                                            ("13801/13802", "13801"), ("", ""), ("—", ""), ("12", "")])
def test_numero_da_os_para_o_link(celula, numero):
    assert tw.numero_da_os(celula) == numero


# ── TROCAR A USINA ───────────────────────────────────────────────────────────────────────────
def test_nome_curto_igual_ao_do_app():
    """Porte de steps/lupa_usinas.py::nome_curto — conservador: só tira cliente e UF exatos."""
    assert tw.nome_curto("Axis", "Axis - Petrolina 3 - PE") == "Petrolina 3"
    assert tw.nome_curto("Thopen", "Thopen - Boa Esperança do Sul 1 e 2 - SP") == "Boa Esperança do Sul 1 e 2"
    assert tw.nome_curto("Solier Qair", "Solier - Cascavel") == "Solier - Cascavel"   # não é o cliente
    assert tw.nome_curto("", "Piracicaba I") == "Piracicaba I"


def test_nome_curto_ambiguo_volta_ao_nome_completo():
    """"Linhares 1" existe na Axis e na Thopen: gravar o curto apontaria para dois clientes."""
    us = tw.usinas_do_catalogo([
        {"usina": "Axis - Linhares 1 - ES", "cliente": "Axis", "code": "AXS-LIN100-X"},
        {"usina": "Thopen - Linhares 1 - ES", "cliente": "Thopen", "code": "THP-LIN101-X"}])
    assert sorted(u["curto"] for u in us) == ["Axis - Linhares 1 - ES", "Thopen - Linhares 1 - ES"]


def test_escopo_inclui_as_linhas_de_check_escondidas(cli, banco):
    """PEIII virou PTL300 em 13 linhas e a 14ª, 'Em conformidade', ficou para trás (08/09)."""
    j = cli.get("/os/api/tickets/Trackers/usina-escopo?antigo=PEIII&novo=Petrolina%202").get_json()
    assert sorted(j["linhas"]) == [101, 102, 103]
    assert j["n_ocs"] == 2 and j["n_checks"] == 1
    assert "3 linhas" in j["pergunta"] and "Petrolina 2" in j["pergunta"]


def test_renomear_grava_a_linha_INTEIRA_so_com_a_usina_trocada(cli, banco):
    r = cli.post("/os/api/tickets/Trackers/renomear-usina",
                 json={"antigo": "PEIII", "novo": "Petrolina 2", "linhas": [101, 102, 103]})
    j = r.get_json()
    assert r.status_code == 200 and sorted(j["corrigidas"]) == [101, 102, 103] and j["falhas"] == []
    for row in (101, 102, 103):
        l = banco["linhas"][row]
        assert l["Usina"] == "Petrolina 2"
        assert l["Causa raiz"] == "fim de curso" and l["Cliente"] == "Axis"      # nada apagado
    assert banco["linhas"][104]["Usina"] == "Tupi"                                # fora do escopo


def test_renomear_recusa_nome_fora_do_cadastro(cli, banco):
    """Sem esta trava, a rota escreveria qualquer texto na coluna Usina de dezenas de linhas."""
    r = cli.post("/os/api/tickets/Trackers/renomear-usina",
                 json={"antigo": "PEIII", "novo": "Qualquer Coisa", "linhas": [101]})
    assert r.status_code == 400 and banco["puts"] == []


def test_renomear_pula_a_linha_que_ja_mudou(cli, banco):
    banco["linhas"][102]["Usina"] = "Outra"                 # alguém corrigiu por outro caminho
    j = cli.post("/os/api/tickets/Trackers/renomear-usina",
                 json={"antigo": "PEIII", "novo": "Petrolina 2", "linhas": [101, 102]}).get_json()
    assert j["corrigidas"] == [101]
    assert j["falhas"][0]["linha"] == 102
    assert banco["linhas"][102]["Usina"] == "Outra"          # não foi sobrescrita


def test_renomear_respeita_o_tamanho_do_lote(cli, banco):
    """Cada chamada cabe em ~10 s; a tela manda os lotes e mostra o avanço."""
    linhas = list(range(1, 60))
    j = cli.post("/os/api/tickets/Trackers/renomear-usina",
                 json={"antigo": "PEIII", "novo": "Petrolina 2", "linhas": linhas}).get_json()
    assert len(j["corrigidas"]) + len(j["falhas"]) == tw.LOTE_USINA


def test_porte_da_lupa_usinas_da_o_MESMO_resultado_do_app_no_catalogo_real():
    """O porte roda no servidor (sem PyQt6); o original, só no app. Nesta máquina os dois existem,
    e comparar usina por usina no catálogo inteiro é a trava que o `ast` não daria para função."""
    pytest.importorskip("PyQt6")
    from steps import lupa_usinas as lu
    try:
        ativos = api.load_assets_cached()
    except Exception:                                    # noqa: BLE001
        pytest.skip("catálogo indisponível")
    if not ativos:
        pytest.skip("catálogo vazio")
    assert tw.usinas_do_catalogo(ativos) == lu.usinas_do_catalogo(ativos)

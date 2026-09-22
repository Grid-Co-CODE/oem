# tests/test_os_web_solic.py
"""Solicitação / PCM na web (Levi, 21/09/2026: "traga a parte de Solicitação / PCM para a web").

Dois tipos de teste aqui, e a diferença importa:

1. FIDELIDADE — `solic_web.py` tem uma cópia da régua que vive em `steps/solic_pcm.py`, porque
   aquele módulo é Qt e um servidor web não pode importá-lo. Estes testes leem o CÓDIGO-FONTE do
   app e falham se um lado mudar sem o outro. É a mesma trava do `test_os_web_fidelidade.py`.

2. COMPORTAMENTO — as decisões que, se saírem erradas, criam OS no ativo errado, escondem uma
   aprovação que não aconteceu, ou apagam a sugestão do supervisor. Todas já custaram alguma coisa
   uma vez, no app; o porte não pode reintroduzi-las.
"""
import ast
import os

import pytest

from os_web import lancador, solic_web as sw

_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "os_creator")


def _fonte(rel):
    with open(os.path.join(_APP, rel), encoding="utf-8") as f:
        return f.read()


def _constante(tree, nome):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == nome for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("%s nao encontrado" % nome)


# ── 1. fidelidade com o app ──────────────────────────────────────────────────────────────────
def test_padroes_da_os_iguais_aos_do_app():
    """"Programada" e "Corretiva" são o que o PCM cria ao aprovar. Divergir aqui muda a OS."""
    t = ast.parse(_fonte("steps/solic_pcm.py"))
    assert sw.CLASSIF1_PADRAO == _constante(t, "_CLASSIF1_PADRAO")
    assert sw.TIPO_PADRAO == _constante(t, "_TIPO_PADRAO")
    assert sw.SEM_CLASSIF == _constante(t, "_SEM_CLASSIF")


def test_reguas_das_colunas_iguais_as_do_app():
    t = ast.parse(_fonte("steps/solic_pcm.py"))
    assert sw._CANCELADAS == _constante(t, "_CANCELADAS")
    assert sw._REFAZER == _constante(t, "_REFAZER")


@pytest.mark.parametrize("s, esperado", [
    ({"status": "Aberta", "id_work_order": None}, sw.PENDENTE),
    ({"status": "Pendente", "id_work_order": None}, sw.PENDENTE),
    ({"status": "Em processo", "id_work_order": 9}, sw.ANDAMENTO),
    ({"status": "Concluída", "id_work_order": 9}, sw.FINALIZADA),
    ({"status": "Resolvida sem OS", "id_work_order": 9}, sw.FINALIZADA),
    ({"status": "Cancelada", "id_work_order": None}, sw.FINALIZADA),
    ({"status": "Rejeitada", "id_work_order": None}, sw.FINALIZADA),
    ({"status": "Reaberta (refazer)", "id_work_order": None}, sw.FORA),
])
def test_coluna_de(s, esperado):
    """O que separa pendente de resolvida é TER OS, não o id_status: a solicitação criada pelo app
    volta como OPEN_STATUS (1) e a criada pela web do Fracttal, como REQUEST_TODO (7)."""
    assert sw.coluna_de(s) == esperado


def test_resolvida_sem_os_cai_em_pendentes_como_no_app():
    """DEFEITO HERDADO, de proposito. "Resolvida sem OS" (SOLVED_WITHOUT_OT_STATUS) por definicao
    NAO tem OS — e a regra manda para Pendentes tudo que nao tem OS, antes de olhar o status. O
    resultado e que uma solicitacao ja resolvida fica na fila do PCM para sempre.

    A web NAO conserta isso sozinha: app e web lendo a mesma fila e discordando do que esta nela
    seria pior que o defeito. O conserto e uma linha na regra (`coluna_de`), nos dois lados ao
    mesmo tempo, e e decisao do Levi. Enquanto nao for, este teste segura o comportamento igual
    dos dois lados — e existe para que ninguem ache que e descuido."""
    assert sw.coluna_de({"status": "Resolvida sem OS", "id_work_order": None}) == sw.PENDENTE


def test_cancelada_com_os_ainda_e_finalizada():
    """O cancelamento vence: uma solicitação cancelada não é "em andamento" só porque gerou OS."""
    assert sw.coluna_de({"status": "Cancelada", "id_work_order": 9}) == sw.FINALIZADA


# ── 2. comportamento ─────────────────────────────────────────────────────────────────────────
def test_separar_conta_as_devolvidas_sem_mostra_las():
    rows = [{"status": "Aberta", "id_work_order": None, "usina": "Tupi"},
            {"status": "Reaberta (refazer)", "id_work_order": None, "usina": "Tupi"},
            {"status": "Em processo", "id_work_order": 4, "usina": "Tupi"}]
    por = sw.separar(rows)
    assert len(por[sw.PENDENTE]) == 1 and len(por[sw.ANDAMENTO]) == 1
    # a devolvida não entra em coluna nenhuma, mas some-la em silêncio faria o total não bater
    assert por["fora"] == 1 and por["total"] == 2


def test_separar_busca_em_varios_campos():
    rows = [{"status": "Aberta", "id_work_order": None, "usina": "Tupi", "ativo": "Inversor 1.1",
             "descricao": "sem comunicacao", "criado_por": "Ana", "id_code": 3601},
            {"status": "Aberta", "id_work_order": None, "usina": "Araputanga", "ativo": "Tracker 4",
             "descricao": "parado", "criado_por": "Bruno", "id_code": 3602}]
    assert len(sw.separar(rows, "tupi")[sw.PENDENTE]) == 1
    assert len(sw.separar(rows, "bruno")[sw.PENDENTE]) == 1
    assert len(sw.separar(rows, "3601")[sw.PENDENTE]) == 1
    assert len(sw.separar(rows, "nada disso")[sw.PENDENTE]) == 0


def test_linha_le_o_bloco_pcm():
    """Tema, técnico, data e subtarefas só chegam à fila pela observação: a solicitação não tem
    campo para eles no Fracttal."""
    obs = ("caiu ontem\n[PCM]\nTema: inversor_inspecao\nTécnico sugerido: João\n"
           "Data sugerida: 23/09/2026 08:00\nSubtarefas:\n- [Numérico] Corrente (A)")
    d = sw.linha({"observacao": obs, "ativo": "Inversor 1.1, Lote 3, Rua X", "status": "Aberta"})
    assert d["_tema"] == "inversor_inspecao"
    assert d["_tecnico"] == "João" and d["_data_sug"] == "23/09/2026 08:00"
    assert d["_relato"] == "caiu ontem"                     # o bloco não polui o relato
    assert d["_subs"] == [{"tipo": "num", "desc": "Corrente (A)", "anexo": False}]
    assert d["_ativo"] == "Inversor 1.1"                    # sem endereço


def test_asset_da_nao_casa_por_nome():
    """A regra que mais importa deste módulo. Casar por nome escolheu o ativo de OUTRO CLIENTE ao
    aprovar a 3534 (02/09) — "Chave Seccionadora 1" existe em várias usinas."""
    catalogo = [{"id": 1, "code": "APG-CH1", "label": "Chave Seccionadora 1"},
                {"id": 2, "code": "TESTE-CH1", "label": "Chave Seccionadora 1"}]
    # sem id_item nem code, NÃO adivinha
    assert sw.asset_da({"ativo": "Chave Seccionadora 1"}, catalogo) is None
    assert sw.asset_da({"id_item": 2}, catalogo)["code"] == "TESTE-CH1"
    assert sw.asset_da({"code": "APG-CH1"}, catalogo)["id"] == 1
    # id_item manda sobre o code quando os dois vêm
    assert sw.asset_da({"id_item": 1, "code": "TESTE-CH1"}, catalogo)["id"] == 1


def test_subtarefas_nunca_voltam_vazias():
    """Nove dos catorze temas ainda não têm checklist escrito. Travar neles faria a OS nascer sem
    subtarefa nenhuma — pior que nascer com as três da base."""
    assert sw.subtarefas_do_tema("") and sw.subtarefas_do_tema("tema_que_nao_existe")
    assert len(sw.subtarefas_do_tema("inversor_inspecao")) > len(sw.subtarefas_do_tema(""))


def test_observacao_carrega_o_bloco():
    txt = sw.observacao("caiu ontem", "inversor_inspecao", "João", "23/09/2026 08:00",
                        [{"tipo": "num", "desc": "Corrente (A)", "anexo": True}])
    assert txt.startswith("caiu ontem")
    assert "[PCM]" in txt and "inversor_inspecao" in txt
    assert "Corrente (A)" in txt and "anexo obrigat" in txt   # o anexo sobrevive à ida e volta


def test_validar_criar():
    assert sw.validar_criar({"descricao": "", "ativos": ["A"], "classif1": 1}) == sw.ERRO_SEM_DESC
    assert sw.validar_criar({"descricao": "x", "ativos": [], "classif1": 1}) == sw.ERRO_SEM_ATIVO
    assert sw.validar_criar({"descricao": "x", "ativos": ["A"], "classif1": None}) == sw.ERRO_SEM_C1
    assert sw.validar_criar({"descricao": "x", "ativos": ["A"], "classif1": 9}) == ""


def test_mensagem_bulk_diz_os_numeros():
    r = sw.mensagem_bulk([{"code": "A", "ok": True, "id_code": 3601},
                          {"code": "B", "ok": True, "id_code": 3602}])
    assert r["ok"] == 2 and "3601" in r["mensagem"] and "3602" in r["mensagem"]
    r = sw.mensagem_bulk([{"code": "A", "ok": True, "id_code": 3601},
                          {"code": "B", "ok": False, "erro": "recusado"}])
    assert r["falhas"] == 1 and "recusado" in r["mensagem"]


def test_aprovacao_sem_folio_nao_pode_dizer_que_deu_certo():
    """O `clonar_os` devolve ok=True mesmo quando só criou a TAREFA. Sem folio, a tarefa fica no
    kanban do Fracttal onde ninguém a vê — e a solicitação continua na fila."""
    ok = sw.mensagem_aprovacao({"ok": True, "os": {"wo_folio": "13801", "id_work_order": 99}}, 3601)
    assert ok["ok"] and "13801" in ok["mensagem"]

    meio = sw.mensagem_aprovacao({"ok": True, "os": {}, "aviso": "A OS não recebeu número."}, 3601)
    assert meio["ok"] is False
    assert "continua na fila" in meio["mensagem"]

    ruim = sw.mensagem_aprovacao({"ok": False, "erro": "unique_violation"}, 3601)
    assert ruim["ok"] is False and "unique_violation" in ruim["mensagem"]


def test_data_brt_do_input_datetime_local():
    d = sw.data_brt("2026-09-21T14:30")
    assert (d.year, d.month, d.day, d.hour, d.minute) == (2026, 9, 21, 14, 30)
    assert d.utcoffset().total_seconds() == -3 * 3600          # Brasília, como o app
    assert sw.data_brt("").tzinfo is not None                   # vazio = agora, mas COM fuso


# ── 3. o lançador não pode esconder tela pronta ──────────────────────────────────────────────
def test_cards_prontos_nao_apontam_para_em_breve():
    """Quatro telas já servidas por `rotas_*.py` continuavam no "em breve" — o card dizia que não
    existia uma página que abria (Levi, 21/09: "a parte de ativos não foi construída")."""
    from os_web import blueprints
    servidas = set()
    for mod in blueprints.modulos():
        servidas.update(_rotas_do_modulo(mod))
    for c in lancador.CARDS + lancador.ABAS:
        href = c["href"]
        if href.startswith("/os/em-breve/"):
            rota = "/" + href.split("/os/em-breve/")[1]
            assert rota not in servidas, ("o card %r manda para 'em breve' mas /os%s existe"
                                          % (c["chave"], rota))


def _rotas_do_modulo(nome):
    """As rotas que o blueprint serve. O Blueprint guarda as rotas como funcoes diferidas — o jeito
    estavel de le-las e registrar num app de mentira e ler o url_map."""
    import importlib

    from flask import Flask
    mod = importlib.import_module("os_web.%s" % nome)
    app = Flask(__name__)
    app.register_blueprint(mod.bp)
    return [str(r)[3:] for r in app.url_map.iter_rules() if str(r).startswith("/os/")]


def test_aba_solic_e_o_card_pcm_sao_telas_DIFERENTES():
    """Os dois se chamam "PCM" e nao sao a mesma coisa — foi o engano de 21/09.

    A ABA "Solicitacao / PCM" e o pedido de servico + a fila de aprovacao (steps/solicitacao.py e
    steps/solic_pcm.py). O CARD "PCM" e a PcmTab (steps/pcm.py): OS planejada por familia de plano,
    varios ativos de uma vez — outra tela, outro fluxo, ainda nao portada. Apontar um para o outro
    trocaria uma pela outra sem ninguem perceber."""
    hrefs = {c["chave"]: c["href"] for c in lancador.CARDS + lancador.ABAS}
    assert hrefs["solic"] == "/os/solicitacao"
    assert hrefs["pcm"] == "/os/em-breve/pcm"
    assert hrefs["ativos"] == "/os/ativos"

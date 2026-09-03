"""A aba Solicitação / PCM: a régua das colunas e o que a fila leva para a OS.

A régua de coluna é o coração do painel e é fácil de quebrar sem sintoma: se ela classificar
errado, a solicitação some da coluna Pendentes e o PCM simplesmente não a vê — sem erro, sem
alarme. Foi assim que 62 solicitações reabertas ficaram paradas por uma mediana de 86 dias.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import solic_spec as sp
from steps.solic_pcm import SolicPcmTab, coluna_de, PENDENTE, ANDAMENTO, FINALIZADA


def test_sem_OS_vinculada_e_pendente():
    assert coluna_de({"id_work_order": None, "status": "Aberta"}) == PENDENTE


def test_reaberta_sem_OS_tambem_e_pendente():
    """As 60 reabertas medidas em 02/09 estao exatamente nesse estado: pedido devolvido para
    refazer, sem OS, sem dono. Sao elas que enchem a fila no primeiro dia."""
    assert coluna_de({"id_work_order": None, "status": "Reaberta (refazer)"}) == PENDENTE


def test_cancelada_nunca_e_pendente():
    # cancelada tambem nao tem OS; sem esta regra, 154 canceladas entrariam na fila do PCM
    assert coluna_de({"id_work_order": None, "status": "Cancelada"}) == FINALIZADA
    assert coluna_de({"id_work_order": None, "status": "Rejeitada"}) == FINALIZADA


def test_com_OS_aberta_e_andamento_e_concluida_e_finalizada():
    assert coluna_de({"id_work_order": 1, "status": "OS em processo"}) == ANDAMENTO
    assert coluna_de({"id_work_order": 1, "status": "OS em verificação"}) == ANDAMENTO
    assert coluna_de({"id_work_order": 1, "status": "Resolvida com OS"}) == FINALIZADA
    assert coluna_de({"id_work_order": 1, "status": "OS concluída"}) == FINALIZADA


def test_a_regua_nao_usa_id_status():
    """Nao pode depender de id_status: a solicitacao criada pelo app volta como OPEN_STATUS (1) e
    a criada pela web do Fracttal, como REQUEST_TODO (7) — as duas pendentes. Medido nas
    solicitacoes 3533 e 3534, criadas de verdade."""
    a = {"id_work_order": None, "status": "Aberta", "id_status": 1}
    b = {"id_work_order": None, "status": "Aberta", "id_status": 7}
    assert coluna_de(a) == coluna_de(b) == PENDENTE


def test_a_aba_tem_o_hub_e_as_quatro_paginas(qapp):
    t = SolicPcmTab()
    assert t.stack.count() == 5                 # hub + as quatro
    assert t.stack.currentIndex() == t.HUB      # a aba abre no hub, nao numa das telas


def test_a_ordem_da_navegacao_segue_o_fluxo(qapp):
    """Nova solicitacao vem PRIMEIRO: quem abre a aba na maioria das vezes e o supervisor, para
    pedir. A ordem antiga (Painel primeiro) era a ordem em que as telas foram escritas."""
    t = SolicPcmTab()
    assert [b.text() for b in t._btns] == ["Nova solicitação", "Painel", "Fila do PCM", "Histórico"]


def test_o_hub_esconde_a_navegacao_e_a_traz_de_volta(qapp):
    """Duas barras de navegacao na mesma tela e a pessoa perguntando qual das duas manda."""
    t = SolicPcmTab()
    assert not t._btns[0].isVisible() or t.stack.currentIndex() == t.HUB
    t.ir(t.FILA)
    assert all(b.isVisibleTo(t) for b in t._btns)
    t.ir(t.HUB)
    assert not any(b.isVisibleTo(t) for b in t._btns)


def test_a_area_pcm_revela_os_tres_destinos(qapp):
    """Os tres cards do PCM so aparecem depois do clique em Area PCM — e o segundo clique leva
    direto para a fila, que e o destino de quem esta ali para aprovar."""
    t = SolicPcmTab()
    assert not t.hub.sub.isVisibleTo(t.hub)
    t.hub._abrir_pcm()
    assert t.hub.sub.isVisibleTo(t.hub)
    assert len(t.hub._subcards) == 3            # Painel, Fila do PCM, Historico
    t.hub._abrir_pcm()                          # segundo clique: vai direto para a fila
    assert t.stack.currentIndex() == t.FILA


def test_o_deep_link_cai_na_pagina_do_formulario(qapp):
    """O 'Criar Solicitação deste ativo' do detalhe da OS. Sem isso ele cairia no PAINEL e o
    pre-preenchimento aconteceria numa tela que ninguem esta vendo."""
    t = SolicPcmTab()
    t.ir(t.FILA)
    t.abrir_nova()
    assert t.stack.currentIndex() == t.NOVA


def test_a_fila_sem_tema_ainda_monta_subtarefas():
    """Nove dos catorze temas nao tem checklist. Se a fila travasse neles, o PCM voltaria para o
    Fracttal e a OS nasceria sem nada."""
    base = sp.subtarefas_base()
    assert len(base) == len(sp.BASE)
    assert any(s["attachments_required"] for s in base)
    assert base[0]["description"] == sp.BASE[0]["desc"]


def test_a_fila_comeca_desabilitada(qapp):
    # sem selecao nao ha o que aprovar; botao ativo sem alvo e convite a erro
    t = SolicPcmTab()
    assert not t.fila.b_aprovar.isEnabled()


def test_selecionar_habilita_e_traz_o_tema_do_bloco(qapp):
    t = SolicPcmTab()
    obs = sp.observacao_com_bloco("relato", {"tema": "vegetacao", "tecnico": "Ana",
                                             "data": "10/09/2026"})
    s = {"id_code": 1, "usina": "Tucano", "ativo": "Roçadeira", "descricao": "roçar",
         "descricao_full": "roçar", "observacao": obs, "criado_por": "Ana", "data": "2026-09-02",
         "id_work_order": None, "status": "Aberta"}
    t.fila.set_itens([s], [])
    assert t.fila.b_aprovar.isEnabled()
    assert t.fila.cb_tema.currentData() == "vegetacao"
    assert "Ana" in t.fila.lbl_sug.text()
    # o titulo do Fracttal e reescrito, e o original aparece para o PCM ver o que muda
    assert "Roçagem e supressão vegetal" in t.fila.lbl_titulo.text()
    assert "o supervisor escreveu" in t.fila.lbl_orig.text()


# ── a busca do ativo: onde uma OS pode nascer na usina errada ────────────────
def _fila(qapp, assets):
    t = SolicPcmTab()
    t.fila._assets = assets
    return t.fila


ATIVOS = [
    {"id": 111, "code": "TESTE100-CHSC1", "description": "Chave Seccionadora 1   { TESTE100-CHSC1 }"},
    {"id": 222, "code": "APG100-CHSC1",   "description": "Chave Seccionadora 1   { APG100-CHSC1 }"},
]


def test_acha_o_ativo_pelo_id_item(qapp):
    f = _fila(qapp, ATIVOS)
    a = f._asset_da({"id_item": 111, "ativo": "Chave Seccionadora 1", "code": ""})
    assert a["code"] == "TESTE100-CHSC1"


def test_acha_pelo_codigo_quando_nao_ha_id(qapp):
    f = _fila(qapp, ATIVOS)
    a = f._asset_da({"id_item": None, "code": "APG100-CHSC1", "ativo": "Chave Seccionadora 1"})
    assert a["id"] == 222


def test_NUNCA_casa_so_pelo_nome(qapp):
    """O teste que existe por causa de um erro real.

    Ao aprovar a solicitação 3534 (TESTE - PA), o casamento por nome escolheu o ativo da APG100
    — outra usina, de cliente de verdade. "Chave Seccionadora 1" existe em várias. Sem id nem
    código, a resposta certa é None: o PCM recarrega os ativos, em vez de a OS nascer no lugar
    errado sem ninguém perceber."""
    f = _fila(qapp, ATIVOS)
    assert f._asset_da({"id_item": None, "code": "", "ativo": "Chave Seccionadora 1"}) is None


def test_id_que_nao_existe_no_catalogo_devolve_None(qapp):
    f = _fila(qapp, ATIVOS)
    assert f._asset_da({"id_item": 999, "code": "", "ativo": "Chave Seccionadora 1"}) is None


# ── o responsável: sem ele a OS não nasce numerada ───────────────────────────
PESSOAS = [{"name": "Ana Souza", "id_personnel": 10},
           {"name": "Bruno Lima", "id_personnel": 20}]


def test_sem_responsavel_a_fila_nao_aprova(qapp):
    """A criação da OS tem DUAS fases: `create_os_rpc` só cria a tarefa, e o número da OS vem do
    `_work_order_insert`, que EXIGE responsável. Sem essa régua a aprovação "dava certo" e não
    aparecia OS nenhuma — foi o que aconteceu em três tentativas na solicitação 3534."""
    f = _fila(qapp, ATIVOS)
    f.set_responsaveis(PESSOAS)
    assert f.cb_resp.currentData() is None      # começa em "— selecione —"
    assert f.cb_resp.count() == 3               # o placeholder + as duas pessoas


def test_o_tecnico_sugerido_vira_o_responsavel(qapp):
    """O que fecha o ciclo do fluxo: a sugestão do supervisor deixa de ser texto na observação e
    já chega pré-selecionada como responsável da OS."""
    t = SolicPcmTab()
    t.fila.set_responsaveis(PESSOAS)
    obs = sp.observacao_com_bloco("relato", {"tema": "nobreak", "tecnico": "Bruno Lima",
                                             "data": "10/09/2026"})
    t.fila.set_itens([{"id_code": 9, "usina": "Tucano", "ativo": "Nobreak 1", "descricao": "x",
                       "observacao": obs, "id_work_order": None, "status": "Aberta"}], ATIVOS)
    assert t.fila.cb_resp.currentData() == 20


def test_tecnico_que_nao_esta_na_lista_nao_seleciona_ninguem(qapp):
    """Nome que não casa não pode cair no primeiro da lista: seria OS atribuída a quem o
    supervisor não pediu, sem ninguém perceber."""
    f = _fila(qapp, ATIVOS)
    f.set_responsaveis(PESSOAS)
    f._pre_selecionar_responsavel("Fulano de Tal")
    assert f.cb_resp.currentData() is None


def test_a_fila_reaproveita_os_tecnicos_do_formulario(qapp):
    """Uma chamada de rede em vez de duas: a lista que o formulário já buscou é a mesma."""
    t = SolicPcmTab()
    t.nova._set_tecnicos(PESSOAS)
    assert t._pessoas() == PESSOAS


# ── o chip do tema no cartão da fila ─────────────────────────────────────────
def test_o_chip_do_tema_nunca_quebra_linha(qapp):
    """O chip tem fundo arredondado com padding desenhado para UMA linha. "Proteção —
    transformador e cabine" virava duas (28 px contra 15), o fundo saía torto e passava por cima
    da borda do cartão. Nome que não cabe é aparado com "…", e o nome inteiro fica no tooltip —
    aparar sem tooltip esconderia informação."""
    from steps.solic_pcm import _CartaoFila
    for tema in ("", "protecao_transformador", "vegetacao", "nobreak"):
        obs = sp.observacao_com_bloco("x", {"tema": tema}) if tema else ""
        c = _CartaoFila({"id_code": 1, "usina": "UFV Tucano", "ativo": "Nobreak 1",
                         "descricao": "x", "observacao": obs, "criado_por": "F",
                         "data": "2026-09-02", "status": "Aberta"}, lambda *_: None)
        assert c._chip.wordWrap() is False
        assert "\n" not in c._chip.text()
        nome = (sp.TEMAS.get(tema) or {}).get("nome") or "sem tema"
        assert c._chip.toolTip() == nome          # nada se perde ao aparar
        assert c._chip.text() == nome or c._chip.text().endswith("…")


# ── técnico e data como valor que vira campo ao clicar ───────────────────────
def test_tecnico_e_data_aparecem_como_texto_e_viram_campo(qapp):
    """Nesta tela o técnico e a data quase sempre só precisam ser CONFIRMADOS — o supervisor já
    escreveu. Combo e date picker abertos dão a uma conferência o peso de um formulário."""
    t = SolicPcmTab()
    obs = sp.observacao_com_bloco("x", {"tema": "nobreak", "tecnico": "João Vieira",
                                        "data": "05/09/2026"})
    t.fila.set_responsaveis([{"name": "João Vieira", "id_personnel": 7}])
    t.fila.set_itens([{"id_code": 1, "usina": "U", "ativo": "A", "descricao": "x",
                       "observacao": obs, "id_work_order": None, "status": "Aberta"}], [])
    assert t.fila.ed_tecnico.lbl.text() == "João Vieira"
    assert t.fila.ed_data.lbl.text() == "05/09/2026"
    assert t.fila.cb_resp.currentData() == 7          # o sugerido já é o responsável
    t.fila.ed_tecnico.abrir()
    assert t.fila.ed_tecnico._pilha.currentIndex() == 1
    t.fila.ed_tecnico.fechar()
    assert t.fila.ed_tecnico._pilha.currentIndex() == 0


def test_tecnico_sugerido_fora_do_cadastro_continua_visivel(qapp):
    """Sumir com o nome faria parecer que o supervisor não sugeriu ninguém, quando ele sugeriu
    alguém que não está cadastrado — que é uma informação diferente, e útil."""
    t = SolicPcmTab()
    t.fila.set_responsaveis([{"name": "Ana", "id_personnel": 1}])
    t.fila._pre_selecionar_responsavel("Fulano de Tal")
    assert t.fila.cb_resp.currentData() is None
    assert t.fila.ed_tecnico.lbl.text() == "Fulano de Tal"


def test_o_tema_escolhido_marca_o_campo(qapp):
    """A borda verde do combo: é o campo que decide o checklist da OS."""
    t = SolicPcmTab()
    base = {"id_code": 1, "usina": "U", "ativo": "A", "descricao": "x",
            "id_work_order": None, "status": "Aberta"}
    t.fila.set_itens([dict(base, observacao=sp.observacao_com_bloco("x", {"tema": "nobreak"}))], [])
    assert t.fila.cb_tema.property("temado") == "1"
    t.fila.set_itens([dict(base, observacao="")], [])
    assert t.fila.cb_tema.property("temado") == "0"

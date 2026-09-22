# -*- coding: utf-8 -*-
"""Fila do PCM, lote de 15/09: o clique na observação, a OS pai e o botão Atualizar.

O primeiro é o defeito que o Levi viu em campo — "clico na observação, o texto grande fica
resumido num campo pequeno e todo o resto da tela fica escuro". Medido antes do conserto: a
pilha do campo ia de 92 para 1638 px ao trocar o rótulo pelo editor, o que empurrava sugestão,
etiquetas, tema, subtarefas e botões 1,5 mil pixels para baixo — fora da janela."""
import pytest
import solic_spec as sp

RELATO_LONGO = (
    "Foi aberto chamado por problemas no backtracking. O fabricante informou que a curva esta "
    "desalinhada em relacao ao projeto e pediu que a equipe de campo confirme o azimute dos "
    "trackers da fileira 12 antes de qualquer intervencao. A medicao deve ser feita entre 9h e "
    "15h, com o sol alto, e registrada em foto. Se o desvio for maior que 2 graus, abrir chamado "
    "de garantia com o numero de serie da estrutura e o relatorio de comissionamento anexado.")


def _solicitacao(relato):
    return {"id_code": 3608, "usina": "Tupi Paulista 1 e 2", "ativo": "Estrutura Trackers",
            "criado_por": "Singrid Vieira", "data": "2026-09-11 10:00:00", "status": "Pendente",
            "cor_status": "#01C0DD", "descricao_full": "Chamado de garantia",
            "observacao": relato + "\n\n" + sp.bloco({"tema": "tracker_chamado"})}


@pytest.fixture
def fila(qapp):
    from steps.solic_pcm import _Fila
    f = _Fila(lambda: None)
    f.resize(1500, 900)
    f.set_itens([_solicitacao(RELATO_LONGO)], [])
    return f


def _y_do_aprovar(f):
    return f.b_aprovar.mapTo(f, f.b_aprovar.rect().topLeft()).y()


def test_clicar_na_observacao_nao_mexe_no_resto_da_tela(fila):
    """O defeito inteiro num número: onde estava o botão Aprovar antes e depois do clique."""
    antes = _y_do_aprovar(fila)
    alt_antes = fila.v_obs.height()
    fila.v_obs.abrir()
    assert _y_do_aprovar(fila) == antes, "a ficha desceu ao abrir o editor da observação"
    assert fila.v_obs.height() == alt_antes, "o campo mudou de altura ao virar editor"
    assert fila.ed_obs.height() == alt_antes, "o editor ficou de um tamanho e o rótulo de outro"


# A altura da observacao saia do TEXTO ate 16/09. Com as duas colunas ela passou a ser
# dimensionada para EMPATAR os cartoes do pedido e da decisao, e a regra nova vive em
# tests/test_fila_pcm_duas_colunas.py — nao ha duas verdades sobre o mesmo campo.


def test_redimensionar_a_tela_nao_derruba_o_app(fila, qapp):
    """A conta da altura depende da LARGURA, então ela refaz no resize — e foi ali que o
    conserto quase virou outro defeito: mexer na altura dentro do resizeEvent realimenta o
    próprio evento, e `QTimer.singleShot(0, self, slot)` (a forma com contexto) NÃO existe
    neste PyQt6 — levanta TypeError dentro do método virtual, e exceção em virtual do Qt aborta
    o processo. Este teste roda o caminho que a suíte não cobria."""
    for larg in (1500, 1100, 820, 1920):
        fila.resize(larg, 900)
        qapp.processEvents()
    # Em janela estreita os campos quebram em mais linhas e os cartoes ficam mais altos — o
    # teto fixo de 400 px que havia aqui era da regra antiga. O que importa e nao derrubar.
    assert fila.v_obs.height() >= 92


def test_a_fila_tem_campo_de_os_pai(fila):
    """A OS nascida na fila nunca teve como ser vinculada a uma pai — o campo só existia em
    Criar OS, COS e PCM."""
    assert hasattr(fila, "os_pai")
    assert fila.os_pai.id_parent() is None, "campo vazio tem de significar SEM OS pai"


def test_trocar_de_solicitacao_limpa_a_os_pai(fila):
    """Aprovar avança para a próxima: a pai da anterior seguindo no campo vincularia OS errada."""
    fila.os_pai.addItem("8899 — OS anterior", 35648555)
    fila.os_pai.setCurrentIndex(fila.os_pai.count() - 1)
    fila.os_pai._sel = 35648555
    assert fila.os_pai.id_parent() == 35648555
    fila._selecionar(_solicitacao("outro pedido"))
    assert fila.os_pai.id_parent() is None


def test_aprovar_solicitacao_leva_o_id_parent_para_a_criacao(monkeypatch):
    """Ter o campo na tela não basta: o valor precisa chegar ao `clonar_os`, que é quem monta o
    payload com `id_parent`."""
    import api
    visto = {}
    monkeypatch.setattr(api, "_solicitacao_row", lambda *a, **k: {})
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda *a, **k: None)
    monkeypatch.setattr(api, "clonar_os", lambda *a, **k: visto.update(k) or {"ok": True})
    api.aprovar_solicitacao({"id": 1}, "titulo", [], "3608", 7, "Fulano", id_parent=35648555)
    assert visto.get("id_parent") == 35648555


def test_o_botao_atualizar_chama_quem_busca_e_destrava_no_fim(qapp):
    """Antes era: voltar ao Painel, atualizar, entrar na Fila de novo — e perder a seleção."""
    from steps.solic_pcm import _Fila
    chamadas = []
    f = _Fila(lambda: None, on_atualizar=lambda: chamadas.append(1))
    f.b_atualizar.click()
    assert chamadas == [1]
    assert not f.b_atualizar.isEnabled(), "sem travar, dá para disparar cinco buscas em fila"
    f.fim_da_atualizacao()
    assert f.b_atualizar.isEnabled()
    assert f.b_atualizar.text() == "Atualizar"


def test_o_painel_avisa_quem_depende_da_lista(qapp):
    """A Fila lê a lista do Painel. Sem o aviso, o botão Atualizar recarregaria o Painel e a
    fila continuaria mostrando a lista velha — e o botão ficaria preso em "atualizando…" se a
    busca desse erro."""
    from steps.solic_pcm import _Painel
    p = _Painel(lambda *_: None)
    avisos = []
    p.on_carregou = lambda: avisos.append(1)
    p._ok([])
    assert avisos == [1], "fim de carga com sucesso não avisou"
    p._err("falhou")
    assert avisos == [1, 1], "erro também é fim de carga — sem avisar, o botão trava"

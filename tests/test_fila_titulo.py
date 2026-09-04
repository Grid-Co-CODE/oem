# -*- coding: utf-8 -*-
"""O crash da troca de tema, o título editável e o modo somente-leitura da Fila (04/09)."""
import pytest
import solic_spec as sp


@pytest.fixture
def fila(qapp):
    from steps.solic_pcm import _Fila
    f = _Fila(lambda: None)
    f.set_itens([{"id_code": 3550, "usina": "Colonia", "ativo": "INV-03", "criado_por": "F",
                  "data": "2026-09-01 10:00:00", "status": "Pendente", "cor_status": "#01C0DD",
                  "descricao_full": "inversor parado",
                  "observacao": "x\n\n" + sp.bloco({"tema": "inversor_inspecao"})}], [])
    return f


def test_trocar_o_tema_pelo_sinal_nao_derruba_o_app(fila):
    """O defeito que FECHAVA o app ao escolher um tema.

    `currentIndexChanged` manda o ÍNDICE, e ele caía no parâmetro `do_bloco` de
    `_pintar_subs(do_bloco=None)` — que espera uma LISTA de subtarefas. Com índice != 0 virava
    `set_itens(2)`, "int object is not iterable", e exceção dentro de slot do PyQt6 ABORTA o
    processo (0xC0000409). Ficou escondido enquanto o combo não abria (o defeito do
    `PopupFocusReason`, corrigido na 184): ninguém conseguia trocar de tema para descobrir.

    O teste chama `_pintar_subs` com um inteiro — exatamente o que o sinal fazia."""
    fila._pintar_subs(2)                      # antes: TypeError -> abort
    assert fila.editor_subs.itens(), "a lista de subtarefas ficou vazia"

    for i in range(min(4, fila.cb_tema.count())):
        fila.cb_tema.setCurrentIndex(i)       # o caminho real, pelo sinal
    assert fila.editor_subs.itens()


def test_o_titulo_escrito_a_mao_sobrevive_a_troca_de_tema(fila):
    """Trocar o tema regenera o título — menos quando o PCM escreveu o dele. Desfazer trabalho
    de gente sem avisar é o pior tipo de automação."""
    fila._abrir_titulo()
    fila.ed_titulo.setText("TITULO DO PCM")
    fila._fechar_titulo()
    assert fila._titulo_manual is True

    i = next((k for k in range(fila.cb_tema.count())
              if fila.cb_tema.itemData(k) == "tracker_chamado"), 1)
    fila.cb_tema.setCurrentIndex(i)
    assert fila.lbl_titulo.text() == "TITULO DO PCM"


def test_titulo_volta_ao_padrao_do_tema_em_outra_solicitacao(fila):
    """A marca de 'escrito à mão' é por solicitação: a próxima começa do padrão."""
    fila._abrir_titulo()
    fila.ed_titulo.setText("TITULO DO PCM")
    fila._fechar_titulo()
    fila.set_itens(fila._itens, [])
    assert fila._titulo_manual is False
    assert fila.lbl_titulo.text() != "TITULO DO PCM"


def test_somente_leitura_trava_tudo_o_que_grava(fila):
    """O Painel abre a Fila em qualquer coluna. Se a solicitação já virou OS, nada é editável —
    a API do Fracttal não edita OS criada, e deixar os campos ativos ofereceria uma edição que
    morre no botão."""
    fila.set_somente_leitura(True)
    assert not fila.b_aprovar.isEnabled()
    assert not fila.b_devolver.isEnabled()
    assert not fila.cb_tema.isEnabled()
    fila._abrir_titulo()
    assert not fila.ed_titulo.isVisible(), "o título abriu para edição em modo leitura"
    assert "consulta" in fila.hint.text().lower()

    fila.set_somente_leitura(False)
    assert fila.b_aprovar.isEnabled()

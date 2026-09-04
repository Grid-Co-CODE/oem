# -*- coding: utf-8 -*-
"""Baixar todos os anexos de uma OS de uma vez (pedido do Levi, 04/09).

Nenhum teste vai à rede: `baixar_em_massa` recebe a função de download por injeção."""
import os

import pytest


@pytest.fixture
def baixar(qapp):
    from steps.documentos import baixar_em_massa
    return baixar_em_massa


def _fake(u):
    if u == "EXPIRADA":
        raise OSError("url expirada")
    return b"conteudo-" + u.encode()


def test_agrupa_por_subtarefa_e_numera_dentro_de_cada_uma(baixar, tmp_path):
    """A foto só vale se dá para saber QUAL passo do serviço ela comprova, e a ORDEM é o
    roteiro da inspeção. O nome que vem do Fracttal é quase sempre `image.jpg`."""
    itens = [{"nome": "image.jpg", "url": "a", "subtarefa": "Medir tensão"},
             {"nome": "laudo.pdf", "url": "b", "subtarefa": "Anexar laudo"},
             {"nome": "image.jpg", "url": "c", "subtarefa": "Medir tensão"}]
    g, f = baixar(itens, str(tmp_path), baixar=_fake)
    rel = sorted(os.path.relpath(x, str(tmp_path)) for x in g)
    assert not f
    assert rel == [os.path.join("Anexar laudo", "01 - laudo.pdf"),
                   os.path.join("Medir tensão", "01 - image.jpg"),
                   os.path.join("Medir tensão", "02 - image.jpg")]


def test_dois_anexos_com_o_mesmo_nome_nao_se_sobrescrevem(baixar, tmp_path):
    """O celular manda tudo como `image.jpg`. Sem tratar, o segundo apagaria o primeiro EM
    SILÊNCIO — o pior tipo de perda, porque ninguém percebe."""
    itens = [{"nome": "image.jpg", "url": "a", "subtarefa": "P"},
             {"nome": "image.jpg", "url": "b", "subtarefa": "P"}]
    g, _ = baixar(itens, str(tmp_path), baixar=_fake)
    assert len(g) == 2
    assert len({os.path.basename(x) for x in g}) == 2
    for cam in g:
        assert os.path.getsize(cam) > 0


def test_um_arquivo_que_falha_nao_derruba_o_lote(baixar, tmp_path):
    """A URL do Fracttal é pré-assinada e expira. Se a do meio morrer, as outras já baixadas
    continuam valendo — e o relatório diz qual faltou."""
    itens = [{"nome": "ok1.jpg", "url": "a", "subtarefa": "P"},
             {"nome": "morta.jpg", "url": "EXPIRADA", "subtarefa": "P"},
             {"nome": "ok2.jpg", "url": "c", "subtarefa": "P"}]
    g, f = baixar(itens, str(tmp_path), baixar=_fake)
    assert len(g) == 2
    assert [n for n, _ in f] == ["morta.jpg"]


def test_nota_de_texto_vira_txt(baixar, tmp_path):
    """`type=3` não tem arquivo, é texto digitado pelo técnico — e é ele que costuma explicar
    a foto. Sem isto sumiria do pacote."""
    itens = [{"nome": "obs", "is_text": True, "descricao": "sem pendência", "subtarefa": "P"}]
    g, f = baixar(itens, str(tmp_path), baixar=_fake)
    assert not f and len(g) == 1
    assert g[0].endswith(".txt")
    with open(g[0], encoding="utf-8") as fh:
        assert fh.read() == "sem pendência"


def test_nome_invalido_no_windows_e_saneado(baixar, tmp_path):
    r"""`\ / : * ? " < > |` são proibidos no Windows, e nome terminado em ponto quebra ao
    gravar. O Fracttal aceita esses caracteres na descrição."""
    itens = [{"nome": 'ru:im*?.jpg', "url": "a", "subtarefa": "Passo/2"}]
    g, f = baixar(itens, str(tmp_path), baixar=_fake)
    assert not f and len(g) == 1
    assert os.path.exists(g[0])
    assert ":" not in os.path.basename(g[0]) and "*" not in os.path.basename(g[0])


def test_anexo_sem_subtarefa_cai_na_raiz(baixar, tmp_path):
    itens = [{"nome": "solto.png", "url": "a"}]
    g, _ = baixar(itens, str(tmp_path), baixar=_fake)
    assert os.path.dirname(g[0]) == str(tmp_path)

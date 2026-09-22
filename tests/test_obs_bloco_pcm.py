# -*- coding: utf-8 -*-
"""O bloco [PCM] é transporte, e editar a observação não pode apagá-lo (Levi, 15/09/2026).

A solicitação do Fracttal não tem campo para tema, técnico sugerido, data sugerida nem para a
lista de subtarefas que o supervisor editou. Tudo isso viaja DENTRO da observação, em formato
parseável, e a Fila do PCM lê de volta — a grade de subtarefas que o PCM vê é montada a partir
dele. Daí as duas regras que estes testes guardam:

  · a tela mostra só o RELATO, senão o PCM lê a mesma lista duas vezes;
  · ao gravar, o bloco volta INTACTO, senão a fila perde o tema e as subtarefas em silêncio.
"""
import solic_spec as sp


OBS = """Transformador da cabine 1 com ruído alto desde ontem.
Equipe de campo já isolou o trecho.

[PCM]
Tema: Transformador - substituição
Técnico sugerido: Adriano Silva
Data sugerida: 15/09/2026 07:00
Subtarefas:
- [Texto] Realizar a desenergização do transformador  (anexo obrigatório)
- [Texto] Registro fotográfico da atividade  (anexo obrigatório)"""


def test_o_relato_e_so_o_que_a_pessoa_escreveu():
    r = sp.relato(OBS)
    assert r.startswith("Transformador da cabine 1")
    assert "isolou o trecho" in r
    assert "[PCM]" not in r and "Subtarefas:" not in r, "o transporte não é texto de gente"


def test_o_bloco_sai_inteiro_para_ser_devolvido():
    b = sp.so_bloco(OBS)
    assert b.startswith("[PCM]")
    assert "Adriano Silva" in b and "Registro fotográfico" in b
    assert "ruído alto" not in b, "o relato não entra no bloco"


def test_relato_mais_bloco_reconstituem_a_observacao():
    """É exatamente o que a Fila faz ao gravar: texto novo + bloco guardado."""
    novo = "Transformador da cabine 1 com ruído alto. Peça sobressalente já separada."
    inteiro = (novo + "\n\n" + sp.so_bloco(OBS)).strip()
    assert sp.relato(inteiro) == novo
    assert sp.parse(inteiro).get("tecnico") == "Adriano Silva"
    assert len(sp.parse(inteiro).get("subtarefas") or []) == 2


def test_observacao_sem_bloco_nao_inventa_nada():
    livre = "Só um relato, sem sugestão nenhuma."
    assert sp.relato(livre) == livre
    assert sp.so_bloco(livre) == ""


def test_observacao_vazia():
    assert sp.relato("") == "" and sp.so_bloco("") == ""
    assert sp.relato(None) == "" and sp.so_bloco(None) == ""


def test_observacao_que_e_SO_bloco():
    """Acontece quando o supervisor não escreve relato: o campo abre vazio e o bloco sobrevive."""
    so = sp.so_bloco(OBS)
    assert sp.relato(so) == ""
    assert sp.so_bloco(so) == so


def test_gravar_so_o_relato_APAGARIA_o_bloco():
    """O teste que explica o bug: é isto que a tela fazia antes de guardar o bloco à parte."""
    novo = "texto novo"
    assert sp.parse(novo) == {}, "sem bloco, a fila perde tema, técnico e subtarefas"

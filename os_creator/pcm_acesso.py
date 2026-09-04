# -*- coding: utf-8 -*-
"""A tranca da Área PCM.

O QUE ELA É, E O QUE NÃO É. É uma **tranca de porta**, não um cofre. O app roda na máquina de
quem usa: quem quiser mesmo entrar consegue — basta abrir o executável ou trocar o relógio. O
que ela impede é o acesso POR ENGANO: o supervisor que clica em "Área PCM" por curiosidade e
aprova uma solicitação sem querer, ou o técnico que muda um tema achando que é só olhar.

Se um dia a exigência for de verdade — auditoria, gente demitida que não pode mais aprovar —,
o caminho é o login que o app JÁ TEM (`fracttal-os-creator-multiusuario`): o Fracttal sabe quem
entrou, e a permissão pode vir de lá. Esta senha não substitui aquilo, e não deve ser vendida
como se substituísse.

GUARDO O HASH, não o texto. Não muda o limite acima — muda só que quem abrir o .exe num editor
de texto não acha a senha de graça. Custa nada e evita o achado bobo.
"""
import hashlib
import os

# SHA-256 de "PCM@2026" (definida pelo Levi em 04/09/2026).
_HASH = "f410f28011208877564e48fa6ea6c74020be2817de7bdce661ad45ee3b51894e"

_liberado = False          # por SESSÃO: pedir a cada clique faria a senha acabar no monitor


def _norm(t):
    return (t or "").strip()


def confere(senha) -> bool:
    return hashlib.sha256(_norm(senha).encode("utf-8")).hexdigest() == _HASH


def liberado() -> bool:
    return _liberado


def liberar():
    global _liberado
    _liberado = True


def trancar():
    """Volta a pedir a senha. Existe para o teste e para um eventual 'sair da área'."""
    global _liberado
    _liberado = False

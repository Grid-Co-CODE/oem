"""Prova que a bancada de testes existe e enxerga o os_creator.

Existe porque a migração de 28/08 (git filter-repo) deixou tests/ e conftest.py para trás no
repositório antigo — o repo novo nasceu sem bancada nenhuma."""


def test_os_creator_importavel():
    import versao
    assert versao.APP_VERSAO

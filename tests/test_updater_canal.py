"""O endereço de atualização — a única linha do app cujo erro não se conserta remotamente.

`RELEASE_REPO` fica gravado dentro do .exe de cada pessoa. Se ele apontar para um repositório
onde a release não foi publicada, a máquina continua funcionando e simplesmente para de receber
versão nova — em silêncio, sem erro nenhum na tela. Quando alguém percebe, o conserto é
reinstalar máquina a máquina.

Por isso o valor é conferido aqui: um `git revert` distraído ou um merge de branch antiga que
trouxesse de volta o endereço pessoal derrubaria a migração de 31/08 sem ninguém notar.
"""
import os
import re

import steps.updater as updater

CANAL = "Grid-Co-CODE/oem-release"


def test_o_canal_e_o_repositorio_da_organizacao():
    # migrado em 31/08, depois de a T.I. liberar a escrita. O endereço pessoal antigo
    # (Levi-6242/os-creator-releases) segue recebendo release enquanto houver máquina abaixo da
    # 167, mas quem instala hoje já nasce olhando para cá.
    assert updater.RELEASE_REPO == CANAL


def test_a_url_do_versao_json_sai_do_canal():
    # a URL é montada por f-string; trocar o repositório sem que a URL acompanhe já aconteceu em
    # projeto irmão e só aparece em produção.
    assert updater._VERSAO_URL == (
        "https://github.com/%s/releases/latest/download/versao.json" % CANAL)


def test_o_repositorio_publico_nao_aparece_com_credencial():
    # o canal é público de propósito (asset sem login). Um token na URL vazaria em toda máquina.
    fonte = os.path.join(os.path.dirname(updater.__file__), "updater.py")
    with open(fonte, encoding="utf-8") as f:
        txt = f.read()
    assert not re.search(r"github\.com/[^\s\"']*[:@]", txt)
    assert "Authorization" not in txt

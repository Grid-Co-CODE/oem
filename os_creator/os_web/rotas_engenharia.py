# os_creator/os_web/rotas_engenharia.py
"""Área Engenharia na web — a moldura do desktop (steps/engenharia/tela.py), nada mais.

Nasce vazia de propósito, como no app: o conteúdo é da Engenharia (docs/ambiente-compartilhado-engenharia.md, §7) e
desenhá-lo aqui anularia o arranjo do fork. Título, descrição e ícone vêm do descritor da área (`steps/engenharia`),
o mesmo que o launcher do desktop lê — assim, quando a Engenharia mudar o texto, a web acompanha sem edição."""
from __future__ import annotations

from flask import Blueprint, render_template

from steps import engenharia as area

from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_engenharia", __name__, url_prefix="/os")

AVISO = "Área em construção pela Engenharia. O primeiro fluxo será OS de ETM."   # o texto da tela do desktop


@bp.route("/engenharia")
@exige_sessao
def engenharia():
    return render_template("engenharia.html", conta=_conta(), aba="criar", titulo=area.TITULO, descricao=area.DESCRICAO,
                           aviso=AVISO, icone_svg=area.ICONES.get(area.ICONE, ""))

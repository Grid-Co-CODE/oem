# os_creator/os_web/rotas_fornecedores.py
"""Controle de fornecedores — a terceira porta do card de Chamados (Levi, 27/09/2026). A tela edita os modelos da
inspeção de chamado (base, tipo de ativo, fornecedor); a regra de validar e gravar é do `chamado_modelos_store`, o
desenho dos dados é do `fornecedores_web`. Salvar vale NA HORA para a Inspeção de chamados deste servidor; os outros
processos pegam na próxima releitura (TTL do store)."""
from __future__ import annotations

import requests
from flask import Blueprint, jsonify, render_template, request, session

import chamado_modelos_store as modelos

from . import fornecedores_web as fw
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_fornecedores", __name__, url_prefix="/os")


@bp.route("/chamados/fornecedores")
@exige_sessao
def fornecedores():
    modelos.garantir()
    return render_template("fornecedores.html", conta=_conta(), aba="criar", dados=fw.tela(modelos.efetivo()),
                           erro_banco=modelos._estado.get("erro") or "")


@bp.route("/api/fornecedores/salvar", methods=["POST"])
@exige_sessao
def api_salvar():
    c = request.get_json(silent=True) or {}
    conta = session.get("conta") or {}
    quem = str(conta.get("nome") or conta.get("email") or "").strip()
    try:
        valor = modelos.salvar(str(c.get("chave") or ""), c.get("dados") or {}, str(c.get("versao") or ""), quem)
    except ValueError as e:
        return jsonify({"erro": str(e)}), 400
    except modelos.Conflito as e:
        return jsonify({"erro": str(e), "conflito": True}), 409
    except modelos.SemCredencial as e:
        return jsonify({"erro": str(e)}), 403
    except requests.RequestException as e:
        return jsonify({"erro": "O banco da Gridco não respondeu: %s" % str(e)[:160]}), 502
    return jsonify({"ok": True, "versao": valor.get("versao"), "tela": fw.tela(modelos.efetivo()),
                    "mensagem": "Salvo. A próxima inspeção aberta pelo OS Creator já sai com isto."})

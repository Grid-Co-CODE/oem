# -*- coding: utf-8 -*-
"""As observações da equipe de chamados sobre cada OS de acompanhamento (a OS 3), no banco da Gridco: workbook
`os_creator`, aba `chamados_obs`, UMA LINHA POR OBSERVAÇÃO.

Pedido do Levi em 27/09/2026: "ao clicar na OS abre uma tela onde ela vê todas as informações do chamado daquele ativo
e pode escrever observações, essas observações vão salvar o dia que a Singrid escreveu".

POR QUE NÃO NA NOTA DA OS: a nota da OS 3 é a cópia das respostas do técnico, montada pelo servidor do App (até 3.800
caracteres, de onde se abre o ticket no fornecedor). Misturar o diário ali estragaria as duas coisas — e editar a nota
troca o texto INTEIRO: duas pessoas escrevendo ao mesmo tempo, uma perde o que escreveu.

SÓ POST, NUNCA PUT: observação não se edita nem se apaga pela tela. Linha nova a cada vez é o que torna a escrita
segura entre duas pessoas (não há linha para uma sobrescrever a da outra) e o que mantém o histórico honesto.

A DATA É DO SERVIDOR, em Brasília, carimbada na hora em que a linha é gravada — a pessoa não digita data. A planilha de
chamados tinha 3 datas digitadas no futuro (2027); aqui isso não acontece.
"""
import datetime as dt
import json
import threading
import time
import uuid

import gridco_abas as ga

WORKBOOK = "os_creator"
NOME_ABA = "chamados_obs"
# `extra` é JSON para o que vier depois: a aba não alarga depois de criada (ver gridco_abas.Aba.id)
COLUNAS = ["id", "quando", "os", "ativo", "tipo", "texto", "quem", "email", "extra"]
TIPOS = ("obs", "ticket", "finalizado")
LIMITE_TEXTO = 2000
TTL = 60           # s: a leitura da aba inteira vale isto (a própria escrita já entra no cache na hora)

ABA = ga.Aba(WORKBOOK, NOME_ABA, COLUNAS)
SemCredencial = ga.SemCredencial

_estado = {"lista": None, "lido": 0.0}
_trava = threading.Lock()
BRT = dt.timezone(dt.timedelta(hours=-3))


def agora_brt() -> dt.datetime:
    return dt.datetime.now(BRT).replace(microsecond=0)


def _linhas() -> list:
    """As linhas cruas — o ÚNICO ponto que vai à rede na leitura (os testes trocam só este)."""
    return ABA.linhas()


def _de_linha(l: dict):
    r = ABA.registro(l)
    if not (str(r.get("id") or "").strip() and str(r.get("quando") or "").strip() and str(r.get("os") or "").strip()):
        return None
    try:
        extra = json.loads(r.get("extra") or "{}")
    except (TypeError, ValueError):
        extra = {}
    tipo = str(r.get("tipo") or "obs").strip()
    return {"id": str(r["id"]).strip(), "quando": str(r["quando"]).strip(), "os": str(r["os"]).strip(),
            "ativo": str(r.get("ativo") or "").strip(), "tipo": tipo if tipo in TIPOS else "obs",
            "texto": str(r.get("texto") or ""), "quem": str(r.get("quem") or "").strip(),
            "email": str(r.get("email") or "").strip(), "extra": extra if isinstance(extra, dict) else {}}


def listar(forcar: bool = False) -> list:
    """Todas as observações, da mais antiga à mais nova. Levanta se o banco não responder."""
    with _trava:
        if _estado["lista"] is not None and not forcar and time.time() - _estado["lido"] < TTL:
            return list(_estado["lista"])
    vistos, lista = set(), []
    for l in _linhas():
        x = _de_linha(l)
        if x and x["id"] not in vistos:               # o id é o que impede o clique duplo de virar duas entradas
            vistos.add(x["id"])
            lista.append(x)
    lista.sort(key=lambda x: x["quando"])
    with _trava:
        _estado.update(lista=lista, lido=time.time())
    return list(lista)


def do_os(folio) -> list:
    alvo = str(folio).strip()
    return [x for x in listar() if x["os"] == alvo]


def ultima_por_os() -> dict:
    """{nº da OS: quando da última entrada} — a régua da cobrança ("há N dias sem atualização")."""
    out = {}
    for x in listar():
        out[x["os"]] = max(out.get(x["os"], ""), x["quando"])
    return out


def finalizado_por_os() -> dict:
    """{nº da OS: quando foi finalizada pela tela}. A OS de acompanhamento é concluída sem registro de execução, e aí o
    Fracttal deixa a data de fim VAZIA — sem esta data o card finalizado não diria quando, nem sairia do quadro."""
    out = {}
    for x in listar():
        if x["tipo"] == "finalizado":
            out[x["os"]] = max(out.get(x["os"], ""), x["quando"])
    return out


def adicionar(os_folio, texto: str, tipo: str = "obs", ativo: str = "", quem: str = "", email: str = "",
              extra: dict = None, agora: dt.datetime = None, id_: str = "") -> dict:
    """Grava UMA observação, com a data e a hora do servidor. → o registro gravado."""
    texto = str(texto or "").strip()
    if not texto:
        raise ValueError("Escreva a observação antes de salvar.")
    if len(texto) > LIMITE_TEXTO:
        raise ValueError("A observação passa de %d caracteres." % LIMITE_TEXTO)
    if tipo not in TIPOS:
        raise ValueError("Tipo de observação desconhecido: %s." % tipo)
    if not str(os_folio or "").strip():
        raise ValueError("Sem o número da OS.")
    reg = {"id": (id_ or uuid.uuid4().hex[:12]), "quando": (agora or agora_brt()).isoformat(),
           "os": str(os_folio).strip(), "ativo": str(ativo or "").strip(), "tipo": tipo, "texto": texto,
           "quem": str(quem or "").strip(), "email": str(email or "").strip(), "extra": dict(extra or {})}
    ABA.inserir(dict(reg, extra=json.dumps(reg["extra"], ensure_ascii=False)))
    with _trava:
        if _estado["lista"] is not None and all(x["id"] != reg["id"] for x in _estado["lista"]):
            _estado["lista"].append(reg)
            _estado["lista"].sort(key=lambda x: x["quando"])
    return reg

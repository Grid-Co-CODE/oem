# -*- coding: utf-8 -*-
"""O que o PCM edita no banco da Gridco e o app de mesa só lia do código — os temas da Solicitação (`temas_store`) e os
modelos da inspeção de chamado (`chamado_modelos_store`) —, aplicado na ABERTURA do app.

POR QUE EXISTE. Achado em 27/09/2026: o `temas_store.aplicar_no_spec` dizia "chamado uma vez na abertura do app" e nada o
chamava — só a tela de Temas, depois de salvar, e só na máquina de quem salvou. O PCM salvava um tema e as outras
máquinas seguiam com os do código na Solicitação e na Fila. O `chamado_modelos_store`, do mesmo dia, nasceu com o mesmo
buraco: o os_web aplicava (`garantir`), a Inspeção do app de mesa não.

EM DUAS METADES, de propósito:
- `ler()` roda no ApiWorker e só vai à rede. Com o banco fora do ar ela espera os timeouts (20 s por pedido), e isso
  não pode segurar a janela.
- `aplicar()` roda na thread da interface, no slot do `ok`, na MESMA passada em que os combos são remontados: nenhum
  clique cai entre o `sp.TEMAS` novo e o combo ainda velho, nem no meio da troca dos dicionários. Aplicar é trocar
  dicionário em memória — cabe na thread da interface com folga, e os combos só podem ser remontados nela.

BANCO FORA DO AR = NADA MUDA. A parte que falhou volta `None` e o código fica como estava. A semente NÃO é reaplicada:
`temas_store.da_semente()` não guarda o `obrig`, e reaplicá-la tornaria obrigatória a "Verificar danos em outros itens
pré-roçada" da Vegetação — o código mudando por causa de uma queda de rede. A falha vai para o
%TEMP%\\criaros_erros.log: "o PCM salvou e na minha máquina não mudou" começa por lá.

Vale na PRÓXIMA ABERTURA: o que o PCM salvar com o app já aberto chega na vez seguinte em que ele abrir (a tela de Temas
da própria máquina aplica na hora)."""
import chamado_modelos_store as cms
import temas_store as ts
from workers import registrar_erro


def ler() -> dict:
    """As duas abas, cada uma por conta própria: uma fora do ar não segura a outra. Nunca levanta."""
    lido = {"temas": None, "chamado": None}
    try:
        lido["temas"] = ts.do_banco() or None       # aba vazia = nada a aplicar: vale o código
    except Exception:                               # noqa: BLE001 — banco fora: segue o código
        registrar_erro()
    try:
        lido["chamado"] = cms.carregar(forcar=True)
    except Exception:                               # noqa: BLE001
        registrar_erro()
    return lido


def aplicar(lido) -> dict:
    """Joga por cima do código o que `ler` trouxe. {"temas": mudou?, "chamado": mudou?} — é o que diz à janela quais
    telas remontar."""
    lido = lido or {}
    feito = {"temas": False, "chamado": False}
    if lido.get("temas"):
        feito["temas"] = bool(ts.aplicar_no_spec(lido["temas"]))
    if lido.get("chamado") is not None:
        cms.aplicar(lido["chamado"])
        feito["chamado"] = bool(lido["chamado"])     # aba vazia: o pacote segue no código, nada a remontar
    return feito

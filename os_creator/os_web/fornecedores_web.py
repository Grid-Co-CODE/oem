# os_creator/os_web/fornecedores_web.py
"""Controle de fornecedores (Levi, 27/09/2026): as subtarefas que descem na inspeção de chamado, por tipo de ativo e
fornecedor — "separe entre inversor, tracker e +oque tiver … algo parecido com o PCM na administração dos temas".
PURO; a gravação é do `chamado_modelos_store` e as rotas moram em `rotas_fornecedores.py`.

A inspeção nasce com três blocos, nesta ordem (`chamado_garantia.spec.subtarefas`): a BASE (toda inspeção), o bloco do
TIPO de ativo (a identificação do equipamento) e o que o FORNECEDOR pede a mais. A tela mostra os três e deixa editar
cada um no seu lugar — mudar a base num fornecedor mudaria todos sem ninguém perceber.
"""
from __future__ import annotations

import chamado_insp_spec as ci
import chamado_spec as cs
import gridco_abas as ga

# (tipo do pacote, nome na aba, como a tela chama o bloco). "Tracker" é o "Estrutura Trackers" do catálogo: não existe
# tipo "Tracker" no Fracttal (medido: 0 ativos) — o tracker individual É Estrutura Trackers.
ABAS = [("Inversor", "Inversor", "Todo inversor"), ("Estrutura Trackers", "Tracker", "Todo tracker"),
        ("NCU", "NCU", "Toda NCU"), ("RSU", "RSU", "Toda RSU"),
        ("Estação Meteorológica", "Estação meteorológica", "Toda estação meteorológica"),
        ("Cabine", "Cabine", "Toda cabine"), ("Skid", "Skid", "Todo skid")]
TIPO_NOME = {"texto": "Texto", "longo": "Texto longo", "num": "Número", "simnao": "Sim / Não",
             "verif": "Verificação", "lista": "Lista"}


def _chaves_desc(subs) -> set:
    return {str(s.get("desc") or "").strip().lower() for s in subs or []}


def tela(ef: dict) -> dict:
    """O JSON que a tela desenha: os blocos como valem agora (com versão e origem) e, por aba, a contagem REAL de cada
    fornecedor — pela função do pacote, que tira as repetidas e as que valem só para outro tipo."""
    blocos = {}
    for ch, v in ef.items():
        blocos[ch] = {"subtarefas": list(v.get("subtarefas") or []), "versao": v.get("versao") or "",
                      "por": v.get("por") or "", "origem": v.get("origem") or "codigo"}
        if ch.startswith("MARCA:"):
            blocos[ch].update(canal=v.get("canal") or "", atende=list(v.get("atende") or []),
                              arquivado=bool(v.get("arquivado")), igual_a=v.get("igual_a") or "")
    antes_base = _chaves_desc(ef["BASE"]["subtarefas"])
    abas = []
    for tipo, nome, todo in ABAS:
        antes = antes_base | _chaves_desc(ef.get("TIPO:" + tipo, {}).get("subtarefas"))
        forn = []
        for ch, v in ef.items():
            if not ch.startswith("MARCA:") or tipo not in (v.get("atende") or []):
                continue
            m = ch[6:]
            arq = bool(v.get("arquivado"))
            proprias = [s for s in v.get("subtarefas") or []
                        if (not s.get("so_para") or tipo in s["so_para"])
                        and str(s.get("desc") or "").strip().lower() not in antes]
            forn.append({"marca": m, "arquivado": arq, "canal": v.get("canal") or "", "igual_a": v.get("igual_a") or "",
                         "n_proprias": len(proprias),
                         "n_total": 0 if arq else len(ci.subtarefas(tipo, m)),
                         "resumo": "" if arq else ci.resumo(tipo, m)})
        forn.sort(key=lambda f: (f["arquivado"], f["marca"].lower()))
        sem_doc = [m for m in cs.FABRICANTES_SEM_DOC if "MARCA:" + m not in ef] if tipo == "Inversor" else []
        abas.append({"tipo": tipo, "nome": nome, "todo": todo, "fornecedores": forn, "sem_doc": sem_doc,
                     "alias": sorted(a for a, g in ci.ALIAS_TIPO.items() if g == tipo),
                     "n_base_tipo": len(ci.subtarefas(tipo, ""))})
    return {"abas": abas, "blocos": blocos, "tipos": TIPO_NOME, "tipos_ativo": [t for t, _, _ in ABAS],
            "pode_gravar": ga.pode_gravar()}

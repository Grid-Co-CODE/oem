# os_creator/os_web/ativos_web.py
"""Ativos — a parte pura do porte de `steps/ativos.py`: constantes da tela (o teste de fidelidade compara com o app),
o registro enxuto que vai ao navegador, o resumo das últimas OS e os destinos do menu "Criar OS neste ativo"."""
from __future__ import annotations
from urllib.parse import quote

import api

# (rótulo curto p/ caber, valor EXATO do tipo p/ o filtro) — `steps/ativos.py::TIPOS_CHIP`
TIPOS_CHIP = (("Inversor", "Inversor"), ("Trackers", "Estrutura Trackers"), ("Cabine", "Cabine"),
              ("Estação Met.", "Estação Meteorológica"), ("Skid", "Skid"))
LIMITE_TABELA = 400
# menu do "Criar OS": (rótulo, frase do plano de Performance). As frases são as de `api._PERF_PLANOS` — o `perf_criar`
# casa a sugestão por trecho, então a frase inteira sempre acerta. SEM frase o app caía fixo em Recomposição (item 17).
DESTINOS_OS = (
    ("Performance · Coleta e análise de dados", "coleta de dados de geracao"),
    ("Performance · Inspeção geral do inversor", "inspecao geral do inversor"),
    ("Performance · Recomposição de string", "recomposicao de string"),
    ("Performance · Verificação de tracker parado", "verificacao de tracker parado"),
)
COR_STATUS = {"Concluída": "#3fb27f", "Em Processo": "#4a9eff", "Em Verificação": "#eb8b57", "Cancelada": "#e05454"}
ROTULO_INSPECAO = "Inspeção de chamado (garantia)"


def nome_curto(descricao) -> str:
    """'Inversor 2.18 {SMA Sunny}' → 'Inversor 2.18' (o que vem entre chaves é metadado do Fracttal)."""
    return str(descricao or "").split("{")[0].strip()


def usina_exibe(usina, cliente) -> str:
    """'2C - Araputanga 1 - MT' com cliente '2C' → 'Araputanga 1 - MT' (item 7): o cliente na frente só repetia a
    coluna ao lado."""
    u, c = str(usina or "").strip(), str(cliente or "").strip()
    if c and api._norm_txt(u).startswith(api._norm_txt(c) + " - "):
        return u[len(c) + 3:].strip() or u
    return u


def enxuto(a: dict) -> dict:
    """Só o que a tela usa — 18 mil registros inteiros pesariam à toa no navegador."""
    return {"id": a.get("id"), "code": a.get("code"), "nome": nome_curto(a.get("description")), "tipo": a.get("tipo"),
            "cliente": a.get("cliente"), "usina": a.get("usina"), "usina_curta": usina_exibe(a.get("usina"), a.get("cliente")),
            "id_parent": a.get("id_parent")}


def os_resumo(lista: list) -> list:
    """As últimas 4 OS do ativo, da MAIOR para a menor (item 5), no formato do cartãozinho do painel."""
    out = []
    for d in sorted(lista or [], key=api._ordem_os, reverse=True)[:4]:
        out.append({"folio": d.get("folio") or "—", "id": d.get("id"), "data": (api.fmt_data_br(d.get("event_date")) or "")[:5],
                    "tipo_tarefa": (d.get("tipo_tarefa") or "—")[:20], "status": d.get("status") or "—",
                    "cor": COR_STATUS.get(d.get("status"), "#8A93A8")})
    return out


def destinos(a: dict, inspecao: bool) -> list:
    """Os destinos do menu: os 4 planos de Performance (a tela de criar já aceita usina/ativo sugeridos) e, para quem tem
    modelo de inspeção, a Inspeção de chamado (garantia)."""
    usina, nome = a.get("usina") or "", nome_curto(a.get("description"))
    out = [{"rotulo": r, "href": f"/os/performance/criar?frase={quote(t)}&usina={quote(usina)}&ativo={quote(nome)}"}
           for r, t in DESTINOS_OS]
    if inspecao:
        out.append({"rotulo": ROTULO_INSPECAO, "href": f"/os/inspecao?ativo={a.get('id')}"})
    return out

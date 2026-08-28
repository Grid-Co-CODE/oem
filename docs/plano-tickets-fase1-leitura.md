# Tickets no OS Creator — Fase 1 (leitura) — plano de implementação

> **Para quem for executar:** SUB-SKILL OBRIGATÓRIA — use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar tarefa a tarefa. Os passos usam
> caixinhas (`- [ ]`) para acompanhamento.

**Objetivo:** aba Tickets no OS Creator mostrando as ocorrências de Trackers e Strings vindas da
Gridco Performance API, **somente leitura**, com a indisponibilidade recalculada pelo app e
validada contra o gabarito existente.

**Arquitetura:** três camadas separadas por responsabilidade. `tickets_api.py` só fala HTTP e
pagina. `tickets_spec.py` é puro: declara as duas abas, converte linha↔dicionário, calcula
indisponibilidade e estado — sem rede, portanto inteiramente testável. `steps/tickets.py` é só
tela. A tela entra como card do lançador, seguindo o padrão do Ativos.

**Stack:** Python 3.14 · PyQt6 · requests · pytest 9.1

**Spec:** [`docs/tickets-no-os-creator.md`](tickets-no-os-creator.md)

## Restrições globais

- **pt-BR em tudo**, inclusive comentário de código.
- **Sem emoji na interface.** Severidade se comunica por cor.
- Tema navy: `BG=#0B1020`, `CARD=#121A2B`, `INPUT=#1A2337`, `BORDER=#2A3550`, `GREEN=#A6E22E`,
  `TEXT=#FFFFFF`, `MUTED=#8A93A8`. Cores vêm de `steps/ui.py`; **não inventar hex**.
- Cores de estado (fora da paleta da marca): `#e05454` vermelho, `#eb8b57` âmbar,
  `#4a9eff` azul, `#3fb27f` verde.
- **Esta fase não escreve nada.** Nenhuma chamada `PUT` ou `POST`. Nenhum uso do
  `GRIDCO_SQL_TOKEN`.
- Toda chamada de rede na tela vai por `ApiWorker` (`workers.py`). **Nunca** `QThread` solta.
- Comentário de código explica **por quê**, citando o caso real que motivou a regra.
- Base da API: `https://app.gridco.com.br/db_performace`. Leitura é aberta, sem credencial.
- `sheet_id` **123** = Trackers, **128** = Strings indisp.

---

### Tarefa 1: Infraestrutura de teste no repositório

O `git filter-repo` da migração de 28/08 só preservou `os_creator/` e `chamado_garantia/`. O
`tests/`, o `conftest.py` e o `pytest.ini` ficaram no repositório antigo. Sem isto, nenhuma das
tarefas seguintes tem onde rodar.

**Arquivos:**
- Criar: `pytest.ini`
- Criar: `conftest.py`
- Criar: `tests/test_infra.py`

**Interfaces:**
- Consome: nada
- Produz: `import api`, `import tickets_api`, `import tickets_spec` funcionam de dentro de
  `tests/`, porque o `conftest.py` põe `os_creator/` no `sys.path`

- [ ] **Passo 1: escrever o teste que falha**

`tests/test_infra.py`:

```python
"""Prova que a bancada de testes existe e enxerga o os_creator.

Existe porque a migração de 28/08 (git filter-repo) deixou tests/ e conftest.py para trás no
repositório antigo — o repo novo nasceu sem bancada nenhuma."""


def test_os_creator_importavel():
    import versao
    assert versao.APP_VERSAO
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python -m pytest tests/test_infra.py -v`
Esperado: FALHA com `ModuleNotFoundError: No module named 'versao'`

- [ ] **Passo 3: criar o `pytest.ini` e o `conftest.py`**

`pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

`conftest.py` (na raiz do repositório):

```python
"""Fixtures e caminho de import dos testes.

Fica na RAIZ de propósito: o pytest insere o diretório de cada conftest.py no sys.path, e daqui
dá para apontar `os_creator/` sem instalar nada.

APPEND, nunca insert(0), pelo mesmo motivo documentado em os_creator/api.py: a raiz do
repositório não pode ganhar precedência sobre a pasta do app."""
import os
import sys

_RAIZ = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.join(_RAIZ, "os_creator")
if _APP not in sys.path:
    sys.path.insert(0, _APP)          # aqui insert(0) é correto: queremos o os_creator na frente
```

- [ ] **Passo 4: rodar e ver passar**

Rodar: `python -m pytest tests/test_infra.py -v`
Esperado: PASSA

- [ ] **Passo 5: commitar**

```bash
git add pytest.ini conftest.py tests/test_infra.py
git commit -m "test: bancada de testes, perdida na migracao do repositorio"
```

---

### Tarefa 2: Cálculo da indisponibilidade (janela solar 06–18)

O coração da fase. Função pura, sem rede. A fórmula foi lida do `.xlsx` vivo em 28/08 e está
transcrita na spec §10.

**Arquivos:**
- Criar: `os_creator/tickets_calc.py`
- Criar: `tests/test_tickets_calc.py`

**Interfaces:**
- Consome: nada
- Produz:
  - `indisponibilidade_horas(ini, fim) -> float | None`
  - `indisponibilidade_gridco(indisp, responsabilidade) -> float | None`
  - `_para_dt(v) -> datetime | None`

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_tickets_calc.py`:

```python
"""Régua da indisponibilidade — janela solar 06:00–18:00.

Os casos saem da fórmula LET lida no `.xlsx` (aba Trackers, coluna U) em 28/08. O que o Excel
faz, o app tem de fazer igual: fora da janela solar não conta, e dia inteiro vale 12 horas."""
from tickets_calc import indisponibilidade_gridco, indisponibilidade_horas


def test_mesmo_dia_dentro_da_janela():
    # 08:00 → 12:00 = 4 h
    assert indisponibilidade_horas("2026-08-01T08:00:00", "2026-08-01T12:00:00") == 4.0


def test_mesmo_dia_comecando_antes_das_6():
    # 03:00 é grampeado para 06:00 → 06:00–10:00 = 4 h
    assert indisponibilidade_horas("2026-08-01T03:00:00", "2026-08-01T10:00:00") == 4.0


def test_mesmo_dia_terminando_depois_das_18():
    # 22:00 é grampeado para 18:00 → 14:00–18:00 = 4 h
    assert indisponibilidade_horas("2026-08-01T14:00:00", "2026-08-01T22:00:00") == 4.0


def test_mesmo_dia_inteiramente_fora_da_janela():
    # 19:00 → 23:00: os dois grampeiam para 18:00 → zero
    assert indisponibilidade_horas("2026-08-01T19:00:00", "2026-08-01T23:00:00") == 0.0


def test_dias_seguidos_sem_dia_inteiro_no_meio():
    # ponta do dia 1: 18 − 10 = 8 h ; ponta do dia 2: 14 − 6 = 8 h ; nenhum dia inteiro
    assert indisponibilidade_horas("2026-08-01T10:00:00", "2026-08-02T14:00:00") == 16.0


def test_com_dois_dias_inteiros_no_meio():
    # 8 + 8 + 2 dias inteiros × 12 = 40 h
    assert indisponibilidade_horas("2026-08-01T10:00:00", "2026-08-04T14:00:00") == 40.0


def test_fim_vazio_devolve_none():
    # o IFERROR do Excel devolve "" — aqui é None, e a tela mostra vazio, NÃO zero.
    # Zero significaria "ficou zero hora parado", que é uma afirmação falsa.
    assert indisponibilidade_horas("2026-08-01T10:00:00", None) is None
    assert indisponibilidade_horas("2026-08-01T10:00:00", "") is None


def test_data_invalida_devolve_none():
    assert indisponibilidade_horas("A ser verificado", "2026-08-01T10:00:00") is None


def test_gridco_sim_repassa_o_valor_cheio():
    assert indisponibilidade_gridco(10.0, "Sim") == 10.0


def test_gridco_parcial_desconta_seis():
    assert indisponibilidade_gridco(10.0, "Parcial") == 4.0


def test_gridco_parcial_curto_nao_fica_negativo():
    # DESVIO DELIBERADO do Excel: a fórmula original não tem piso, então uma ocorrência Parcial
    # de 2 h daria −4. Indisponibilidade negativa não significa nada num relatório de cliente.
    assert indisponibilidade_gridco(2.0, "Parcial") == 0.0


def test_gridco_nao_e_vazio_dao_zero():
    assert indisponibilidade_gridco(10.0, "Não") == 0.0
    assert indisponibilidade_gridco(10.0, None) == 0.0


def test_gridco_sem_indisponibilidade_devolve_none():
    assert indisponibilidade_gridco(None, "Sim") is None
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python -m pytest tests/test_tickets_calc.py -v`
Esperado: FALHA com `ModuleNotFoundError: No module named 'tickets_calc'`

- [ ] **Passo 3: implementar**

`os_creator/tickets_calc.py`:

```python
"""Indisponibilidade das ocorrências — a conta que hoje é fórmula do Excel.

A régua é JANELA SOLAR 06:00–18:00: hora fora dela não conta, e dia inteiro vale 12 horas.
Transcrita da fórmula LET da coluna U da aba Trackers, lida do `.xlsx` vivo em 28/08. Não é
`fim − início`, e essa diferença é grande: uma parada da noite de sexta à manhã de segunda dá
24 h nesta régua e 56 h na subtração ingênua.

A aba Trackers NÃO tem esses valores hoje (1.516 linhas encerradas, zero números): a fórmula de lá
aponta para `[1]!Tracker`, tabela em arquivo externo cujo vínculo não resolve. O gabarito para
conferir esta implementação são as 232 linhas de Strings indisp, onde a fórmula é local e
funciona."""
from datetime import datetime

INICIO_SOLAR = 6
FIM_SOLAR = 18
HORAS_DIA_INTEIRO = FIM_SOLAR - INICIO_SOLAR      # 12


def _para_dt(v):
    """Aceita o que a API devolve (ISO, com ou sem T, com ou sem fuso). Lixo vira None.

    Lixo acontece de verdade: a coluna Inversor da aba tem 'A ser verificado' e
    'Mapeamento agendado para 04/05' no lugar do valor."""
    if v in (None, "", " "):
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip().replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _hora_decimal(d):
    return d.hour + d.minute / 60.0 + d.second / 3600.0


def _grampeia(h):
    return min(max(h, INICIO_SOLAR), FIM_SOLAR)


def indisponibilidade_horas(ini, fim):
    """Horas solares entre início e fim. None quando não dá para calcular.

    None, nunca zero: o IFERROR do Excel devolve vazio, e vazio significa "não sei", enquanto
    zero significaria "ficou zero hora parado" — afirmação falsa sobre uma ocorrência aberta."""
    a, b = _para_dt(ini), _para_dt(fim)
    if a is None or b is None:
        return None

    h_ini, h_fim = _hora_decimal(a), _hora_decimal(b)

    if a.date() == b.date():
        return round(max(0.0, _grampeia(h_fim) - _grampeia(h_ini)), 6)

    # dias distintos: as duas pontas + os dias inteiros do meio
    ponta_ini = max(0.0, FIM_SOLAR - max(h_ini, INICIO_SOLAR))
    ponta_fim = max(0.0, min(h_fim, FIM_SOLAR) - INICIO_SOLAR)
    dias_meio = max(0, (b.date() - a.date()).days - 1)
    return round(dias_meio * HORAS_DIA_INTEIRO + ponta_ini + ponta_fim, 6)


def indisponibilidade_gridco(indisp, responsabilidade):
    """Parcela da indisponibilidade que é responsabilidade da Grid Co.

    Três casos, medidos na fórmula: Sim = valor cheio, Parcial = valor − 6, resto = 0.
    `Parcial` é o caso DOMINANTE (173 de 264 linhas de Trackers), então errar aqui erraria a
    maioria das linhas.

    DESVIO DELIBERADO: o Excel não põe piso no `− 6`, então uma ocorrência Parcial curta daria
    negativo. Aqui o piso é zero."""
    if indisp is None:
        return None
    r = str(responsabilidade or "").strip().lower()
    if r == "sim":
        return indisp
    if r == "parcial":
        return round(max(0.0, indisp - 6.0), 6)
    return 0.0
```

- [ ] **Passo 4: rodar e ver passar**

Rodar: `python -m pytest tests/test_tickets_calc.py -v`
Esperado: 13 PASSAM

- [ ] **Passo 5: commitar**

```bash
git add os_creator/tickets_calc.py tests/test_tickets_calc.py
git commit -m "feat(tickets): indisponibilidade por janela solar 06-18"
```

---

### Tarefa 3: Declaração das abas e conversão linha↔dicionário

15 das 23 colunas de Trackers e 15 das 18 de Strings são idênticas (spec §3). Este módulo é o que
faz "aba nova = declaração, não tela nova".

**Arquivos:**
- Criar: `os_creator/tickets_spec.py`
- Criar: `tests/test_tickets_spec.py`

**Interfaces:**
- Consome: nada
- Produz:
  - `ABAS: dict[str, dict]` — chaves `"Trackers"` e `"Strings"`, cada uma com
    `{"sheet_id": int, "extras": list[str], "rotulo": str}`
  - `NUCLEO: list[str]` — as 15 colunas compartilhadas
  - `linha_para_dict(headers, values) -> dict`
  - `estado_do_ticket(num_os, status_os, fim) -> str`
  - `ESTADOS: list[tuple[str, str, str]]` — (chave, rótulo, cor), na ordem do ciclo

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_tickets_spec.py`:

```python
"""Declaração das abas e o estado do ticket."""
from tickets_spec import ABAS, NUCLEO, estado_do_ticket, linha_para_dict


def test_as_duas_abas_declaradas_com_o_sheet_id_certo():
    assert ABAS["Trackers"]["sheet_id"] == 123
    assert ABAS["Strings"]["sheet_id"] == 128


def test_nucleo_tem_as_quinze_colunas_compartilhadas():
    assert len(NUCLEO) == 15
    assert "Início da ocorrência" in NUCLEO
    assert "Fim da ocorrência" in NUCLEO
    assert "Responsabilidade da Grid Co.?" in NUCLEO


def test_extras_nao_repetem_o_nucleo():
    for aba in ABAS.values():
        assert not (set(aba["extras"]) & set(NUCLEO))


def test_linha_para_dict_casa_cabecalho_com_valor():
    d = linha_para_dict(["Usina", "Status"], ["Araputanga", "Parado"])
    assert d["Usina"] == "Araputanga"
    assert d["Status"] == "Parado"


def test_linha_para_dict_tolera_valores_a_menos():
    # a API devolve linhas curtas quando as últimas células estão vazias
    d = linha_para_dict(["Usina", "Status", "Fim da ocorrência"], ["Araputanga"])
    assert d["Usina"] == "Araputanga"
    assert d["Status"] is None
    assert d["Fim da ocorrência"] is None


def test_linha_para_dict_ignora_cabecalho_vazio():
    # a coluna A da planilha é vazia — o cabeçalho começa em B
    d = linha_para_dict(["", "Usina"], ["lixo", "Araputanga"])
    assert d == {"Usina": "Araputanga"}


def test_estado_sem_os_e_aberta():
    assert estado_do_ticket("", "", None) == "aberta"
    assert estado_do_ticket(None, None, None) == "aberta"


def test_estado_com_os_em_processo():
    assert estado_do_ticket("10847", "Em Processo", None) == "com_os"


def test_estado_em_verificacao():
    # o estado que o Levi pediu em azul: o técnico fechou, ninguém confirmou
    assert estado_do_ticket("10847", "Em Verificação", None) == "verificando"


def test_estado_concluida_sem_fim_fica_a_fechar():
    # OS concluída mas o Fim ainda não foi gravado. Na fase de leitura isso é o passivo que a
    # fase de escrita vai resolver — precisa aparecer, não ser confundido com encerrada.
    assert estado_do_ticket("10847", "Concluída", None) == "a_fechar"


def test_estado_encerrada_exige_fim_preenchido():
    assert estado_do_ticket("10847", "Concluída", "2026-08-03T11:57:43") == "encerrada"


def test_fim_preenchido_encerra_mesmo_sem_os():
    # linha antiga, de antes da integração: tem fim e nunca teve OS
    assert estado_do_ticket("", "", "2026-08-03T11:57:43") == "encerrada"
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python -m pytest tests/test_tickets_spec.py -v`
Esperado: FALHA com `ModuleNotFoundError: No module named 'tickets_spec'`

- [ ] **Passo 3: implementar**

`os_creator/tickets_spec.py`:

```python
"""As abas de ocorrência do workbook `tickets_performance`, declaradas.

Medido em 28/08: 15 das 23 colunas de Trackers e 15 das 18 de Strings indisp são IDÊNTICAS. Não
são duas coisas — é uma ocorrência com dois conjuntos de extras. Por isso a tela é uma só e a aba
seguinte (Desligamentos, Inv. com baixa performance) entra aqui como declaração, não como tela
nova."""

NUCLEO = [
    "Usina", "Código da usina", "Cliente", "UF", "Supervisor(a)", "Responsável",
    "Causa raiz", "Responsabilidade da Grid Co.?",
    "Início da ocorrência", "Início do chamado pela Grid Co.", "Fim da ocorrência",
    "Indisponibilidade (horas)", "Indisponibilidade da Grid Co. (horas)",
    "Comentários para os clientes", "Comentários gerais",
]

ABAS = {
    "Trackers": {
        "sheet_id": 123,
        "rotulo": "Trackers",
        "extras": ["Fonte", "Equipamento", "Status", "Nº do SKID",
                   "Quantidade de trackers parados", "Nº do tracker / Identificação",
                   "Inversor", "Plano de ação"],
    },
    "Strings": {
        "sheet_id": 128,
        "rotulo": "Strings indisp",
        "extras": ["Inversor", "Quantidade de strings no inversor",
                   "Quantidade de strings no afetadas"],
    },
}

# (chave, rótulo, cor). A ORDEM é o ciclo de vida; a tela desenha nesta ordem.
# `a_fechar` só aparece na fase de leitura: é a OS concluída cujo Fim ainda não foi gravado —
# exatamente o passivo que a fase de escrita vai resolver.
ESTADOS = [
    ("aberta",      "Aberta",         "#e05454"),
    ("com_os",      "OS criada",      "#eb8b57"),
    ("verificando", "Em verificação", "#4a9eff"),
    ("a_fechar",    "A fechar",       "#eb8b57"),
    ("encerrada",   "Encerrada",      "#3fb27f"),
]
COR_ESTADO = {k: c for k, _, c in ESTADOS}
NOME_ESTADO = {k: n for k, n, _ in ESTADOS}


def linha_para_dict(headers, values):
    """Casa o cabeçalho com os valores da linha.

    Duas tolerâncias necessárias: a API devolve listas de valores mais curtas quando as últimas
    células estão vazias, e a planilha tem a coluna A vazia (o cabeçalho começa em B), o que
    produz um nome de coluna em branco que não interessa a ninguém."""
    out = {}
    for i, nome in enumerate(headers or []):
        chave = str(nome or "").strip()
        if not chave:
            continue
        out[chave] = values[i] if i < len(values or []) else None
    return out


def estado_do_ticket(num_os, status_os, fim):
    """Onde a ocorrência está no ciclo de vida. Ver spec §5."""
    if fim not in (None, "", " "):
        return "encerrada"
    if not str(num_os or "").strip():
        return "aberta"
    s = str(status_os or "").strip().lower()
    if "verifica" in s:
        return "verificando"
    if "conclu" in s:
        return "a_fechar"
    return "com_os"
```

- [ ] **Passo 4: rodar e ver passar**

Rodar: `python -m pytest tests/test_tickets_spec.py -v`
Esperado: 12 PASSAM

- [ ] **Passo 5: commitar**

```bash
git add os_creator/tickets_spec.py tests/test_tickets_spec.py
git commit -m "feat(tickets): declaracao das abas e ciclo de vida da ocorrencia"
```

---

### Tarefa 4: Cliente da API (leitura e paginação)

**Arquivos:**
- Criar: `os_creator/tickets_api.py`
- Criar: `tests/test_tickets_api.py`

**Interfaces:**
- Consome: `tickets_spec.linha_para_dict`
- Produz:
  - `BASE: str`
  - `listar_linhas(sheet_id, limite_total=None) -> list[dict]`
  - `_paginar(sheet_id, buscar) -> list[dict]` (injeção da função de busca, para teste sem rede)

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_tickets_api.py`:

```python
"""Paginação do cliente da Gridco Performance API.

A rota tem TETO DE 1000 linhas por chamada, e a aba Trackers tem 2.781. Sem paginar, o app
mostraria dois terços da realidade e ninguém perceberia — que é a pior classe de erro aqui."""
import tickets_api


def _falsa(paginas):
    """Devolve uma função de busca que serve as páginas dadas, na ordem."""
    chamadas = []

    def buscar(sheet_id, limit, offset):
        chamadas.append((limit, offset))
        i = offset // limit
        return paginas[i] if i < len(paginas) else []

    buscar.chamadas = chamadas
    return buscar


def test_uma_pagina_so():
    linhas = [{"row_number": n} for n in range(10)]
    r = tickets_api._paginar(123, _falsa([linhas]))
    assert len(r) == 10


def test_pagina_ate_o_fim():
    cheia = [{"row_number": n} for n in range(1000)]
    resto = [{"row_number": n} for n in range(200)]
    r = tickets_api._paginar(123, _falsa([cheia, resto]))
    assert len(r) == 1200


def test_para_quando_a_pagina_vem_vazia():
    cheia = [{"row_number": n} for n in range(1000)]
    b = _falsa([cheia, []])
    r = tickets_api._paginar(123, b)
    assert len(r) == 1000
    assert len(b.chamadas) == 2


def test_nunca_pede_mais_que_o_teto():
    b = _falsa([[{"row_number": 1}]])
    tickets_api._paginar(123, b)
    assert all(limit <= 1000 for limit, _ in b.chamadas)
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python -m pytest tests/test_tickets_api.py -v`
Esperado: FALHA com `ModuleNotFoundError: No module named 'tickets_api'`

- [ ] **Passo 3: implementar**

`os_creator/tickets_api.py`:

```python
"""Cliente de LEITURA da Gridco Performance API (espelho das planilhas).

Leitura é aberta: não usa credencial nenhuma. Escrita exigiria o GRIDCO_SQL_TOKEN e está fora
desta fase de propósito — enquanto o pipeline ainda subir o .xlsx com replace=true, qualquer
escrita daqui seria apagada no sync seguinte (ver spec §8)."""
import requests

from tickets_spec import linha_para_dict

BASE = "https://app.gridco.com.br/db_performace"
TETO = 1000          # teto da rota; a aba Trackers tem 2.781 linhas
TIMEOUT = 20


def _buscar(sheet_id, limit, offset):
    r = requests.get("%s/api/sheets/%s/rows" % (BASE, sheet_id),
                     params={"limit": limit, "offset": offset}, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else (d.get("rows") or d.get("items") or [])


def _paginar(sheet_id, buscar=None):
    """Junta as páginas até vir uma incompleta ou vazia.

    `buscar` é injetável para o teste rodar sem rede."""
    buscar = buscar or _buscar
    out, offset = [], 0
    while True:
        pagina = buscar(sheet_id, TETO, offset)
        if not pagina:
            break
        out.extend(pagina)
        if len(pagina) < TETO:
            break
        offset += TETO
    return out


def listar_linhas(sheet_id):
    """Todas as linhas da aba, já como dicionários {coluna: valor}.

    A primeira linha devolvida pela API carrega o cabeçalho; é ela que dá os nomes de coluna."""
    cruas = _paginar(sheet_id)
    if not cruas:
        return []
    headers = cruas[0].get("headers") or []
    out = []
    for r in cruas[1:]:
        d = linha_para_dict(headers, r.get("values") or [])
        d["_row"] = r.get("row_number")
        out.append(d)
    return out
```

- [ ] **Passo 4: rodar e ver passar**

Rodar: `python -m pytest tests/test_tickets_api.py -v`
Esperado: 4 PASSAM

- [ ] **Passo 5: commitar**

```bash
git add os_creator/tickets_api.py tests/test_tickets_api.py
git commit -m "feat(tickets): cliente de leitura da Gridco Performance API com paginacao"
```

---

### Tarefa 5: Portão de aceite — validar contra o gabarito de Strings

A tarefa que decide se as tarefas 2–4 podem ser confiadas. **Se falhar, a fase não avança.**

A aba Trackers não serve de gabarito: 1.516 linhas encerradas e zero valores (a fórmula de lá
aponta para arquivo externo que não resolve). O gabarito são as **232 linhas de Strings indisp**.

**Arquivos:**
- Criar: `tests/fixtures/tickets_strings.json`
- Criar: `tests/test_tickets_gabarito.py`

**Interfaces:**
- Consome: `tickets_api.listar_linhas`, `tickets_calc.indisponibilidade_horas`,
  `tickets_calc.indisponibilidade_gridco`
- Produz: nada (é portão)

- [ ] **Passo 1: gravar a fixture com dado real**

Rodar, da raiz do repositório:

```bash
python -c "import sys; sys.path.insert(0,'os_creator'); import json, tickets_api; json.dump(tickets_api.listar_linhas(128), open('tests/fixtures/tickets_strings.json','w',encoding='utf-8'), ensure_ascii=False)"
```

Esperado: arquivo criado com ~232 linhas. A fixture é gravada **uma vez** e commitada: o teste
precisa ser reproduzível sem rede e sem depender do estado da planilha no dia.

- [ ] **Passo 2: escrever o teste que falha**

`tests/test_tickets_gabarito.py`:

```python
"""Portão de aceite: o cálculo do app tem de bater com o que já está na planilha.

Gabarito são as 232 linhas de `Strings indisp`, a única das duas abas cuja fórmula de
indisponibilidade resolve (a de Trackers aponta para arquivo externo e está vazia, 1.516 linhas
encerradas sem número).

Divergência que não seja arredondamento REPROVA: é conta que vai para relatório de cliente."""
import io
import json
import os

from tickets_calc import indisponibilidade_gridco, indisponibilidade_horas

_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "tickets_strings.json")
TOLERANCIA = 0.02          # ~1 minuto; cobre arredondamento, não cobre régua errada


def _linhas():
    with io.open(_FIX, encoding="utf-8") as f:
        return json.load(f)


def _num(v):
    return v if isinstance(v, (int, float)) else None


def test_a_fixture_tem_gabarito_suficiente():
    com_valor = [l for l in _linhas() if _num(l.get("Indisponibilidade (horas)")) is not None]
    assert len(com_valor) >= 200, "gabarito pequeno demais para o portão significar algo"


def test_indisponibilidade_bate_com_a_planilha():
    ruins = []
    for l in _linhas():
        esperado = _num(l.get("Indisponibilidade (horas)"))
        if esperado is None:
            continue
        obtido = indisponibilidade_horas(l.get("Início da ocorrência"),
                                         l.get("Fim da ocorrência"))
        if obtido is None or abs(obtido - esperado) > TOLERANCIA:
            ruins.append((l.get("_row"), l.get("Início da ocorrência"),
                          l.get("Fim da ocorrência"), esperado, obtido))
    assert not ruins, "linhas divergentes (linha, ini, fim, planilha, app): %s" % ruins[:10]


def test_gridco_bate_com_a_planilha():
    ruins = []
    for l in _linhas():
        esperado = _num(l.get("Indisponibilidade da Grid Co. (horas)"))
        base = _num(l.get("Indisponibilidade (horas)"))
        if esperado is None or base is None:
            continue
        obtido = indisponibilidade_gridco(base, l.get("Responsabilidade da Grid Co.?"))
        # o piso em zero é desvio DELIBERADO do Excel: onde a planilha ficou negativa, o app
        # devolve 0 e isso não conta como divergência.
        if esperado < 0 and obtido == 0.0:
            continue
        if obtido is None or abs(obtido - esperado) > TOLERANCIA:
            ruins.append((l.get("_row"), l.get("Responsabilidade da Grid Co.?"), esperado, obtido))
    assert not ruins, "linhas divergentes (linha, responsabilidade, planilha, app): %s" % ruins[:10]
```

- [ ] **Passo 3: rodar**

Rodar: `python -m pytest tests/test_tickets_gabarito.py -v`

**Se passar:** as tarefas 2–4 estão validadas contra dado real; siga.

**Se falhar:** **PARE e reporte.** Não ajuste a tolerância para o teste passar — isso é falsificar
o portão. A régua da spec §10 é o que manda; se o app diverge, ou a transcrição da fórmula está
errada, ou a planilha tem casos que a fórmula não cobre. Os dois desfechos são achado, não bug de
teste, e precisam ser levados ao Levi antes de qualquer código novo.

- [ ] **Passo 4: commitar**

```bash
git add tests/fixtures/tickets_strings.json tests/test_tickets_gabarito.py
git commit -m "test(tickets): portao de aceite contra as 232 linhas de Strings"
```

---

### Tarefa 6: Ativo, SKID e cabine vindos do catálogo

A spec §7 manda mostrar **Ativo · SKID · Cabine** ao lado da usina, resolvidos no catálogo do
Fracttal e **não lidos da planilha** — a coluna `Inversor` da aba tem 212 vazios e o resto com
anotações no lugar do valor (`"A ser verificado"`, `"Mapeamento agendado para 04/05"`).

**Arquivos:**
- Criar: `os_creator/tickets_ativo.py`
- Criar: `tests/test_tickets_ativo.py`

**Interfaces:**
- Consome: `api.load_assets_cached()` — devolve lista de dicts com
  `id`, `id_parent`, `code`, `description`, `tipo`, `usina`
- Produz:
  - `cadeia_de_pais(ativo, por_id) -> list[dict]` — do ativo até a raiz
  - `cabine_de(ativo, por_id) -> dict | None`
  - `indexar(ativos) -> dict[int, dict]`

- [ ] **Passo 1: escrever os testes que falham**

`tests/test_tickets_ativo.py`:

```python
"""Resolução de ativo e cabine pelo catálogo do Fracttal.

Cadeias medidas no cadastro em 28/08:
  tracker  : Tracker 1.100 -> Estrutura Trackers -> Usina        (NÃO passa por cabine)
  inversor : Inversor 1.1 -> QGBT 1 -> SKID 1 -> Cabine 1 -> Usina

Portanto cabine existe para Strings e não existe para Trackers. Isso é o cadastro, não uma
limitação do app — e a tela precisa dizer 'não se aplica' em vez de mentir um valor."""
from tickets_ativo import cabine_de, cadeia_de_pais, indexar

USINA = {"id": 1, "id_parent": None, "code": "2C-APG100", "tipo": "Usina",
         "description": "2C - Araputanga 1 - MT"}
ESTRUT = {"id": 2, "id_parent": 1, "code": "APG100-ETKR1", "tipo": "Estrutura Trackers",
          "description": "Estrutura Trackers Araputanga"}
TRACKER = {"id": 3, "id_parent": 2, "code": "APG100-ETKR1.100", "tipo": "Estrutura Trackers",
           "description": "Tracker 1.100 STI STI-H250"}
CABINE = {"id": 4, "id_parent": 1, "code": "APG100-CABN1", "tipo": "Cabine",
          "description": "Cabine 1 Araputanga"}
SKID = {"id": 5, "id_parent": 4, "code": "APG100-SKID1", "tipo": "Skid",
        "description": "SKID 1 Araputanga"}
QGBT = {"id": 6, "id_parent": 5, "code": "APG100-QGBT1", "tipo": "QGBT",
        "description": "QGBT 1 Araputanga"}
INVERSOR = {"id": 7, "id_parent": 6, "code": "APG100-INV1.1", "tipo": "Inversor",
            "description": "Inversor 1.1 Huawei SUN2000"}

TODOS = [USINA, ESTRUT, TRACKER, CABINE, SKID, QGBT, INVERSOR]


def test_cadeia_do_tracker_sobe_ate_a_usina():
    por_id = indexar(TODOS)
    codes = [a["code"] for a in cadeia_de_pais(TRACKER, por_id)]
    assert codes == ["APG100-ETKR1.100", "APG100-ETKR1", "2C-APG100"]


def test_tracker_nao_tem_cabine():
    # não é falha: no cadastro do Fracttal o tracker não pendura em cabine
    assert cabine_de(TRACKER, indexar(TODOS)) is None


def test_inversor_tem_cabine():
    c = cabine_de(INVERSOR, indexar(TODOS))
    assert c is not None
    assert c["code"] == "APG100-CABN1"


def test_ciclo_no_id_parent_nao_trava():
    # defensivo: cadastro com pai apontando para si mesmo não pode congelar a tela
    louco = {"id": 9, "id_parent": 9, "code": "X", "tipo": "Inversor", "description": "X"}
    assert len(cadeia_de_pais(louco, indexar([louco]))) == 1


def test_pai_inexistente_encerra_a_cadeia():
    orfao = {"id": 10, "id_parent": 999, "code": "Y", "tipo": "Inversor", "description": "Y"}
    assert [a["code"] for a in cadeia_de_pais(orfao, indexar([orfao]))] == ["Y"]
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python -m pytest tests/test_tickets_ativo.py -v`
Esperado: FALHA com `ModuleNotFoundError: No module named 'tickets_ativo'`

- [ ] **Passo 3: implementar**

`os_creator/tickets_ativo.py`:

```python
"""Resolve ativo e cabine pelo catálogo do Fracttal, não pela planilha.

Por que não pela planilha: a coluna `Inversor` da aba Trackers tem 212 vazios e o resto com
anotação no lugar do valor ('A ser verificado', 'Mapeamento agendado para 04/05'). O catálogo dá
o nome e o código reais.

Cadeias medidas em 28/08 (16.289 ativos em cache):
    tracker  : Tracker 1.100 -> Estrutura Trackers -> Usina        — sem cabine
    inversor : Inversor 1.1 -> QGBT 1 -> SKID 1 -> Cabine 1 -> Usina

Trackers não penduram em cabine no cadastro. A tela mostra 'não se aplica' — mentir um valor
seria pior que não ter."""

_LIMITE_SUBIDA = 12          # trava contra id_parent circular; a cadeia real tem no máximo 5


def indexar(ativos):
    return {a.get("id"): a for a in (ativos or []) if a.get("id") is not None}


def cadeia_de_pais(ativo, por_id):
    """Do ativo até a raiz, ele próprio incluído."""
    out, atual, visto = [], ativo, set()
    while atual is not None and len(out) < _LIMITE_SUBIDA:
        ident = atual.get("id")
        if ident in visto:
            break
        visto.add(ident)
        out.append(atual)
        atual = por_id.get(atual.get("id_parent"))
    return out


def cabine_de(ativo, por_id):
    """A cabine na linhagem do ativo, ou None quando não existe (caso dos trackers)."""
    for a in cadeia_de_pais(ativo, por_id):
        if str(a.get("tipo") or "").strip().lower() == "cabine":
            return a
    return None
```

- [ ] **Passo 4: rodar e ver passar**

Rodar: `python -m pytest tests/test_tickets_ativo.py -v`
Esperado: 5 PASSAM

- [ ] **Passo 5: commitar**

```bash
git add os_creator/tickets_ativo.py tests/test_tickets_ativo.py
git commit -m "feat(tickets): resolve ativo e cabine pelo catalogo do Fracttal"
```

---

### Tarefa 7: A tela, somente leitura

**Arquivos:**
- Criar: `os_creator/steps/tickets.py`
- Modificar: `os_creator/app.py` — lista `cards` em `_build_launcher` e o `if/elif` de
  `_mostrar_modo`
- Modificar: `os_creator/steps/ui.py` — acrescentar o ícone `"ticket"` ao `_LUCIDE`
- Modificar: `os_creator/app.py` — acrescentar o ícone `"ticket"` ao `_ICO`

> **Atenção — a armadilha que quebrou a v135:** existem **dois** dicionários de ícone diferentes,
> `app.py::_ICO` (cards do lançador) e `steps/ui.py::_LUCIDE` (dentro das telas). Um nome que só
> exista em um deles levanta `KeyError` dentro do `MainWindow.__init__` e **o app não abre**.
> Acrescente `"ticket"` nos DOIS.

**Interfaces:**
- Consome: `tickets_api.listar_linhas`, `tickets_spec.ABAS`, `tickets_spec.estado_do_ticket`,
  `tickets_spec.COR_ESTADO`, `tickets_spec.NOME_ESTADO`, `tickets_calc.indisponibilidade_horas`,
  `tickets_ativo.indexar`, `tickets_ativo.cabine_de`, `api.load_assets_cached`,
  `workers.ApiWorker`, `workers.slot_seguro`
- Produz:
  - `steps.tickets.TicketsTab(on_voltar=None)` com `_selfnav = True`
  - `steps.tickets.ordenar_ocorrencias(ocs) -> list[dict]`
- **Contrato interno da ocorrência:** o dicionário que sai de `tickets_api.listar_linhas` traz as
  colunas da planilha mais `_row`. A tela **acrescenta** três chaves antes de ordenar ou exibir:
  `_estado` (de `estado_do_ticket`), `_dias` (inteiro, dias desde `Início da ocorrência`) e
  `_horas` (de `indisponibilidade_horas`). `ordenar_ocorrencias` depende de `_estado` e `_dias`.

**Referência visual:** [`docs/esbocos/tickets.py`](esbocos/tickets.py) é o esboço **aprovado pelo
Levi em 28/08**, executável (`python docs/esbocos/tickets.py`) e com dado real em
`docs/esbocos/tickets_trackers_amostra.json`. Layout, cores, textos e hierarquia saem dele. Ele é
mockup: não importa nada do app e não deve ser copiado como está — serve de gabarito visual.

- [ ] **Passo 1: escrever o teste que falha**

A tela em si não é testável sem display; o que é testável é a **ordenação** — a regra de qual
ocorrência aparece primeiro. Extraia-a como função pura no módulo da tela.

`tests/test_tickets_ordem.py`:

```python
"""Ordem da lista: primeiro o que precisa de gente.

Sem isto a tela mostraria as 2.781 linhas na ordem da planilha, e as ocorrências que exigem ação
ficariam enterradas no meio das 734 'Em conformidade'."""
from steps.tickets import ordenar_ocorrencias


def _oc(estado, dias):
    return {"_estado": estado, "_dias": dias}


def test_verificando_vem_antes_de_tudo():
    r = ordenar_ocorrencias([_oc("com_os", 90), _oc("verificando", 1)])
    assert r[0]["_estado"] == "verificando"


def test_sem_os_vem_logo_depois():
    r = ordenar_ocorrencias([_oc("com_os", 90), _oc("aberta", 1), _oc("verificando", 1)])
    assert [x["_estado"] for x in r] == ["verificando", "aberta", "com_os"]


def test_dentro_do_mesmo_estado_a_mais_velha_primeiro():
    r = ordenar_ocorrencias([_oc("aberta", 3), _oc("aberta", 40), _oc("aberta", 10)])
    assert [x["_dias"] for x in r] == [40, 10, 3]


def test_encerradas_por_ultimo():
    r = ordenar_ocorrencias([_oc("encerrada", 99), _oc("com_os", 1)])
    assert r[0]["_estado"] == "com_os"
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `python -m pytest tests/test_tickets_ordem.py -v`
Esperado: FALHA com `ModuleNotFoundError: No module named 'steps.tickets'`

- [ ] **Passo 3: criar a tela com a função de ordenação**

`os_creator/steps/tickets.py` — comece pelo esqueleto abaixo e monte o resto reproduzindo
`docs/esbocos/tickets.py`, que é o esboço aprovado. Rode-o antes (`python docs/esbocos/tickets.py`)
para ver o alvo. Os componentes obrigatórios, todos presentes no esboço:

| componente | onde | o que faz |
|---|---|---|
| Cabeçalho | topo | Voltar · título · chips `Trackers`/`Strings` · busca |
| Faixa de contadores | abaixo do cabeçalho | 4 blocos: Em aberto, Sem OS, Com OS, Em verificação — cada um na cor do seu estado |
| Coluna 1 | esquerda, 220 px | filtros por estado e por usina, com contagem; nota fixa sobre a ronda |
| Coluna 2 | centro, expansível | tabela: tarja de cor · Usina · Skid/Tracker · OS · Causa raiz · Início (**data e hora**) · Há quantos dias |
| Coluna 3 | direita, 452 px | painel: usina, `Ativo · SKID · Cabine`, barra de ciclo, aviso do estado, campos, comentários |

Cuidados de PyQt6 que o esboço já resolve e a tela precisa manter (todos custaram tempo antes):

- `QLabel` herda de `QFrame`: uma regra `QFrame{border:…}` no card pai vaza para todo label
  filho. Ponha `border:none` nos labels.
- O `QWidget` interno do `QScrollArea` pinta a cor de janela e vira um retângulo mais claro
  dentro do card. Corrige com `QScrollArea > QWidget > QWidget{background:transparent;}`.
- Campo somente-leitura usa o **mesmo** fundo do editável (`INPUT`); a diferença é a cor do
  texto. Fundo diferente vira buraco na tela — foi corrigido no esboço a pedido do Levi.
- `outline:0` na tabela e `item:focus{border:none}`, senão o retângulo de foco espreme o texto.

```python
"""Aba Tickets — ocorrências de Trackers e Strings vindas da Gridco Performance API.

FASE 1: SOMENTE LEITURA. Nada aqui escreve. A escrita depende de a aba sair do upload do
pipeline antes (spec §8) — enquanto o `.xlsx` subir com replace=true, qualquer gravação nossa
seria apagada no sync seguinte.

A tela é uma só para as duas abas: 15 das 23 colunas de Trackers e 15 das 18 de Strings são
idênticas, então o que muda entre elas é só o bloco de extras."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout

import tickets_api
import tickets_calc
import tickets_spec
from steps.ui import BG, CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED
from workers import ApiWorker, slot_seguro

# ordem dos estados na lista: quem precisa de gente primeiro. `a_fechar` vem junto de `com_os`
# porque é a mesma espera — a diferença é só de quem depende.
_PESO_ESTADO = {"verificando": 0, "aberta": 1, "a_fechar": 2, "com_os": 3, "encerrada": 4}


def ordenar_ocorrencias(ocs):
    """Primeiro o que precisa de gente; dentro do mesmo estado, a mais velha na frente."""
    return sorted(ocs, key=lambda o: (_PESO_ESTADO.get(o.get("_estado"), 9),
                                      -(o.get("_dias") or 0)))


class TicketsTab(QWidget):
    """Catálogo de ocorrências: lista + painel. Leitura."""
    _selfnav = True          # o wrapper do app NÃO põe a barra de Voltar — o daqui é o único

    def __init__(self, on_voltar=None):
        super().__init__()
        self._on_voltar = on_voltar
        self._aba = "Trackers"
        self._ocs, self._sel = [], None
        self._w = None
        self._monta()
        self._carregar()

    # ... montagem da tela conforme o esboço aprovado ...
```

- [ ] **Passo 4: rodar e ver passar**

Rodar: `python -m pytest tests/test_tickets_ordem.py -v`
Esperado: 4 PASSAM

- [ ] **Passo 5: ligar no lançador**

Em `os_creator/app.py`, dentro da lista `cards` de `_build_launcher`, logo após a entrada de
`"Ativos"`:

```python
            ("ticket", "Tickets", "Ocorrências de trackers e strings — leitura",
             lambda: self._mostrar_modo("tickets")),
```

E em `_mostrar_modo`, junto dos outros `elif`:

```python
            elif key == "tickets":                                    # ocorrências (leitura)
                from steps.tickets import TicketsTab
                inner = TicketsTab(on_voltar=lambda: self.criar_stack.setCurrentIndex(0))
```

Acrescente a chave `"ticket"` ao `_ICO` em `app.py` **e** ao `_LUCIDE` em `steps/ui.py`, com o
mesmo desenho (lucide `ticket`).

- [ ] **Passo 6: abrir o app inteiro**

Rodar: `python os_creator/main.py`

Esperado: a janela principal abre, o card **Tickets** aparece no lançador, clicar nele mostra a
lista carregada da API, e voltar funciona.

> Este passo não é opcional. A v135 saiu quebrada porque as telas foram testadas isoladas e a
> `MainWindow` não — e como o atualizador só rodava depois dela, quem instalou ficou preso na
> versão quebrada. Confira também `%TEMP%\criaros_erros.log`: `@slot_seguro` engole exceção, e o
> rastro só aparece lá.

- [ ] **Passo 7: commitar**

```bash
git add os_creator/steps/tickets.py os_creator/app.py os_creator/steps/ui.py tests/test_tickets_ordem.py
git commit -m "feat(tickets): aba de ocorrencias em somente-leitura"
```

---

### Tarefa 8: Suíte completa e nota de versão

- [ ] **Passo 1: rodar tudo**

Rodar: `python -m pytest -v`
Esperado: todos passam, incluindo o portão da Tarefa 5.

- [ ] **Passo 2: escrever a nota de versão**

Criar `notas_tickets_fase1.txt`, uma linha por tópico, **na linguagem de quem usa o app**:

```
Nova aba Tickets: mostra as ocorrências de trackers e de strings que hoje moram na planilha, direto do banco. Por enquanto é só consulta — nada é alterado por aqui
A lista já vem na ordem do que precisa de atenção: primeiro as OS que estão em verificação, depois as ocorrências sem OS nenhuma, e dentro de cada grupo as mais antigas na frente
A indisponibilidade passou a ser calculada pelo app, com a mesma régua de janela solar 06:00–18:00 da planilha. Nos trackers esse número não existia — a fórmula da planilha estava quebrada e 1.516 ocorrências encerradas estavam sem valor
```

- [ ] **Passo 3: commitar**

```bash
git add notas_tickets_fase1.txt
git commit -m "docs: notas de versao da fase 1 de tickets"
```

**NÃO compilar release.** O combinado com o Levi é acumular o lote e publicar só quando ele mandar.

---

## Onde este plano para

Na entrega 2 da spec §16. O próximo passo **não é código**: é combinar com quem edita a planilha
que as abas Trackers e Strings passaram a ser do app. Depois disso vêm o corte no pipeline, a
coluna `OS` e a escrita — segundo plano.

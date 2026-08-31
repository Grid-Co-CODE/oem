# Tickets no OS Creator — design

**Data:** 28/08/2026 · **Decisões:** Levi Maia · **Estado:** aprovado o desenho, spec para revisão

Integrar o banco de tickets (Gridco Performance API) ao OS Creator, começando pelas abas
**Trackers** e **Strings indisp**, com o objetivo de aposentar a planilha
`Tickets de Performance (atualizada).xlsx`.

---

## 1. O problema

Hoje o analista trabalha em dois lugares que não se falam: cria a OS no OS Creator e, à parte,
digita a linha da ocorrência na planilha. As consequências medidas:

- **Ocorrência sem OS é invisível.** Não existe coluna de OS nas abas Trackers e Strings — só
  em "Tickets de Performance" e "Desligamentos". Tracker parado sem ninguém mandado olhar não
  aparece em lugar nenhum.
- **O dado digitado apodrece.** A coluna `Inversor` da aba Trackers tem 212 vazios e o resto com
  anotações no lugar do valor: *"Mapeamento agendado para 04/05"*, *"A ser verificado"*, *"-"*.
- **A planilha trava.** Arquivo compartilhado, edição concorrente ruim.

## 2. Escopo

**Entra:** abas `Trackers` (sheet_id 123, 2.781 linhas, 23 colunas) e `Strings indisp`
(sheet_id 128, 233 linhas, 18 colunas) do workbook `tickets_performance`.

**Não entra agora:** as outras 13 abas. `Desligamentos` e `Inv. com baixa perfor.` são as
próximas candidatas — a plataforma também as lê, e o modelo desta spec já as comporta.

**Não entra nunca (nesta spec):** substituir a plataforma. A tela mora no OS Creator, decisão do
Levi em 28/08 depois de eu levantar a alternativa do 5050.

## 3. O modelo: uma ocorrência, dois conjuntos de extras

As duas abas **não são coisas diferentes**. Medido: **15 colunas são idênticas**.

| | colunas | compartilhadas | exclusivas |
|---|---|---|---|
| Trackers | 23 | 15 | 8 |
| Strings indisp | 18 | 15 | 3 |

**Núcleo (15):** Usina · Código da usina · Cliente · UF · Supervisor · Responsável · Causa raiz ·
Responsabilidade da Grid Co.? · Início da ocorrência · Início do chamado pela Grid Co. ·
Fim da ocorrência · Indisponibilidade (horas) · Indisponibilidade da Grid Co. (horas) ·
Comentários para os clientes · Comentários gerais

**Extras de Trackers (8):** Fonte · Equipamento · Status · Nº do SKID ·
Quantidade de trackers parados · Nº do tracker / Identificação · Inversor · Plano de ação

**Extras de Strings (3):** Inversor · Quantidade de strings no inversor ·
Quantidade de strings no afetadas

Consequência de design: **uma tela, um formulário**, com um bloco de extras trocado pelo tipo.
Aba nova é declaração (`sheet_id` + lista de extras), não tela nova.

## 4. O fluxo inverteu: a OS gera o ticket

Decisão do Levi (28/08). Antes o ticket vinha primeiro; agora:

1. O analista cria a OS de tracker parado / string zerada no **Performance**, como já faz.
2. O app cria **uma linha por ativo** na aba correspondente, já preenchida: usina, código,
   cliente, UF, SKID, nº do tracker, `Início da ocorrência` (data **e hora**), Status, responsável
   e o **número da OS**.
3. `Causa raiz` nasce **vazia de propósito** — só o técnico pode dizer.
4. Quando a OS é concluída, o `Fim da ocorrência` é preenchido e a indisponibilidade é calculada.

**N tickets : 1 OS.** Cada tracker tem a sua linha; uma OS pode cobrir vários. Isso já existe:
é o **modo agrupado** do Performance (uma OS, uma tarefa por ativo), shipado em 26/08.

Não existe "nova ocorrência" na tela. Linha sem OS seria sinal de que faltou OS.

## 5. Ciclo de vida

| estado | quando | cor |
|---|---|---|
| **Aberta** | sem OS vinculada | vermelho |
| **OS criada** | OS existe, técnico em campo | âmbar |
| **Em verificação** | OS em `Em Verificação` — o técnico fechou, ninguém confirmou | **azul** |
| **Encerrada** | OS `Concluída` e fim registrado | verde |

O **azul** é o estado que o Levi pediu explicitamente: *"muitos técnicos fecham OS sem resolver o
problema"*. Enquanto a OS estiver em verificação, o `Fim da ocorrência` vale como **provisório** e
a tela diz isso.

## 6. Fim da ocorrência: três fontes, e reversível

**Medido na OS 10509 (concluída):**

| campo | valor |
|---|---|
| OS `data_fim` | `2026-08-03T11:57:43` |
| tarefa `fim` | `''` |
| tarefa `inicio` | `''` |

Concluir a OS **não** preenche a data da tarefa — quem preenche é o cronômetro de execução. Já
estava documentado em `api.checar_data_fim` (medido antes na OS 10567: nula antes, nula depois).

**Ordem de preferência, decidida pelo Levi:**

1. **Data de fim da tarefa** — a real, do cronômetro. Preferida sempre que existir.
2. **Data de conclusão da OS** (`data_fim`) — sempre existe, mas é quando a OS foi *fechada no
   sistema*, não quando o técnico terminou em campo. Aproximada.
3. **Digitada à mão** — quando o analista sabe a hora certa.

A tela mostra qual está valendo e desabilita a opção 1 quando não há dado, **com o motivo escrito**
("sem cronômetro, a tarefa fecha sem hora") — em vez de esconder a opção boa.

**Desmarcar o fim reabre a ocorrência.** Requisito explícito. Efeito colateral que é o
comportamento certo: a linha volta a ter `Fim` vazio e **volta para a ronda do WhatsApp**, que lê
`Status="Parado"` com `Fim da ocorrência` vazio. O problema voltou a existir, a ronda volta a cobrar.

## 7. Identificação vem do catálogo, não da planilha

O painel mostra **Ativo · SKID · Cabine** ao lado da usina, resolvidos no catálogo do Fracttal
(16.289 ativos em cache), não lidos da planilha.

**Cadeias medidas no cadastro:**

- Tracker: `Tracker 1.100 → Estrutura Trackers → Usina` — **não passa por cabine**
- Inversor: `Inversor 1.1 → QGBT 1 → SKID 1 → Cabine 1 → Usina` — **cabine disponível**

Portanto: cabine aparece cheia na aba **Strings** e como "não se aplica" na de **Trackers**. Não é
limitação do app; é o cadastro. Mudar isso seria reparentar 5.879 estruturas de tracker no
Fracttal — fora de escopo, e só com ordem explícita.

Cliente, UF, Supervisor e Responsável **não aparecem no formulário** (Levi, 28/08): vêm do
catálogo, não mudam, e não são decisão de ninguém nesta tela.

## 8. A coluna `OS` — e a ordem que não pode inverter

As abas Trackers e Strings **não têm** coluna de OS. Criar é aprovado (Levi, 28/08), mas há
uma dependência dura:

> Enquanto o pipeline subir o `.xlsx` com `replace=true`, um sync apaga qualquer coluna que não
> exista na planilha de origem.

**Ordem obrigatória:**

1. A aba sai do upload do pipeline (seção 9).
2. Só então a coluna `OS` é criada.
3. Só então o app escreve nela.

## 9. O corte: como o Excel morre sem big-bang

**Fluxo hoje:**

```
Tickets.xlsx (OneDrive)
   ↓  coleta API PV/src/sync_gridco_api.py --aplicar   (sync-xlsx, replace=true)
Gridco Performance API / PostgreSQL
   ↓  bd_api.sincronizar()  —  _bd_api_loop, 30 min
plataforma/bases/Tickets de Performance (atualizada).xlsx
   ↓  TICKETS_PATH
plataforma: cruzamento de trackers + ronda do WhatsApp
```

**A plataforma já está a jusante do banco.** Ela lê o espelho que o `bd_api.gerar_xlsx()`
materializa **a partir da API**. Se o OS Creator escrever no banco, a plataforma recebe em até 30
minutos, **sem alteração nenhuma no código dela**.

O que precisa mudar é só a subida. Mas o `sync-xlsx` sobe o **workbook inteiro**, e a plataforma lê
**três** abas dele (`Trackers`, `Desligamentos`, `Inv. com baixa perfor.`) — parar o sync inteiro
congelaria as outras duas.

**Solução:** o pipeline já monta uma cópia (`_pipe_tickets_performance.xlsx`) e já a limpa. Essa
cópia passa a **remover as abas que o app domina** antes do upload. Aba migrada some do upload; o
Excel segue alimentando as demais. Migração uma aba por vez, com o Excel vivo ao lado.

### Implementado em 31/08 — e desligado

`coleta API PV/src/sync_gridco_api.py` ganhou a limpeza **E**, comandada por uma lista:

```python
ABAS_DO_APP = {
    "tickets_performance": [],        # o corte será: ["Trackers", "Strings indisp"]
}
```

**Encher essa lista É o corte.** Enquanto vazia, o pipeline roda exatamente como antes.

**A pergunta que decidia tudo — aba ausente do arquivo é apagada no banco?** Medido contra o
`zz_teste_claude_apagar`: gravei uma linha-marca em `Strings indisp`, subi o arquivo **sem**
`Trackers` e **sem** `Strings indisp`, e a API respondeu

```
{"sheets":13,"inserted":14446,"updated":7296,"deleted":0}
```

com a marca ainda lá. **`replace=true` substitui só as abas presentes no arquivo; aba ausente ele
nem olha.** É isso que permite migrar uma aba por vez sem big-bang — e sem essa medição o corte
seria um chute que custaria os dados de quem digita.

**Por que a remoção é mínima (só a entrada em `xl/workbook.xml`):** o arquivo tem 165 partes, com
pivôs, gráficos, tabelas nomeadas, `calcChain` e `definedName` indexado por posição de aba. Tirar
de verdade a planilha do zip obrigaria a mexer também em `_rels`, `[Content_Types].xml` e nos
índices — quatro chances de gerar um pacote que o importador recusa. É `workbook.xml` que decide o
que um leitor enxerga como aba; tirar a linha de lá basta. Conferido com openpyxl: o pacote abre e
as duas abas somem.

**Provado nos três casos** (executando a `limpa()` real do arquivo):

| lista | resultado |
|---|---|
| vazia (hoje) | 15 abas, nada removido — idêntico ao comportamento atual |
| `["Trackers", "Strings indisp"]` | 13 abas, as duas fora, e 18 mil fórmulas a menos para limpar |
| nome que não existe | avisa alto e não remove nada — falha barulhenta, não silenciosa |

## 10. Indisponibilidade: quem calcula

Hoje é fórmula do Excel; o banco guarda só o resultado (política valores-only). Sem o Excel,
**o app calcula**.

Fórmulas lidas do `.xlsx` vivo em 28/08 (`9.Pós Operação/3. Análises de Performance/`). **Não é
`Fim − Início`** — é **janela solar 06:00–18:00**, 12 horas por dia cheio:

```
horaIni, horaFim = hora decimal (h + m/60 + s/3600)

mesmo dia:
    total = max(0, clamp(horaFim,6,18) − clamp(horaIni,6,18))

dias distintos:
    total = max(0, 18 − max(horaIni, 6))          # ponta do primeiro dia
          + max(0, min(horaFim, 18) − 6)          # ponta do último dia
          + max(0, fimDia − iniDia − 1) × 12      # dias inteiros

erro (ex.: Fim vazio) → "" (vazio, não zero)
```

`Indisponibilidade da Grid Co. (horas)` — a regra tem **três** casos, e eu tinha suposto dois:

| Responsabilidade da Grid Co.? | valor |
|---|---|
| `Sim` | = Indisponibilidade (horas) |
| `Parcial` | = Indisponibilidade (horas) **− 6** |
| qualquer outro / vazio | `0` |

**Bug latente na fórmula atual:** o `− 6` não tem piso. Ocorrência `Parcial` com menos de 6 horas
solares dá **negativo**. Hoje não acontece — as 173 linhas `Parcial` de Trackers estão todas em
aberto, sem valor — mas o app precisa decidir. Recomendo `max(0, indisp − 6)` e registrar a
divergência deliberada em comentário; número negativo de indisponibilidade não significa nada
num relatório de cliente.

### A aba Trackers não tem esse número hoje

Medido em 28/08, no banco e no `.xlsx`:

| aba | encerradas | com indisponibilidade numérica |
|---|---|---|
| Trackers | 1.516 | **0** |
| Strings indisp | 220 | 232 |

**Causa:** a fórmula de Trackers referencia `[1]!Tracker[[#This Row],…]` — uma tabela em **arquivo
externo**, cujo vínculo não resolve. O Excel nunca calculou, então o sync levou vazio. A de
Strings usa a tabela local `Strings_indisponiveis` e funciona.

Duas consequências:

- **Não existe gabarito para validar Trackers.** São 1.516 ocorrências encerradas sem número —
  qualquer relatório que dependa dele hoje está lendo vazio.
- **O app calculando é a primeira vez que esse número existe** para trackers. Não há risco de
  divergir de nada, porque não há nada.

**Portão de aceite (revisado):** recalcular as **232 linhas de Strings** e comparar com o valor
que já está lá. Divergência que não seja arredondamento **bloqueia** a entrega. Para Trackers,
validar por amostra conferida à mão — sem gabarito, o teste é aritmético, não comparativo.

## 11. Concorrência

Poucos analistas, raramente simultâneos (Levi). Portanto: **sem trava**.

Antes de gravar, o app relê a linha (`GET /api/sheets/{id}/rows/{n}`). Se algum campo mudou desde
que a tela carregou, mostra o que mudou e pergunta. Simples, e cobre o caso real.

## 12. Passivo antigo: buscar OS pelo ativo

As linhas que já existem não ganham OS retroativamente. Para elas, um botão **"Procurar OS"**
que resolve usina + tracker no catálogo e lista as OS daquele ativo para o analista vincular.

Reaproveita `api.ultimas_os_do_ativo(id_item)`, que a aba Ativos já usa.

## 13. Interface com a API

`https://app.gridco.com.br/db_performace` · leitura aberta · escrita exige
`Authorization: Bearer <GRIDCO_SQL_TOKEN>` (raiz do repo, `tokens.txt`).

| operação | rota |
|---|---|
| listar linhas | `GET /api/sheets/{id}/rows?limit=&offset=` — **teto de 1000, paginar** |
| buscar | `GET /api/sheets/{id}/search` |
| gravar linha | `PUT /api/sheets/{id}/rows/{n}` |
| criar linha | `POST /api/sheets/{id}/rows` |
| histórico | `GET /api/sheets/{id}/rows/{n}/history` |

Armadilhas conhecidas: `PUT` apaga as fórmulas da linha (inofensivo na política valores-only);
`/api/sheets` **ignora** filtro por workbook — filtrar por `workbook_key` do lado do cliente.

## 14. O que não pode quebrar

- **A ronda do WhatsApp** lê `Status="Parado"` com `Fim da ocorrência` vazio. Toda escrita
  preserva essa semântica. Teste de regressão obrigatório.
- **`TICKETS_TRK`, `TICKETS_PARADO_ABERTO`, `TICKETS_RSU_ABERTO`** na plataforma dependem das
  mesmas colunas, casando por nome de usina e número do tracker.
- **Nomes de coluna** são a interface. Renomear é mudança de contrato.

## 15. Riscos

| risco | mitigação |
|---|---|
| Cálculo de horas divergir do Excel | Portão de aceite da seção 10 |
| Escrever na coluna errada (dado desalinhado na origem) | Conferir alinhamento cabeçalho×valor antes de qualquer escrita; começar **somente-leitura** |
| Fechar ticket indevidamente | Fim é provisório enquanto a OS estiver em verificação; desmarcar sempre disponível |
| Sync do Excel sobrescrever o app | Ordem da seção 8; a aba sai do upload **antes** da coluna existir |
| API fora do ar | A tela é o único caminho depois do corte — precisa de erro claro e de não perder o que foi digitado |

## 16. Ordem de entrega

A spec descreve o estado final. O caminho até ele é este, e a ordem importa: **nada escreve antes
que a leitura esteja provada**, e a coluna `OS` não pode existir antes do corte (seção 8).

| # | entrega | escreve? | destrava |
|---|---|---|---|
| 1 | Tela em **somente-leitura**: lista, filtros, painel, ciclo de vida, paginação | não | prova o alinhamento cabeçalho×valor sem risco |
| 2 | Recálculo das horas de todas as linhas encerradas, comparado com o valor atual | não | o portão de aceite da seção 10 |
| 3 | Pipeline deixa de subir `Trackers` e `Strings indisp` | — | o corte |
| 4 | Coluna `OS` criada nas duas abas | — | o vínculo |
| 5 | Escrita: salvar o formulário, com releitura antes de gravar | **sim** | edição sai do Excel |
| 6 | Criação automática da linha ao criar a OS no Performance | **sim** | o fluxo invertido |
| 7 | Fim da ocorrência pela OS, com as três fontes e o desmarcar | **sim** | fecha o ciclo |
| 8 | "Procurar OS" para o passivo antigo | **sim** | limpa o legado |

Entre a 2 e a 3 há uma decisão de gente, não de código: combinar com quem edita a planilha que
aquelas duas abas passaram a ser do app. Depois da 3, editá-las no Excel não tem mais efeito.

## 17. Fora de escopo

Detecção automática de tracker parado gerando ticket (o analista digita — Levi);
as outras 13 abas; migrar a leitura da plataforma para a API direta; reparentar trackers sob
cabine no Fracttal.

# Ambiente compartilhado: a Engenharia edita a própria área

Spec escrito em **31/08/2026**. Levantamento feito consultando o GitHub e o clone de trabalho ao
vivo — não é de memória. Os valores marcados como *verificado* saíram de chamada de API nesta data.

## 1. O que se quer

Um card **Engenharia** no OS Creator, abrindo uma tela voltada a **OS de ETM**, mantida por alguém
da Engenharia — não por quem cuida do app. A pessoa não é desenvolvedora: ela trabalha com um
agente de código (Claude Code) descrevendo o que precisa.

O conteúdo da tela é da Engenharia e vai evoluir sem passar por aqui. O que a casa segura é o
**layout**: cores e componentes saem do `steps/ui.py`, e nada além disso entra.

Este documento desenha o ambiente que torna isso seguro. **Não** desenha a tela de ETM — ver §7.

## 2. O que já existe

Mais do que parece. A migração de 28/08 e o canal de release de 31/08 já montaram a estrutura de
dois repositórios que o arranjo pede.

| Peça | Onde | Estado |
|---|---|---|
| Código, privado | `Grid-Co-CODE/oem` | existe; `Levi-6242` e `admin-gridco` como admin *(verificado)* |
| Instaladores, público | `Grid-Co-CODE/oem-release` | existe, publicando desde 31/08 |
| Fronteira de propriedade da área | `os_creator/steps/engenharia/CLAUDE.md` | escrito; pasta sem código |
| Contrato de tela e armadilhas do PyQt6 | `os_creator/steps/CLAUDE.md` | escrito |
| Grade de cards do launcher | `os_creator/app.py`, lista `cards` | 8 cards |
| GitHub Actions no repositório | — | habilitado, `allowed_actions: all` *(verificado)* |

O `steps/engenharia/CLAUDE.md` é a peça mais valiosa. Ele já separa o que é da área do que não é,
e já dá ao agente o aviso certo: o erro grave não é o que quebra, é o que funciona, cria a OS e
grava errado no sistema do cliente.

## 3. O que não existe

### 3.1 Não há `.github/` no repositório

Nenhum workflow, nenhum CODEOWNERS, nenhum template de PR *(verificado: `find .github` vazio)*.

Isso importa porque o `steps/engenharia/CLAUDE.md` **promete três coisas que não existem**, na
seção "Como publicar":

| Promessa no documento | Realidade hoje |
|---|---|
| "O `CODEOWNERS` chama o revisor certo automaticamente" | não há CODEOWNERS, e o plano bloqueia (§3.2) |
| "O build confere se o app abre antes de publicar" | não há build automático |
| "Aprovado, a publicação é automática" | a publicação é manual, na máquina do Levi |

É o pior tipo de defeito de documentação: a pessoa vai confiar num guarda-corpo ausente. Corrigir
isso é parte do escopo (§6.4).

### 3.2 O plano do GitHub bloqueia metade do guarda-corpo

A organização está no plano **free** *(verificado: `plan.name = "free"`, 3 assentos ocupados)*, e o
`oem` é **privado**. Em repositório privado de conta free, o GitHub não oferece proteção de branch:

```
GET repos/Grid-Co-CODE/oem/branches/main/protection
GET repos/Grid-Co-CODE/oem/rulesets
  -> HTTP 403 "Upgrade to GitHub Pro or make this repository public to enable this feature."
```

**Consequência direta: hoje não há como impedir um push direto no `main`.** Também não há como
exigir revisão antes do merge.

O CODEOWNERS cai na mesma faixa de plano (público no free; privado só a partir do Pro/Team).
*Não verificado ao vivo* — é regra de plano do GitHub, não medição.

GitHub Actions, ao contrário, funciona em repositório privado no free (cota mensal incluída). O CI
de §6.2 é viável hoje, sem mudar de plano.

### 3.3 A pessoa da Engenharia não está na organização

Membros hoje: `admin-gridco`, `EmersonGrid`, `Levi-6242` *(verificado)*. Nenhum é o engenheiro.

### 3.4 O padrão de cor que se quer travar já está divergente

| Fonte | Fundo | Card |
|---|---|---|
| `steps/ui.py` — o que o código usa | `BG = #0B1020` | `CARD = #121A2B` |
| `CLAUDE.md` da raiz — o que o texto manda | `#090d18` | `#161d30` |

E o resto do `steps/` não cumpre a própria regra: **223 literais hex, 88 cores distintas** em
`steps/*.py` *(verificado por contagem)*, contra os 8 nomes que o `ui.py` exporta (`BG`, `CARD`,
`INPUT`, `BORDER`, `GREEN`, `GREEN_INK`, `TEXT`, `MUTED`).

Duas consequências para o desenho:

1. Um lint de cor **global reprovaria o repositório inteiro**. Ele só pode valer dentro de
   `steps/engenharia/` — pasta nova, que começa limpa e nunca acumula a dívida.
2. A régua escrita para a Engenharia **não pode citar hex**. Se citar, o agente obedece ao
   documento e escreve o `#090d18` do texto contra o `#0B1020` do código. A régua cita **nomes**.

## 4. Decisão

Três arranjos foram considerados. Escolhido o **A**.

| | Como | Custo | Fraqueza |
|---|---|---|---|
| **A. Fork + CI** *(escolhido)* | acesso `read`, trabalho em fork, PR | zero | nada obriga a revisão humana |
| B. GitHub Team | tudo de A, mais proteção de branch e CODEOWNERS | ~US$4/pessoa/mês | compra recorrente; depende da T.I. |
| C. Só convenção | acesso `write`, confiar no `CLAUDE.md` | zero | é o estado que o documento já descreve e que falhou |

**Por que A resolve sem pagar:** o fork de repositório privado está liberado na organização
*(verificado: `members_can_fork_private_repositories: true`, `allow_forking: true`, 0 forks hoje)*.
Com acesso `read`, o engenheiro **fisicamente não consegue empurrar no `main`** — o que substitui a
proteção de branch que o plano bloqueia. O que o Team compraria a mais é disciplina de revisão, não
segurança. Subir para B se a revisão manual começar a falhar.

**Por que não C:** é o arranjo que o documento já descreve, e o modo de falha é o que a própria
pasta avisa — o agente acha o caminho curto pelo `api.py` para "resolver logo".

## 5. Fluxo de trabalho

1. Engenheiro entra na organização com acesso **read** ao `oem`.
2. Forka para a conta dele.
3. Trabalha em branch no fork, com o agente, dentro de `steps/engenharia/`.
4. Testa no app aberto, criando OS de teste na usina `TESTE - PA`.
5. Abre PR para `Grid-Co-CODE/oem`.
6. O CI roda os três portões de §6.2.
7. **Levi revisa e faz o merge.** Manual, e o documento dirá isso.
8. **Levi publica** pelo `release.py`. Manual, e o documento dirá isso.

## 6. Desenho

### 6.1 Componentes

| Novo | Onde | Dono |
|---|---|---|
| Workflow de PR, e o portão 1 dentro dele | `.github/workflows/pr.yml` | app |
| Portões 2 e 3, como teste | `tests/test_fronteira_engenharia.py` | app |
| Registro de áreas no launcher | `os_creator/app.py` | app |
| Pacote da área, com descritor e tela | `os_creator/steps/engenharia/` | Engenharia |
| Fronteira corrigida | `os_creator/steps/engenharia/CLAUDE.md` | app |

O portão 1 **não pode ser um teste**: ele depende de saber quais arquivos o PR tocou, e o `pytest`
só enxerga o disco. Ele é um passo do workflow, comparando com a base do PR. Os portões 2 e 3
enxergam só o disco, então são teste — e assim reprovam também na máquina de quem escreveu, antes
de virar PR.

### 6.2 O portão automático

Workflow em PR, runner Linux, Python 3.14, `QT_QPA_PLATFORM=offscreen`. Linux por custo: runner
Windows consome cota em dobro, e nada aqui precisa de Windows.

**Portão 1 — fronteira.** Os arquivos alterados num PR vindo de fork têm de caber inteiramente em
`steps/engenharia/**`. É a tabela "o que não é seu" virando gate. Sem ele, a tabela é um pedido — e
o modo de falha documentado é justamente o agente que passa por cima dela.

A regra é essa uma linha, sem exceção para o `app.py`, porque a linha de registro da área é escrita
**uma única vez**, por quem cuida do app, ao criar a pasta (§6.3). Depois disso a Engenharia nunca
mais precisa do `app.py` — nem para trocar o título do card, o ícone ou a descrição, que passam a
morar no descritor dentro da própria pasta.

**Portão 2 — layout.** Dentro de `steps/engenharia/**`: nenhum literal hex, nenhum emoji. Cor só
por nome importado do `ui.py`. Restrito à pasta pelo motivo de §3.4.

**Portão 3 — não quebrou.** `pytest` completo, `import app` sob `QT_QPA_PLATFORM=offscreen`
*(verificado: importa limpo, 14 ícones em `_ICO`)*, e todo ícone citado por uma área existe no
dicionário depois do merge.

Sobre esse último, o registro histórico precisa de correção: a v135 foi um `KeyError` que impediu o
app de abrir, mas o `_icone()` **ganhou fallback justamente por causa dela** — hoje um nome
desconhecido cai no ícone `doc` e registra o erro no log, sem derrubar nada. Então o portão 3 não
evita crash: evita **card com o ícone errado, em silêncio**, que ninguém percebe porque o app abre
normalmente. Defeito menor que o de 2026, e ainda assim invisível sem o teste.

> **O que o CI não prova.** Que a OS sai certa. O app exige login no Fracttal para abrir de fato,
> então nenhum robô cria OS na `TESTE - PA`. O teste humano continua obrigatório, e o documento da
> área precisa dizer isso em vez de sugerir que o build cobre.

### 6.3 Registro de áreas: fazer da "uma linha" uma verdade

O `steps/engenharia/CLAUDE.md` diz que a área é dona de "uma linha, a sua" no `app.py`. Hoje um card
novo exige **três** toques: a entrada na lista `cards`, o ramo em `_mostrar_modo` e o ícone em
`_ICO`. Com o portão 1 ativo, essa diferença deixa de ser imprecisão de texto e vira PR reprovado.

Então a estrutura se inverte: o pacote da área exporta o próprio descritor — título, descrição,
ícone e classe da tela — e o `app.py` ganha um registro com **uma linha por área**, escrita uma vez
por quem cuida do app.

**O registro não substitui os 8 cards de hoje.** Eles ficam exatamente como estão, na lista `cards`;
o registro só acrescenta os cards de área **depois** deles. É o que mantém o card de Engenharia no
fim da grade, que é a condição do gotcha logo abaixo.

Três ganhos além da promessa cumprida:

- Trocar título, descrição ou ícone do card vira mudança **dentro** da pasta da área — o que faz o
  portão 1 poder ser uma regra só, sem exceção que o agente possa alargar.

- A Engenharia **nunca toca no `_ICO`**, que é a armadilha dos dois dicionários de ícone descrita em
  `steps/CLAUDE.md`: ler o nome de um e usar no outro levanta `KeyError` e o app não abre.
- A instrução "copie esta pasta trocando o nome", para uma segunda área, passa a funcionar como
  está escrita.

> **Gotcha a evitar.** Em `app.py` o selo "N atribuídas a você" está preso em
> `self._launcher_cards[2]`, com comentário avisando que o índice já mudou uma vez, quando um card
> entrou antes do Performance. Um card novo inserido antes dele move o selo para o card errado, em
> silêncio. O card de Engenharia entra **no fim da lista**, e um teste tranca o selo no card certo —
> mesma ideia do `test_updater_canal.py`, que tranca o canal de release dentro do repositório.

### 6.4 O documento da fronteira

Reescrever a seção "Como publicar" do `steps/engenharia/CLAUDE.md` para descrever o que existe:

- o CI confere fronteira, layout e que o app importa — **isso passa a ser verdade** com §6.2;
- a revisão e o merge são **do Levi**, manuais; não há CODEOWNERS e o plano não permite;
- a publicação é **manual**, pelo `release.py`, na máquina de build;
- o teste na `TESTE - PA` é obrigatório porque o CI não o cobre.

E remover qualquer hex do texto, pelo motivo de §3.4: a régua cita nomes do `ui.py`.

### 6.5 Publicação

Continua manual, pelo `C:\GridcoBuild\release.py`, que **não está no git**. Automatizar exigiria
runner Windows, PyInstaller e Inno — projeto próprio, fora daqui. O que entra no escopo é parar de
prometer o contrário. Versionar o `release.py` segue como Fase 0 do plano de ambiente compartilhado
já levantado no repositório da plataforma.

## 7. Fora de escopo, de propósito

**O conteúdo da tela de ETM.** Ela nasce como esqueleto navegável — card, tela, botão Voltar,
fronteira funcionando — e a Engenharia preenche. Desenhar a tela por eles anularia o motivo do
arranjo.

Também fora: automatizar release (§6.5), migrar de plano (§4), e limpar os 223 hex do resto do
`steps/` (§3.4).

## 8. Verificação

O arranjo só está pronto quando cada item abaixo for observado, não deduzido:

1. Um PR de teste vindo do fork, tocando **só** `steps/engenharia/`, é **aprovado** pelos 3 portões.
2. Um PR de teste que altera `api.py` é **reprovado** pelo portão 1, com a mensagem dizendo por quê.
3. Um PR de teste com um hex cru em `steps/engenharia/` é **reprovado** pelo portão 2.
4. Um PR de teste com um ícone inexistente no registro é **reprovado** pelo portão 3 — sem ele, o
   card abriria com o ícone `doc` e ninguém notaria.
5. O app **abre** com o card novo, e o selo "N atribuídas a você" continua no card de Performance.
6. Uma tentativa de push direto no `main` pela conta do engenheiro é **recusada pelo GitHub**.

O item 6 é o que sustenta a decisão de §4. Se ele não passar, o arranjo A não se sustenta e a
conversa volta para o plano Team.

## 9. Riscos conhecidos

| Risco | Por quê | Mitigação |
|---|---|---|
| Nada obriga a revisão humana | o plano free não tem revisão obrigatória | aceito; sobe para Team se falhar |
| O CI não prova que a OS sai certa | o app exige login no Fracttal | teste humano na `TESTE - PA`, dito no documento |
| Cota de Actions do plano free | minutos mensais limitados em repositório privado | runner Linux; o job é curto |
| Fork fica defasado do `main` | fluxo de fork exige sincronizar | dito no documento da área |
| O portão 1 atrapalha pedido legítimo | mudar o `api.py` às vezes é necessário | o `CLAUDE.md` já prevê: abrir a conversa, e quem cuida do `api.py` escreve |

## 10. Documentos relacionados

- `os_creator/steps/engenharia/CLAUDE.md` — a fronteira da área
- `os_creator/steps/CLAUDE.md` — contrato de tela e armadilhas do PyQt6
- `os_creator/CLAUDE.md` — armadilhas da API do Fracttal e régua de verificação
- `os_creator/MOVIDO.md` — por que o código saiu da conta pessoal em 28/08
- `docs/plano-github-ambiente-compartilhado.md`, no repositório da plataforma — Fases 0 a 4,
  incluindo versionar o `release.py`

# steps/engenharia/ — a área de Engenharia

Esta pasta é da **Engenharia**. Tudo que a área precisa mudar mora aqui dentro.

> **Primeira vez aqui?** Comece por `docs/onboarding-engenharia.md` — acesso, máquina,
> como abrir o app e como abrir o primeiro PR. Este arquivo só diz a fronteira.

Leia primeiro `steps/CLAUDE.md` (como se escreve uma tela) e `os_creator/CLAUDE.md`
(armadilhas da API do Fracttal e a régua de verificação). Este arquivo só diz a fronteira.

> Modelo para outras áreas: copie esta pasta trocando o nome, e ajuste as duas listas abaixo.

## O que é seu

- Qualquer arquivo dentro de `steps/engenharia/` — e só.
- Título, descrição e ícone do seu card moram no `__init__.py` **desta pasta**, não no `app.py`.
  A linha que registra a área no `app.py` foi escrita uma vez, por quem cuida do app, e você não
  precisa dela nunca mais — nem para trocar o ícone.

## O que não é seu

Se a tarefa parece exigir mexer em algo desta lista, **pare e abra a conversa** em vez de editar.
Não é burocracia: são arquivos que todas as áreas usam ao mesmo tempo, e uma mudança aqui altera
telas que você não testou.

| Arquivo | Por que não |
|---|---|
| `api.py` | 5.000+ linhas, é o que **todas** as telas usam para falar com o Fracttal. Mudar uma função aqui muda o comportamento de Performance, COS, PCM e Chamados junto. |
| `steps/ui.py` | Tema e componentes compartilhados. Um ajuste de cor ou de espaçamento aparece em todas as telas. |
| `app.py` — **inteiro** | Navegação e janela principal. Erro aqui impede o app de **abrir**, e a v135 provou que app que não abre também não atualiza. Não há exceção: seu card é montado a partir do `__init__.py` da sua pasta, então não existe "a sua linha" para editar aqui. |
| `cos_spec.py`, `chamado_garantia/` | Regras de negócio de outras áreas. |
| `.spec`, `release.py`, workflows | Empacotamento e publicação. |

**Precisa de uma função nova no `api.py`?** É pedido legítimo e acontece. Abra a conversa
descrevendo o que precisa receber e devolver — quem cuida do `api.py` escreve, e você chama.
O que não pode é a função nascer no meio de uma tarefa de tela, sem ninguém olhar.

## Aviso para agente de código

Se você é um agente trabalhando nesta pasta: a tabela acima **não** é uma sugestão de estilo.
Editar aqueles arquivos para "resolver logo" é o modo de falha específico que este documento
existe para impedir. Quando o caminho mais curto passar por eles, **diga isso e pare** —
não siga em frente.

E o mais importante: **o erro grave aqui não é o que quebra.** É o que funciona, cria a OS e
grava errado no sistema do cliente. Compilar, abrir e a tela responder não é evidência de nada.
A evidência é a OS aberta no Fracttal, conferida campo a campo. Se você não conseguiu fazer isso,
diga que não conseguiu.

## Como publicar

Você trabalha num **fork** do repositório, não neste clone. É de propósito: o plano do GitHub em
que a organização está não permite proteger o `main` de repositório privado, e o fork é o que
garante, de fato, que um engano não chegue lá.

1. Forke `Grid-Co-CODE/oem` para a sua conta e trabalhe num branch seu.
2. Teste segundo a lista de `steps/CLAUDE.md` — **incluindo abrir o app inteiro e criar uma OS de
   teste no cliente `TESTE - PA`** — é o CLIENTE, e a usina é uma das 16 dele.
3. Abra o PR para `Grid-Co-CODE/oem`.
4. O CI confere três coisas, e reprova o PR se alguma falhar:
   - os arquivos alterados cabem **nesta pasta**;
   - não há cor escrita à mão nem emoji aqui dentro;
   - a suíte de testes passa e o app importa.
5. **A revisão e o merge são do Levi**, à mão. Não há revisor automático: CODEOWNERS exige plano
   pago em repositório privado.
6. **A publicação também é do Levi**, à mão, pelo `release.py` na máquina de build. Não existe
   passo automático de compilar.

> **O que o CI NÃO confere: se a OS sai certa.** O app precisa de login no Fracttal para abrir de
> verdade, então nenhum robô cria OS na `TESTE - PA`. O portão verde diz que você não quebrou o
> app e não saiu da sua pasta — não diz que a regra de negócio está certa.
>
> E o erro grave aqui não é o que quebra. É o que funciona, cria a OS e grava errado no sistema do
> cliente. Compilar, abrir e a tela responder não é evidência de nada. A evidência é a OS aberta no
> Fracttal, conferida campo a campo. Se você não conseguiu fazer isso, **diga que não conseguiu**.

**Seu fork envelhece.** Antes de começar cada trabalho, traga o `main` de cá para o seu fork —
senão o PR vem com conflito que não é seu.

## Convenções

- **pt-BR em tudo**, inclusive comentário de código.
- **Sem emoji na interface.**
- Tema navy + verde Grid, nunca lilás. **As cores saem por nome de `steps/ui.py`** — `BG`, `CARD`,
  `INPUT`, `BORDER`, `GREEN`, `GREEN_INK`, `TEXT`, `MUTED`. Não escreva o valor à mão: o texto e o
  código já divergiram uma vez, e quem copia o valor de um documento escolhe o errado. O teste
  `tests/test_fronteira_engenharia.py` reprova hexadecimal dentro desta pasta.
- Comentário explica **por quê**, citando o caso real que motivou a regra.

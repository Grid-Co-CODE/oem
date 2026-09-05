# Começar a trabalhar na área de Engenharia

Para quem vai manter a tela da Engenharia no OS Creator sem ser desenvolvedor, trabalhando com um
agente de código. Escrito em **04/09/2026**.

Este documento cobre o que vem **antes** de programar: máquina, acesso, o primeiro PR. O que se
pode e não se pode mexer está em `os_creator/steps/engenharia/CLAUDE.md`, e como se escreve uma
tela está em `os_creator/steps/CLAUDE.md` — os dois são lidos pelo agente sozinho quando você
abre o Claude Code na pasta do projeto. Não precisa decorá-los.

O porquê do arranjo (por que fork e não acesso direto) está em
`docs/ambiente-compartilhado-engenharia.md`. Ler é opcional; o resumo é: o plano do GitHub em que
a organização está **não permite proteger o `main`** de repositório privado, e o fork é o que
garante, de fato, que um engano não chegue lá.

---

## 1. O acesso (não depende de você)

Peça a quem administra a organização no GitHub (`admin-gridco`):

> Convidar o usuário **@seu-usuario-github** para a organização `Grid-Co-CODE`, com acesso
> **`read`** no repositório `oem`.

`read`, e não `write`. Não é desconfiança: é o que substitui a proteção de branch que o plano
bloqueia. Com `read` você **fisicamente não consegue** empurrar no `main` — nem por engano, nem
com o agente insistindo.

Quem mantém o app **não consegue fazer esse convite**: ele é `member` da organização, não `admin`.

---

## 2. A máquina

Instale, nesta ordem:

| O quê | Onde | Por quê |
|---|---|---|
| **Python 3.14** | python.org | é a versão que o CI usa; outra pode passar aqui e reprovar lá |
| **Git** | git-scm.com | para clonar e abrir PR |
| **Claude Code** | claude.com/code | o agente |

No Windows, **não use o `python` que abre a Microsoft Store** — ele virtualiza o AppData e o app
não acha os arquivos de estado. Confira com:

```bash
python -c "import sys; print(sys.executable)"
```

Se o caminho tiver `WindowsApps`, é o alias errado. Instale o Python real do python.org e use o
caminho completo dele.

---

## 3. O clone

```bash
gh repo fork Grid-Co-CODE/oem --clone
cd oem
python -m pip install -r os_creator/requirements.txt
python -m pip install pytest
```

O `fork --clone` já configura o `origin` como o **seu** fork e o `upstream` como o repositório da
Grid. É por isso que se usa esse comando e não um `git clone` direto.

---

## 4. Abrir o app

```bash
cd os_creator
python main.py
```

**O app pede o seu login do Fracttal** — o mesmo e-mail e senha que você usa no site. Não existe
modo sem login: a OS é criada no seu nome, e o app não carrega senha da empresa.

> **Errar a senha bloqueia a conta por 15 a 30 minutos.** Não fique tentando. Se não entrar,
> confirme no site do Fracttal primeiro.

Rodando os testes:

```bash
python -m pytest          # da raiz do repositório
```

---

## 5. O ciclo de trabalho

```bash
git checkout -b eng/o-que-voce-esta-fazendo
# ... trabalhe com o agente, dentro de os_creator/steps/engenharia/ ...
python -m pytest
git push -u origin eng/o-que-voce-esta-fazendo
gh pr create --repo Grid-Co-CODE/oem
```

O PR dispara três conferências automáticas, e reprova se alguma falhar:

1. **Os arquivos alterados cabem na pasta da área** — nada fora de `steps/engenharia/`.
2. **Sem cor escrita à mão e sem emoji** dentro da pasta. A cor sai de `steps/ui.py` pelo nome
   (`BG`, `CARD`, `GREEN`, `TEXT`, `MUTED`), nunca copiada como `#0B1020`. Assim, o dia em que o
   tema mudar, a sua tela muda junto.
3. **A suíte passa e o app importa.**

Depois: **a revisão e o merge são de quem mantém o app**, à mão. **A publicação também** — o
instalador é compilado numa máquina específica. Não existe passo automático, e o seu PR aprovado
não vira versão instalada até alguém compilar.

---

## 6. O que o portão verde NÃO diz

Ele diz que você não quebrou o app e não saiu da sua pasta. **Não diz que a OS sai certa.**

Nenhum robô cria OS: o app precisa de login no Fracttal para abrir de verdade. E o erro grave
aqui **não é o que quebra** — é o que funciona, cria a OS e grava errado no sistema do cliente.

Por isso, antes de abrir o PR:

1. Abra o app inteiro, não só a sua tela.
2. Crie uma OS de teste no **cliente `TESTE - PA`** — ele existe para isso, e tem 221 ativos
   em 16 usinas (`Estrutura Trackers`, `Cabine 1`, `Estação Meteorológica`…). Escolha a usina
   que combina com o que você mexeu.

   > `TESTE - PA` é o **cliente**, não a usina. Três documentos antigos diziam "usina
   > `TESTE - PA`" e quem procurasse por esse nome na lista de usinas não acharia.
3. **Abra a OS no Fracttal** e confira campo a campo o que foi gravado.

O passo 3 é a evidência. Compilar, abrir e a tela responder não é evidência de nada.

---

## 7. Quando a tarefa parece exigir sair da pasta

Acontece, e é pedido legítimo: uma função nova no `api.py`, um componente novo no `ui.py`.

**Não deixe o agente escrever.** Ele vai propor — é o caminho curto, e ele não sabe que aquele
arquivo é usado por outras quatro telas que você não testou. Abra a conversa descrevendo **o que
a função precisa receber e devolver**; quem cuida do arquivo compartilhado escreve, e você chama.

A conferência 1 do CI existe exatamente para isso: se escapar, ela reprova antes de qualquer
pessoa perder tempo.

---

## 8. Onde pedir ajuda

| Dúvida | Onde |
|---|---|
| O que posso mexer | `os_creator/steps/engenharia/CLAUDE.md` |
| Como se escreve uma tela aqui | `os_creator/steps/CLAUDE.md` |
| Armadilhas da API do Fracttal | `os_creator/CLAUDE.md` |
| Por que o arranjo é assim | `docs/ambiente-compartilhado-engenharia.md` |
| Acesso, merge, publicação | quem mantém o app |

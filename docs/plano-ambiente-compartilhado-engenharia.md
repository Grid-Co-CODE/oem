# Plano de implementação — ambiente compartilhado da Engenharia

> **Para quem executa com agente:** SUB-SKILL OBRIGATÓRIA — usar `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar tarefa a tarefa. Os passos usam
> caixa (`- [ ]`) para acompanhamento.

**Objetivo:** dar à Engenharia uma área própria no OS Creator — um card e uma tela — que ela mantém
por PR vindo de fork, com portões automáticos que seguram fronteira e layout.

**Arquitetura:** o pacote `steps/engenharia/` exporta o próprio descritor (título, descrição, ícone,
fábrica da tela) e o `app.py` ganha um registro de áreas com uma linha por área, escrita uma vez.
Assim a área nunca precisa tocar em arquivo compartilhado, e o portão de fronteira do CI pode ser
uma regra só: o PR de fork tem de caber em `os_creator/steps/engenharia/`.

**Tecnologias:** Python 3.14, PyQt6 ≥ 6.7, pytest, GitHub Actions (runner Linux, `QT_QPA_PLATFORM=offscreen`).

**Spec:** `docs/ambiente-compartilhado-engenharia.md` — o plano argumenta a partir dele; leia os dois.

**Repositório:** `Grid-Co-CODE/oem`. Clone de trabalho: `C:\GridcoBuild\oem` (fora do OneDrive, porque
o sync corrompe o PyInstaller — ver `os_creator/MOVIDO.md`).

## Restrições globais

Valem para toda tarefa, sem repetição em cada uma.

- **pt-BR em tudo**, inclusive comentário de código.
- **Sem emoji na interface.** Severidade se comunica por cor.
- **Dentro de `steps/engenharia/`: cor só por nome importado de `steps/ui.py`** — `BG`, `CARD`,
  `INPUT`, `BORDER`, `GREEN`, `GREEN_INK`, `TEXT`, `MUTED`. Nenhum literal hexadecimal no código-fonte.
- Comentário de código explica **por quê**, citando o caso real que motivou a regra. É o padrão dos
  arquivos deste repositório; mantenha.
- Testes rodam **da raiz do repositório**: `python -m pytest`. O `conftest.py` da raiz põe
  `os_creator/` no `sys.path`; o `pytest.ini` já traz `testpaths = tests` e `addopts = -q`.
- **Use o Python real, não o alias do Windows.** `python` no PowerShell/Git Bash cai no atalho da
  Microsoft Store e responde "Python não foi encontrado". Use `py` ou o caminho completo do 3.14.
- **Commit só quando o Levi pedir** (`CLAUDE.md` da raiz do outro repositório e prática deste). Os
  passos de commit estão escritos e prontos, mas confirme antes de rodar o primeiro.
- Não toque em `api.py`, `steps/ui.py`, `cos_spec.py`, `chamado_garantia/`, `.spec` ou `release.py`.
  A tarefa 2 é a **única** que altera `app.py`, e só nos três pontos descritos ali.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Tarefa |
|---|---|---|
| `os_creator/steps/engenharia/__init__.py` | descritor da área: o que o launcher lê para montar o card | 1 |
| `os_creator/steps/engenharia/tela.py` | a tela da área — esqueleto, a Engenharia preenche | 1 |
| `conftest.py` *(modificar)* | fixture `qapp`, para testes que instanciam widget | 1 |
| `tests/test_area_engenharia.py` | o contrato do descritor e a tela abrindo | 1 |
| `os_creator/app.py` *(modificar)* | registro de áreas, `_mostrar_area`, selo achado por título | 2 |
| `tests/test_launcher_areas.py` | o registro ligado, o ícone fundido, o selo travado | 2 |
| `tests/test_fronteira_engenharia.py` | portão 2 — cor por nome, sem emoji | 3 |
| `.github/workflows/pr.yml` | portão 1 no workflow, e roda os portões 2 e 3 | 4 |
| `.github/pull_request_template.md` | a lista do que o CI **não** cobre | 5 |
| `os_creator/steps/engenharia/CLAUDE.md` *(modificar)* | a fronteira, sem as três promessas falsas | 5 |

O portão 1 **não pode ser teste**: depende do diff do PR, e o `pytest` só enxerga o disco. Ele é
passo do workflow. Os portões 2 e 3 são teste, e assim reprovam também na máquina de quem escreveu.

---

### Tarefa 1: O pacote da área — descritor e tela esqueleto

**Arquivos:**
- Criar: `os_creator/steps/engenharia/__init__.py`
- Criar: `os_creator/steps/engenharia/tela.py`
- Modificar: `conftest.py` (acrescentar a fixture `qapp` ao fim)
- Testar: `tests/test_area_engenharia.py`

**Interfaces:**
- Consome: nada de tarefas anteriores. Usa `steps.ui` (`TEXT`, `MUTED`), que já existe.
- Produz — a tarefa 2 depende destes nomes exatos:
  - `steps.engenharia.CHAVE: str` = `"eng"`
  - `steps.engenharia.TITULO: str` = `"Engenharia"`
  - `steps.engenharia.DESCRICAO: str`
  - `steps.engenharia.ICONE: str` = `"etm"`
  - `steps.engenharia.ICONES: dict[str, str]` — nome → corpo SVG, mesmo formato de `app._ICO`
  - `steps.engenharia.abrir(on_voltar) -> QWidget`

- [ ] **Passo 1: Escrever o teste que falha**

Criar `tests/test_area_engenharia.py`:

```python
"""O descritor da área da Engenharia: o que o launcher lê para montar o card.

Existe porque o contrato entre o app e a área é ESTE arquivo, não o `app.py`. Se um campo sumir
ou trocar de nome, o card some da grade sem erro nenhum — o launcher só não acha o que iterar, e
o app abre normalmente com um card a menos. Ver docs/ambiente-compartilhado-engenharia.md, §6.3.
"""
import steps.engenharia as area


def test_o_descritor_tem_os_campos_que_o_launcher_le():
    assert area.CHAVE == "eng"
    assert area.TITULO == "Engenharia"
    assert area.DESCRICAO.strip()
    assert area.ICONE


def test_o_icone_citado_existe_no_proprio_pacote():
    # a área nunca toca no `_ICO` do app.py — `steps/CLAUDE.md` documenta que existem DOIS
    # dicionários de ícone e que trocar um pelo outro levanta KeyError. Ela traz o próprio, e
    # quem confere que o nome citado existe é este teste, antes de qualquer merge.
    assert area.ICONE in area.ICONES
    assert area.ICONES[area.ICONE].strip().startswith("<")


def test_a_tela_abre(qapp):
    tela = area.abrir(on_voltar=lambda: None)
    assert tela is not None


def test_a_tela_nao_desenha_o_proprio_voltar(qapp):
    # sem `_selfnav`, quem desenha o "← Voltar" é o `_wrap_modo` do app.py. Se a tela desenhasse
    # outro, ficariam DOIS Voltar na mesma tela — o caso que `steps/CLAUDE.md` documenta.
    tela = area.abrir(on_voltar=lambda: None)
    assert not getattr(tela, "_selfnav", False)
```

- [ ] **Passo 2: Rodar e ver falhar**

Rodar da raiz: `py -m pytest tests/test_area_engenharia.py -v`
Esperado: FALHA com `ModuleNotFoundError: No module named 'steps.engenharia'` — a pasta existe, mas
só com o `CLAUDE.md`, sem `__init__.py`. E `fixture 'qapp' not found`.

- [ ] **Passo 3: Acrescentar a fixture `qapp` ao `conftest.py`**

Ao **fim** do `conftest.py` da raiz, sem tocar no que já está lá:

```python
import pytest


@pytest.fixture(scope="session")
def qapp():
    """QApplication única para os testes que instanciam widget.

    `scope="session"` não é otimização: o Qt não admite duas QApplication no mesmo processo, e
    criar a segunda aborta o interpretador sem traceback nenhum — o teste "some" em vez de falhar.

    A plataforma offscreen é fixada aqui, e não só no workflow, para o teste passar igual na
    máquina de quem escreveu — que tem tela e, sem isto, abriria janela de verdade no meio da suíte.
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
```

- [ ] **Passo 4: Escrever o descritor**

Criar `os_creator/steps/engenharia/__init__.py`:

```python
"""Descritor da área de Engenharia — o que o launcher do `app.py` lê para montar o card.

A área é dona desta pasta inteira. O `app.py` a registra com UMA linha e nunca precisa ser tocado
de novo: título, descrição e ícone moram aqui. É isso que permite ao portão de fronteira do CI ser
uma regra só ("o PR de fork cabe em steps/engenharia/"), sem exceção que se possa alargar.

Ver `CLAUDE.md` ao lado (a fronteira) e `docs/ambiente-compartilhado-engenharia.md` (o arranjo).
"""

CHAVE = "eng"                      # identifica a página da área dentro do stack do launcher
TITULO = "Engenharia"
DESCRICAO = "OS de ETM e as análises da Engenharia"

# O ícone mora AQUI, e não no `_ICO` do app.py, de propósito: `steps/CLAUDE.md` documenta que
# existem dois dicionários de ícone e que ler o nome de um para usar no outro levanta KeyError.
# A área nunca precisa saber disso — o launcher funde `ICONES` no dicionário dele ao registrar.
ICONE = "etm"
ICONES = {
    # estação meteorológica: mastro, sensor no topo e as duas hastes da medição
    "etm": '<path d="M12 21V10"/><path d="M8 21h8"/><circle cx="12" cy="7" r="3"/>'
           '<path d="M5 7a7 7 0 0 1 2-4.9"/><path d="M19 7a7 7 0 0 0-2-4.9"/>',
}


def abrir(on_voltar):
    """Cria a tela da área.

    O import é adiado para dentro da função porque o launcher lê este módulo no arranque só para
    montar o card — carregar a tela inteira ali atrasaria a abertura do app por uma tela que talvez
    ninguém clique. É o mesmo padrão do `_mostrar_modo`, onde cada `from steps.X import Y` vive
    dentro do ramo, e não no topo do arquivo.
    """
    from steps.engenharia.tela import EngenhariaTab
    return EngenhariaTab(on_voltar=on_voltar)
```

- [ ] **Passo 5: Escrever a tela esqueleto**

Criar `os_creator/steps/engenharia/tela.py`:

```python
"""Tela da Engenharia — esqueleto.

Nasce vazia de propósito: o conteúdo é da Engenharia, e desenhá-lo aqui anularia o motivo do
arranjo (docs/ambiente-compartilhado-engenharia.md, §7). O que já vem pronto é a moldura — a tela
aparece na grade, o Voltar funciona e as cores vêm do tema.

REGRA DESTA PASTA: cor só por nome importado de `steps/ui.py`. Nenhum hexadecimal escrito à mão —
o teste `tests/test_fronteira_engenharia.py` reprova. O motivo não é gosto: o `CLAUDE.md` da raiz
manda #090d18 e o `steps/ui.py` usa #0B1020, então quem escreve hex escolhe entre dois valores em
conflito e a tela sai fora do tema sem ninguém notar. Nome resolve para o que o código usa de fato.
"""
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from steps.ui import MUTED, TEXT


class EngenhariaTab(QWidget):
    """Moldura da área.

    Sem `_selfnav`, quem desenha o "← Voltar" é o `_wrap_modo` do `app.py`; desenhar outro aqui
    deixaria dois Voltar na mesma tela (`steps/CLAUDE.md`).

    O `border:none` em cada QLabel não é excesso: QLabel herda de QFrame, e uma regra de borda no
    card pai vaza para todo filho — foi assim que um ponto de status de 6px virou círculo pintado.
    """

    def __init__(self, on_voltar=None):
        super().__init__()
        self._on_voltar = on_voltar          # guardado para quando a área tiver navegação própria
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(8)

        titulo = QLabel("Engenharia")
        titulo.setStyleSheet(
            f"font-size:20px; font-weight:600; color:{TEXT}; background:transparent; border:none;")
        v.addWidget(titulo)

        sub = QLabel("Área em construção pela Engenharia. O primeiro fluxo será OS de ETM.")
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"font-size:13px; color:{MUTED}; background:transparent; border:none;")
        v.addWidget(sub)

        v.addStretch(1)
```

- [ ] **Passo 6: Rodar e ver passar**

Rodar: `py -m pytest tests/test_area_engenharia.py -v`
Esperado: 4 passed.

Depois a suíte inteira, para garantir que a fixture nova não mexeu em nada:
`py -m pytest`
Esperado: tudo que passava antes continua passando.

- [ ] **Passo 7: Commit**

```bash
git add os_creator/steps/engenharia/__init__.py os_creator/steps/engenharia/tela.py conftest.py tests/test_area_engenharia.py
git commit -m "feat(engenharia): descritor da area e a tela esqueleto"
```

---

### Tarefa 2: O registro de áreas no launcher

**Arquivos:**
- Modificar: `os_creator/app.py` — três pontos, descritos abaixo
- Testar: `tests/test_launcher_areas.py`

**Interfaces:**
- Consome: `steps.engenharia.CHAVE / TITULO / DESCRICAO / ICONE / ICONES / abrir` (tarefa 1).
- Produz: `app.AREAS: list[module]` — a lista que a tarefa 3 e o teste de fronteira não usam, mas
  que a tarefa 5 documenta como "a sua linha"; e `MainWindow._mostrar_area(area)`.

- [ ] **Passo 1: Escrever o teste que falha**

Criar `tests/test_launcher_areas.py`:

```python
"""O registro de áreas do launcher.

Existe porque a promessa feita à Engenharia — "você é dona de uma linha no app.py" — só é verdade
se card, título, descrição e ícone vierem do pacote da área. Quando alguma dessas pontas volta
para o `app.py`, o portão de fronteira do CI passa a reprovar PR legítimo e a área fica sem saída.
Ver docs/ambiente-compartilhado-engenharia.md, §6.3.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # antes de importar app: ele carrega PyQt

import app

# Os 14 nomes que o `_ICO` tinha antes de existir área alguma. Repetidos aqui de propósito: é o
# que faz o teste de colisão falhar se uma área tentar usar um deles.
_ICONES_DO_APP = {
    "bolt", "stack", "calendar", "file", "copy", "arrow", "plus", "doc",
    "history", "clipboard", "headset", "searchcheck", "rack", "ticket",
}


def test_a_engenharia_esta_registrada_como_area():
    assert "eng" in [a.CHAVE for a in app.AREAS]


def test_o_icone_de_toda_area_entrou_no_dicionario_do_launcher():
    # Sem isto o card abre com o ícone `doc` e ninguém percebe: o `_icone()` ganhou fallback
    # justamente por causa da v135, então nome desconhecido não derruba mais o app — só troca o
    # desenho, em silêncio, e o erro fica só no log.
    for a in app.AREAS:
        assert a.ICONE in app._ICO, (
            "ícone '%s' da área '%s' não entrou no _ICO" % (a.ICONE, a.CHAVE))


def test_nenhuma_area_sobrescreve_icone_do_app():
    # `_ICO.update()` de uma área com nome repetido trocaria o desenho de um card do app sem aviso.
    for a in app.AREAS:
        colisoes = _ICONES_DO_APP & set(a.ICONES)
        assert not colisoes, "área '%s' redefine ícone do app: %s" % (a.CHAVE, colisoes)


def test_o_selo_de_analises_nao_volta_a_ser_achado_por_indice():
    # O selo "N atribuídas a você" já apontou para o card errado quando o Tickets entrou no meio
    # da lista, e o comentário no código avisava que aconteceria de novo. Agora é achado pelo
    # título. Este teste impede que a busca por índice volte num merge distraído — mesma ideia do
    # test_updater_canal.py, que tranca o canal de release dentro do repositório.
    fonte = os.path.join(os.path.dirname(app.__file__), "app.py")
    with open(fonte, encoding="utf-8") as f:
        txt = f.read()
    assert '_cards_por_titulo["Performance"]' in txt
    assert "_launcher_cards[2]" not in txt
```

- [ ] **Passo 2: Rodar e ver falhar**

Rodar: `py -m pytest tests/test_launcher_areas.py -v`
Esperado: FALHA com `AttributeError: module 'app' has no attribute 'AREAS'`.

- [ ] **Passo 3: Registrar a área — ponto 1 de 3 no `app.py`**

Logo **depois** da linha `_ICONE_PADRAO = "doc"` e **antes** de `def _icone(`:

```python
# ── Áreas: cada área mantém a própria pasta e entra aqui com UMA linha ────────────────────────
# A fronteira de cada uma está em `steps/<area>/CLAUDE.md`; o arranjo, em
# `docs/ambiente-compartilhado-engenharia.md`. Card, título, descrição e ícone saem do descritor
# do pacote — é o que permite ao portão de fronteira do CI ser uma regra só, sem exceção para o
# `app.py` que alguém (ou algum agente) possa alargar depois.
from steps import engenharia as _area_engenharia

AREAS = [_area_engenharia]

for _area in AREAS:                    # o ícone da área entra no dicionário do launcher aqui,
    _ICO.update(_area.ICONES)          # para a área nunca precisar editar o `_ICO` (a v135).
```

- [ ] **Passo 4: Acrescentar os cards e destravar o selo — ponto 2 de 3**

Em `_build_launcher`, **substituir** o bloco que hoje vai do `self._launcher_cards = []` até a
linha `self._card_perf = self._launcher_cards[2]` (e o comentário de três linhas que a acompanha)
por:

```python
        # As áreas entram DEPOIS dos cards do app, sempre. Não é estética: o selo do card
        # Performance era buscado por índice fixo (`_launcher_cards[2]`) e já apontou para o card
        # errado uma vez, quando o Tickets entrou no meio da lista. Aqui o índice deixa de importar
        # — o selo passa a ser achado pelo título — e a ordem no fim mantém a grade estável para
        # quem já usa o app.
        for area in AREAS:
            cards.append((area.ICONE, area.TITULO, area.DESCRICAO,
                          # `a=area` prende o valor no momento do laço; sem isso todos os cards de
                          # área abririam a ÚLTIMA da lista, porque a lambda fecharia sobre a
                          # variável e não sobre o valor.
                          lambda a=area: self._mostrar_area(a)))

        self._launcher_cards = []
        self._cards_por_titulo = {}
        for i, (ic, t, s, cb) in enumerate(cards):
            card = _CardOS(ic, t, s, cb)
            self._launcher_cards.append(card)
            self._cards_por_titulo[t] = card
            grid.addWidget(card, i // 3, i % 3)
        self._card_perf = self._cards_por_titulo["Performance"]
```

- [ ] **Passo 5: Abrir a tela da área — ponto 3 de 3**

Logo **depois** do fim do método `_mostrar_modo` (a linha
`self.criar_stack.setCurrentIndex(self._modo_idx[key])`) e antes de `def _ativo_para_performance`:

```python
    def _mostrar_area(self, area):
        """Abre a tela de uma área registrada.

        Espelha o `_mostrar_modo` de propósito — mesma criação sob demanda, mesmo `reiniciar` ao
        reentrar —, mas o painel vem do descritor do pacote em vez de um `elif` aqui dentro. É o
        que mantém o `app.py` fora do caminho de quem mantém a área: card novo, título novo ou
        ícone novo não passam mais por este arquivo.
        """
        key = "area:" + area.CHAVE
        if key not in self._modo_idx:
            inner = area.abrir(on_voltar=lambda: self.criar_stack.setCurrentIndex(0))
            tornar_todos_pesquisaveis(inner)
            self._modo_idx[key] = self.criar_stack.addWidget(self._wrap_modo(inner))
            self._modo_inner = getattr(self, "_modo_inner", {})
            self._modo_inner[key] = inner
            if hasattr(inner, "carregar_inicial"):
                inner.carregar_inicial()
        else:
            alvo = getattr(self, "_modo_inner", {}).get(key)
            if alvo is not None and hasattr(alvo, "reiniciar"):
                alvo.reiniciar()
        self.criar_stack.setCurrentIndex(self._modo_idx[key])
```

- [ ] **Passo 6: Rodar e ver passar**

Rodar: `py -m pytest tests/test_launcher_areas.py -v`
Esperado: 4 passed.

E a suíte inteira: `py -m pytest`
Esperado: tudo verde.

- [ ] **Passo 7: Abrir o app e ver o card**

Este passo é humano e **não é opcional** — o CI não abre o app com login.

```bash
cd /c/GridcoBuild/oem/os_creator && py main.py
```

Conferir, com os próprios olhos:
1. A grade mostra **9 cards**, com **Engenharia no último lugar**.
2. O ícone dele é a estação meteorológica, **não** a folha de papel (o fallback `doc`).
3. O selo "N atribuídas a você" continua **no card Performance**.
4. Clicar em Engenharia abre a tela, com **um só** "← Voltar", e o Voltar retorna à grade.

Se aparecer o ícone errado, o `_ICO.update` do passo 3 não rodou — confira se ficou depois do `_ICO`.

- [ ] **Passo 8: Commit**

```bash
git add os_creator/app.py tests/test_launcher_areas.py
git commit -m "feat(launcher): registro de areas — a Engenharia entra com uma linha"
```

---

### Tarefa 3: Portão 2 — cor por nome, e sem emoji

**Arquivos:**
- Testar: `tests/test_fronteira_engenharia.py` (criar)

**Interfaces:**
- Consome: `steps.engenharia` (tarefa 1), só para descobrir o caminho da pasta.
- Produz: nada que outra tarefa importe. A tarefa 4 roda estes testes no CI.

- [ ] **Passo 1: Escrever o teste que falha**

Criar `tests/test_fronteira_engenharia.py`:

```python
"""Portão 2 do CI: o layout da área da Engenharia.

A área é dona do conteúdo; a casa segura o layout. Na prática isso é uma regra só — cor sai por
nome importado de `steps/ui.py`, nunca por hexadecimal escrito à mão.

POR QUE VALE SÓ PARA `steps/engenharia/`: o resto do `steps/` tem 223 literais hexadecimais em 88
cores distintas (medido em 31/08/2026). A mesma regra aplicada ao repositório inteiro reprovaria
tudo e seria desligada na primeira semana. A pasta nova começa limpa e não acumula a dívida.

POR QUE "NOME, NUNCA HEX": o `CLAUDE.md` da raiz manda #090d18 e o `steps/ui.py` usa #0B1020.
Quem escreve hex à mão escolhe entre dois valores em conflito, e a tela sai fora do tema sem
ninguém notar. Nome não tem esse problema — resolve para o que o código usa de fato.
"""
import os
import re

import steps.engenharia as area

_PASTA = os.path.dirname(area.__file__)
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# pictogramas e dingbats. A faixa de SETAS fica de fora de propósito: o app usa "← Voltar", e
# incluí-la reprovaria código correto.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\uFE0F]")


def _fontes():
    """Todo .py da pasta da área."""
    for raiz, _dirs, arquivos in os.walk(_PASTA):
        if "__pycache__" in raiz:
            continue
        for nome in sorted(arquivos):
            if nome.endswith(".py"):
                yield os.path.join(raiz, nome)


def _ocorrencias(padrao):
    achados = []
    for caminho in _fontes():
        with open(caminho, encoding="utf-8") as f:
            for n, linha in enumerate(f, 1):
                if padrao.search(linha):
                    achados.append("%s:%d: %s" % (os.path.basename(caminho), n, linha.strip()))
    return achados


def test_a_area_tem_pelo_menos_um_arquivo_para_conferir():
    # sem isto, apagar a pasta por engano deixaria os dois testes abaixo passando com zero
    # arquivo lido — portão aberto que parece fechado.
    assert list(_fontes()), "nenhum .py encontrado em %s" % _PASTA


def test_nenhuma_cor_escrita_a_mao_na_area():
    achados = _ocorrencias(_HEX)
    assert not achados, (
        "cor escrita à mão na área da Engenharia. Importe o nome de steps/ui.py "
        "(BG, CARD, INPUT, BORDER, GREEN, GREEN_INK, TEXT, MUTED):\n" + "\n".join(achados))


def test_sem_emoji_na_area():
    achados = _ocorrencias(_EMOJI)
    assert not achados, (
        "emoji na área da Engenharia; severidade se comunica por cor:\n" + "\n".join(achados))


def test_a_regra_pega_o_que_deve_pegar():
    """O lint precisa FALHAR quando deve.

    Sem este teste, um erro na expressão regular deixa o portão aberto e todo mundo acha que está
    protegido — que é exatamente o modo de falha que este arranjo inteiro existe para evitar.
    """
    assert _HEX.search("color:#0B1020;")
    assert _HEX.search('"#fff"')
    assert not _HEX.search("color:{TEXT}")          # f-string com nome: é o jeito certo
    assert not _HEX.search("# comentário comum")
    assert _EMOJI.search("pronto \U0001F600")
    assert not _EMOJI.search("← Voltar")            # seta não é emoji: o app usa isso no wrap
```

- [ ] **Passo 2: Rodar e ver passar de primeira**

Rodar: `py -m pytest tests/test_fronteira_engenharia.py -v`
Esperado: **5 passed** — a tela da tarefa 1 já obedece à regra.

> Um teste que passa de primeira não prova nada. Por isso o passo 3.

- [ ] **Passo 3: Provar que o portão reprova**

Sujar a tela de propósito e conferir que o teste pega. Editar
`os_creator/steps/engenharia/tela.py` à mão, trocando a última linha por:

```python
        v.addStretch(1)  # cor:#123456
```

E rodar:

```bash
cd /c/GridcoBuild/oem && py -m pytest tests/test_fronteira_engenharia.py -v
```

> Edição à mão, e não um script de uma linha, de propósito: heredoc (`<<'FIM'`) quebra no shell
> deste ambiente, e o passo existe para provar o portão — não para brigar com aspas.

Esperado: **FALHA** em `test_nenhuma_cor_escrita_a_mao_na_area`, e a mensagem tem de citar
`tela.py`, o número da linha e a lista de nomes do `ui.py`.

Desfazer: `git checkout os_creator/steps/engenharia/tela.py`
Rodar de novo: `py -m pytest tests/test_fronteira_engenharia.py -v` → 5 passed.

- [ ] **Passo 4: Commit**

```bash
git add tests/test_fronteira_engenharia.py
git commit -m "test(engenharia): portao de layout — cor por nome, sem emoji"
```

---

### Tarefa 4: Portão 1 e o workflow de PR

**Arquivos:**
- Criar: `.github/workflows/pr.yml`

**Interfaces:**
- Consome: os testes das tarefas 1 a 3 (roda `pytest` inteiro).
- Produz: os três portões rodando em PR. A verificação ao vivo é a tarefa 6.

- [ ] **Passo 1: Escrever o workflow**

Criar `.github/workflows/pr.yml`:

```yaml
# Portões do PR. O arranjo e o porquê estão em docs/ambiente-compartilhado-engenharia.md.
#
# Roda em Linux de propósito: runner Windows consome cota em dobro, e nada aqui precisa de
# Windows — a compilação do .exe continua manual, na máquina de build.
name: PR

on:
  pull_request:

jobs:
  fronteira:
    # PORTAO 1. So vale para PR vindo de FORK, que e o fluxo da Engenharia. PR de branch interna
    # e de quem mantem o app, e esse pode tocar em qualquer arquivo.
    if: github.event.pull_request.head.repo.full_name != github.repository
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # o diff precisa da base; checkout raso nao traz o commit dela

      - name: Os arquivos alterados cabem na pasta da area
        env:
          BASE: ${{ github.event.pull_request.base.sha }}
          CABECA: ${{ github.event.pull_request.head.sha }}
        run: |
          # Ao criar uma AREA NOVA, acrescente a pasta dela aqui. E acao de quem cuida do app, na
          # mesma hora em que a linha do registro entra no app.py — nunca da propria area.
          PERMITIDO='^os_creator/steps/engenharia/'

          fora=$(git diff --name-only "$BASE" "$CABECA" | grep -v "$PERMITIDO" || true)
          if [ -n "$fora" ]; then
            echo "::error::Este PR altera arquivos fora da pasta da area:"
            echo "$fora"
            echo ""
            echo "A fronteira esta em os_creator/steps/engenharia/CLAUDE.md."
            echo "Precisa de mudanca fora dela? E pedido legitimo e acontece: abra a conversa"
            echo "descrevendo o que precisa receber e devolver. Quem cuida do arquivo compartilhado"
            echo "escreve, e a area chama. O que nao pode e a mudanca nascer no meio de uma tarefa"
            echo "de tela, sem ninguem olhar."
            exit 1
          fi
          echo "OK: o PR fica dentro da pasta da area."

  testes:
    # PORTOES 2 e 3. Rodam em TODO PR, inclusive os internos.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Bibliotecas de sistema do Qt
        # O PyQt6 do PyPI nao traz as libs X/EGL do sistema. Sem elas o import falha com
        # "could not load the Qt platform plugin", mesmo com QT_QPA_PLATFORM=offscreen.
        run: |
          sudo apt-get update
          sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3

      - name: Dependencias
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r os_creator/requirements.txt pytest

      - name: Testes
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -m pytest
```

- [ ] **Passo 2: Conferir que o YAML é válido antes de subir**

```bash
cd /c/GridcoBuild/oem
py -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/pr.yml',encoding='utf-8')); print('jobs:', list(d['jobs']))"
```
Esperado: `jobs: ['fronteira', 'testes']`

Se o `yaml` não estiver instalado: `py -m pip install pyyaml`.

- [ ] **Passo 3: Conferir o portão 1 localmente, antes de depender do CI**

A lógica do portão 1 é uma linha de shell; dá para provar aqui, sem esperar um PR:

```bash
cd /c/GridcoBuild/oem
PERMITIDO='^os_creator/steps/engenharia/'
printf 'os_creator/steps/engenharia/tela.py\n' | grep -v "$PERMITIDO" || echo "PASSA (esperado)"
printf 'os_creator/api.py\n' | grep -v "$PERMITIDO"
```
Esperado: a primeira linha imprime `PASSA (esperado)`; a segunda imprime `os_creator/api.py` —
que é o que faz o passo do workflow chamar `exit 1`.

- [ ] **Passo 4: Commit**

```bash
git add .github/workflows/pr.yml
git commit -m "ci: portao de fronteira no PR de fork e a suite em runner Linux"
```

> **O que ainda não está provado.** Que o `pytest` passa no Ubuntu — o `keyring` e o Qt podem
> pedir mais biblioteca de sistema do que a lista acima. Isso só aparece no primeiro PR de teste
> (tarefa 6, item 1). Se falhar lá, o conserto é acrescentar o pacote que faltou nesta etapa —
> não desligar o job.

---

### Tarefa 5: O documento da fronteira, e o que o CI não cobre

**Arquivos:**
- Modificar: `os_creator/steps/engenharia/CLAUDE.md` — a seção "Como publicar" e as "Convenções"
- Criar: `.github/pull_request_template.md`
- Modificar: `tests/test_fronteira_engenharia.py` — acrescentar o teste do documento

**Interfaces:**
- Consome: os portões das tarefas 3 e 4, que este documento passa a descrever com precisão.
- Produz: nada que outra tarefa importe.

- [ ] **Passo 1: Escrever o teste que falha**

Acrescentar ao fim de `tests/test_fronteira_engenharia.py`:

```python
def test_o_documento_da_area_nao_cita_hexadecimal():
    """A régua escrita para a Engenharia cita NOME, nunca hex.

    Se o documento trouxer #090d18 (o valor do CLAUDE.md da raiz) e o código usar #0B1020 (o do
    steps/ui.py), o agente obedece ao documento — é o que ele lê primeiro — e a tela sai fora do
    tema. O texto perde a autoridade sobre cor e a devolve ao `steps/ui.py`, que é quem manda.
    """
    caminho = os.path.join(_PASTA, "CLAUDE.md")
    with open(caminho, encoding="utf-8") as f:
        achados = ["%d: %s" % (n, l.strip())
                   for n, l in enumerate(f, 1) if _HEX.search(l)]
    assert not achados, (
        "o CLAUDE.md da área cita cor em hexadecimal; cite o NOME do steps/ui.py:\n"
        + "\n".join(achados))
```

- [ ] **Passo 2: Rodar e ver falhar**

Rodar: `py -m pytest tests/test_fronteira_engenharia.py::test_o_documento_da_area_nao_cita_hexadecimal -v`
Esperado: FALHA citando a linha das "Convenções" que hoje diz `Tema navy (#090d18 / #161d30)`.

- [ ] **Passo 3: Corrigir a seção "Convenções" do `CLAUDE.md` da área**

Em `os_creator/steps/engenharia/CLAUDE.md`, **substituir** a linha do tema por:

```markdown
- Tema navy + verde Grid, nunca lilás. **As cores saem por nome de `steps/ui.py`** — `BG`, `CARD`,
  `INPUT`, `BORDER`, `GREEN`, `GREEN_INK`, `TEXT`, `MUTED`. Não escreva o valor à mão: o texto e o
  código já divergiram uma vez, e quem copia o valor de um documento escolhe o errado. O teste
  `tests/test_fronteira_engenharia.py` reprova hexadecimal dentro desta pasta.
```

- [ ] **Passo 4: Corrigir a seção "Como publicar", que hoje promete o que não existe**

**Substituir a seção inteira** por:

```markdown
## Como publicar

Você trabalha num **fork** do repositório, não neste clone. É de propósito: o plano do GitHub em
que a organização está não permite proteger o `main` de repositório privado, e o fork é o que
garante, de fato, que um engano não chegue lá.

1. Forke `Grid-Co-CODE/oem` para a sua conta e trabalhe num branch seu.
2. Teste segundo a lista de `steps/CLAUDE.md` — **incluindo abrir o app inteiro e criar uma OS de
   teste no cliente `TESTE - PA`**.
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
```

- [ ] **Passo 5: Corrigir "O que é seu", que hoje aponta para o `app.py`**

Na seção **"O que é seu"**, substituir a segunda linha por:

```markdown
- Qualquer arquivo dentro de `steps/engenharia/` — e só. Título, descrição e ícone do seu card
  moram no `__init__.py` desta pasta, não no `app.py`. A linha que registra a área no `app.py` foi
  escrita uma vez, por quem cuida do app, e você não precisa dela nunca mais.
```

- [ ] **Passo 6: Criar o template de PR**

Criar `.github/pull_request_template.md`:

```markdown
## O que muda

<!-- Uma frase. O que a tela passa a fazer. -->

## Como foi testado

O CI confere que o app importa, que o PR ficou na pasta da área e que não há cor à mão nem emoji.
Ele **não** confere se a OS sai certa — isso é humano.

- [ ] Abri o app inteiro e a tela respondeu
- [ ] Criei uma OS de teste no cliente `TESTE - PA`
- [ ] **Conferi a OS no Fracttal, campo a campo** — e não só que "não deu erro"
- [ ] Não conferi no Fracttal, e digo isso aqui: <!-- por quê -->

## Fora da pasta da área

- [ ] Este PR fica inteiro em `os_creator/steps/<area>/`
- [ ] Precisa de mudança fora dela, e está descrita abaixo para quem cuida do arquivo
```

- [ ] **Passo 7: Rodar e ver passar**

Rodar: `py -m pytest tests/test_fronteira_engenharia.py -v`
Esperado: 6 passed.

E a suíte inteira: `py -m pytest` → tudo verde.

- [ ] **Passo 8: Ler o documento inteiro uma vez, do começo**

Passo humano. Abrir `os_creator/steps/engenharia/CLAUDE.md` e ler de ponta a ponta, procurando
**uma** coisa: alguma frase que ainda descreva algo que não existe. Foi esse o defeito que este
plano inteiro corrige; reintroduzi-lo em outra seção seria irônico e caro.

- [ ] **Passo 9: Commit**

```bash
git add os_creator/steps/engenharia/CLAUDE.md .github/pull_request_template.md tests/test_fronteira_engenharia.py
git commit -m "docs(engenharia): a fronteira passa a descrever o ambiente que existe"
```

---

### Tarefa 6: Acesso, fork e a verificação ao vivo

**Não é tarefa de agente.** Cada item exige a conta do Levi (dono da organização) ou a do
engenheiro. Um agente não consegue executar nenhum deles, e não deve tentar.

**Arquivos:** nenhum. É a §8 do spec, executada.

- [ ] **Passo 1: Subir o branch e abrir o PR interno**

```bash
cd /c/GridcoBuild/oem && git push -u origin HEAD
```
Abrir o PR para `main`. O job `testes` roda; o `fronteira` é pulado de propósito (PR interno).

Se o `pytest` falhar no Ubuntu, o motivo mais provável é biblioteca de sistema faltando para o Qt
ou o `keyring`. Acrescentar o pacote na etapa "Bibliotecas de sistema do Qt" da tarefa 4 e empurrar
de novo. **Não desligar o job para destravar o merge** — o job existe justamente para isso.

- [ ] **Passo 2: Convidar o engenheiro para a organização**

Em `github.com/orgs/Grid-Co-CODE/people` → Invite member. Hoje são 3: `admin-gridco`,
`EmersonGrid`, `Levi-6242`.

- [ ] **Passo 3: Dar acesso de LEITURA ao `oem`**

`github.com/Grid-Co-CODE/oem/settings/access` → Add people → papel **Read**.

**Read, não Write.** É o item de que toda a decisão depende: sem proteção de branch no plano free,
o acesso de escrita permitiria push direto no `main`. O fork é o que substitui a proteção.

- [ ] **Passo 4: O engenheiro forka e clona**

Ele forka `Grid-Co-CODE/oem` para a conta dele e clona **fora do OneDrive** — o sync corrompe o
PyInstaller (`os_creator/MOVIDO.md`).

O git **não** traz `.env`, `fracttal_login.txt` nem `assets_cache.json` — são ignorados de
propósito. Copiar de um clone que já funcione, senão o build falha: o `assets_cache.json` está no
`datas` do `.spec`.

- [ ] **Passo 5: Os quatro PRs de teste**

Cada um é um PR do fork, e o resultado esperado é **reprovação** em três deles. Um portão que nunca
reprovou não está provado.

| # | O PR faz | Esperado |
|---|---|---|
| 1 | muda só um texto em `steps/engenharia/tela.py` | **passa** nos três portões |
| 2 | muda uma linha de `os_creator/api.py` | **reprova** no portão 1, citando o arquivo |
| 3 | põe `color:#123456` em `tela.py` | **reprova** no portão 2, citando arquivo e linha |
| 4 | troca `ICONE = "etm"` por `"inexistente"` | **reprova** no portão 3 |

Se o 2, 3 ou 4 **passar**, o portão correspondente está aberto e a tarefa dele não está pronta.

- [ ] **Passo 6: A verificação que sustenta a decisão inteira**

O engenheiro, na conta dele, tenta empurrar direto no `main` de `Grid-Co-CODE/oem`:

```bash
git push https://github.com/Grid-Co-CODE/oem.git HEAD:main
```

**Esperado: o GitHub recusa por falta de permissão.**

Se **não** recusar, o arranjo escolhido não se sustenta — o acesso não é Read, ou algo mais o
concede. Parar aqui e voltar à conversa: a alternativa é o plano Team (§4 do spec), que traz
proteção de branch de verdade.

- [ ] **Passo 7: Fechar o ciclo até o usuário**

Depois de aprovar e fazer o merge do PR 1, publicar uma versão pelo `release.py`, na máquina de
build, e confirmar numa máquina já instalada que ela atualiza e que o card Engenharia aparece.

É o único passo que prova que o caminho existe inteiro — do PR do engenheiro até a tela de quem usa.

---

## Conferência do plano contra o spec

| Seção do spec | Onde é implementada |
|---|---|
| §5 fluxo de trabalho | tarefa 6, passos 2 a 5; e o `CLAUDE.md` da tarefa 5 |
| §6.2 portão 1 (fronteira) | tarefa 4, job `fronteira` |
| §6.2 portão 2 (layout) | tarefa 3 |
| §6.2 portão 3 (não quebrou) | tarefa 4, job `testes`; e o teste de ícone da tarefa 2 |
| §6.2 "o que o CI não prova" | tarefa 5, passos 4 e 6 (documento e template) |
| §6.3 registro de áreas | tarefas 1 e 2 |
| §6.3 gotcha do selo | tarefa 2, passos 4 e 6, e o teste que tranca a busca por título |
| §6.4 documento da fronteira | tarefa 5 |
| §6.5 publicação manual | tarefa 5, passo 4, item 6; e tarefa 6, passo 7 |
| §7 tela de ETM fora de escopo | tarefa 1, passo 5 — esqueleto de propósito |
| §8 verificação, itens 1 a 6 | tarefa 6, passos 5 e 6; item 5 na tarefa 2, passo 7 |
| §9 risco "fork envelhece" | tarefa 5, passo 4, última linha |

Sem lacuna: toda seção do spec tem tarefa, e nenhuma tarefa existe sem seção que a justifique.

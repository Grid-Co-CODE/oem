# OS Creator na web — o mesmo app dentro da Plataforma de Performance

Pedido do Levi em 12/09/2026: *"traga toda a estrutura do OS Creator para a plataforma, de forma que para entrar no
card tenha que logar no Fracttal"*, e a régua: *"segue o mesmo design e lógica do OS Creator, não vamos fazer um
redesign ainda. Após logar quero que apareça a mesma coisa que aparece para quem loga no OS Creator"*.

## Onde mora e como sobe

| Peça | Onde | O que faz |
|---|---|---|
| serviço web | `os_creator/os_web/` (este repositório) | Flask + waitress em `127.0.0.1:5090`, telas em HTML no tema do app |
| motor | `os_creator/api.py` (o mesmo do desktop) | RPC do Fracttal na sessão da pessoa; nada foi duplicado |
| publicação | Plataforma de Performance (`plataforma/app.py`, proxy `/os/*`) | mesmo túnel e mesmo login da plataforma na frente |
| lançador | `deploy/os_web.cmd` + `deploy/os_web.vbs` | pythonw REAL, log em `logs/os_web.log` |

```
cd os_creator
python -m os_web.servir            # http://127.0.0.1:5090/os/
python -m pytest tests/test_os_web_*.py -q
```

## Dois logins, dois sistemas

O login Microsoft da plataforma não loga ninguém no Fracttal. Na web, "logar no Fracttal" é e-mail + senha do Fracttal
(`rpc/login_new`, senha em MD5 duplo, igual ao app); a senha só serve para obter o JWT de sessão e não é guardada. Quem
entra no Fracttal pela Microsoft (SSO) não tem senha lá — o navegador embutido do desktop captura o token, um navegador
comum não consegue (same-origin). Quatro saídas:

0. **Entrar pela tela do Fracttal (OAuth, em teste desde 12/09).** A doc oficial lista `one.fracttal.com/oauth/authorize`
   com `authorization_code`; sondado ao vivo, o authorize manda para a tela `accessgrant` do Fracttal One levando o nosso
   callback. `os_web/oauth_fracttal.py`: `/os/login/fracttal` (state na sessão, callback só para a nossa casa) →
   `/os/login/fracttal/volta` troca o `code` pelo token e DIAGNOSTICA ao vivo se o RPC aceita (é ele que cria OS). Se
   aceitar, o token vira a sessão da área /os; se não, a tela mostra o erro e nada é guardado. Falta o teste real com
   uma conta (o token de client_credentials levava 401 no RPC; o de uma pessoa pode ser diferente).

1. **Senha no Fracttal.** Se o administrador puder definir senha para as contas que hoje entram só pela Microsoft, o
   login da web (e-mail + senha) já basta — nada a instalar, nada a construir.
2. **O app instalado faz o login Microsoft.** O botão *Entrar com Microsoft / SSO* chama `gridos://sso?volta=<url do
   /os/login>`; o OS Creator abre a janela de SSO que a equipe já conhece (`steps/sso_login.py`), a pessoa entra, e ele
   devolve o navegador em `volta#sso=<jwt>` — a página entra sozinha (`sso_volta.py`; o token vai no fragmento, que
   não chega a servidor nem a log). Exige a versão do app com o `gridos://sso` (o app se atualiza sozinho pela release).
3. **Favorito (bookmarklet).** Reserva para quem não tem o app: `os_web/static/sso_bookmarklet.js` (o `_POLL_JS` do app)
   varre localStorage/sessionStorage/cookies na aba do Fracttal, copia o JWT e a pessoa cola no login da web. Depois de
   copiar, fechar a aba do Fracttal: ele renova a sessão e mata a cópia.

Uma extensão de navegador reproduziria o app por inteiro (abre a aba, lê o header, fecha), mas exigiria distribuição
pela T.I.; ficou engavetada por simplicidade (Levi, 12/09). OAuth para integradores continua sendo a saída limpa.

A sessão é **por pessoa**: `os_web/sessao.py` guarda o JWT num `ContextVar` durante a requisição e costura as quatro
funções do `api.py` que tocam o token (`_read_jwt`, `_save_jwt`, `_clear_jwt`, `_rpc_try_refresh`). Fora de requisição
o desktop continua no arquivo/keyring. O JWT vive num cookie do serviço (`os_sessao`, `Path=/os`, HttpOnly, 12 h) que a
plataforma repassa nos dois sentidos. Sessão derrubada no Fracttal (`USER_NOT_LOGIN`) → volta ao login com o aviso.

O Fracttal aceita cerca de uma sessão por conta: entrar pela web derruba o Fracttal aberto em outra aba, e vice-versa.

## O que já está na web (fase 1) e o que ainda mora só no app

- **Tela inicial**: cabeçalho, avatar com iniciais, nome e cargo; três abas; os nove cards do launcher, na ordem e com os
  textos do `app.py` (o teste de fidelidade lê o código do app com `ast` e acusa divergência).
- **Performance**: os quatro planos, cascata Cliente → Usina pela carteira real, ativos com o plano
  (`api.get_performance_alvos`), modos Geração / Usina / ETM, OS pai e observação por ativo, responsável, uma OS por
  ativo (`api.create_performance_os`). Deep link da plataforma: `/os/performance/criar?frase=…&usina=…&ativo=…&obs=…&os_pai=…&resp=…`.
- **Históricos de OS**: criadas por mim / atribuídas a mim, período, busca, colunas e cores do app; o número abre o
  detalhe (`api.get_os_detalhes`).
- **Ainda só no app**: Ativos, COS, PCM, Chamados, Inspeção de chamados, Tradicional, Clonar OS, Engenharia,
  Solicitação / PCM, Tickets, Alocação de análises; na Performance: tickets, imagens e OS agrupada; no detalhe: trocar
  responsável, cancelar, clonar. Cada card abre uma página que diz isso.

## Tamanho real do que "passa"

35 mil linhas no OS Creator. Cerca de 7,7 mil passam como estão (`api.py` e as specs puras). As outras ~27 mil são 47
telas Qt em `steps/`: a regra já está fora delas, mas cada tela nasce de novo em HTML. A fase 1 refez três.

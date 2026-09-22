// os_creator/os_web/static/perf.js — a tela PerfCriar do app, no navegador. Mesma lógica: cascata Cliente → Usina,
// ativos com o plano, uma OS por ativo, título '[Ativo] - base' (literal em ETM/Usina), confirmação antes de criar.
(function () {
  const root = document.getElementById('perf');
  if (!root) return;
  const FRASE = root.dataset.frase, TITULO = root.dataset.titulo;
  const ABA_TICKET = root.dataset.abaTicket || '';   // '' = plano que nao gera ocorrencia
  const gerarTicket = () => { const c = document.getElementById('ck_ticket'); return !!(c && c.checked); };
  const TEM_MODOS = root.dataset.temModos === '1', TRACKER = root.dataset.tracker === '1';
  const ETM_TIPO = 'Estação Meteorológica', USINA_TIPO = 'Usina';
  const ETM_TITULO = '[ETM] - Coleta e análise de dados', USINA_TITULO = '[Usina] - Coleta e análise de dados de geração';
  const $ = (id) => document.getElementById(id);
  const cbCli = $('cb_cli'), cbUsi = $('cb_usi'), busca = $('busca'), tbody = $('tbody'), hint = $('hint'), selLbl = $('sel_lbl');
  const edNome = $('ed_nome'), preview = $('preview'), resumo = $('resumo'), cbResp = $('cb_resp'), btn = $('btn_criar');
  let alvos = [], base = TITULO, modo = 'geracao', checked = new Set(), obs = {}, ospai = {}, imgs = {}, isTracker = TRACKER;
  let qtd = {};                  // quantidade da OCORRENCIA por ativo (a aba de tickets do plano)
  // A TABELA ABRE DE 10 EM 10 (Levi, 22/09). A Timon 1 tem 50 inversores e a tela virava uma
  // rolagem de duas telas antes de o primeiro campo aparecer. O limite e so de EXIBICAO: a
  // selecao, a busca e a criacao continuam valendo sobre a lista inteira.
  const PAGINA = 10;
  let limite = PAGINA;
  let sug = {usina: root.dataset.sugUsina, ativo: root.dataset.sugAtivo, obs: root.dataset.sugObs, os_pai: root.dataset.sugOspai,
             resp: root.dataset.sugResp, modo: root.dataset.sugModo};
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const apiErro = (j, r) => (j && j.erro) ? (j.login ? j.erro + ' Entre de novo em /os/login.' : j.erro) : ('HTTP ' + r.status);

  function tituloDe(a) { return modo === 'etm' ? ETM_TITULO : modo === 'usina' ? USINA_TITULO : '[' + a.label + '] - ' + (edNome.value.trim() || base); }

  function setModo(m) {
    modo = TEM_MODOS ? m : 'geracao';
    document.querySelectorAll('.os-seg-btn').forEach(b => b.classList.toggle('on', b.dataset.modo === modo));
    const unico = modo === 'etm' || modo === 'usina';
    $('w_filtro').hidden = unico; $('b_all').hidden = unico; $('b_none').hidden = unico;
    $('lb_ativos').innerHTML = modo === 'etm' ? 'Estação meteorológica <i>*</i> <small>(a estação da usina)</small>'
      : modo === 'usina' ? 'Usina <i>*</i> <small>(a planta inteira — UMA OS só)</small>'
      : 'Ativos <i>*</i> <small>(marque um ou vários — cada um vira uma OS)</small>';
    $('chip_prefixo').innerHTML = (modo === 'etm' ? '[ETM]' : modo === 'usina' ? '[Usina]' : '[Ativo]') + '&nbsp;&nbsp;-';
    edNome.readOnly = unico;
    $('lb_nome').innerHTML = 'Nome da tarefa <i>*</i> <small>' + (modo === 'etm' ? '(fixo para ETM)' : modo === 'usina' ? '(fixo para Usina)' : '(editável; o prefixo [Ativo] entra automático por OS)') + '</small>';
    const fixos = [ETM_TITULO.split(' - ')[1], USINA_TITULO.split(' - ')[1]];
    if (modo === 'etm') edNome.value = ETM_TITULO.split(' - ')[1];
    else if (modo === 'usina') edNome.value = USINA_TITULO.split(' - ')[1];
    else if (fixos.includes(edNome.value.trim())) edNome.value = base;
    checked = new Set(); limite = PAGINA; repop(); marcarUnico();
  }

  function visivel(a) {                                   // PerfCriar._repop: o MODO decide quem aparece
    if (!TEM_MODOS) return true;
    const alvo = modo === 'etm' ? ETM_TIPO : modo === 'usina' ? USINA_TIPO : null;
    if (alvo) return a.tipo === alvo;
    return a.tipo !== ETM_TIPO && a.tipo !== USINA_TIPO;   // Geração = só os inversores
  }

  // ── imagens por ativo (Levi, 21/09) ──────────────────────────────────────────────────────
  // Guardadas em base64 na propria pagina ate a criacao: o `create_performance_os` so pode
  // anexar DEPOIS que a OS existe (o anexo e preso a tarefa), entao subir antes seria arquivo
  // orfao no S3. Mesmo caminho do app de mesa, que tambem junta e manda junto.
  const MAX_IMG = 12, MAX_MB = 8;
  let alvoColar = 0;            // ultimo ativo em que se clicou em 'anexar' — e quem recebe o Ctrl+V

  function nImgs(id) { return (imgs[id] || []).length; }

  function rotuloImg(id) {
    const n = nImgs(id);
    return n ? n + (n > 1 ? ' imagens' : ' imagem') : 'anexar';
  }

  function lerArquivos(id, lista) {
    const files = [...(lista || [])].filter(f => /^image\//.test(f.type));
    if (!files.length) return;
    const cabe = MAX_IMG - nImgs(id);
    if (cabe <= 0) { alerta('Limite de ' + MAX_IMG + ' imagens por ativo.'); return; }
    files.slice(0, cabe).forEach(f => {
      if (f.size > MAX_MB * 1048576) { alerta('"' + f.name + '" tem mais de ' + MAX_MB + ' MB.'); return; }
      const fr = new FileReader();
      fr.onload = () => {
        (imgs[id] = imgs[id] || []).push({nome: nomeSeguro(f.name || 'imagem.png', f.type), b64: String(fr.result).split(',')[1] || '',
                                          url: String(fr.result)});   // `url` e so a miniatura: sai antes de enviar
        pintarImg(id); if (imgAberta === id) pintarJanela();
      };
      fr.readAsDataURL(f);
    });
    if (files.length > cabe) alerta('Entraram ' + cabe + '; o limite e ' + MAX_IMG + ' por ativo.');
  }

  function pintarImg(id) {
    const cel = tbody.querySelector('tr[data-id="' + id + '"] .c-img');
    if (!cel) return;
    const b = cel.querySelector('.img-b'), x = cel.querySelector('.img-x');
    if (b) { b.textContent = rotuloImg(id); b.classList.toggle('tem', !!nImgs(id)); }
    if (x) x.hidden = !nImgs(id);
    updPreview();
  }

  function alerta(t) { const h = $('hint_criar'); if (h) h.textContent = t; }

  // ── A JANELA DE IMAGENS (a mesma do Tradicional e do app) ──
  const EXT = /\.(png|jpe?g|gif|bmp|webp)$/i;
  // O NOME PRECISA SEGUIR SENDO DE IMAGEM: o servidor recusa anexo sem extensao de imagem, e a
  // recusa derruba a criacao inteira ("'inversor queimado' nao e imagem"). Quem renomeia escreve o
  // nome; a extensao volta sozinha. Barra vira sublinhado: no S3 ela abriria uma subpasta.
  function nomeSeguro(nome, tipo) {
    let n = String(nome || '').trim().replace(/[\\/]+/g, '_') || 'imagem';
    if (!EXT.test(n)) n += '.' + ((/image\/(\w+)/.exec(tipo || '') || [0, 'png'])[1].replace('jpeg', 'jpg'));
    return n;
  }
  let imgAberta = 0;
  const modalImg = $('modal_img');
  function pintarJanela() {
    const lista = imgs[imgAberta] || [];
    $('img_vazio').hidden = !!lista.length;
    $('img_grid').innerHTML = lista.map((im, k) => '<div class="trad-img-cell"><img src="' + (im.url || ('data:image/png;base64,' + im.b64)) + '" alt="">'
      + '<input type="text" class="trad-img-nome" value="' + esc(im.nome) + '" data-k="' + k + '" title="Clique para trocar o nome do anexo">'
      + '<button type="button" class="os-btn secondary mini" data-rm="' + k + '">Remover</button></div>').join('');
  }
  function abrirJanela(id) {
    const al = alvos.find(a => a.id === id);
    imgAberta = id; $('img_erro').hidden = true;
    $('img_titulo').innerHTML = 'Anexar imagens à OS de <b>' + esc(al ? (al.label || al.code) : 'ativo') + '</b>';
    pintarJanela(); modalImg.hidden = false; document.body.classList.add('os-modal-aberto');
  }
  function fecharJanela() {
    const id = imgAberta; imgAberta = 0; modalImg.hidden = true; document.body.classList.remove('os-modal-aberto');
    if (id) pintarImg(id);
  }
  modalImg.addEventListener('click', (ev) => { if (ev.target.closest('[data-fechar-img]')) fecharJanela(); });
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && imgAberta) fecharJanela(); });
  $('b_img_add').onclick = () => $('img_file').click();
  $('img_file').onchange = () => { if (imgAberta) lerArquivos(imgAberta, $('img_file').files); $('img_file').value = ''; };
  $('b_img_paste').onclick = async () => {
    // o botao le a area de transferencia pela API do navegador; se ela negar, o Ctrl+V com a
    // janela aberta continua funcionando — e a mensagem diz isso, em vez de so falhar
    const arquivos = [];
    try {
      for (const it of await navigator.clipboard.read()) {
        const t = it.types.find(x => x.startsWith('image/'));
        if (t) { const b = await it.getType(t); arquivos.push(new File([b], 'captura_' + (nImgs(imgAberta) + arquivos.length + 1) + '.png', {type: t})); }
      }
    } catch (e) { /* sem permissao: cai no aviso */ }
    if (!arquivos.length) { $('img_erro').hidden = false; $('img_erro').textContent = 'Não há imagem na área de transferência — copie uma captura de tela e use Ctrl+V com esta janela aberta.'; return; }
    $('img_erro').hidden = true; lerArquivos(imgAberta, arquivos);
  };
  $('img_grid').addEventListener('click', (ev) => {
    const k = ev.target.dataset.rm; if (k === undefined) return;
    (imgs[imgAberta] || []).splice(Number(k), 1); pintarJanela(); pintarImg(imgAberta);
  });
  $('img_grid').addEventListener('change', (ev) => {
    if (!ev.target.classList.contains('trad-img-nome')) return;
    const im = (imgs[imgAberta] || [])[Number(ev.target.dataset.k)]; if (!im) return;
    const antes = im.nome;
    im.nome = nomeSeguro(ev.target.value, (/^data:([^;]+)/.exec(im.url || '') || [0, 'image/png'])[1]);
    ev.target.value = im.nome;
    if (im.nome !== ev.target.value.trim() || antes !== im.nome) updPreview();
  });

  function repop() {
    const txt = norm(busca.value);
    const rows = alvos.filter(al => visivel(al) && (!txt || norm(al.label).includes(txt) || norm(al.code).includes(txt)));
    if (!alvos.length) { tbody.innerHTML = '<tr class="vazio"><td colspan="6">Selecione a usina para carregar os ativos com o plano.</td></tr>'; updCount(); return; }
    if (!rows.length) {
      tbody.innerHTML = '<tr class="vazio"><td colspan="6">' + (TEM_MODOS && modo !== 'geracao'
        ? '⚠ esta usina não tem ' + (modo === 'etm' ? 'Estação Meteorológica' : 'o item de usina') + ' cadastrada no Fracttal.' : 'Nenhum ativo casa com o filtro.') + '</td></tr>';
      updCount(); return;
    }
    if (limite > PAGINA && limite > rows.length) limite = Math.max(PAGINA, Math.ceil(rows.length / PAGINA) * PAGINA);
    const vis = rows.slice(0, limite);
    tbody.innerHTML = vis.map(al => {
      const on = checked.has(al.id);
      return '<tr data-id="' + al.id + '">' +
        '<td class="c-chk"><input type="checkbox" class="chk" ' + (on ? 'checked' : '') + '></td>' +
        '<td><span class="os-nome-ativo" title="' + esc(al.code) + '">' + esc(al.label) + '</span><span class="os-code">' + esc(al.code) + '</span></td>' +
        '<td class="c-qtd ' + (document.querySelector('th.c-qtd').classList.contains('oculta') ? 'oculta' : '') + '">'
          + '<input type="number" min="1" class="qtd" value="' + (qtd[al.id] == null ? (TRACKER ? 1 : 1) : qtd[al.id]) + '"'
          + (on ? '' : ' disabled') + ' title="Quantas ocorrencias esta OS registra na planilha de Tickets"></td>' +
        '<td class="c-pai"><input type="text" class="pai" placeholder="nº" value="' + esc(ospai[al.id] || '') + '" ' + (on ? '' : 'disabled') + '></td>' +
        '<td><input type="text" class="obs" placeholder="observação desta OS" value="' + esc(obs[al.id] || '') + '" ' + (on ? '' : 'disabled') + '></td>' +
        '<td class="c-img"><button type="button" class="img-b' + (nImgs(al.id) ? ' tem' : '') + '"' + (on ? '' : ' disabled')
          + ' title="Anexar imagens a esta OS (tambem aceita colar com Ctrl+V)">' + esc(rotuloImg(al.id)) + '</button>'
          + '<button type="button" class="img-x" title="tirar as imagens deste ativo"' + (nImgs(al.id) ? '' : ' hidden') + '>x</button>'
          + '<input type="file" class="img-f" accept="image/*" multiple hidden></td></tr>';
    }).join('') + rodapeMais(rows, vis);
    updCount();
  }

  // O rodape da tabela. Diz TRES coisas, e as tres importam:
  //  · quantos de quantos estao na tela (senao "50 marcado(s)" com 10 linhas visiveis assusta);
  //  · quantos MARCADOS estao escondidos — cada um vira uma OS, e nao poder ve-los nao pode
  //    significar nao saber que existem;
  //  · e os dois botoes, "mais 10" e "todos".
  function rodapeMais(rows, vis) {
    if (rows.length <= vis.length) return '';
    const escondidosMarcados = rows.slice(vis.length).filter(a => checked.has(a.id)).length;
    const faltam = rows.length - vis.length;
    return '<tr class="mais"><td colspan="6"><div class="mais-in">'
      + '<span class="os-ajuda">Mostrando ' + vis.length + ' de ' + rows.length + ' ativos'
      + (escondidosMarcados ? ' · <b>' + escondidosMarcados + ' marcado(s) fora da tela</b>' : '')
      + '</span>'
      + '<button type="button" class="os-btn secondary mini" data-mais="' + PAGINA + '">Mostrar mais '
      + Math.min(PAGINA, faltam) + '</button>'
      + '<button type="button" class="os-btn secondary mini" data-mais="tudo">Mostrar todos (' + rows.length + ')</button>'
      + '</div></td></tr>';
  }

  function updCount() { selLbl.textContent = checked.size + ' marcado(s)'; updPreview(); }
  function updPreview() {
    const al = alvos.find(a => checked.has(a.id)) || alvos.find(visivel);
    preview.innerHTML = al ? 'Fica, por ex.: <b>' + esc(tituloDe(al)) + '</b>  ·  a observação de cada OS vem da tabela de ativos acima.'
                           : 'A observação de cada OS vem da tabela de ativos acima.';
  }
  function marcarUnico() {                                 // ETM e Usina: o ativo já vem marcado (é sempre ele)
    if (!(modo === 'etm' || modo === 'usina')) return;
    alvos.filter(visivel).forEach(a => checked.add(a.id)); repop();
  }

  tbody.addEventListener('change', (ev) => {
    const tr = ev.target.closest('tr'); if (!tr) return; const id = Number(tr.dataset.id);
    if (ev.target.classList.contains('chk')) { ev.target.checked ? checked.add(id) : checked.delete(id);
      // TODOS os campos da linha, e nao so `pai` e `obs`: o botao de imagens e a quantidade do
      // ticket nasceram depois e ficavam travados ate um repop — marcar o ativo nao destravava o
      // "anexar", que era o "botao nao funciona" do Levi (21/09).
      tr.querySelectorAll('input.pai,input.obs,input.qtd,button.img-b').forEach(i => i.disabled = !ev.target.checked);
      updCount(); }
    if (ev.target.classList.contains('obs')) obs[id] = ev.target.value;
    if (ev.target.classList.contains('pai')) ospai[id] = ev.target.value;
  });
  tbody.addEventListener('input', (ev) => { const tr = ev.target.closest('tr'); if (!tr) return; const id = Number(tr.dataset.id);
    if (ev.target.classList.contains('obs')) { obs[id] = ev.target.value; agendarQtd(id); }
    if (ev.target.classList.contains('pai')) ospai[id] = ev.target.value;
    if (ev.target.classList.contains('qtd')) qtd[id] = Number(ev.target.value) || 1; });
  // a contagem de strings vem do SERVIDOR: a regra ("PV"/"STR"/"String") e medida e mora no
  // Python; uma copia em JS seria uma segunda verdade gravando em planilha de producao.
  let tQtd = {};
  function agendarQtd(id) {
    if (!ABA_TICKET || TRACKER) return;
    clearTimeout(tQtd[id]);
    tQtd[id] = setTimeout(async () => {
      try {
        const r = await fetch('/os/api/performance/qtd?frase=' + encodeURIComponent(FRASE)
          + '&texto=' + encodeURIComponent(obs[id] || ''));
        const j = await r.json();
        if (!r.ok) return;
        qtd[id] = j.qtd || 1;
        const c = tbody.querySelector('tr[data-id="' + id + '"] .qtd');
        if (c && document.activeElement !== c) c.value = qtd[id];
      } catch (e) { /* sem rede, fica o que estava */ }
    }, 350);
  }
  // imagens: o botao abre o seletor, o x limpa a linha, e o ativo em foco recebe o Ctrl+V
  tbody.addEventListener('click', (ev) => {
    const mais = ev.target.dataset && ev.target.dataset.mais;
    if (mais) { limite = mais === 'tudo' ? Infinity : limite + PAGINA; repop(); return; }
    const tr = ev.target.closest('tr'); if (!tr) return; const id = Number(tr.dataset.id);
    if (ev.target.classList.contains('img-b')) { alvoColar = id; abrirJanela(id); }
    if (ev.target.classList.contains('img-x')) { delete imgs[id]; pintarImg(id); }
  });
  tbody.addEventListener('change', (ev) => {
    if (!ev.target.classList.contains('img-f')) return;
    const tr = ev.target.closest('tr'); if (!tr) return;
    lerArquivos(Number(tr.dataset.id), ev.target.files);
    ev.target.value = '';                       // escolher o MESMO arquivo de novo tem de disparar
  });
  document.addEventListener('paste', (ev) => {
    // SO COM A JANELA ABERTA (22/09). Antes o Ctrl+V caia no ultimo ativo em que se clicou,
    // com a janela fechada — a imagem entrava num ativo que a pessoa nao estava olhando.
    if (!imgAberta) return;
    alvoColar = imgAberta;
    if (!alvoColar || !checked.has(alvoColar)) return;
    const f = [...((ev.clipboardData || {}).items || [])].filter(i => i.kind === 'file').map(i => i.getAsFile());
    if (f.length) { ev.preventDefault(); lerArquivos(alvoColar, f); }
  });
  $('b_all').onclick = () => { alvos.filter(visivel).forEach(a => checked.add(a.id)); repop(); };
  $('b_none').onclick = () => { checked = new Set(); repop(); };
  busca.oninput = () => { limite = PAGINA; repop(); };    // filtrar volta para a 1a pagina
  edNome.oninput = updPreview;
  document.querySelectorAll('.os-seg-btn').forEach(b => b.onclick = () => setModo(b.dataset.modo));

  async function carregarUsinas(preservar) {
    const cli = cbCli.value; const cur = preservar ? cbUsi.value : '';
    const r = await fetch('/os/api/performance/usinas?cliente=' + encodeURIComponent(cli)); const j = await r.json();
    cbUsi.innerHTML = '<option value="">— Selecione a usina —</option>' + (j.usinas || []).map(u => '<option value="' + esc(u) + '"' + (u === cur ? ' selected' : '') + '>' + esc(u) + '</option>').join('');
  }
  cbCli.onchange = async () => { await carregarUsinas(true); onUsina(); };
  cbUsi.onchange = onUsina;

  async function onUsina() {
    const usi = cbUsi.value;
    alvos = []; checked = new Set(); obs = {}; ospai = {}; imgs = {}; qtd = {}; limite = PAGINA; repop();
    resumo.textContent = 'Selecione a usina para carregar o plano.'; hint.textContent = '';
    if (!usi) return;
    hint.textContent = 'buscando ativos com o plano…';
    const r = await fetch('/os/api/performance/alvos?usina=' + encodeURIComponent(usi) + '&frase=' + encodeURIComponent(FRASE));
    const j = await r.json();
    if (!r.ok) { hint.textContent = '⚠ ativos: ' + apiErro(j, r); return; }
    if (j.cliente && cbCli.value !== j.cliente && [...cbCli.options].some(o => o.value === j.cliente)) { cbCli.value = j.cliente; await carregarUsinas(true); }
    isTracker = !!j.is_tracker; base = j.base || TITULO;
    if (!edNome.value.trim() || edNome.value.trim() === TITULO) edNome.value = base;
    alvos = j.ativos || [];
    if (j.erro) hint.textContent = '⚠ ' + j.erro;
    limite = PAGINA; repop(); marcarUnico();
    if (alvos.length) {
      hint.textContent = tbody.querySelectorAll('tr[data-id]').length + ' ativo(s) com o plano.';
      resumo.textContent = 'carregando o plano…';
      fetch('/os/api/performance/plano?id_task=' + alvos[0].plano_id_task + '&id_item=' + alvos[0].plano_id_item)
        .then(r => r.json().then(jj => ({ok: r.ok, jj}))).then(({ok, jj}) => { resumo.innerHTML = ok ? esc(jj.resumo).replace(/(Tipo|Classif\. 1|Classif\. 2|Criticidade|Duração):/g, '<b>$1:</b>') : '⚠ plano: ' + apiErro(jj, {status: '?'}); })
        .catch(e => { resumo.textContent = '⚠ plano: ' + e; });
    } else if (!j.erro) { hint.textContent = 'Nenhum ativo desta usina tem esse plano.'; resumo.textContent = '—'; }
    aplicarSugestao();
  }

  function aplicarSugestao() {                             // deep link da plataforma: marca o inversor + observação + OS pai
    if (!sug.ativo) return;
    const alvo = norm(sug.ativo); const numAlvo = (alvo.match(/(\d+(?:\.\d+)?)\s*$/) || [])[1];
    let al = alvos.find(a => norm(a.label) === alvo || (numAlvo && (norm(a.label).match(/(\d+(?:\.\d+)?)\s*$/) || [])[1] === numAlvo));
    if (!al) al = alvos.find(a => norm(a.label).includes(alvo));
    if (al) { checked.add(al.id); if (sug.obs) obs[al.id] = sug.obs; if (sug.os_pai) ospai[al.id] = sug.os_pai; repop();
      hint.textContent = 'Ativo ' + al.label + ' pré-selecionado pela plataforma.'; }
    else hint.textContent = '⚠ Não achei "' + sug.ativo + '" nesta usina — marque o ativo à mão.';
    sug.ativo = '';
  }

  async function carregarResp() {
    cbResp.innerHTML = '<option value="">carregando…</option>';
    try {
      const r = await fetch('/os/api/responsaveis'); const j = await r.json();
      if (!r.ok) throw new Error(apiErro(j, r));
      cbResp.innerHTML = '<option value="">— selecione —</option>' + (j.pessoas || []).map(p => '<option value="' + esc(p.id_personnel) + '" data-name="' + esc(p.name) + '">' + esc(p.name) + '</option>').join('');
      if (sug.resp) { const alvo = norm(sug.resp); const o = [...cbResp.options].find(o => norm(o.dataset.name) === alvo); if (o) cbResp.value = o.value; sug.resp = ''; }
    } catch (e) { cbResp.innerHTML = '<option value="">⚠ falha — relogue e clique em ↻</option>'; $('hint_criar').textContent = '⚠ responsável: ' + e.message; }
  }
  $('b_resp').onclick = carregarResp;

  btn.onclick = async () => {
    const ids = alvos.filter(a => visivel(a) && checked.has(a.id));
    if (!ids.length) { alert('Marque ao menos um ativo.'); return; }
    const opt = cbResp.selectedOptions[0];
    if (!opt || !opt.value) { alert('Escolha o responsável.'); return; }
    const b = edNome.value.trim() || base;
    const itens = ids.map(a => ({asset: {id: a.id, code: a.code, label: a.label, tipo: a.tipo, usina: cbUsi.value, cliente: cbCli.value},
      plano_id_task: a.plano_id_task, plano_id_item: a.plano_id_item, linkar: a.linkar, note: (obs[a.id] || '').trim(), os_pai: (ospai[a.id] || '').trim(),
      imagens: (imgs[a.id] || []).map(x => ({nome: x.nome, b64: x.b64})), qtd_ticket: qtd[a.id] || null}));
    let aviso = '';
    if (isTracker) aviso += "\nTrackers individuais: as OS usam o plano da 'Estrutura Trackers' (subtarefas copiadas).";
    if (modo === 'etm') aviso += '\nTítulo: ' + ETM_TITULO + ' · etiquetas: PERFORMANCE + ENGENHARIA.';
    if (modo === 'usina') aviso += '\nUMA OS na planta inteira, no lugar de uma por inversor.\nTítulo: ' + USINA_TITULO;
    // dito ANTES de criar: a linha de ticket e gravacao em planilha de producao, e quem confirma
    // tem de saber se ela vai acontecer — nos dois sentidos (mesma regra do app).
    const ger = gerarTicket();
    if (ABA_TICKET) {
      aviso += ger
        ? '\n' + itens.length + ' ocorrencia(s) na aba ' + ABA_TICKET + ', com '
          + itens.reduce((t, i) => t + (i.qtd_ticket || 1), 0) + ' no total.'
        : '\nSEM ocorrencia na planilha de Tickets.';
    }
    const nImg = itens.reduce((t, i) => t + (i.imagens || []).length, 0);
    if (nImg) aviso += '\n' + nImg + ' imagem(ns) serao anexadas.';
    const prog = $('dt_exec').value; if (prog) aviso += '\nProgramada para ' + prog.replace('T', ' ') + '.';
    if (!confirm('Vou criar ' + itens.length + ' OS — uma por ativo — com o plano \'' + TITULO + '\'.' + aviso + '\n\nContinuar?')) return;
    btn.disabled = true; $('hint_criar').textContent = 'criando ' + itens.length + ' OS… (pode levar alguns segundos)';
    const res = $('resultado'); res.hidden = true;
    try {
      const r = await fetch('/os/api/performance/criar', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({frase: FRASE, base: b, modo, evento: $('dt_prog').value, programada: prog, itens,
                              gerar_ticket: ger,
                              responsavel: {id_personnel: Number(opt.value), name: opt.dataset.name}})});
      const j = await r.json();
      res.hidden = false; res.classList.toggle('ruim', !r.ok || !j.ok);
      res.textContent = r.ok ? j.mensagem : ('⚠ ' + apiErro(j, r));
      if (r.ok && j.ok) { checked = new Set(); obs = {}; ospai = {}; imgs = {}; qtd = {}; repop(); }
    } catch (e) { res.hidden = false; res.classList.add('ruim'); res.textContent = '⚠ ' + e; }
    btn.disabled = false; $('hint_criar').textContent = '';
  };

  // arranque: modo do deep link, usina sugerida e responsáveis
  if (TEM_MODOS && (sug.modo === 'etm' || sug.modo === 'usina')) setModo(sug.modo); else setModo('geracao');
  carregarResp();
  if (sug.usina) { const o = [...cbUsi.options].find(o => norm(o.value) === norm(sug.usina) || norm(o.value).includes(norm(sug.usina))); if (o) { cbUsi.value = o.value; onUsina(); } }
})();

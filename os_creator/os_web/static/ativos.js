// Ativos — a AtivosTab (steps/ativos.py) em JS puro. O catálogo inteiro vem enxuto de /os/api/ativos/catalogo e o
// filtro é todo local (a `_aplica` do app); a hierarquia é o drill-down por id_parent dentro da usina escolhida.
(function () {
  const $ = id => document.getElementById(id);
  const LIMITE = +($('ativos').dataset.limite || 400);
  const norm = s => String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const fmtN = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  let TODOS = [], POR_ID = {}, RECENTES = new Set(), FILTRADOS = [];
  let cliente = '', usina = '', tipo = '', visao = 'lista', selId = null;

  // ── carga ──
  async function carregar() {
    const r = await fetch('/os/api/ativos/catalogo');
    if (!r.ok) { $('sub').textContent = 'não consegui carregar o catálogo: HTTP ' + r.status; return; }
    const d = await r.json();
    chegou(d.ativos || [], d.info || {});
    fetch('/os/api/ativos/recentes').then(x => x.ok ? x.json() : {codes: []}).then(j => { RECENTES = new Set(j.codes || []); aplica(); }).catch(() => {});
  }
  function chegou(ativos, info) {
    TODOS = ativos; POR_ID = {}; TODOS.forEach(a => { if (a.id != null) POR_ID[a.id] = a; });
    const usinas = new Set(TODOS.map(a => a.usina));
    $('sub').textContent = fmtN(TODOS.length) + ' ativos  ·  ' + usinas.size + ' usinas' + idadeTxt(info);
    arvore(); aplica();
  }
  function idadeTxt(info) {
    if (!info || !info.ts) return '';
    const d = new Date(info.ts * 1000);
    const q = String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0') + ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    return '  ·  lista de ' + q + (info.expirado ? '  (desatualizada)' : '');
  }

  // ── árvore cliente → usina ──
  function arvore() {
    const termo = norm($('busca_usina').value);
    const porCli = new Map(), nAtivos = new Map();
    TODOS.forEach(a => { const c = a.cliente || '—'; if (!porCli.has(c)) porCli.set(c, new Set()); porCli.get(c).add(a.usina || '—'); nAtivos.set(c, (nAtivos.get(c) || 0) + 1); });
    const box = $('arvore'); box.innerHTML = '';
    [...porCli.keys()].sort((a, b) => (nAtivos.get(b) - nAtivos.get(a))).forEach(cli => {
      let us = [...porCli.get(cli)].sort();
      if (termo) { us = us.filter(u => norm(u).includes(termo) || norm(cli).includes(termo)); if (!us.length) return; }
      const l = document.createElement('div'); l.className = 'at-cli' + ((cli === cliente && !usina) ? ' sel' : '');
      l.innerHTML = '<span>' + esc(cli) + '</span><small>(' + porCli.get(cli).size + ' usinas)</small>';
      l.addEventListener('click', () => { cliente = cliente === cli ? '' : cli; usina = ''; arvore(); aplica(); });
      box.appendChild(l);
      if (termo || cli === cliente) us.forEach(u => {
        const lu = document.createElement('div'); lu.className = 'at-usi' + (u === usina ? ' sel' : '');
        lu.textContent = usinaExibe(u, cli).slice(0, 26);
        lu.addEventListener('click', () => { usina = usina === u ? '' : u; if (usina) cliente = cli; arvore(); aplica(); });
        box.appendChild(lu);
      });
    });
  }
  function usinaExibe(u, c) { u = String(u || '').trim(); c = String(c || '').trim(); return (c && norm(u).startsWith(norm(c) + ' - ')) ? (u.slice(c.length + 3).trim() || u) : u; }

  // ── chips ──
  document.querySelectorAll('.at-chip[data-tipo]').forEach(b => b.addEventListener('click', () => {
    tipo = b.dataset.tipo; document.querySelectorAll('.at-chip[data-tipo]').forEach(x => x.classList.toggle('on', x === b)); aplica();
  }));
  document.querySelectorAll('.at-chip[data-visao]').forEach(b => b.addEventListener('click', () => {
    visao = b.dataset.visao; document.querySelectorAll('.at-chip[data-visao]').forEach(x => x.classList.toggle('on', x === b));
    $('v_lista').hidden = visao !== 'lista'; $('v_hier').hidden = visao !== 'hier'; aplica();
  }));

  // ── lista / hierarquia ──
  function aplica() {
    const termo = norm($('busca').value);
    FILTRADOS = TODOS.filter(a => (!cliente || (a.cliente || '—') === cliente) && (!usina || (a.usina || '—') === usina) && (!tipo || a.tipo === tipo)
      && (!termo || norm(a.code + ' ' + a.nome + ' ' + a.usina + ' ' + a.tipo).includes(termo)));
    if (visao === 'hier') { pintaHier(); return; }
    pinta(FILTRADOS.slice(0, LIMITE));
    const extra = FILTRADOS.length - LIMITE;
    $('rodape').textContent = fmtN(FILTRADOS.length) + ' ativos' + (extra > 0 ? ' · mostrando os ' + LIMITE + ' primeiros, refine a busca' : '') + (RECENTES.size ? ' · linha verde = OS nos últimos 30 dias' : '');
  }
  function linha(a, cols) {
    const tr = document.createElement('tr'); tr.dataset.id = a.id;
    tr.className = (RECENTES.has(a.code) ? 'recente' : '') + (a.id === selId ? ' sel' : '');
    tr.innerHTML = cols.map(c => '<td' + (c.cls ? ' class="' + c.cls + '"' : '') + '>' + esc(c.v) + '</td>').join('');
    tr.addEventListener('click', () => selecionar(a));
    return tr;
  }
  function pinta(itens) {
    const tb = $('tbody'); tb.innerHTML = '';
    itens.forEach(a => tb.appendChild(linha(a, [{v: a.code}, {v: a.nome}, {v: a.tipo}, {v: a.usina_curta}])));
    if (!itens.length) tb.innerHTML = '<tr><td colspan="4" class="at-hint">nenhum ativo neste recorte</td></tr>';
  }
  function pintaHier() {
    const tb = $('hbody'); tb.innerHTML = '';
    if (!usina) { $('rodape').textContent = 'escolha uma USINA na árvore da esquerda para ver a hierarquia'; return; }
    const escopo = TODOS.filter(a => (a.usina || '—') === usina), ids = new Set(escopo.map(a => a.id));
    const filhos = new Map(), raizes = [];
    escopo.forEach(a => { if (a.id_parent != null && ids.has(a.id_parent)) { if (!filhos.has(a.id_parent)) filhos.set(a.id_parent, []); filhos.get(a.id_parent).push(a); } else raizes.push(a); });
    raizes.sort((a, b) => ((a.tipo !== 'Usina') - (b.tipo !== 'Usina')) || String(a.code).localeCompare(String(b.code)));
    const no = (a, nivel) => { tb.appendChild(linha(a, [{v: a.nome, cls: nivel ? 'nivel' + Math.min(nivel, 4) : ''}, {v: a.code}, {v: a.tipo}]));
      (filhos.get(a.id) || []).sort((x, y) => String(x.code).localeCompare(String(y.code))).forEach(f => no(f, nivel + 1)); };
    raizes.forEach(a => no(a, 0));
    $('rodape').textContent = escopo.length + ' ativos na hierarquia de ' + usinaExibe(usina, cliente);
  }

  // ── seleção → painel do ativo ──
  async function selecionar(a) {
    selId = a.id;
    document.querySelectorAll('.at-tbl tbody tr').forEach(tr => tr.classList.toggle('sel', +tr.dataset.id === a.id));
    $('d_nome').textContent = a.nome || '—'; $('d_code').textContent = a.code || '';
    $('d_tipo').textContent = (a.tipo || '—').slice(0, 26); $('d_marca').textContent = '…';
    $('d_usina').textContent = (a.usina_curta || '—').slice(0, 26); $('d_cliente').textContent = (a.cliente || '—').slice(0, 26);
    $('os_box').innerHTML = ''; $('os_hint').hidden = false; $('os_hint').textContent = 'buscando as OS…';
    $('b_os').disabled = true; $('menu').hidden = true;
    const r = await fetch('/os/api/ativos/' + a.id);
    if (!r.ok || selId !== a.id) { if (selId === a.id) $('os_hint').textContent = 'não consegui buscar as OS'; return; }
    const d = await r.json();
    $('d_marca').textContent = String(d.marca || '—').slice(0, 26);
    if (!(d.os || []).length) $('os_hint').textContent = 'nenhuma OS neste ativo';
    else { $('os_hint').hidden = true;
      $('os_box').innerHTML = d.os.map(o => '<div class="at-os-item"><div class="l1"><a class="folio" href="/os/os/' + esc(o.id) + '" title="abrir a OS">' + esc(o.folio) + '</a><span class="data">' + esc(o.data) + '</span></div>' +
        '<div class="l2"><span>' + esc(o.tipo_tarefa) + '</span><span class="st" style="color:' + esc(o.cor) + '">' + esc(o.status) + '</span></div></div>').join(''); }
    const m = $('menu'); m.innerHTML = '';
    (d.destinos || []).forEach((x, i, arr) => { if (i === arr.length - 1 && x.rotulo.startsWith('Inspeção')) { const s = document.createElement('div'); s.className = 'sep'; m.appendChild(s); }
      const l = document.createElement('a'); l.href = x.href; l.textContent = x.rotulo; m.appendChild(l); });
    $('b_os').disabled = false;
  }
  $('b_os').addEventListener('click', e => { e.stopPropagation(); $('menu').hidden = !$('menu').hidden; });
  document.addEventListener('click', e => { if (!e.target.closest('.at-menu-wrap')) $('menu').hidden = true; });

  // ── busca (220 ms, como o QTimer do app) + Ctrl+F ──
  let t1, t2;
  $('busca').addEventListener('input', () => { clearTimeout(t1); t1 = setTimeout(aplica, 220); });
  $('busca_usina').addEventListener('input', () => { clearTimeout(t2); t2 = setTimeout(arvore, 200); });
  document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') { e.preventDefault(); $('busca').focus(); $('busca').select(); } });

  // ── Atualizar catálogo (ignora o cache de 24 h) ──
  $('b_reload').addEventListener('click', async () => {
    const b = $('b_reload'); b.disabled = true; b.textContent = 'atualizando…'; $('sub').textContent = 'buscando o catálogo no Fracttal…';
    const antes = TODOS.length;
    try {
      const r = await fetch('/os/api/ativos/atualizar', {method: 'POST'});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      const rc = await fetch('/os/api/ativos/catalogo'); const d = await rc.json();
      chegou(d.ativos || [], d.info || j.info || {});
      const delta = TODOS.length - antes;
      if (delta) $('rodape').textContent = 'catálogo atualizado — ' + (delta > 0 ? '+' : '') + delta + ' ativo(s) em relação à lista anterior';
    } catch (e) { $('sub').textContent = 'não consegui atualizar: ' + String(e.message || e).slice(0, 90); }
    b.disabled = false; b.textContent = 'Atualizar';
  });

  carregar();
})();

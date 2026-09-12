// os_creator/os_web/static/perf.js — a tela PerfCriar do app, no navegador. Mesma lógica: cascata Cliente → Usina,
// ativos com o plano, uma OS por ativo, título '[Ativo] - base' (literal em ETM/Usina), confirmação antes de criar.
(function () {
  const root = document.getElementById('perf');
  if (!root) return;
  const FRASE = root.dataset.frase, TITULO = root.dataset.titulo;
  const TEM_MODOS = root.dataset.temModos === '1', TRACKER = root.dataset.tracker === '1';
  const ETM_TIPO = 'Estação Meteorológica', USINA_TIPO = 'Usina';
  const ETM_TITULO = '[ETM] - Coleta e análise de dados', USINA_TITULO = '[Usina] - Coleta e análise de dados de geração';
  const $ = (id) => document.getElementById(id);
  const cbCli = $('cb_cli'), cbUsi = $('cb_usi'), busca = $('busca'), tbody = $('tbody'), hint = $('hint'), selLbl = $('sel_lbl');
  const edNome = $('ed_nome'), preview = $('preview'), resumo = $('resumo'), cbResp = $('cb_resp'), btn = $('btn_criar');
  let alvos = [], base = TITULO, modo = 'geracao', checked = new Set(), obs = {}, ospai = {}, isTracker = TRACKER;
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
    checked = new Set(); repop(); marcarUnico();
  }

  function visivel(a) {                                   // PerfCriar._repop: o MODO decide quem aparece
    if (!TEM_MODOS) return true;
    const alvo = modo === 'etm' ? ETM_TIPO : modo === 'usina' ? USINA_TIPO : null;
    if (alvo) return a.tipo === alvo;
    return a.tipo !== ETM_TIPO && a.tipo !== USINA_TIPO;   // Geração = só os inversores
  }

  function repop() {
    const txt = norm(busca.value);
    const rows = alvos.filter(al => visivel(al) && (!txt || norm(al.label).includes(txt) || norm(al.code).includes(txt)));
    if (!alvos.length) { tbody.innerHTML = '<tr class="vazio"><td colspan="6">Selecione a usina para carregar os ativos com o plano.</td></tr>'; updCount(); return; }
    if (!rows.length) {
      tbody.innerHTML = '<tr class="vazio"><td colspan="6">' + (TEM_MODOS && modo !== 'geracao'
        ? '⚠ esta usina não tem ' + (modo === 'etm' ? 'Estação Meteorológica' : 'o item de usina') + ' cadastrada no Fracttal.' : 'Nenhum ativo casa com o filtro.') + '</td></tr>';
      updCount(); return;
    }
    tbody.innerHTML = rows.map(al => {
      const on = checked.has(al.id);
      return '<tr data-id="' + al.id + '">' +
        '<td class="c-chk"><input type="checkbox" class="chk" ' + (on ? 'checked' : '') + '></td>' +
        '<td><span class="os-nome-ativo" title="' + esc(al.code) + '">' + esc(al.label) + '</span><span class="os-code">' + esc(al.code) + '</span></td>' +
        '<td class="c-qtd ' + (document.querySelector('th.c-qtd').classList.contains('oculta') ? 'oculta' : '') + '"><span class="os-ajuda">' + (TRACKER ? '1' : '—') + '</span></td>' +
        '<td class="c-pai"><input type="text" class="pai" placeholder="nº" value="' + esc(ospai[al.id] || '') + '" ' + (on ? '' : 'disabled') + '></td>' +
        '<td><input type="text" class="obs" placeholder="observação desta OS" value="' + esc(obs[al.id] || '') + '" ' + (on ? '' : 'disabled') + '></td>' +
        '<td class="c-img"><span class="os-ajuda" title="anexar imagens: em breve na web">—</span></td></tr>';
    }).join('');
    updCount();
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
    if (ev.target.classList.contains('chk')) { ev.target.checked ? checked.add(id) : checked.delete(id); tr.querySelectorAll('input.pai,input.obs').forEach(i => i.disabled = !ev.target.checked); updCount(); }
    if (ev.target.classList.contains('obs')) obs[id] = ev.target.value;
    if (ev.target.classList.contains('pai')) ospai[id] = ev.target.value;
  });
  tbody.addEventListener('input', (ev) => { const tr = ev.target.closest('tr'); if (!tr) return; const id = Number(tr.dataset.id);
    if (ev.target.classList.contains('obs')) obs[id] = ev.target.value; if (ev.target.classList.contains('pai')) ospai[id] = ev.target.value; });
  $('b_all').onclick = () => { alvos.filter(visivel).forEach(a => checked.add(a.id)); repop(); };
  $('b_none').onclick = () => { checked = new Set(); repop(); };
  busca.oninput = repop;
  edNome.oninput = updPreview;
  document.querySelectorAll('.os-seg-btn').forEach(b => b.onclick = () => setModo(b.dataset.modo));

  async function carregarUsinas(preservar) {
    const cli = cbCli.value; const cur = preservar ? cbUsi.value : '';
    const r = await fetch('/os/api/performance/usinas?cliente=' + encodeURIComponent(cli)); const j = await r.json();
    cbUsi.innerHTML = '<option value="">— Selecione a usina —</option>' + (j.usinas || []).map(u => '<option' + (u === cur ? ' selected' : '') + '>' + esc(u) + '</option>').join('');
  }
  cbCli.onchange = async () => { await carregarUsinas(true); onUsina(); };
  cbUsi.onchange = onUsina;

  async function onUsina() {
    const usi = cbUsi.value;
    alvos = []; checked = new Set(); obs = {}; ospai = {}; repop();
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
    repop(); marcarUnico();
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
      plano_id_task: a.plano_id_task, plano_id_item: a.plano_id_item, linkar: a.linkar, note: (obs[a.id] || '').trim(), os_pai: (ospai[a.id] || '').trim()}));
    let aviso = '';
    if (isTracker) aviso += "\nTrackers individuais: as OS usam o plano da 'Estrutura Trackers' (subtarefas copiadas).";
    if (modo === 'etm') aviso += '\nTítulo: ' + ETM_TITULO + ' · etiquetas: PERFORMANCE + ENGENHARIA.';
    if (modo === 'usina') aviso += '\nUMA OS na planta inteira, no lugar de uma por inversor.\nTítulo: ' + USINA_TITULO;
    const prog = $('dt_exec').value; if (prog) aviso += '\nProgramada para ' + prog.replace('T', ' ') + '.';
    if (!confirm('Vou criar ' + itens.length + ' OS — uma por ativo — com o plano \'' + TITULO + '\'.' + aviso + '\n\nContinuar?')) return;
    btn.disabled = true; $('hint_criar').textContent = 'criando ' + itens.length + ' OS… (pode levar alguns segundos)';
    const res = $('resultado'); res.hidden = true;
    try {
      const r = await fetch('/os/api/performance/criar', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({frase: FRASE, base: b, modo, evento: $('dt_prog').value, programada: prog, itens,
                              responsavel: {id_personnel: Number(opt.value), name: opt.dataset.name}})});
      const j = await r.json();
      res.hidden = false; res.classList.toggle('ruim', !r.ok || !j.ok);
      res.textContent = r.ok ? j.mensagem : ('⚠ ' + apiErro(j, r));
      if (r.ok && j.ok) { checked = new Set(); obs = {}; ospai = {}; repop(); }
    } catch (e) { res.hidden = false; res.classList.add('ruim'); res.textContent = '⚠ ' + e; }
    btn.disabled = false; $('hint_criar').textContent = '';
  };

  // arranque: modo do deep link, usina sugerida e responsáveis
  if (TEM_MODOS && (sug.modo === 'etm' || sug.modo === 'usina')) setModo(sug.modo); else setModo('geracao');
  carregarResp();
  if (sug.usina) { const o = [...cbUsi.options].find(o => norm(o.value) === norm(sug.usina) || norm(o.value).includes(norm(sug.usina))); if (o) { cbUsi.value = o.value; onUsina(); } }
})();

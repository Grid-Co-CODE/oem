// Clonar OS — o ClonarOSDialog (steps/clonar.py) em JS puro: a OS de referência fica em D.tarefas e a tela edita nela
// (ativo, descrição, subtarefas, data/hora por tarefa); "Criar clone" manda tudo para /os/api/clonar/criar.
(function () {
  const $ = id => document.getElementById(id);
  const raiz = $('clonar');
  let D = null;            // dados de /os/api/clonar/os
  let sel = -1;            // índice da tarefa selecionada
  const temAtivo = t => t && t.asset && t.asset.id != null;
  const nomeDe = t => (t.asset && (t.asset.label || t.asset.code)) || t.ativo_nome || t.code || '?';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const hoje0800 = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') + 'T08:00'; };
  const hint = t => { $('hint').textContent = t || ''; };
  function resultado(txt, ok) { const r = $('resultado'); r.hidden = !txt; r.textContent = txt || ''; r.className = 'os-resultado ' + (ok ? 'ok' : 'erro'); }
  async function apiErro(r) { try { const j = await r.json(); return j.erro || ('HTTP ' + r.status); } catch (e) { return 'HTTP ' + r.status; } }

  // ── carga ──
  async function carregar(folio) {
    folio = String(folio || '').trim();
    if (!/^\d+$/.test(folio)) { hint('informe o número da OS'); return; }
    hint('lendo a OS de referência…'); resultado('');
    $('resumo').textContent = 'Lendo a OS de referência…';
    const r = await fetch('/os/api/clonar/os?folio=' + encodeURIComponent(folio));
    if (!r.ok) { const e = await apiErro(r); $('resumo').innerHTML = '<span class="sem">' + esc(e) + '</span>'; hint(''); return; }
    D = await r.json(); sel = -1;
    $('t_ref').textContent = 'OS de referência ' + (D.folio || folio);
    try { history.replaceState(null, '', '/os/clonar?folio=' + encodeURIComponent(folio)); } catch (e) { /* prévia local (file://) não tem histórico */ }
    $('obs').value = D.notas || '';
    const n = (D.etiqueta_ids || []).length;
    $('chk_etiq_txt').textContent = 'Clonar etiquetas (' + n + ')';
    $('chk_etiq').disabled = !n; $('chk_etiq').checked = n > 0;
    renderTabela();
    const comAtivo = (D.tarefas || []).filter(temAtivo);
    $('b_upd_all').disabled = !comAtivo.length;
    if (!comAtivo.length) {
      $('resumo').innerHTML = '<span class="sem">Nenhuma tarefa desta OS tem ativo no catálogo carregado — recarregue os ativos no Criar OS e tente de novo.</span>';
      $('btn_criar').disabled = true; hint(''); return;
    }
    atualizaResumo();
    hint('desmarque um ativo p/ não clonar; clique na linha p/ editar as subtarefas');
    if (D.tarefas.length) selecionar(0);
  }

  function renderTabela() {
    const tb = $('tbody'); tb.innerHTML = '';
    (D.tarefas || []).forEach((t, i) => {
      const tem = temAtivo(t);
      const tr = document.createElement('tr'); tr.dataset.i = i; tr.className = (tem ? 'tem' : '') + (i === sel ? ' sel' : '');
      const nSub = (t.subtarefas || []).filter(s => s._keep !== false).length;
      tr.innerHTML = '<td><span class="ativo-nome">' + (tem ? '<input type="checkbox" class="chk-ativo"' + (t._skip ? '' : ' checked') + ' title="Incluir este ativo no clone">' : '') +
        '<span class="' + (tem ? '' : 'sem') + '">' + esc(nomeDe(t)) + '</span></span></td>' +
        '<td class="' + (tem ? '' : 'sem') + '">' + esc((t.tipo || 'Corretiva') + ' · ' + (t.descricao || '—')) + '</td>' +
        '<td class="c-subt">' + nSub + '</td>' +
        '<td>' + (tem ? '<input type="datetime-local" class="dt" value="' + esc(t.event_date || hoje0800()) + '"' + (t._skip ? ' disabled' : '') + '>' : '<span class="sem">ignorada</span>') + '</td>';
      tr.addEventListener('click', e => { if (e.target.closest('input')) return; selecionar(i); });
      const chk = tr.querySelector('.chk-ativo');
      if (chk) chk.addEventListener('change', () => { t._skip = !chk.checked; tr.querySelector('.dt').disabled = t._skip; atualizaResumo(); });
      const dt = tr.querySelector('.dt');
      if (dt) dt.addEventListener('change', () => { t.event_date = dt.value; });
      tb.appendChild(tr);
    });
    if (!(D.tarefas || []).length) tb.innerHTML = '<tr class="vazio"><td colspan="4">Esta OS não tem tarefas.</td></tr>';
  }

  function atualizaResumo() {
    const ts = (D && D.tarefas) || [];
    const incl = ts.filter(t => temAtivo(t) && !t._skip);
    const nExcl = ts.filter(t => temAtivo(t) && t._skip).length, nSem = ts.filter(t => !temAtivo(t)).length;
    if (!incl.length) { $('resumo').innerHTML = '<span class="sem">Nenhum ativo marcado para clonar.</span>'; $('btn_criar').disabled = true; return; }
    const nAtivos = new Set(incl.map(t => (t.asset && t.asset.code) || t.code)).size;
    const totalSub = incl.reduce((s, t) => s + (t.subtarefas || []).length, 0);
    let msg = 'Serão clonadas <b>' + incl.length + ' tarefa(s)</b> em <b>' + nAtivos + ' ativo(s)</b> e <b>' + totalSub + ' subtarefa(s)</b>, em <b>uma nova OS</b>.';
    const extra = []; if (nExcl) extra.push(nExcl + ' desmarcada(s)'); if (nSem) extra.push(nSem + ' sem ativo');
    if (extra.length) msg += '<br><span style="color:var(--f-muted)">' + extra.join(' · ') + ' não entram.</span>';
    $('resumo').innerHTML = msg; $('btn_criar').disabled = false;
  }

  // ── tarefa selecionada ──
  function selecionar(i) {
    sel = i; const t = D.tarefas[i];
    [...$('tbody').querySelectorAll('tr')].forEach(tr => tr.classList.toggle('sel', +tr.dataset.i === i));
    const tem = temAtivo(t);
    $('b_upd').disabled = !tem;
    const cb = $('ed_ativo'); cb.innerHTML = '';
    if (tem) {
      cb.disabled = false;
      (t.candidatos || [t.asset]).forEach(a => { const o = document.createElement('option'); o.value = a.id; o.textContent = a.label || a.code || '?'; o._a = a; if (a.id === t.asset.id) o.selected = true; cb.appendChild(o); });
    } else { cb.disabled = true; cb.innerHTML = '<option value="">(tarefa sem ativo — não clonável)</option>'; }
    $('ed_desc').disabled = false; $('ed_desc').value = t.descricao || '';
    renderSubs();
  }
  function renderSubs() {
    const t = D.tarefas[sel]; const box = $('subs'); box.innerHTML = '';
    $('sub_titulo').innerHTML = '<b>Subtarefas</b> <span style="color:var(--f-muted)">· ' + esc(nomeDe(t)) + ' (desmarque p/ não incluir, ou exclua)</span>';
    const subs = t.subtarefas || [];
    if (!subs.length) { box.innerHTML = '<div class="os-ajuda">(sem subtarefas — será criada com \'Procedimento\')</div>'; return; }
    subs.forEach(s => {
      const row = document.createElement('div'); row.className = 'cl-sub';
      const keep = s._keep !== false;
      row.innerHTML = '<input type="checkbox" class="k"' + (keep ? ' checked' : '') + ' title="Incluir esta subtarefa no clone">' +
        '<input type="text" class="d" value="' + esc(s.description || '') + '"' + (keep ? '' : ' disabled') + (s.task_form_item_type_description ? ' title="Tipo: ' + esc(s.task_form_item_type_description) + '"' : '') + '>' +
        '<button type="button" class="os-btn secondary mini" title="Remover esta subtarefa do clone">Excluir</button>';
      row.querySelector('.k').addEventListener('change', e => { s._keep = e.target.checked; row.querySelector('.d').disabled = !s._keep; refreshCount(); });
      row.querySelector('.d').addEventListener('input', e => { s.description = e.target.value; });
      row.querySelector('button').addEventListener('click', () => { t.subtarefas.splice(t.subtarefas.indexOf(s), 1); renderSubs(); refreshCount(); });
      box.appendChild(row);
    });
  }
  function refreshCount() {
    const t = D.tarefas[sel]; const tr = $('tbody').querySelector('tr[data-i="' + sel + '"]');
    if (tr) tr.querySelector('.c-subt').textContent = (t.subtarefas || []).filter(s => s._keep !== false).length;
    atualizaResumo();
  }
  $('ed_ativo').addEventListener('change', e => {
    const t = D && D.tarefas[sel]; const o = e.target.selectedOptions[0]; if (!t || !o || !o._a) return;
    t.asset = o._a; t.code = o._a.code || t.code; t.ativo_nome = o._a.label || o._a.code || t.ativo_nome;
    const tr = $('tbody').querySelector('tr[data-i="' + sel + '"]'); if (tr) tr.querySelector('.ativo-nome span:last-child').textContent = nomeDe(t);
    atualizaResumo();
  });
  $('ed_desc').addEventListener('input', e => {
    const t = D && D.tarefas[sel]; if (!t) return; t.descricao = e.target.value;
    const tr = $('tbody').querySelector('tr[data-i="' + sel + '"]'); if (tr) tr.children[1].textContent = (t.tipo || 'Corretiva') + ' · ' + (t.descricao || '—');
  });

  // ── data em massa ──
  const dts = () => [...$('tbody').querySelectorAll('input.dt')];
  const grava = () => dts().forEach(inp => { const t = D.tarefas[+inp.closest('tr').dataset.i]; if (t) t.event_date = inp.value; });
  $('b_data').addEventListener('click', () => { const d = $('bulk_date').value; if (!d) return; dts().forEach(inp => { inp.value = d + 'T' + ((inp.value || hoje0800()).slice(11, 16) || '08:00'); }); grava(); });
  const setHora = hm => { dts().forEach(inp => { inp.value = (inp.value || hoje0800()).slice(0, 10) + 'T' + hm; }); grava(); };
  $('b_manha').addEventListener('click', () => setHora('07:00'));
  $('b_tarde').addEventListener('click', () => setHora('13:00'));
  $('b_mes').addEventListener('click', () => {
    dts().forEach(inp => { const v = inp.value || hoje0800(); const d = new Date(v); if (isNaN(d)) return; d.setMonth(d.getMonth() + 1);
      inp.value = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') + 'T' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); });
    grava();
  });

  // ── modelo ──
  $('b_upd').addEventListener('click', async () => {
    const t = D && D.tarefas[sel]; if (!temAtivo(t)) { hint('Selecione uma tarefa com ativo.'); return; }
    $('b_upd').disabled = true; hint('buscando as subtarefas do modelo no Fracttal…');
    const r = await fetch('/os/api/clonar/modelo', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({asset_id: t.asset.id, descricao: t.descricao || ''})});
    const j = r.ok ? await r.json() : {erro: await apiErro(r)};
    $('b_upd').disabled = false;
    if (j.achou) { t.subtarefas = j.subtarefas || []; renderSubs(); refreshCount(); hint('subtarefas atualizadas do modelo (' + t.subtarefas.length + ').'); }
    else { hint(''); resultado(j.erro || 'Não encontrei um modelo com esse nome para o ativo.', false); }
  });
  $('b_upd_all').addEventListener('click', async () => {
    const com = (D.tarefas || []).filter(temAtivo); if (!com.length) return;
    if (!confirm('Isso substitui as subtarefas de ' + com.length + ' tarefa(s) pela versão atual do modelo de cada ativo — quaisquer edições/exclusões manuais serão perdidas.\n\nContinuar?')) return;
    $('b_upd_all').disabled = true; $('b_upd').disabled = true; $('btn_criar').disabled = true;
    hint('atualizando ' + com.length + ' tarefa(s) do modelo… (pode levar alguns segundos)');
    const r = await fetch('/os/api/clonar/modelo-todas', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tarefas: D.tarefas})});
    const j = r.ok ? await r.json() : {erro: await apiErro(r)};
    $('b_upd_all').disabled = false;
    if (!r.ok) { hint(''); resultado(j.erro, false); atualizaResumo(); return; }
    let nOk = 0, falhas = [];
    (j.resultados || []).forEach((res, i) => { const t = D.tarefas[i]; if (!res) return; if (res.achou) { t.subtarefas = res.subtarefas || []; nOk++; } else falhas.push(t.descricao || t.code || '?'); });
    renderTabela(); if (sel >= 0) selecionar(sel); atualizaResumo();
    hint(nOk + ' tarefa(s) atualizada(s) do modelo' + (falhas.length ? '; ' + falhas.length + ' sem modelo.' : '.'));
    if (falhas.length) resultado(nOk + ' atualizada(s). Sem modelo correspondente (' + falhas.length + '):\n- ' + falhas.slice(0, 12).join('\n- ') + (falhas.length > 12 ? '\n…' : ''), false);
  });

  // ── responsável: filtro por nome ──
  $('resp_busca').addEventListener('input', e => {
    const q = e.target.value.toLowerCase(); [...$('cb_resp').options].forEach(o => { if (o.value) o.hidden = q && !o.textContent.toLowerCase().includes(q); });
  });

  // ── criar ──
  $('btn_criar').addEventListener('click', async () => {
    grava();
    const clonar = (D.tarefas || []).filter(t => !t._skip);
    if (!clonar.filter(temAtivo).length) { resultado('Nenhum ativo marcado para clonar.', false); return; }
    const cb = $('cb_resp'); const idp = cb.value;
    if (!idp) { resultado('Escolha o responsável.', false); return; }
    const n = clonar.filter(temAtivo).length;
    if (!confirm('Criar uma OS nova com ' + n + ' tarefa(s) clonada(s) da OS ' + (D.folio || '') + '?')) return;
    $('btn_criar').disabled = true; resultado('');
    hint('criando clone com ' + n + ' tarefa(s)… (pode levar alguns segundos)');
    const corpo = {tarefas: D.tarefas, id_responsible: +idp, responsible_name: cb.selectedOptions[0].textContent.trim(),
                   clonar_etiquetas: $('chk_etiq').checked, etiqueta_ids: D.etiqueta_ids || [], note: $('obs').value.trim()};
    const r = await fetch('/os/api/clonar/criar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)});
    const j = r.ok ? await r.json() : {ok: false, mensagem: await apiErro(r)};
    $('btn_criar').disabled = false; hint('');
    resultado(j.mensagem || (j.ok ? 'OS clonada.' : 'Falha desconhecida ao clonar.'), !!j.ok);
    if (j.ok && j.id_work_order) resultado(j.mensagem + '\nAbrir a OS: /os/os/' + j.id_work_order, true);
  });

  $('b_carregar').addEventListener('click', () => carregar($('folio').value));
  $('folio').addEventListener('keydown', e => { if (e.key === 'Enter') carregar($('folio').value); });
  $('bulk_date').value = hoje0800().slice(0, 10);
  if (raiz.dataset.folio) carregar(raiz.dataset.folio);
})();

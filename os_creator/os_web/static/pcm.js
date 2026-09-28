// os_creator/os_web/static/pcm.js — a PcmTab do app (steps/pcm.py), no navegador: o card PCM, "PCM — OS por plano de
// tarefas". Mesma lógica: cascata Cliente → Usina → Tipo + busca (_on_cli/_on_usi/_refresh); a marcação sobrevive a
// filtro e a troca de usina (o `_checked`); "Carregar planos" (get_plans_for_assets + as contagens); a família do plano
// reordena a tabela com plano no topo; cada linha mostra o plano da família (o "[Grid Co.]" de saída), as subtarefas, a
// data/hora e o TEMPO (seta de 30 em 30 min); a programação em massa; "Sem plano de tarefas"; observação, Requerido
// por e OS pai; e a confirmação antes de criar UMA OS com cada ativo como tarefa. Aviso fica na página, nunca em janela.
(function () {
  'use strict';
  const root = document.getElementById('pcm');
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const enc = encodeURIComponent;
  const apiErro = (j, r) => (j && j.erro) ? (j.login ? j.erro + ' Entre de novo em /os/login.' : j.erro) : ('HTTP ' + r.status);
  const p2 = (n) => (n < 10 ? '0' : '') + n;
  const cmp = (x, y) => (x < y ? -1 : (x > y ? 1 : 0));    // a ordem do Python (ponto de código), não a do idioma
  const HOJE = root.dataset.hoje;
  const SEL = '— selecione —';                                // steps/pcm.py::_SEL
  const DUR_PADRAO = 900;                                     // api.duracao_do_plano(padrao=900): 15 min até ler o plano
  const DICA_TEMPO = 'Quanto a tarefa deve durar. Vem do plano; edite se esta for diferente. A seta anda de 30 em 30 minutos.';
  const SVG_CIMA = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>';
  const SVG_BAIXO = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';

  const cbCli = $('cb_cli'), cbUsi = $('cb_usi'), cbTipo = $('cb_tipo'), busca = $('busca');
  const ckSem = $('ck_sem_plano'), descLbl = $('desc_lbl'), edDesc = $('ed_desc');
  const famLbl = $('fam_lbl'), cbFam = $('cb_familia'), bPlanos = $('b_planos'), avisoPlanos = $('aviso_planos');
  const bComPlano = $('b_complano'), bAll = $('b_all'), bNone = $('b_none'), tbody = $('tbody'), selLbl = $('sel_lbl');
  const bulkDate = $('bulk_date'), obs = $('obs'), cbResp = $('cb_resp'), bResp = $('b_resp');
  const ospaiIn = $('ospai_in'), ospaiLista = $('ospai_lista'), btn = $('btn_criar'), hint = $('hint'), res = $('resultado');

  // ── o estado, com os nomes do PcmTab.__init__ ──
  let ativos = [];                    // os ativos da usina (o `_assets` já filtrado por cliente/usina e pela regra do tracker)
  let linhas = [];                    // as linhas da tabela, na ordem da tela — é o que o `_criar` percorre
  const checked = new Set();          // _checked: ids marcados; sobrevivem a filtro, a troca de usina e a Limpar fora da tabela
  let planosByAsset = {};             // _planos_by_asset: id do ativo -> [planos] (do último Carregar)
  let loadedFor = new Set();          // _loaded_for: os ativos cujos planos já foram carregados
  const subt = {};                    // _subt: id_task -> nº de subtarefas (cache da tela)
  const durPlano = {};                // id_task -> segundos: a duração do plano, que chega junto da contagem
  const dtByAsset = {};               // _dt_by_asset: a data de cada ativo sobrevive à troca de família
  const durByAsset = {};              // _dur_by_asset: só o tempo que a PESSOA mexeu; ausente = vale o do plano
  let semPlano = false;               // _sem_plano
  let pessoas = [];                   // a lista do "Requerido por"
  let ultimaData = bulkDate.value || HOJE;

  // o pedido que a PESSOA disparou: com o círculo de carga (carga.js)
  async function pedir(url, opcoes, texto) {
    const r = await OsCarga.buscar(url, Object.assign({credentials: 'same-origin'}, opcoes || {}), texto || 'Carregando…');
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(apiErro(j, r));
    return j;
  }

  // ── cascata (_cli / _usi / _on_cli / _on_usi) ──
  // o cliente vai no `value` da opção (o texto cru, o `currentText()` do app): sem o atributo, o navegador colapsa o
  // espaço duplo do nome (tests/test_os_web_option_value.py, 22/09)
  const cli = () => (cbCli.selectedIndex > 0 ? cbCli.options[cbCli.selectedIndex].value : null);
  const usi = () => (cbUsi.selectedIndex > 0 ? cbUsi.options[cbUsi.selectedIndex].value : null);
  const tipo = () => (cbTipo.selectedIndex > 0 ? cbTipo.options[cbTipo.selectedIndex].value : null);
  const fam = () => cbFam.value || null;                     // _fam: "(carregue os planos)" e "(todas)" = qualquer família
  const opcao = (v) => '<option value="' + esc(v) + '">' + esc(v) + '</option>';
  let seqCli = 0, seqUsi = 0;                                // a resposta velha (cliente trocado no meio) não pinta a tela

  async function onCli() {
    const c = cli(), meu = ++seqCli;
    cbUsi.innerHTML = '<option value="">— Selecione a usina —</option>'; cbUsi.disabled = true;
    if (c) {
      try {
        const us = (await pedir('/os/api/pcm/usinas?cliente=' + enc(c), null, 'Carregando as usinas…')).usinas || [];
        if (meu !== seqCli) return;
        cbUsi.innerHTML += us.map(opcao).join('');
        cbUsi.disabled = !us.length;
      } catch (e) { if (meu === seqCli) hint.textContent = '⚠ ' + e.message; }
    }
    if (meu === seqCli) await onUsi();
  }

  async function onUsi() {
    const c = cli(), u = usi(), meu = ++seqUsi;
    cbTipo.innerHTML = '<option value="">Todos os tipos</option>'; cbTipo.disabled = true;
    ativos = [];
    if (u) {
      try {
        const j = await pedir('/os/api/pcm/ativos?cliente=' + enc(c || '') + '&usina=' + enc(u), null, 'Carregando os ativos…');
        if (meu !== seqUsi) return;
        const ts = j.tipos || [];
        cbTipo.innerHTML += ts.map(opcao).join('');
        cbTipo.disabled = !ts.length;
        ativos = j.ativos || [];
      } catch (e) { if (meu === seqUsi) hint.textContent = '⚠ ' + e.message; }
    }
    if (meu === seqUsi) refresh();
  }

  // ── a tabela (_has_plan / _refresh / _fill_row / _fill_planos) ──
  const planosDe = (aid, f) => (planosByAsset[aid] || []).filter((p) => f == null || p.family === f);
  function temPlano(aid, f) {                                // _has_plan: só conta o ativo já carregado
    return aid != null && loadedFor.has(aid) && planosDe(aid, f).length > 0;
  }
  const linhaDe = (aid) => tbody.querySelector('tr[data-id="' + aid + '"]');
  const dim = (t) => '<span class="pcm-dim">' + esc(t) + '</span>';

  function refresh() {                                       // _refresh: filtra, ordena e redesenha tudo
    const u = usi(), t = tipo(), txt = (busca.value || '').trim().toLowerCase(), f = fam();
    linhas = !u ? [] : ativos.filter((a) => a.tipo && (!t || a.tipo === t) && (!txt || String(a.label || '').toLowerCase().includes(txt)));
    // COM plano (na família atual) no topo, SEM plano embaixo; cada bloco por nome
    linhas.sort((a, b) => ((temPlano(a.id, f) ? 0 : 1) - (temPlano(b.id, f) ? 0 : 1))
      || cmp(String(a.label || a.code || '').toLowerCase(), String(b.label || b.code || '').toLowerCase()));
    fillPlanos();
  }

  function fillPlanos() {                                    // _fill_planos: todas as linhas, na ordem que já estão
    tbody.innerHTML = linhas.length ? linhas.map(linhaHtml).join('')
      : '<tr class="vazio"><td colspan="5">' + (usi() ? 'Nenhum ativo nesta seleção.' : 'Selecione cliente e usina para ver os ativos.') + '</td></tr>';
    fetchCounts();
    updLabel();
  }

  function linhaHtml(a) {
    const c = celulas(a);
    return '<tr data-id="' + esc(a.id) + '"' + (c.sem ? ' class="sem"' : '') + '><td class="c-ativo"><label class="pcm-chk">'
      + '<input type="checkbox" class="chk"' + (checked.has(a.id) ? ' checked' : '') + '><span>' + esc(a.label || a.code || '?') + '</span></label></td>'
      + '<td class="c-plano">' + c.c1 + '</td><td class="c-subt">' + c.c2 + '</td><td class="c-dt">' + c.c3 + '</td><td class="c-tempo">' + c.c4 + '</td></tr>';
  }

  function fillRow(aid) {                                    // _fill_row de UMA linha (o check da pessoa não é redesenhado)
    const tr = linhaDe(aid), a = linhas.find((x) => x.id === aid);
    if (!tr || !a) return;
    const c = celulas(a), td = tr.children;
    tr.classList.toggle('sem', !!c.sem);
    td[1].innerHTML = c.c1; td[2].innerHTML = c.c2; td[3].innerHTML = c.c3; td[4].innerHTML = c.c4;
  }

  // Plano (combo) + nº de subtarefas + data + tempo de UMA linha, conforme o modo, a família e se o ativo está marcado
  function celulas(a) {
    const aid = a.id;
    if (!checked.has(aid)) return {c1: dim('—'), c2: '', c3: dim('—'), c4: ''};
    if (semPlano) {                                          // ativo marcado = tarefa com a subtarefa 'Procedimento'
      return {c1: '<span class="pcm-dim pcm-pre">' + esc('Procedimento  (sem plano de tarefas)') + '</span>', c2: '1', c3: dataHtml(aid), c4: ''};
    }
    if (!loadedFor.has(aid)) return {c1: dim('clique em “Carregar planos”'), c2: '', c3: dim('—'), c4: ''};
    const ps = planosDe(aid, fam()).slice().sort((x, y) => cmp(String(x.description || '').toLowerCase(), String(y.description || '').toLowerCase()));
    if (!ps.length) return {sem: true, c1: esc('— sem plano nesta família —'), c2: '—', c3: '—', c4: ''};
    // tem plano(s): o combo abre no primeiro com "grid" no nome (o [Grid Co.]), senão no primeiro — pcm_web.plano_padrao
    let gi = ps.findIndex((p) => String(p.description || '').toLowerCase().includes('grid'));
    if (gi < 0) gi = 0;
    const c1 = '<select class="plano" data-osb="nativo">' + ps.map((p, i) => '<option value="' + esc(p.id_task) + '"'
      + (i === gi ? ' selected' : '') + '>' + esc(p.description || '?') + '</option>').join('') + '</select>';
    const idt = ps[gi].id_task;
    return {c1: c1, c2: contagemHtml(idt), c3: dataHtml(aid), c4: tempoHtml(aid, idt)};
  }

  function contagemHtml(idt) {                               // _set_count_cell
    const n = subt[idt];
    if (n == null) return dim('…');
    if (Number(n) === 0) return '<span class="pcm-red">0</span>';
    return esc(n);
  }

  // _add_date_editor: a data vale POR ATIVO (a tabela é redesenhada a cada troca de família); a primeira vez, a data da
  // programação em massa às 08:00
  function dataHtml(aid) {
    if (!dtByAsset[aid]) dtByAsset[aid] = (bulkDate.value || ultimaData || HOJE) + 'T08:00';
    return '<input type="datetime-local" class="dt" value="' + esc(dtByAsset[aid]) + '" autocomplete="off">';
  }

  // ── o tempo da tarefa (o _TempoTarefa): HH:mm, começando no que o PLANO diz; a seta anda de 30 em 30 min ──
  const minutosDe = (seg) => Math.floor(Number(seg) / 60);
  function hhmm(min) { const t = Math.max(0, Math.min(min, 23 * 60 + 59)); return p2(Math.floor(t / 60)) + ':' + p2(t % 60); }
  function lerTempo(txt) {                                   // "01:30" (ou "1:30", "0130") → minutos; null se não é horário
    const m = /^\s*(\d{1,2}):?(\d{2})\s*$/.exec(txt || '');
    if (!m) return null;
    const h = Number(m[1]), mi = Number(m[2]);
    return (h <= 23 && mi <= 59) ? h * 60 + mi : null;
  }
  // _TempoTarefa.stepBy: vai para o múltiplo seguinte NA DIREÇÃO do passo (01:10 sobe para 01:30 e desce para 01:00);
  // nunca zera (piso de 15 min, ou o do plano se ele for mais curto); para em 23:30; no limite não anda, nunca ao contrário
  function passoTempo(m, passos) {
    const PASSO = 30, TETO = 23 * 60 + 30;
    let novo = passos > 0 ? (Math.floor(m / PASSO) + 1) * PASSO : (Math.floor((m + PASSO - 1) / PASSO) - 1) * PASSO;
    const piso = Math.min(15, m) || 15;
    novo = Math.max(piso, Math.min(TETO, novo));
    if ((passos > 0 && novo < m) || (passos < 0 && novo > m)) novo = m;
    return novo;
  }
  const segTempo = (aid, idt) => durByAsset[aid] || durPlano[idt] || DUR_PADRAO;   // `_dur_by_asset.get(aid) or duracao_do_plano`
  function tempoHtml(aid, idt) {
    return '<span class="pcm-tempo" title="' + esc(DICA_TEMPO) + '"><input type="text" class="tp" value="' + hhmm(minutosDe(segTempo(aid, idt)))
      + '" inputmode="numeric" maxlength="5" autocomplete="off" aria-label="Tempo da tarefa (HH:mm)"><span class="tp-setas">'
      + '<button type="button" class="tp-b" data-passo="1" tabindex="-1" aria-label="Mais 30 minutos">' + SVG_CIMA + '</button>'
      + '<button type="button" class="tp-b" data-passo="-1" tabindex="-1" aria-label="Menos 30 minutos">' + SVG_BAIXO + '</button></span></span>';
  }
  function planoDaLinha(tr) { const cb = tr && tr.querySelector('select.plano'); return cb && cb.value ? Number(cb.value) : null; }
  // o tempo que a linha mostra quando ninguém mexeu nele: o do plano que o combo mostra agora
  function pintarTempo(tr) {
    const inp = tr && tr.querySelector('input.tp'), aid = tr && Number(tr.dataset.id);
    if (!inp || durByAsset[aid] != null || document.activeElement === inp) return;
    inp.value = hhmm(minutosDe(segTempo(aid, planoDaLinha(tr))));
  }
  function andar(inp, passos) {
    const tr = inp.closest('tr'), aid = Number(tr.dataset.id);
    const m = lerTempo(inp.value);
    const atual = m == null ? minutosDe(segTempo(aid, planoDaLinha(tr))) : m;
    const novo = passoTempo(atual, passos);
    inp.value = hhmm(novo);
    if (novo !== atual) durByAsset[aid] = novo * 60;        // o timeChanged do app só vem quando o tempo muda
  }

  // ── contagem de subtarefas (_fetch_counts_visiveis / _set_counts / _counts_err) ──
  let contando = false;
  function paresFaltando() {
    const out = [];
    tbody.querySelectorAll('tr[data-id] select.plano').forEach((cb) => {
      if (cb.value && !(cb.value in subt)) out.push([Number(cb.value), Number(cb.closest('tr').dataset.id)]);
    });
    return out;
  }
  // em segundo plano, sem o círculo: no app é uma thread e a tabela segue usável. Um pedido por vez (o `self._ws`); no
  // fim, pega o que sobrou — menos o que acabou de ser pedido e não veio, para a falha não virar um laço de pedidos
  function fetchCounts(excluir) {
    if (contando) return;
    const pares = paresFaltando().filter((p) => !(excluir && excluir.has(p[0])));
    if (!pares.length) return;
    contando = true;
    const pedidos = new Set(excluir || []);
    pares.forEach((p) => pedidos.add(p[0]));
    fetch('/os/api/pcm/subtarefas?pares=' + pares.map((p) => p[0] + ':' + p[1]).join(','), {credentials: 'same-origin'})
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j) { Object.assign(subt, j.subt || {}); Object.assign(durPlano, j.dur || {}); } })
      .catch(() => { /* _counts_err: a linha fica em "…" */ })
      .then(() => { contando = false; pintarContagens(); fetchCounts(pedidos); });
  }
  function pintarContagens() {
    tbody.querySelectorAll('tr[data-id]').forEach((tr) => {
      const idt = planoDaLinha(tr);
      if (idt == null) return;
      tr.children[2].innerHTML = contagemHtml(idt);
      pintarTempo(tr);
    });
  }

  // ── "N marcado(s)" (_upd_label / _sem_plano_rows) ──
  function semPlanoRows() {
    if (semPlano) return [];
    const f = fam();
    return linhas.filter((a) => checked.has(a.id) && loadedFor.has(a.id) && !planosDe(a.id, f).length);
  }
  function updLabel() {
    if (semPlano) {
      selLbl.textContent = checked.size + " marcado(s) · sem plano (cada ativo = 1 tarefa, subtarefa 'Procedimento')";
      return;
    }
    const com = linhas.filter((a) => checked.has(a.id) && planoDaLinha(linhaDe(a.id)) != null).length;
    const sem = semPlanoRows().length;
    let msg = esc(checked.size + ' marcado(s)');
    if (loadedFor.size) {
      msg += ' · ' + com + ' com plano';
      if (sem) msg += ' · <span class="pcm-red">' + sem + ' SEM plano nesta família</span>';
    }
    selLbl.innerHTML = msg;
  }

  // ── eventos da tabela ──
  tbody.addEventListener('change', (ev) => {
    const tr = ev.target.closest('tr[data-id]');
    if (!tr) return;
    const aid = Number(tr.dataset.id), el = ev.target;
    if (el.classList.contains('chk')) {                      // _on_item
      if (el.checked) checked.add(aid); else checked.delete(aid);
      fillRow(aid); fetchCounts(); updLabel();
    } else if (el.classList.contains('plano')) {             // _on_combo
      tr.children[2].innerHTML = contagemHtml(Number(el.value));
      pintarTempo(tr);
      fetchCounts();
    } else if (el.classList.contains('dt')) {
      if (el.value) dtByAsset[aid] = el.value; else el.value = dtByAsset[aid] || '';   // o QDateTimeEdit nunca fica vazio
    } else if (el.classList.contains('tp')) {
      const m = lerTempo(el.value);                          // digitar é livre; o que não é horário volta ao que era
      el.value = m == null ? hhmm(minutosDe(segTempo(aid, planoDaLinha(tr)))) : hhmm(m);
    }
  });
  tbody.addEventListener('input', (ev) => {
    const tr = ev.target.closest('tr[data-id]');
    if (!tr) return;
    const aid = Number(tr.dataset.id), el = ev.target;
    if (el.classList.contains('dt') && el.value) dtByAsset[aid] = el.value;
    if (el.classList.contains('tp')) { const m = lerTempo(el.value); if (m != null) durByAsset[aid] = m * 60; }
  });
  tbody.addEventListener('keydown', (ev) => {
    if (!ev.target.classList.contains('tp')) return;
    const passos = {ArrowUp: 1, PageUp: 1, ArrowDown: -1, PageDown: -1}[ev.key];
    if (passos) { ev.preventDefault(); andar(ev.target, passos); }
  });
  tbody.addEventListener('click', (ev) => {
    const b = ev.target.closest('.tp-b');
    if (b) andar(b.closest('.pcm-tempo').querySelector('input.tp'), Number(b.dataset.passo));
  });

  // ── marcar (_marcar_todos / _marcar_com_plano): só as linhas da tabela; marcado fora dela continua marcado ──
  function marcarTodos(marcar) {
    linhas.forEach((a) => { if (marcar) checked.add(a.id); else checked.delete(a.id); });
    fillPlanos();
  }
  bAll.onclick = () => marcarTodos(true);
  bNone.onclick = () => marcarTodos(false);
  bComPlano.onclick = () => {
    if (!loadedFor.size) { hint.textContent = 'Carregue os planos primeiro (marque os ativos → Carregar planos).'; return; }
    const f = fam();
    linhas.forEach((a) => { if (temPlano(a.id, f)) checked.add(a.id); else checked.delete(a.id); });
    fillPlanos();
  };

  // ── "Sem plano de tarefas" (_on_sem_plano): família, Carregar e Só com plano inativos; aparece a descrição ──
  ckSem.onchange = () => {
    semPlano = ckSem.checked;
    cbFam.disabled = bPlanos.disabled = bComPlano.disabled = semPlano;
    famLbl.classList.toggle('desab', semPlano);
    descLbl.hidden = edDesc.hidden = !semPlano;
    refresh();
  };

  // ── carregar planos (_carregar_planos / _set_planos / _planos_err) ──
  bPlanos.onclick = async () => {
    const ids = [...checked];                                // TODOS os marcados, inclusive os que o filtro esconde
    avisoPlanos.hidden = true;
    if (!ids.length) { avisoPlanos.textContent = 'Marque ao menos um ativo primeiro.'; avisoPlanos.hidden = false; return; }
    bPlanos.disabled = true;
    const txt = 'buscando planos de ' + ids.length + ' ativo(s)…';
    hint.textContent = txt;
    try {
      const j = await pedir('/os/api/pcm/planos?ativos=' + ids.join(',') + '&visiveis=' + linhas.map((a) => a.id).join(',')
        + '&conhecidos=' + Object.keys(subt).join(','), null, txt);
      setPlanos(j, ids);
    } catch (e) { hint.textContent = '⚠ planos: ' + e.message; }
    finally { bPlanos.disabled = semPlano; }
  };
  function setPlanos(j, ids) {
    loadedFor = new Set(ids);
    planosByAsset = {};
    Object.keys(j.por_ativo || {}).forEach((k) => { planosByAsset[Number(k)] = j.por_ativo[k] || []; });
    Object.assign(subt, j.subt || {}); Object.assign(durPlano, j.dur || {});
    const fams = j.familias || [];
    // "(todas)" + as famílias; o combo volta para a PRIMEIRA família a cada carga, como no app
    cbFam.innerHTML = '<option value="">(todas)</option>' + fams.map(opcao).join('');
    cbFam.value = j.familia || '';
    hint.textContent = j.n_planos ? j.n_planos + ' plano(s) em ' + fams.length + ' família(s).' : 'Nenhum plano encontrado p/ os ativos marcados.';
    refresh();                                               // re-ordena com plano no topo + preenche
  }

  // ── data/hora em massa (_set_todas_data / _set_todas_hora / _avancar_mes): nas linhas que têm data ──
  function editores(fn) {
    tbody.querySelectorAll('tr[data-id] input.dt').forEach((inp) => {
      const aid = Number(inp.closest('tr').dataset.id), v = inp.value || dtByAsset[aid];
      if (!v) return;
      inp.value = dtByAsset[aid] = fn(v);
    });
  }
  // QDateTime.addMonths(1): o mesmo dia no mês seguinte; se o dia não existe lá (31/01), o último dia do mês (28/02)
  function maisUmMes(v) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(T.*)$/.exec(v);
    if (!m) return v;
    let y = Number(m[1]), mo = Number(m[2]) + 1;
    if (mo > 12) { mo = 1; y += 1; }
    const ultimo = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    return String(y).padStart(4, '0') + '-' + p2(mo) + '-' + p2(Math.min(Number(m[3]), ultimo)) + m[4];
  }
  $('b_data').onclick = () => { const d = bulkDate.value; if (d) editores((v) => d + v.slice(10)); };
  $('b_manha').onclick = () => editores((v) => v.slice(0, 10) + 'T07:00');
  $('b_tarde').onclick = () => editores((v) => v.slice(0, 10) + 'T13:00');
  $('b_mes').onclick = () => editores(maisUmMes);
  bulkDate.addEventListener('change', () => { if (bulkDate.value) ultimaData = bulkDate.value; else bulkDate.value = ultimaData; });

  // ── responsável (_carregar_resp / _set_resp / _resp_err) ──
  async function carregarResp(comCirculo) {
    cbResp.innerHTML = '<option value="">carregando…</option>';
    try {
      const url = '/os/api/responsaveis', op = {credentials: 'same-origin'};
      const r = comCirculo ? await OsCarga.buscar(url, op, 'Recarregando os responsáveis…') : await fetch(url, op);
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(apiErro(j, r));
      pessoas = j.pessoas || [];                             // já em ordem de nome, como o _set_resp
      cbResp.innerHTML = '<option value="">' + SEL + '</option>'
        + pessoas.map((p, i) => '<option value="' + i + '">' + esc(p.name || p.code || '?') + '</option>').join('');
    } catch (e) {
      pessoas = [];
      cbResp.innerHTML = '<option value="">⚠ falha — relogue e clique em ↻</option>';
      hint.textContent = '⚠ responsável: ' + e.message;
    }
  }
  bResp.onclick = () => carregarResp(true);
  const pessoa = () => (cbResp.value === '' ? null : (pessoas[Number(cbResp.value)] || null));

  // ── OS pai (OsPaiPicker): digitou → 300 ms → buscar_os_pai; escolher guarda o id; digitar de novo cancela a escolha ──
  let ospaiSel = null, ospaiTimer = null, ospaiSeq = 0;
  ospaiIn.addEventListener('input', () => { ospaiSel = null; clearTimeout(ospaiTimer); ospaiTimer = setTimeout(buscarOsPai, 300); });
  async function buscarOsPai() {
    const termo = ospaiIn.value.trim();
    if (!termo) return;                                      // _buscar: vazio não busca
    const meu = ++ospaiSeq;
    let lista = [];
    try { lista = (await pedir('/os/api/pcm/os-pai?termo=' + enc(termo), null, 'Buscando a OS pai…')).resultados || []; } catch (e) { lista = []; }
    if (meu !== ospaiSeq) return;
    ospaiLista.innerHTML = lista.map((r, i) => '<div class="pcm-ospai-item' + (i === 0 ? ' on' : '') + '" data-id="' + esc(r.id) + '">'
      + esc(r.folio || '') + (r.descricao ? ' — ' + esc(r.descricao) : '') + '</div>').join('');
    ospaiLista.hidden = !lista.length || document.activeElement !== ospaiIn;   // _preencher: abre se o campo tem o foco
  }
  function escolherOsPai(it) {                               // _on_pick
    ospaiSel = {id: Number(it.dataset.id)};
    ospaiIn.value = it.textContent;
    ospaiLista.hidden = true;
  }
  ospaiLista.addEventListener('mousedown', (ev) => {        // mousedown: o blur do campo chegaria antes do click
    const it = ev.target.closest('.pcm-ospai-item');
    if (it) { ev.preventDefault(); escolherOsPai(it); }
  });
  ospaiIn.addEventListener('keydown', (ev) => {
    if (ospaiLista.hidden) return;
    const itens = [...ospaiLista.querySelectorAll('.pcm-ospai-item')];
    let k = itens.findIndex((x) => x.classList.contains('on'));
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      k = Math.max(0, Math.min(itens.length - 1, k + (ev.key === 'ArrowDown' ? 1 : -1)));
      itens.forEach((x, i) => x.classList.toggle('on', i === k));
    } else if (ev.key === 'Enter' && itens[k]) { ev.preventDefault(); escolherOsPai(itens[k]); }
    else if (ev.key === 'Escape') ospaiLista.hidden = true;
  });
  ospaiIn.addEventListener('blur', () => setTimeout(() => { ospaiLista.hidden = true; }, 150));
  const idParent = () => (ospaiIn.value.trim() ? (ospaiSel ? ospaiSel.id : null) : null);   // OsPaiPicker.id_parent

  // ── criar: 1 OS com cada ativo marcado como tarefa (_criar / _criar_sem_plano / _criou / _err) ──
  function mostrar(msg, ruim, j) {
    res.hidden = false; res.classList.toggle('ruim', !!ruim); res.textContent = msg;
    if (j && j.ok && j.id_work_order) {                      // a OS criada, a um clique (o detalhe da web)
      const a = document.createElement('a');
      a.className = 'os-link pcm-abrir'; a.href = '/os/os/' + enc(j.id_work_order);
      a.textContent = 'Abrir a OS' + (j.folio ? ' nº ' + j.folio : '');
      res.appendChild(document.createTextNode('\n\n')); res.appendChild(a);
    }
    res.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }
  // a data de cada linha que vai virar tarefa: o campo da linha (é o que a pessoa vê)
  function dataDaLinha(aid) { const inp = linhaDe(aid) && linhaDe(aid).querySelector('input.dt'); return inp ? inp.value : null; }

  btn.onclick = () => { if (semPlano) criarSemPlano(); else criar(); };

  // O que o app deixa de fora SEM avisar (27/09): o ativo marcado que o filtro escondeu (ou que é de outra usina — a
  // marca sobrevive à troca) e, no caminho com plano, o marcado depois do último "Carregar planos". A OS continua saindo
  // igual à do app, com as linhas da tabela; só a confirmação passa a dizer quem não vai.
  function lista(itens) {
    return itens.slice(0, 10).map((a) => a.label || a.code || '?').join('\n- ') + (itens.length > 10 ? '\n- …' : '');
  }
  function avisoEscondidos() {
    const naTabela = new Set(linhas.map((a) => a.id));
    const fora = [...checked].filter((id) => !naTabela.has(id));
    if (!fora.length) return '';
    const conhecidos = ativos.filter((a) => fora.includes(a.id)), outros = fora.length - conhecidos.length;
    return '\n\nFicam de FORA (marcados, mas fora da tabela — limpe a busca ou o tipo para incluí-los):'
      + (conhecidos.length ? '\n- ' + lista(conhecidos) : '')
      + (outros ? '\n- ' + outros + ' ativo(s) marcado(s) em outra usina' : '');
  }

  function criar() {
    const sel = [], sem = [];
    linhas.forEach((a) => {
      if (!checked.has(a.id)) return;
      const idt = planoDaLinha(linhaDe(a.id));
      if (idt) {
        sel.push({asset_id: a.id, id_task: idt, event_date: dataDaLinha(a.id),
                  duracao: durByAsset[a.id] != null ? durByAsset[a.id] : null});   // o tempo da linha; null = o do plano
      } else if (loadedFor.has(a.id)) sem.push(a.label || a.code || '?');
    });
    if (!sel.length) { mostrar('Carregue os planos e marque ao menos um ativo com plano.', true); return; }
    const p = pessoa();
    if (!p || !p.id_personnel) { mostrar('Escolha o responsável.', true); return; }
    if (sel.some((s) => !s.event_date)) { mostrar('Data inválida.', true); return; }
    let aviso = '';
    if (sem.length) aviso = '\n\nFicam de FORA (sem plano nesta família):\n- ' + sem.slice(0, 10).join('\n- ') + (sem.length > 10 ? '\n- …' : '');
    const semCarga = linhas.filter((a) => checked.has(a.id) && !loadedFor.has(a.id));
    if (semCarga.length) aviso += '\n\nFicam de FORA (marcados depois de carregar os planos — clique em “Carregar planos” de novo):\n- ' + lista(semCarga);
    aviso += avisoEscondidos();
    if (!confirm('Vou criar UMA OS com ' + sel.length + ' tarefa(s) — uma por ativo marcado.' + aviso + '\n\nContinuar?')) return;
    enviar({sem_plano: false, selecoes: sel, responsavel: {id_personnel: p.id_personnel, name: p.name},
            descricao: '', note: obs.value.trim(), id_parent: idParent()}, sel.length);
  }

  function criarSemPlano() {
    const sel = linhas.filter((a) => checked.has(a.id)).map((a) => ({asset_id: a.id, event_date: dataDaLinha(a.id)}));
    if (!sel.length) { mostrar('Marque ao menos um ativo.', true); return; }
    const p = pessoa();
    if (!p || !p.id_personnel) { mostrar('Escolha o responsável.', true); return; }
    if (sel.some((s) => !s.event_date)) { mostrar('Data inválida.', true); return; }
    const desc = edDesc.value.trim();
    if (!confirm('Vou criar UMA OS com ' + sel.length + " tarefa(s) SEM plano — uma por ativo, subtarefa 'Procedimento'"
                 + (desc ? ' · descrição: ' + desc : '') + '.' + avisoEscondidos() + '\n\nContinuar?')) return;
    enviar({sem_plano: true, selecoes: sel, responsavel: {id_personnel: p.id_personnel, name: p.name},
            descricao: desc, note: obs.value.trim(), id_parent: idParent()}, sel.length);
  }

  async function enviar(corpo, n) {
    btn.disabled = true; res.hidden = true;
    hint.textContent = 'criando 1 OS com ' + n + ' tarefa(s)… (pode levar alguns segundos)';
    try {
      const r = await OsCarga.buscar('/os/api/pcm/criar', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(corpo), credentials: 'same-origin'}, 'Criando a OS no Fracttal…');
      const j = await r.json().catch(() => ({}));
      if (!r.ok) mostrar(apiErro(j, r), true);               // _err (e a recusa do servidor, que repete as do app)
      else mostrar(j.mensagem || '', !j.ok, j);              // _criou
    } catch (e) { mostrar(String(e), true); }
    finally { btn.disabled = false; hint.textContent = ''; }
  }

  // ── arranque (_fill_clientes → _on_cli; carregar_inicial → _carregar_resp) ──
  // o navegador devolve o que estava nos campos ao voltar para a página; a tela nasce limpa, como o diálogo do app
  cbCli.selectedIndex = 0; ckSem.checked = false; busca.value = ''; edDesc.value = ''; obs.value = ''; ospaiIn.value = '';
  if (!bulkDate.value) bulkDate.value = HOJE;
  cbCli.onchange = onCli;
  cbUsi.onchange = onUsi;
  cbTipo.onchange = refresh;
  busca.oninput = refresh;
  cbFam.onchange = refresh;                                  // re-ordena (com plano no topo) + re-preenche
  refresh();
  carregarResp(false);
})();

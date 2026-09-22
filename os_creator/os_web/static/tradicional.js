// os_creator/os_web/static/tradicional.js — o wizard "Tradicional" do app, no navegador. Mesma lógica: Step1 (cascata
// Cliente → Usina → Tipo → Ativos, seleção múltipla que persiste entre filtros, imagens por ativo, duas datas), Step2
// (descrição, observação, etiquetas, tipo/classificações/criticidade), Step3 (subtarefas, mínimo 1) e o Step 4
// ResponsavelDialog (responsável, "já realizada", agrupar, OS pai, Gerar N OS). Confirmação antes de criar.
(function () {
  const root = document.getElementById('trad');
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const enc = encodeURIComponent;
  const apiErro = (j, r) => (j && j.erro) ? (j.login ? j.erro + ' Entre de novo em /os/login.' : j.erro) : ('HTTP ' + r.status);
  const PASSOS = ['Ativo + Data', 'Detalhes da Tarefa', 'Sub tarefas', 'Responsável'];   // app.py::STEP_LABELS
  const CRIT_DEFAULT = root.dataset.critDefault;
  const LIMITE = 4 * 1024 * 1024;                                                          // MAX_CONTENT_LENGTH do app

  async function getJson(url) {
    const r = await fetch(url, {credentials: 'same-origin'});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(apiErro(j, r));
    return j;
  }

  // ── "Passo N de 4 · rótulo" + barra (MainWindow._go) ──
  const steplbl = $('steplbl'), prog = $('prog');
  function irPara(i, rolar) {
    steplbl.textContent = 'Passo ' + (i + 1) + ' de 4  ·  ' + PASSOS[i];
    prog.style.width = ((i + 1) * 25) + '%';
    const card = $('card' + (i + 1));
    if (card && rolar !== false) card.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  // ── barra "Clonar OS nº" → a tela de clonagem ──
  const cloneIn = $('clone_in');
  function clonar() { const n = (cloneIn.value || '').replace(/\D/g, ''); if (n) location.href = '/os/clonar?folio=' + enc(n); }
  $('b_clone').onclick = (e) => { e.preventDefault(); clonar(); };
  cloneIn.onkeydown = (e) => { if (e.key === 'Enter') clonar(); };

  // ═══ Passo 1 — Step1 ═══
  const cbCli = $('cb_cliente'), cbUsi = $('cb_usina'), cbTipo = $('cb_tipo'), busca = $('busca'), tbody = $('tbody'), hint = $('hint');
  const dtProg = $('dt_prog'), dtExec = $('dt_exec'), bNext1 = $('b_next1');
  let assets = [];                    // ativos da usina atual (Step1._assets, já filtrado por cliente/usina)
  const marcados = new Map();         // id -> ativo: persiste entre filtros E entre usinas (Step1._checked)
  // 10 em 10 (Levi, 22/09): so a EXIBICAO; o marcado continua valendo fora da tela
  const PAGINA = 10;
  let limite = PAGINA;
  // O RODAPE da tabela, o mesmo da Performance: quantos de quantos, quantos MARCADOS estao fora
  // da tela (cada um vira uma OS/solicitacao, e nao ve-los nao pode significar nao saber), e os
  // dois botoes. O flex vai num DIV dentro do <td>: no proprio <td> ele anularia o colspan.
  function rodapeMais(rows, vis, estaMarcado, colunas) {
    if (rows.length <= vis.length) return '';
    const fora = rows.slice(vis.length).filter(estaMarcado).length, faltam = rows.length - vis.length;
    return '<tr class="mais"><td colspan="' + colunas + '"><div class="mais-in">'
      + '<span class="os-ajuda">Mostrando ' + vis.length + ' de ' + rows.length + ' ativos'
      + (fora ? ' · <b>' + fora + ' marcado(s) fora da tela</b>' : '') + '</span>'
      + '<button type="button" class="os-btn secondary mini" data-mais="' + PAGINA + '">Mostrar mais ' + Math.min(PAGINA, faltam) + '</button>'
      + '<button type="button" class="os-btn secondary mini" data-mais="tudo">Mostrar todos (' + rows.length + ')</button>'
      + '</div></td></tr>';
  }

  const imgs = new Map();             // id -> [{file, nome, url}] (Step1._imgs — anexo por ativo)
  let progTocada = false;             // a data programada já foi editada à mão? (Step1._prog_tocada)

  function toLocal(d) { const p = (x) => (x < 10 ? '0' : '') + x; return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()); }
  function agoraLocal() { const d = new Date(); d.setSeconds(0, 0); return toLocal(d); }
  function amanhaLocal() { const d = new Date(); d.setDate(d.getDate() + 1); d.setSeconds(0, 0); return toLocal(d); }

  async function onCliente() {
    const cli = cbCli.value;
    cbUsi.innerHTML = '<option value="">— Selecione a usina —</option>'; cbUsi.disabled = true;
    if (cli) {
      try {
        const j = await getJson('/os/api/tradicional/catalogo?cliente=' + enc(cli));
        cbUsi.innerHTML += (j.usinas || []).map((u) => '<option value="' + esc(u) + '">' + esc(u) + '</option>').join('');
        cbUsi.disabled = !(j.usinas || []).length;
      } catch (e) { hint.textContent = '⚠ ' + e.message; }
    }
    await onUsina();
  }

  async function onUsina() {
    const cli = cbCli.value, usi = cbUsi.value;
    cbTipo.innerHTML = '<option value="">Todos os tipos</option>'; cbTipo.disabled = true; assets = [];
    if (usi) {
      hint.textContent = 'carregando ativos…';
      try {
        const j = await getJson('/os/api/tradicional/catalogo?cliente=' + enc(cli) + '&usina=' + enc(usi));
        cbTipo.innerHTML += (j.tipos || []).map((t) => '<option value="' + esc(t) + '">' + esc(t) + '</option>').join('');
        cbTipo.disabled = !(j.tipos || []).length;
        assets = j.ativos || []; limite = PAGINA;
      } catch (e) { hint.textContent = '⚠ ' + e.message; return; }
    }
    refreshAtivos();
  }

  function refreshAtivos() {                                   // Step1._refresh_ativos
    const usi = cbUsi.value, tipo = cbTipo.value, txt = (busca.value || '').trim().toLowerCase();
    if (!usi) {
      tbody.innerHTML = '<tr class="vazio"><td colspan="2">Selecione cliente e usina para ver os ativos.</td></tr>';
      atualizaHint('Selecione cliente e usina para ver os ativos.'); return;
    }
    const rows = assets.filter((a) => a.tipo && (!tipo || a.tipo === tipo) && (!txt || String(a.label || '').toLowerCase().includes(txt)));
    const vis = rows.slice(0, limite);
    tbody.innerHTML = vis.map((a) => {
      const n = (imgs.get(a.id) || []).length;
      return '<tr data-id="' + a.id + '"><td><label class="trad-chk"><input type="checkbox" class="chk"' + (marcados.has(a.id) ? ' checked' : '') +
        '> <span>' + esc(a.label) + '</span></label></td><td class="c-anx"><button type="button" class="os-btn secondary mini anx' + (n ? ' tem' : '') +
        '">' + (n ? n + ' imagem(ns)' : 'Anexar') + '</button></td></tr>';
    }).join('') + rodapeMais(rows, vis, (a) => marcados.has(a.id), 2);
    atualizaHint(rows.length + ' ativo(s) nesta seleção');
  }

  function atualizaHint(base) {                                // Step1._atualiza_hint
    const n = marcados.size;
    hint.textContent = n ? base + '  ·  ' + n + ' marcado(s)' : base;
    bNext1.textContent = n ? 'Próximo (' + n + ') ›››' : 'Próximo ›››';
    bNext1.disabled = !n;
  }

  tbody.addEventListener('change', (ev) => {
    if (!ev.target.classList.contains('chk')) return;
    const id = Number(ev.target.closest('tr').dataset.id), a = assets.find((x) => x.id === id);
    if (ev.target.checked && a) marcados.set(id, a); else marcados.delete(id);
    atualizaHint(hint.textContent.split('  ·')[0]);
  });
  tbody.addEventListener('click', (ev) => {
    const mais = ev.target.dataset && ev.target.dataset.mais;
    if (mais) { limite = mais === 'tudo' ? Infinity : limite + PAGINA; refreshAtivos(); return; }
    if (!ev.target.classList.contains('anx')) return;
    const id = Number(ev.target.closest('tr').dataset.id), a = assets.find((x) => x.id === id);
    if (a) abrirImagens(a);
  });
  cbCli.onchange = onCliente;
  cbUsi.onchange = onUsina;
  cbTipo.onchange = () => { limite = PAGINA; refreshAtivos(); };
  busca.oninput = () => { limite = PAGINA; refreshAtivos(); };

  // as duas datas: incidente travado no passado (teto renovado por minuto) e programada = amanhã EM RELAÇÃO A AGORA
  // enquanto ninguém a editar à mão (Step1._sincronizar_prog — somar um dia ao incidente agendaria no passado)
  function sincronizarProg() { if (!progTocada) dtExec.value = amanhaLocal(); }
  $('b_agora').onclick = () => { dtProg.value = agoraLocal(); sincronizarProg(); };
  dtProg.addEventListener('input', sincronizarProg);
  dtExec.addEventListener('input', () => { progTocada = true; });
  setInterval(() => { dtProg.max = agoraLocal(); }, 60000);

  $('b_reload').onclick = async () => {                       // ↻ → load_assets_cached(force=True)
    hint.textContent = 'Recarregando ativos do Fracttal…';
    try {
      const j = await getJson('/os/api/tradicional/catalogo?recarregar=1');
      const cur = cbCli.value;
      cbCli.innerHTML = '<option value="">— Selecione o cliente —</option>' + (j.clientes || []).map((c) => '<option value="' + esc(c) + '"' + (c === cur ? ' selected' : '') + '>' + esc(c) + '</option>').join('');
      await onCliente();
    } catch (e) { hint.textContent = '⚠ ' + e.message; }
  };
  bNext1.onclick = () => irPara(1);

  // ═══ Passo 2 — Step2 + TipoTarefaBox ═══
  const desc = $('desc'), obs = $('obs'), etiqBusca = $('etiq_busca'), etiqLista = $('etiq_lista');
  const cbTipoTarefa = $('cb_tipo_tarefa'), cbCrit = $('cb_crit'), cbC1 = $('cb_c1'), cbC2 = $('cb_c2'), bNext2 = $('b_next2');
  let labels = [];                    // catálogo [{id, description, color}]
  const etiqMarcadas = new Set();     // ids marcados (persistem ao filtrar)

  async function carregarEtiquetas() {
    try { labels = (await getJson('/os/api/tradicional/etiquetas')).etiquetas || []; } catch (e) { labels = []; }
    etiqBusca.placeholder = labels.length ? 'Filtrar etiquetas…' : '⚠ etiquetas não carregaram';
    filtrarEtiq();
  }
  function filtrarEtiq() {
    const txt = (etiqBusca.value || '').trim().toLowerCase();
    etiqLista.innerHTML = labels.filter((l) => !txt || String(l.description || '').toLowerCase().includes(txt))
      .map((l) => '<label class="trad-item"><input type="checkbox" value="' + esc(l.id) + '"' + (etiqMarcadas.has(l.id) ? ' checked' : '') + '> ' + esc(l.description) + '</label>').join('');
  }
  etiqBusca.oninput = filtrarEtiq;
  etiqLista.addEventListener('change', (ev) => {
    if (ev.target.type !== 'checkbox') return;
    const id = Number(ev.target.value);
    if (ev.target.checked) etiqMarcadas.add(id); else etiqMarcadas.delete(id);
  });

  function fill(cb, itens, comNenhuma) {
    cb.innerHTML = (comNenhuma ? '<option value="">— nenhuma —</option>' : '') + (itens || []).map((it) => '<option value="' + esc(it.id) + '">' + esc(it.description || '?') + '</option>').join('');
  }
  async function carregarTipos() {                            // TipoTarefaBox._carregar → api.get_tipos_classif
    try {
      const j = await getJson('/os/api/tradicional/tipos');
      fill(cbTipoTarefa, j.tipos, false); fill(cbC1, j.c1, true); fill(cbC2, j.c2, true);
    } catch (e) { cbTipoTarefa.innerHTML = '<option value="">⚠ falha ao carregar — relogue</option>'; }
  }
  const tipoPronto = () => !!cbTipoTarefa.value;              // TipoTarefaBox.is_ready
  desc.oninput = () => { bNext2.disabled = !desc.value.trim(); };
  $('b_back2').onclick = () => irPara(0);
  bNext2.onclick = () => { if (desc.value.trim()) irPara(2); };

  // ═══ Passo 3 — Step3 ═══
  const subsEl = $('subs'), bDone = $('b_done'), res = $('resultado');
  function addSub(text) {
    const row = document.createElement('div'); row.className = 'trad-sub';
    row.innerHTML = '<input type="text" class="sub" value="' + esc(text || '') + '"><button type="button" class="os-btn secondary trad-x" title="Remover">✕</button>';
    subsEl.appendChild(row); renum(); updSubs();
  }
  function renum() { subsEl.querySelectorAll('input.sub').forEach((i, k) => { i.placeholder = 'Descrição da sub tarefa ' + (k + 1); }); }
  function subtarefas() { return [...subsEl.querySelectorAll('input.sub')].map((i) => i.value.trim()).filter(Boolean); }
  function updSubs() { bDone.disabled = !subtarefas().length; }
  subsEl.addEventListener('click', (ev) => {
    if (!ev.target.classList.contains('trad-x')) return;
    if (subsEl.children.length <= 1) return;                   // mantém o mínimo de 1
    ev.target.closest('.trad-sub').remove(); renum(); updSubs();
  });
  subsEl.addEventListener('input', updSubs);
  $('b_add_sub').onclick = () => addSub('');
  $('b_back3').onclick = () => irPara(1);

  function mostrarResultado(msg, ruim) {
    res.hidden = false; res.classList.toggle('ruim', !!ruim); res.textContent = msg;
    res.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }

  bDone.onclick = () => {                                     // MainWindow._gerar_os
    if (!marcados.size) { mostrarResultado('Marque ao menos um ativo no Passo 1.', true); irPara(0); return; }
    if (!tipoPronto()) { mostrarResultado('O tipo de tarefa ainda não carregou (ou a sessão expirou). Aguarde um instante ou relogue antes de gerar.', true); irPara(1); return; }
    if (!desc.value.trim()) { mostrarResultado('Preencha a Descrição da tarefa no Passo 2.', true); irPara(1); return; }
    if (!subtarefas().length) return;
    abrirResponsavel();
  };

  // ═══ Passo 4 — ResponsavelDialog ═══
  const modal = $('modal_resp'), respBusca = $('resp_busca'), respLista = $('resp_lista'), bGerar = $('b_gerar'), bCancel = $('b_cancel');
  const ckFin = $('ck_fin'), finpanel = $('finpanel'), finIni = $('fin_ini'), finFim = $('fin_fim'), finResp = $('fin_resp');
  const ckAgrupar = $('ck_agrupar'), wAgrupar = $('w_agrupar'), ospaiIn = $('ospai_in'), ospaiLista = $('ospai_lista'), respErro = $('resp_erro');
  let pessoas = null, pessoaSel = null, ospaiSel = null, ospaiTimer = null;

  function erroModal(m) { respErro.hidden = !m; respErro.textContent = m ? '⚠ ' + m : ''; }

  async function abrirResponsavel() {
    const n = marcados.size;
    $('resp_titulo').innerHTML = '<b>' + n + ' OS</b> a gerar — escolha o <b>responsável</b> <small>(obrigatório na criação)</small>:';
    bGerar.textContent = n > 1 ? 'Gerar ' + n + ' OS' : 'Gerar OS'; bGerar.disabled = true; pessoaSel = null;
    wAgrupar.hidden = !(n > 1); ckAgrupar.checked = false; $('fin').hidden = false;     // agrupar só com mais de um ativo
    ckFin.checked = false; finpanel.hidden = true;
    document.querySelector('input[name=fin_dest][value=final]').checked = true;          // default Finalizados
    finIni.value = dtProg.value; finFim.value = dtProg.value;                            // data inicial = incidente do Passo 1
    finResp.innerHTML = subtarefas().map(() => '').length
      ? subtarefas().map((s) => '<div class="trad-sub-lbl">' + esc(s) + '</div><input type="text" class="resp" placeholder="Resposta…">').join('') : '';
    ospaiIn.value = ''; ospaiSel = null; ospaiLista.hidden = true; erroModal('');
    modal.hidden = false; document.body.classList.add('os-modal-aberto');
    irPara(3, false);
    if (!pessoas) await carregarPessoas(); else filtrarPessoas();
    respBusca.focus();
  }
  function fecharModal() {
    modal.hidden = true; document.body.classList.remove('os-modal-aberto');
    irPara(2, false);
  }
  async function carregarPessoas() {                          // ResponsavelDialog._carregar → api.get_responsaveis
    respBusca.placeholder = 'carregando responsáveis…';
    try {
      pessoas = (await getJson('/os/api/responsaveis')).pessoas || [];
      respBusca.placeholder = 'Filtrar responsável…';
    } catch (e) { pessoas = null; respBusca.placeholder = '⚠ ' + e.message; }
    filtrarPessoas();
  }
  function filtrarPessoas() {
    const txt = (respBusca.value || '').trim().toLowerCase();
    respLista.innerHTML = (pessoas || []).filter((p) => !txt || String(p.name || '').toLowerCase().includes(txt))
      .map((p) => '<div class="trad-pessoa' + (pessoaSel && pessoaSel.id_personnel === p.id_personnel ? ' on' : '') + '" data-id="' + esc(p.id_personnel) + '">' + esc(p.name) + '</div>').join('');
  }
  respBusca.oninput = filtrarPessoas;
  respLista.addEventListener('click', (ev) => {
    const el = ev.target.closest('.trad-pessoa'); if (!el) return;
    pessoaSel = (pessoas || []).find((p) => String(p.id_personnel) === el.dataset.id) || null;
    filtrarPessoas(); bGerar.disabled = !pessoaSel;
  });
  respLista.addEventListener('dblclick', (ev) => { if (ev.target.closest('.trad-pessoa') && pessoaSel) gerar(); });   // duplo clique gera
  ckFin.onchange = () => { finpanel.hidden = !ckFin.checked; };
  ckAgrupar.onchange = () => {                                // _on_agrupar: agrupar e "já realizada" não combinam
    $('fin').hidden = ckAgrupar.checked;
    if (ckAgrupar.checked) { ckFin.checked = false; finpanel.hidden = true; }
  };

  // OS pai (OsPaiPicker): digitou → 300 ms → buscar_os_pai; escolher guarda o id; digitar de novo cancela a escolha
  ospaiIn.addEventListener('input', () => { ospaiSel = null; clearTimeout(ospaiTimer); ospaiTimer = setTimeout(buscarOsPai, 300); });
  async function buscarOsPai() {
    const termo = ospaiIn.value.trim();
    if (!termo) { ospaiLista.hidden = true; return; }
    let lista = [];
    try { lista = (await getJson('/os/api/tradicional/os-pai?q=' + enc(termo))).resultados || []; } catch (e) { lista = []; }
    ospaiLista.innerHTML = lista.map((r) => '<div class="trad-ospai-item" data-id="' + esc(r.id) + '" data-folio="' + esc(r.folio) + '">' + esc(r.folio) + (r.descricao ? ' — ' + esc(r.descricao) : '') + '</div>').join('');
    ospaiLista.hidden = !lista.length;
  }
  ospaiLista.addEventListener('click', (ev) => {
    const it = ev.target.closest('.trad-ospai-item'); if (!it) return;
    ospaiSel = {id: Number(it.dataset.id), folio: it.dataset.folio};
    ospaiIn.value = it.textContent; ospaiLista.hidden = true;
  });

  async function gerar() {                                    // ResponsavelDialog._gerar
    if (!pessoaSel) return;
    const ativos = [...marcados.values()];
    const agrupar = ativos.length > 1 && ckAgrupar.checked;
    let finalizar = null;
    if (ckFin.checked && !agrupar) {
      if (finIni.value && finFim.value && finFim.value < finIni.value) { erroModal('A Data final não pode ser anterior à Data inicial.'); return; }
      finalizar = {to_in_review: document.querySelector('input[name=fin_dest]:checked').value === 'verif', ini: finIni.value, fim: finFim.value,
                   respostas: [...finResp.querySelectorAll('input.resp')].map((i) => i.value.trim())};
    }
    const opt = (cb) => (cb.selectedOptions[0] && cb.value) ? cb.selectedOptions[0].textContent : '';
    const payload = {
      ativos: ativos.map((a) => a.id), desc: desc.value.trim(), obs: obs.value.trim(),
      tipo: {id_main: cbTipoTarefa.value || null, desc_main: opt(cbTipoTarefa), id_priorities: cbCrit.value,
             id_c1: cbC1.value || null, desc_c1: opt(cbC1), id_c2: cbC2.value || null, desc_c2: opt(cbC2)},
      etiquetas: labels.filter((l) => etiqMarcadas.has(l.id)).map((l) => ({id: l.id, description: l.description})),
      subs: subtarefas(), event: dtProg.value, prog: dtExec.value,
      responsavel: {id_personnel: pessoaSel.id_personnel, name: pessoaSel.name, code: pessoaSel.code},
      os_pai: ospaiSel, agrupar: agrupar, finalizar: finalizar,
    };
    let total = 0; ativos.forEach((a) => (imgs.get(a.id) || []).forEach((im) => { total += im.file.size; }));
    if (total > LIMITE) { erroModal('As imagens somam ' + (total / 1048576).toFixed(1) + ' MB; o limite por envio é 4 MB. Remova algumas imagens.'); return; }
    const frase = agrupar ? 'Vou criar 1 OS com ' + ativos.length + ' tarefas (uma por ativo marcado), responsável ' + pessoaSel.name + '.'
                          : 'Vou criar ' + ativos.length + ' OS — uma por ativo marcado —, responsável ' + pessoaSel.name + '.';
    const extra = finalizar ? '\nA OS nasce já realizada (' + (finalizar.to_in_review ? 'Verificação' : 'Finalizados') + ').' : '';
    if (!confirm(frase + extra + (ospaiSel ? '\nOS pai: ' + ospaiSel.folio + '.' : '') + '\n\nContinuar?')) return;
    bGerar.disabled = true; bCancel.disabled = true; erroModal('');
    respBusca.placeholder = agrupar ? 'Gerando 1 OS com ' + ativos.length + ' tarefas…' : 'Gerando ' + ativos.length + ' OS (resp.: ' + pessoaSel.name + ')…';
    try {
      let r;
      if (total > 0) {                                        // imagens → multipart: bytes, como Step1.selected_images()
        const fd = new FormData(); fd.append('payload', JSON.stringify(payload));
        ativos.forEach((a) => (imgs.get(a.id) || []).forEach((im) => fd.append('imagens:' + a.code, im.file, im.nome)));
        r = await fetch('/os/api/tradicional/criar', {method: 'POST', body: fd, credentials: 'same-origin'});
      } else {
        r = await fetch('/os/api/tradicional/criar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), credentials: 'same-origin'});
      }
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { erroModal(apiErro(j, r)); return; }        // erro fica no diálogo, como o QMessageBox.critical do app
      fecharModal();
      mostrarResultado(j.mensagem || '', !j.ok);
      if (j.ok) novaOs();                                     // _final → nova_os(): volta pronto para outra OS
    } catch (e) { erroModal(String(e)); }
    finally { bGerar.disabled = !pessoaSel; bCancel.disabled = false; if (pessoas) respBusca.placeholder = 'Filtrar responsável…'; }
  }
  bGerar.onclick = gerar;
  modal.addEventListener('click', (ev) => { if (ev.target.hasAttribute('data-fechar') && !bCancel.disabled) fecharModal(); });

  function novaOs() {                                         // MainWindow.nova_os: reset dos três passos
    marcados.clear();
    imgs.forEach((lista) => lista.forEach((im) => { if (im.url) URL.revokeObjectURL(im.url); })); imgs.clear();
    dtProg.value = agoraLocal(); progTocada = false; dtExec.value = amanhaLocal();
    busca.value = ''; cbCli.value = ''; onCliente();
    desc.value = ''; obs.value = ''; bNext2.disabled = true;
    etiqMarcadas.clear(); etiqBusca.value = ''; filtrarEtiq();
    cbCrit.value = CRIT_DEFAULT; if (cbC1.options.length) cbC1.selectedIndex = 0; if (cbC2.options.length) cbC2.selectedIndex = 0;
    if (cbTipoTarefa.options.length) cbTipoTarefa.selectedIndex = 0;
    subsEl.innerHTML = ''; addSub('');
    irPara(0);
  }

  // ═══ Imagens de um ativo (PerfAnexoDialog) ═══
  const modalImg = $('modal_img'), imgGrid = $('img_grid'), imgFile = $('img_file'), imgErro = $('img_erro');
  let imgAtivo = null;
  function abrirImagens(a) {
    imgAtivo = a; imgErro.hidden = true;
    $('img_titulo').innerHTML = 'Anexar imagens à OS de <b>' + esc(a.label || a.code || 'ativo') + '</b>';
    renderImgs(); modalImg.hidden = false; document.body.classList.add('os-modal-aberto');
  }
  function fecharImagens() {
    modalImg.hidden = true; imgAtivo = null;
    if (modal.hidden) document.body.classList.remove('os-modal-aberto');
    refreshAtivos();                                          // atualiza o rótulo do botão (N imagem(ns))
  }
  function renderImgs() {
    const lista = imgs.get(imgAtivo.id) || [];
    $('img_vazio').hidden = !!lista.length;
    imgGrid.innerHTML = lista.map((im, k) => '<div class="trad-img-cell"><img src="' + im.url + '" alt="">' +
      '<input type="text" class="trad-img-nome" value="' + esc(im.nome) + '" data-k="' + k + '" title="Clique para editar o nome do arquivo">' +
      '<button type="button" class="os-btn secondary mini" data-rm="' + k + '">Remover</button></div>').join('');
  }
  function addImg(file, nome) {
    const lista = imgs.get(imgAtivo.id) || [];
    lista.push({file: file, nome: nome, url: URL.createObjectURL(file)}); imgs.set(imgAtivo.id, lista); renderImgs();
  }
  $('b_img_add').onclick = () => imgFile.click();
  imgFile.onchange = () => { [...imgFile.files].forEach((f) => addImg(f, f.name)); imgFile.value = ''; };
  async function colar(files) {
    let arquivos = files ? [...files].filter((f) => f.type.startsWith('image/')) : [];
    if (!arquivos.length && navigator.clipboard && navigator.clipboard.read) {
      try {
        for (const it of await navigator.clipboard.read()) {
          const t = it.types.find((x) => x.startsWith('image/'));
          if (t) arquivos.push(await it.getType(t));
        }
      } catch (e) { /* sem permissão de leitura: cai no aviso abaixo */ }
    }
    if (!arquivos.length) { imgErro.hidden = false; imgErro.textContent = 'Não há imagem na área de transferência (copie uma captura de tela primeiro).'; return; }
    imgErro.hidden = true;
    const n = (imgs.get(imgAtivo.id) || []).filter((x) => String(x.nome || '').startsWith('captura')).length;
    arquivos.forEach((b, i) => addImg(b, 'captura_' + (n + i + 1) + '.png'));
  }
  $('b_img_paste').onclick = () => colar(null);
  document.addEventListener('paste', (ev) => {
    if (modalImg.hidden || !imgAtivo) return;
    const files = ev.clipboardData && ev.clipboardData.files;
    if (files && files.length) { ev.preventDefault(); colar(files); }
  });
  imgGrid.addEventListener('click', (ev) => {
    const k = ev.target.dataset.rm; if (k === undefined) return;
    const lista = imgs.get(imgAtivo.id) || [], tirada = lista.splice(Number(k), 1)[0];
    if (tirada && tirada.url) URL.revokeObjectURL(tirada.url);
    renderImgs();
  });
  imgGrid.addEventListener('change', (ev) => {
    if (!ev.target.classList.contains('trad-img-nome')) return;
    const lista = imgs.get(imgAtivo.id) || [], k = Number(ev.target.dataset.k), novo = ev.target.value.trim();
    if (lista[k] && novo) lista[k].nome = novo;
  });
  modalImg.addEventListener('click', (ev) => { if (ev.target.hasAttribute('data-fechar-img')) fecharImagens(); });
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape') return;
    if (!modalImg.hidden) fecharImagens(); else if (!modal.hidden && !bCancel.disabled) fecharModal();
  });

  // arranque
  addSub('');
  irPara(0, false);
  atualizaHint('Selecione cliente e usina para ver os ativos.');
  carregarEtiquetas();
  carregarTipos();
})();

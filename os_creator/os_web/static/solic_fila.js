/* os_creator/os_web/static/solic_fila.js — a Fila do PCM do app na web (`steps/solic_pcm.py::_Fila`; Levi, 13/10/2026:
   "Fila do PCM não está levando para a fila do PCM, referência é a fila do app desktop").

   A lista das que aguardam aprovação à esquerda; à direita a ficha da escolhida, com as regras do app:
   - o TÍTULO sai no padrão do tema ("[Usina][Ativo] - Motivo") e o que o supervisor escreveu aparece riscado; clicar
     edita, e o título escrito à mão não é trocado quando o tema muda (`_titulo_manual`);
   - a OBSERVAÇÃO mostra só o relato; o bloco [PCM] volta intacto ao gravar, o que acontece ao sair do campo e só se
     mudou (`_gravar_obs`);
   - o TÉCNICO sugerido vem pré-escolhido pelo nome; a DATA é a pretendida pelo supervisor (não vai para a OS, como no app);
   - as ETIQUETAS do tema entram marcadas "(tema)" e saem só nesta solicitação; tema sem a lista cai na regra antiga da
     PERFORMANCE — tracker, ETM e garantia (`_CardEtiquetas.aplicar_regra`);
   - CLASSIFICAÇÃO 1 = "Programada" e 2 = a disciplina do tema, só em campo vazio (`_sugerir_classif`);
   - as SUBTAREFAS são as do bloco (o supervisor pode tê-las editado) ou as do tema, editáveis; trocar o tema traz as
     dele (a lista editada só sai com a pessoa dizendo que sim);
   - APROVAR cria a OS e passa para a próxima; MUDAR STATUS e DEVOLVER pedem o motivo; a que já saiu da fila (aberta pelo
     Painel) fica só para ler. */
(function () {
  'use strict';
  var SP = window.SolicPcm, esc = SP.esc;
  function $(id) { return document.getElementById(id); }
  var D = JSON.parse($('fl_dados').textContent || '{}');
  var itens = D.fichas || [], leitura = String(D.leitura || ''), TEMAS = D.temas || [], ETQ = D.etiquetas || [];
  var PERF = String(D.etiqueta_perf || 'PERFORMANCE').toUpperCase();
  var atual = null, tituloManual = false, subsDoBloco = false, obsOriginal = '', expandida = false;
  var etq = [], doTema = new Set(), tirados = new Set(), paiSel = null, paiRelogio = null, paiSeq = 0;

  var lista = $('fl_lista'), cont = $('fl_cont'), nada = $('fl_nada'), ficha = $('fl_ficha'), titulo = $('fl_titulo'),
      tituloEd = $('fl_titulo_ed'), orig = $('fl_orig'), obs = $('fl_obs'), ver = $('fl_ver'), resp = $('fl_resp'),
      chips = $('fl_chips'), etqAdd = $('fl_etq_add'), tipo = $('fl_tipo'), c1 = $('fl_c1'), c2 = $('fl_c2'),
      classif = $('fl_classif'), tema = $('fl_tema'), pai = $('fl_pai'), paiLista = $('fl_pai_lista'),
      aprovar = $('fl_aprovar'), devolver = $('fl_devolver'), bStatus = $('fl_status'), hint = $('fl_hint'),
      modal = $('fl_modal'), mT = $('fl_m_t'), mSt = $('fl_m_st'), mMot = $('fl_m_mot'), mOk = $('fl_m_ok');

  function up(t) { return String(t == null ? '' : t).trim().toUpperCase(); }
  function opcoes(lista_, vazio) {
    return (vazio !== undefined ? '<option value="">' + esc(vazio) + '</option>' : '')
      + lista_.map(function (o) { return '<option value="' + esc(o.v) + '">' + esc(o.r) + '</option>'; }).join('');
  }
  function temOpcao(sel, v) { return Array.prototype.some.call(sel.options, function (o) { return o.value === v; }); }
  function temaDe(chave) { return TEMAS.filter(function (t) { return t.chave === chave; })[0] || null; }
  function soLeitura() { return !atual || String(atual.id) === leitura; }
  function pill(st, cor) {
    return '<span class="spc-pill"' + (cor ? ' style="color:' + esc(cor) + '"' : '') + '>' + esc(st) + '</span>';
  }

  // ── os combos que não mudam de uma solicitação para outra ──
  resp.innerHTML = opcoes((D.pessoas || []).map(function (p) { return {v: p.id, r: p.nome}; }), '— selecione —');
  var tipos = (D.tipos || []).length ? D.tipos : [D.tipo_padrao];
  tipo.innerHTML = opcoes(tipos.map(function (n) { return {v: n, r: n}; }));
  c1.innerHTML = opcoes((D.cl1 || []).map(function (n) { return {v: n, r: n}; }), D.nenhuma);
  c2.innerHTML = opcoes((D.cl2 || []).map(function (n) { return {v: n, r: n}; }), D.nenhuma);
  tema.innerHTML = opcoes(TEMAS.map(function (t) { return {v: t.chave, r: t.nome}; }), '— sem tema —');
  mSt.innerHTML = opcoes((D.status || []).map(function (s) { return {v: s.cod, r: s.rot}; }));
  devolver.hidden = !temOpcao(mSt, 'AGAIN_REQUEST_TODO');
  var editor = SP.editorSubs($('fl_subs'), {tipos: D.tipos_sub,
    vazio: 'Sem tema: a OS nasce com as 3 subtarefas da base. Dá para aprovar assim, e dá para acrescentar o que faltar.'});

  // ── a lista da esquerda ──
  function contador() {
    var vivas = itens.filter(function (f) { return String(f.id) !== leitura; });
    var hoje = vivas.filter(function (f) { return f.hoje; }).length;
    cont.innerHTML = '<b class="spc-verde">' + vivas.length + '</b> aguardando' + (hoje ? ' · <b>' + hoje + '</b> chegaram hoje' : '');
  }
  function pintarLista() {
    lista.innerHTML = itens.map(function (f, i) {
      var t = temaDe(f.tema), chip = f.tema ? (t ? t.nome : f.tema) : 'sem tema';
      return '<div class="spc-cel' + (f === atual ? ' on' : '') + (String(f.id) === leitura ? ' leitura' : '')
        + '" role="option" tabindex="0" aria-selected="' + (f === atual) + '" data-i="' + i + '" title="Aberta em ' + esc(f.aberta) + '">'
        + '<span class="spc-cel-topo"><b class="spc-num">Nº ' + esc(f.id) + '</b>' + pill(f.status, f.cor) + '</span>'
        + '<span class="spc-cel-usina">' + esc(f.usina) + '</span>'
        + '<span class="spc-cel-ativo">' + esc(f.ativo) + '</span>'
        + '<span class="spc-cel-quem">' + esc(f.solicitante) + ' · ' + esc(f.quando) + '</span>'
        + '<span class="spc-chip' + (f.tema ? ' sim' : '') + '" title="' + esc(chip) + '">' + esc(chip) + '</span></div>';
    }).join('') || '<p class="spc-vazio">Nenhuma solicitação aguardando o PCM.</p>';
    contador();
  }
  lista.addEventListener('click', function (e) {
    var c = e.target.closest('.spc-cel'); if (c) selecionar(itens[Number(c.dataset.i)]);
  });
  lista.addEventListener('keydown', function (e) {
    var i = itens.indexOf(atual);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      var j = Math.max(0, Math.min(itens.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
      if (itens[j] && j !== i) { selecionar(itens[j]); var c = lista.querySelector('.spc-cel.on'); if (c) c.focus(); }
    } else if (e.key === 'Enter' || e.key === ' ') {
      var cel = e.target.closest('.spc-cel'); if (cel) { e.preventDefault(); selecionar(itens[Number(cel.dataset.i)]); }
    }
  });

  // ── a ficha ──
  function tituloDoTema() {
    var t = temaDe(tema.value);
    if (!t || !atual) return atual ? (atual.titulo_orig || '') : '';
    var partes = [String(atual.usina || '').trim(), atual.ativo_limpo].filter(Boolean)
      .map(function (p) { return '[' + p + ']'; }).join('');
    return partes ? (partes + ' - ' + t.motivo).replace(/^[\s-]+|[\s-]+$/g, '') : t.motivo;
  }
  function pintarOrig() {
    var f = atual, novo = (titulo.textContent || '').trim(), h = '';
    if (tema.value && !tituloManual && novo && novo !== f.titulo_orig) {
      h = 'o supervisor escreveu: <s>' + esc(f.titulo_orig) + '</s> · título reescrito no padrão';
    }
    if (soLeitura() && f.os_folio) h += (h ? ' · ' : '') + 'virou a OS ' + esc(f.os_folio);
    orig.innerHTML = h;
  }
  function preSelecionar(nome) {
    // o técnico que o SUPERVISOR sugeriu vira o responsável da OS; o nome que não está no cadastro aparece, não some
    var alvo = String(nome || '').trim().toLowerCase(), achou = '';
    for (var i = 0; alvo && i < resp.options.length; i++) {
      if (resp.options[i].value && resp.options[i].text.trim().toLowerCase() === alvo) { achou = resp.options[i].value; break; }
    }
    resp.value = achou;
    var s = $('fl_sug_tec');
    s.hidden = !(alvo && !achou);
    s.textContent = alvo && !achou ? 'o supervisor sugeriu ' + nome + ' (não está na lista de técnicos)' : '';
  }
  function revisarVer() {
    ver.hidden = !(expandida || obs.scrollHeight > obs.clientHeight + 2);
    ver.textContent = expandida ? 'ver menos' : 'ver inteira';
  }
  function habilitar(on) {
    [tema, resp, tipo, c1, c2, etqAdd, pai, aprovar, devolver, bStatus].forEach(function (el) { el.disabled = !on; });
    editor.editavel(on);
    titulo.classList.toggle('travado', !on);
  }
  function selecionar(f) {
    if (!tituloEd.hidden) fecharTitulo();
    if (!obs.readOnly) obs.blur();
    atual = f || null;
    pintarLista();
    nada.hidden = !!atual; ficha.hidden = !atual;
    if (!atual) { habilitar(false); return; }
    var so = soLeitura();
    tituloManual = false; subsDoBloco = !!f.subs_do_bloco;
    tema.value = temaDe(f.tema) ? f.tema : '';
    $('fl_sug').hidden = !f.tema;
    titulo.textContent = f.titulo || f.titulo_orig || '—';
    $('fl_usina').textContent = f.usina; $('fl_solic').textContent = f.solicitante; $('fl_ativo').textContent = f.ativo;
    $('fl_ativo_aviso').hidden = f.ativo_ok || so;
    $('fl_recarregar').href = '/os/solicitacao/atualizar?sel=' + encodeURIComponent(f.id);
    obs.value = f.relato || ''; obsOriginal = f.relato || ''; obs.readOnly = true;
    expandida = false; obs.classList.remove('aberta'); obs.style.height = '';
    preSelecionar(f.tecnico);
    $('fl_data').textContent = f.data_sug || '—';
    tipo.value = temOpcao(tipo, D.tipo_padrao) ? D.tipo_padrao : (tipo.options[0] ? tipo.options[0].value : '');
    c1.value = ''; c2.value = '';
    pai.value = ''; paiSel = null; paiLista.hidden = true;
    etq = []; doTema = new Set(); tirados = new Set();
    aplicarRegra();
    sugerirClassif();
    editor.set(f.subs || []);
    habilitar(!so);
    hint.textContent = so ? 'Esta solicitação já saiu da fila — aqui é só consulta.' : 'Aprovar avança para a próxima';
    pintarOrig();
    $('fl_atualizar').href = '/os/solicitacao/fila?atualizar=1&sel=' + encodeURIComponent(f.id);
    try { history.replaceState(null, '', location.pathname + '?sel=' + encodeURIComponent(f.id)); } catch (e) { /* sem history */ }
    setTimeout(revisarVer, 0);
  }

  // o título: clique edita; Enter grava, Esc desiste
  function abrirTitulo() {
    if (soLeitura()) return;
    tituloEd.value = titulo.textContent; titulo.hidden = true; tituloEd.hidden = false; tituloEd.focus(); tituloEd.select();
  }
  function fecharTitulo() {
    var t = tituloEd.value.trim();
    if (t) { tituloManual = t !== tituloDoTema(); titulo.textContent = t; }
    tituloEd.hidden = true; titulo.hidden = false;
    pintarOrig();
  }
  titulo.addEventListener('click', abrirTitulo);
  titulo.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); abrirTitulo(); } });
  tituloEd.addEventListener('blur', fecharTitulo);
  tituloEd.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); tituloEd.blur(); }
    if (e.key === 'Escape') { tituloEd.value = titulo.textContent; tituloEd.blur(); }
  });

  // a observação: lê-se sempre, edita-se ao clicar, grava ao sair (só se mudou), com o bloco [PCM] de volta (no servidor)
  obs.addEventListener('click', function () { if (!soLeitura() && obs.readOnly) { obs.readOnly = false; obs.focus(); } });
  obs.addEventListener('blur', function () {
    if (obs.readOnly) return;
    obs.readOnly = true;
    var f = atual, novo = obs.value.trim();
    if (!f || soLeitura() || novo === String(obsOriginal || '').trim()) return;
    SP.pedir('/os/api/solic/' + encodeURIComponent(f.id) + '/observacao', {relato: novo}, 'Gravando a observação no Fracttal…')
      .then(function (x) {
        if (x.ok) { f.relato = novo; if (atual === f) obsOriginal = novo; SP.aviso(x.j.mensagem || 'Observação gravada.'); return; }
        // volta o texto anterior: deixar na tela o que não está no Fracttal faria a pessoa ir embora achando que gravou
        if (atual === f) { obs.value = obsOriginal; revisarVer(); }
        SP.aviso('Não consegui gravar a observação no Fracttal. ' + (x.j.erro || ''), true);
      });
  });
  obs.addEventListener('input', revisarVer);
  ver.addEventListener('click', function () {
    expandida = !expandida;
    obs.classList.toggle('aberta', expandida);
    obs.style.height = expandida ? (obs.scrollHeight + 4) + 'px' : '';
    revisarVer();
  });

  // ── etiquetas (_CardEtiquetas) ──
  function etqDoTema() {
    var t = temaDe(tema.value);
    if (t && t.etiquetas) return new Set(t.etiquetas.map(up));
    var garantia = etq.some(function (e) { return SP.norm(e.nome).indexOf('garantia') >= 0; });
    return ((t && t.perf_tema) || (atual && atual.perf_ativo) || garantia) ? new Set([PERF]) : new Set();
  }
  function aplicarRegra() {
    // põe as do tema e tira as que ELE tinha posto quando o tema muda; a que o PCM pôs à mão fica
    var querem = new Set(Array.from(etqDoTema()).filter(function (n) { return !tirados.has(n); }));
    etq = etq.filter(function (e) { return !(doTema.has(up(e.nome)) && !querem.has(up(e.nome))); });
    var tem = new Set(etq.map(function (e) { return up(e.nome); })), postas = [];
    Array.from(querem).sort().forEach(function (nome) {
      if (tem.has(nome)) return;
      var alvo = ETQ.filter(function (e) { return up(e.nome) === nome; })[0];
      if (alvo) { etq.push({id: alvo.id, nome: alvo.nome}); postas.push(nome); }
    });
    doTema = new Set(Array.from(doTema).filter(function (n) { return querem.has(n); })
      .concat(postas).concat(Array.from(querem).filter(function (n) { return tem.has(n); })));
    pintarEtq();
  }
  function pintarEtq() {
    var so = soLeitura();
    chips.innerHTML = etq.map(function (e) {
      var t = doTema.has(up(e.nome));
      return '<button type="button" class="spc-etq' + (t ? ' tema' : '') + '" data-id="' + esc(e.id) + '" title="'
        + (t ? 'Vem do tema desta solicitação. Clique para tirar só aqui — o tema continua igual para as próximas.' : 'Clique para tirar')
        + '"' + (so ? ' disabled' : '') + '>' + esc(e.nome) + '&nbsp;&nbsp;&times;' + (t ? '&nbsp;&nbsp;(tema)' : '') + '</button>';
    }).join('');
    var ids = new Set(etq.map(function (e) { return String(e.id); }));
    etqAdd.innerHTML = opcoes(ETQ.filter(function (e) { return !ids.has(String(e.id)); })
      .map(function (e) { return {v: e.id, r: e.nome}; }), '+ adicionar etiqueta');
    $('fl_etq_aviso').textContent = etq.length ? '' : 'Nenhuma etiqueta — a OS nasce sem marcação.';
  }
  chips.addEventListener('click', function (e) {
    var b = e.target.closest('.spc-etq'); if (!b || soLeitura()) return;
    var fora = etq.filter(function (x) { return String(x.id) === b.dataset.id; })[0];
    if (fora) tirados.add(up(fora.nome));          // quem tirou, tirou: a regra não põe de volta nesta solicitação
    etq = etq.filter(function (x) { return String(x.id) !== b.dataset.id; });
    pintarEtq();
  });
  etqAdd.addEventListener('change', function () {
    var e = ETQ.filter(function (x) { return String(x.id) === etqAdd.value; })[0];
    if (e) { etq.push({id: e.id, nome: e.nome}); tirados.delete(up(e.nome)); }
    aplicarRegra();                                  // a GARANTIA posta à mão traz a PERFORMANCE, como manda a regra
  });

  // ── classificações (_sugerir_classif) ──
  function sugerirClassif() {
    var disc = (temaDe(tema.value) || {}).disciplina || '', posto = false;
    [[c1, D.classif1_padrao], [c2, disc]].forEach(function (par) {
      if (!par[1] || par[0].value) return;
      if (temOpcao(par[0], par[1])) { par[0].value = par[1]; posto = true; }
    });
    textoClassif(posto);
  }
  function textoClassif(posto) {
    var disc = (temaDe(tema.value) || {}).disciplina || '';
    var noPadrao = c1.value === D.classif1_padrao && (!disc || c2.value === disc);
    classif.textContent = (posto || (noPadrao && c1.value)) ? 'padrão das OS do PCM — troque se este caso for diferente' : '';
  }
  c1.addEventListener('change', function () { textoClassif(false); });
  c2.addEventListener('change', function () { textoClassif(false); });

  // ── o tema: título (se não for do PCM), etiquetas, classificação e as subtarefas dele ──
  tema.addEventListener('change', function () {
    if (!atual) return;
    if (!tituloManual) titulo.textContent = tituloDoTema();
    pintarOrig();
    aplicarRegra();
    sugerirClassif();
    if ((editor.mexeu() || subsDoBloco)
        && !window.confirm('Trocar as subtarefas pelas do tema escolhido? A lista de agora sai (as edições também).')) return;
    var f = atual;
    SP.pedir('/os/api/solic/subtarefas?tema=' + encodeURIComponent(tema.value) + '&tipo=' + encodeURIComponent(f.tipo_ativo || ''),
             undefined, 'Buscando as subtarefas do tema…')
      .then(function (x) {
        if (atual !== f) return;
        if (!x.ok) { SP.aviso('Não consegui buscar as subtarefas do tema. ' + (x.j.erro || ''), true); return; }
        editor.set(x.j.subtarefas || []); subsDoBloco = false;
      });
  });

  // ── OS pai (OsPaiPicker): digitou → 300 ms → busca; escolher guarda o ID (não é o nº); digitar de novo desfaz ──
  pai.addEventListener('input', function () { paiSel = null; clearTimeout(paiRelogio); paiRelogio = setTimeout(buscarPai, 300); });
  function buscarPai() {
    var termo = pai.value.trim(), meu = ++paiSeq;
    if (!termo) { paiLista.hidden = true; return; }
    SP.pedir('/os/api/pcm/os-pai?termo=' + encodeURIComponent(termo), undefined, 'Buscando a OS pai…').then(function (x) {
      if (meu !== paiSeq) return;
      var l = (x.j && x.j.resultados) || [];
      paiLista.innerHTML = l.map(function (r, i) {
        return '<div class="spc-pai-op' + (i === 0 ? ' on' : '') + '" role="option" data-id="' + esc(r.id) + '">' + esc(r.folio)
          + (r.descricao ? ' — ' + esc(r.descricao) : '') + (r.responsavel ? ' · ' + esc(r.responsavel) : '') + '</div>';
      }).join('') || '<div class="spc-pai-vazio">Nenhuma OS com esse número.</div>';
      paiLista.hidden = document.activeElement !== pai;
    });
  }
  function escolherPai(op) { paiSel = Number(op.dataset.id); pai.value = op.textContent; paiLista.hidden = true; }
  paiLista.addEventListener('mousedown', function (e) {
    var op = e.target.closest('.spc-pai-op'); if (op) { e.preventDefault(); escolherPai(op); }
  });
  pai.addEventListener('keydown', function (e) {
    if (paiLista.hidden) return;
    var ops = Array.prototype.slice.call(paiLista.querySelectorAll('.spc-pai-op'));
    var k = ops.findIndex(function (o) { return o.classList.contains('on'); });
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!ops.length) return;
      if (k >= 0) ops[k].classList.remove('on');
      k = Math.max(0, Math.min(ops.length - 1, k + (e.key === 'ArrowDown' ? 1 : -1)));
      ops[k].classList.add('on');
    } else if (e.key === 'Enter') {
      e.preventDefault(); if (ops[k]) escolherPai(ops[k]);
    } else if (e.key === 'Escape') { paiLista.hidden = true; }
  });
  pai.addEventListener('blur', function () { setTimeout(function () { paiLista.hidden = true; }, 150); });

  // ── as ações ──
  function ocupado(on, txt) {
    [aprovar, devolver, bStatus].forEach(function (b) { b.disabled = on || soLeitura(); });
    hint.textContent = txt || (soLeitura() ? 'Esta solicitação já saiu da fila — aqui é só consulta.' : 'Aprovar avança para a próxima');
  }
  // a solicitação saiu da fila (aprovada, recusada, devolvida): some da lista e a ficha vai para a próxima
  function tirar(f) {
    var i = itens.indexOf(f);
    if (i < 0) return;
    itens.splice(i, 1);
    if (String(f.id) === leitura) leitura = '';
    selecionar(itens[i] || itens[i - 1] || null);
  }
  aprovar.addEventListener('click', function () {
    var f = atual;
    if (!f || soLeitura()) return;
    if (!f.ativo_ok) { SP.aviso('Não achei o ativo desta solicitação no catálogo. Recarregue os ativos e tente de novo.', true); return; }
    if (!resp.value) {
      SP.aviso('Escolha o responsável pela OS. Sem responsável a tarefa é criada mas NÃO vira OS numerada — ela fica '
               + 'pendente no kanban do Fracttal e ninguém a vê.', true);
      return;
    }
    if (pai.value.trim() && !paiSel) { SP.aviso('Escolha a OS pai na lista que aparece ao digitar o número — ou apague o campo.', true); return; }
    var subs = editor.itens(), t = (titulo.textContent || '').trim() || tituloDoTema(), n = subs.length || 3;
    if (!window.confirm('Criar a OS “' + t + '” com ' + n + ' subtarefa(s)?\n\nA API do Fracttal NÃO edita OS já criada — '
                        + 'confira as subtarefas antes.')) return;
    ocupado(true, 'criando a OS…');
    SP.pedir('/os/api/solic/' + encodeURIComponent(f.id) + '/aprovar', {
      id_responsible: resp.value, responsavel: resp.options[resp.selectedIndex].text, titulo: t, subtarefas: subs,
      tipo: tipo.value, classif1: c1.value, classif2: c2.value, etiquetas: etq.map(function (e) { return e.id; }),
      id_parent: paiSel
    }, 'Criando a OS no Fracttal…').then(function (x) {
      ocupado(false, '');
      if (!x.ok) { SP.aviso(x.j.erro || 'Não consegui criar a OS.', true); return; }
      SP.aviso('OS ' + x.j.folio + ' criada a partir da solicitação Nº ' + f.id + '.');
      tirar(f);          // "Aprovar avança para a próxima": são várias na fila
    });
  });

  // mudar o status / devolver ao supervisor: a mesma janela, o motivo é obrigatório
  function abrirStatus(codigo, rotulo) {
    if (!atual || soLeitura()) return;
    mT.textContent = (rotulo || 'Mudar status') + ' — solicitação ' + atual.id;
    mSt.value = codigo && temOpcao(mSt, codigo) ? codigo : (mSt.options[0] ? mSt.options[0].value : '');
    mMot.value = ''; mOk.disabled = true; mOk.textContent = rotulo || 'Mudar status';
    modal.hidden = false; mMot.focus();
  }
  function fecharModal() { modal.hidden = true; }
  bStatus.addEventListener('click', function () { abrirStatus('', 'Mudar status'); });
  devolver.addEventListener('click', function () { abrirStatus('AGAIN_REQUEST_TODO', 'Devolver ao supervisor'); });
  mMot.addEventListener('input', function () { mOk.disabled = !mMot.value.trim(); });
  modal.addEventListener('click', function (e) { if (e.target.hasAttribute('data-fechar')) fecharModal(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !modal.hidden) fecharModal(); });
  function colunaDe(f) {           // solic_web.coluna_de: o que separa é ter ou não OS, não o id_status
    var st = String(f.status || '').toLowerCase();
    if (st.indexOf('cancelada') >= 0 || st.indexOf('rejeitada') >= 0) return 'finalizada';
    if (st.indexOf('reaberta') >= 0 && !f.id_work_order) return 'fora';
    if (!f.id_work_order) return 'pendente';
    return (st.indexOf('conclu') >= 0 || st.indexOf('resolvid') >= 0) ? 'finalizada' : 'andamento';
  }
  mOk.addEventListener('click', function () {
    var f = atual, motivo = mMot.value.trim();
    if (!f || !motivo) return;
    mOk.disabled = true;
    SP.pedir('/os/api/solic/' + encodeURIComponent(f.id) + '/status', {codigo: mSt.value, motivo: motivo}, 'Mudando o status no Fracttal…')
      .then(function (x) {
        if (!x.ok) { mOk.disabled = false; SP.aviso('Não consegui mudar o status. ' + (x.j.erro || ''), true); return; }
        fecharModal();
        SP.aviso(x.j.mensagem || 'Status alterado.');
        f.status = x.j.status || f.status; f.cor = '';
        if (colunaDe(f) !== 'pendente') tirar(f); else pintarLista();
      });
  });

  pintarLista();
  selecionar(itens.filter(function (f) { return String(f.id) === String(D.sel || ''); })[0] || itens[0] || null);
  window.addEventListener('resize', revisarVer);
})();

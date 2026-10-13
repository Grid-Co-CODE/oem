/* os_creator/os_web/static/solic_hist.js — o Histórico de solicitações do app na web (`steps/historico_solic.py`; Levi,
   13/10/2026: "referência é a fila do app desktop, nem painel do PCM nem histórico nem temas").

   Como no app: Criado por (abre em "Todos os usuários" — filtrar sem ninguém pedir fazia a pessoa achar que a
   solicitação dos outros não existia), a busca direta pelo nº (ignora os filtros e abre a ficha), a busca ampla por
   qualquer campo, os filtros de marcar (Cliente, Usina em cascata, Tipo de ativo, Status), o Período (últimos 30 dias),
   Exportar (CSV com ; e BOM, que o Excel abre direto), Limpar filtros, o ↻ e a atualização de 15 em 15 minutos (que
   mantém os filtros: a lista vem por JSON, a página não recarrega). O Nº abre a ficha (`SolicitacaoDialog`) e a OS
   ligada abre o card da OS — o mesmo do Histórico de OS. */
(function () {
  'use strict';
  var SP = window.SolicPcm, esc = SP.esc;
  function $(id) { return document.getElementById(id); }
  var linhas = (JSON.parse($('hs_dados').textContent || '{}').linhas) || [], filtradas = [], relogio = null;
  var pessoa = $('hs_pessoa'), num = $('hs_num'), busca = $('hs_busca'), de = $('hs_de'), ate = $('hs_ate'),
      corpo = $('hs_corpo'), rodape = $('hs_rodape');

  function pill(st, cor) {
    return '<span class="spc-pill"' + (cor ? ' style="color:' + esc(cor) + '"' : '') + '>' + esc(st) + '</span>';
  }
  function unicos(campo, filtro) {
    var vistos = {};
    linhas.forEach(function (d) {
      var v = d[campo];
      if (v && v !== '—' && (!filtro || filtro(d))) vistos[v] = 1;
    });
    return Object.keys(vistos).sort(function (a, b) { return a.localeCompare(b, 'pt-BR'); });
  }

  // ── as listas de marcar (o os-multi do Histórico de OS; o os_busca.js põe a caixa de digitar) ──
  function multi(nome) { return document.querySelector('.os-multi[data-nome="' + nome + '"]'); }
  function marcados(nome) {
    return Array.prototype.filter.call(multi(nome).querySelectorAll('label'), function (l) { return !l.hidden; })
      .map(function (l) { return l.querySelector('input'); }).filter(function (c) { return c.checked; })
      .map(function (c) { return c.value; });
  }
  function resumo(nome) {
    var det = multi(nome), txt = det.querySelector('.os-multi-txt'), sel = marcados(nome);
    txt.textContent = !sel.length ? txt.getAttribute('data-todos') : (sel.length === 1 ? sel[0] : sel.length + ' selecionados');
  }
  function encher(nome, valores) {
    var lista = multi(nome).querySelector('.os-multi-lista'), antes = new Set(marcados(nome));
    lista.querySelectorAll('label').forEach(function (l) { l.remove(); });
    var html = valores.map(function (v) {
      return '<label><input type="checkbox" value="' + esc(v) + '"' + (antes.has(v) ? ' checked' : '') + '> ' + esc(v) + '</label>';
    }).join('');
    var vazio = lista.querySelector('.osm-vazio');
    if (vazio) vazio.insertAdjacentHTML('beforebegin', html); else lista.insertAdjacentHTML('beforeend', html);
    resumo(nome);
  }
  function cascataUsinas() {
    // as usinas dos clientes marcados (ou todas, sem cliente marcado); a escondida não vale no filtro
    var clis = new Set(marcados('cliente'));
    multi('usina').querySelectorAll('label').forEach(function (l) {
      var u = l.querySelector('input').value;
      l.hidden = clis.size > 0 && !linhas.some(function (d) { return d.usina === u && clis.has(d.cliente); });
    });
    resumo('usina');
  }
  function encherFiltros() {
    var quem = pessoa.value;
    pessoa.innerHTML = '<option value="">Todos os usuários</option>' + unicos('criado_por').map(function (n) {
      return '<option value="' + esc(n) + '">' + esc(n) + '</option>';
    }).join('');
    pessoa.value = quem && Array.prototype.some.call(pessoa.options, function (o) { return o.value === quem; }) ? quem : '';
    encher('cliente', unicos('cliente'));
    encher('usina', unicos('usina'));
    encher('tipo', unicos('tipo'));
    encher('status', unicos('status'));
    cascataUsinas();
  }
  document.querySelectorAll('.os-multi').forEach(function (det) {
    det.addEventListener('change', function () {
      resumo(det.getAttribute('data-nome'));
      if (det.getAttribute('data-nome') === 'cliente') cascataUsinas();
      aplica();
    });
  });
  document.addEventListener('click', function (e) {
    document.querySelectorAll('.os-multi[open]').forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute('open'); });
  });

  // ── o filtro (`_aplica`) ──
  function aplica() {
    var dDe = de.value || '0000-00-00', dAte = ate.value || '9999-99-99', quem = pessoa.value,
        sts = new Set(marcados('status')), clis = new Set(marcados('cliente')), usis = new Set(marcados('usina')),
        tips = new Set(marcados('tipo')), q = busca.value.trim().toLowerCase();
    filtradas = linhas.filter(function (d) {
      if (quem && d.criado_por !== quem) return false;
      if (!(d.dia >= dDe && d.dia <= dAte)) return false;
      if (sts.size && !sts.has(d.status)) return false;
      if (clis.size && !clis.has(d.cliente)) return false;
      if (usis.size && !usis.has(d.usina)) return false;
      if (tips.size && !tips.has(d.tipo)) return false;
      if (!q) return true;
      return [d.id, d.cliente, d.usina, d.ativo, d.descricao_full || d.descricao, d.status, d.os_folio]
        .some(function (c) { return String(c == null ? '' : c).toLowerCase().indexOf(q) >= 0; });
    });
    corpo.innerHTML = filtradas.map(function (d, i) {
      return '<tr><td><button type="button" class="spc-hist-n" data-ficha="' + i + '" title="Clique para ver a solicitação">'
        + esc(d.id) + '</button></td><td>' + esc(d.cliente) + '</td><td>' + esc(d.usina) + '</td>'
        + '<td class="spc-hist-ativo" title="' + esc(d.ativo) + '">' + esc(d.ativo || '—') + '</td>'
        + '<td class="spc-hist-desc" title="' + esc(d.descricao_full || d.descricao) + '">' + esc(d.descricao) + '</td>'
        + '<td class="spc-hist-data">' + esc(d.data) + '</td><td>' + (d.status ? pill(d.status, d.cor) : '') + '</td>'
        + '<td class="spc-hist-osc">' + (d.os_folio && d.id_work_order
          ? '<button type="button" class="spc-hist-os" data-os="' + esc(d.id_work_order) + '" title="Clique para ver a OS">' + esc(d.os_folio) + '</button>'
          : esc(d.os_folio || '—')) + '</td></tr>';
    }).join('') || '<tr class="vazio"><td colspan="8">Nenhuma solicitação com esses filtros.</td></tr>';
    var comOs = filtradas.filter(function (d) { return d.os_folio; }).length;
    rodape.textContent = filtradas.length + ' solicitação(ões) no período · ' + comOs + ' com OS ligada'
      + (filtradas.length !== linhas.length ? '  ·  ' + linhas.length + ' no total' : '');
  }
  pessoa.addEventListener('change', aplica);
  de.addEventListener('change', aplica);
  ate.addEventListener('change', aplica);
  busca.addEventListener('input', function () { clearTimeout(relogio); relogio = setTimeout(aplica, 260); });

  $('hs_limpar').addEventListener('click', function () {
    document.querySelectorAll('.os-multi input:checked').forEach(function (c) { c.checked = false; });
    ['cliente', 'usina', 'tipo', 'status'].forEach(resumo);
    cascataUsinas();
    busca.value = '';
    aplica();
  });

  // ── exportar (steps/exportar.py: ; e BOM, que o Excel em português abre sem perguntar nada) ──
  function exportar() {
    var cab = ['Nº', 'Cliente', 'Usina', 'Ativo', 'Descrição', 'Criada em', 'Status', 'OS ligada', 'Criado por'];
    var cel = function (v) { v = String(v == null ? '' : v); return /[;"\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var txt = [cab].concat(filtradas.map(function (d) {
      return [d.id, d.cliente, d.usina, d.ativo, d.descricao_full || d.descricao, d.data, d.status, d.os_folio, d.criado_por];
    })).map(function (l) { return l.map(cel).join(';'); }).join('\r\n');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['﻿' + txt], {type: 'text/csv;charset=utf-8'}));
    a.download = 'solicitacoes_' + (de.value || 'inicio') + '_a_' + (ate.value || 'hoje') + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
  }
  $('hs_exportar').addEventListener('click', exportar);

  // ── recarregar (↻ e de 15 em 15 minutos), mantendo os filtros ──
  function recarregar() {
    rodape.textContent = 'carregando solicitações…';
    SP.pedir('/os/api/solic/historico', undefined, 'Buscando as solicitações no Fracttal…').then(function (x) {
      if (!x.ok) { SP.aviso('Não consegui atualizar: ' + (x.j.erro || 'sem resposta'), true); aplica(); return; }
      linhas = x.j.linhas || [];
      encherFiltros();
      aplica();
    });
  }
  $('hs_recarregar').addEventListener('click', recarregar);
  setInterval(function () { if (!document.hidden && $('hs_ficha').hidden && $('os_card').hidden) recarregar(); }, 15 * 60 * 1000);
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) { e.preventDefault(); busca.focus(); busca.select(); }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'e' || e.key === 'E')) { e.preventDefault(); exportar(); }
    if (e.key === 'Escape') { if (!$('os_card').hidden) fecharOs(); else if (!$('hs_ficha').hidden) fecharFicha(); }
  });

  // ── a ficha (SolicitacaoDialog) ──
  var fichaEl = $('hs_ficha'), atual = null, anexos = [];
  function buscarJson(url) {          // em segundo plano (a contagem dos anexos): sem o círculo de carga, de propósito
    return fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }
  function abrirFicha(d) {
    atual = d;
    $('hs_f_t').textContent = 'Solicitação ' + d.id;
    $('hs_f_st').innerHTML = d.status ? pill(d.status, d.cor) : '';
    $('hs_f_ativo').textContent = d.ativo || '—';
    $('hs_f_meta').innerHTML = [['Cliente', d.cliente], ['Usina', d.usina], ['Criada em', d.data], ['Criado por', d.criado_por]]
      .map(function (p) { return '<div><dt>' + esc(p[0]) + '</dt><dd>' + esc(p[1] || '—') + '</dd></div>'; }).join('');
    $('hs_f_os').disabled = !d.id_work_order;
    $('hs_f_os_n').textContent = d.os_folio ? 'OS ' + d.os_folio : '—';
    $('hs_f_os_d').textContent = d.os_folio ? 'clique para abrir' : 'ainda sem OS gerada';
    $('hs_f_tit').textContent = d.descricao_full || d.descricao || '(sem título)';
    $('hs_f_obs').textContent = d.observacao || '';
    $('hs_f_obs_box').hidden = !String(d.observacao || '').trim();
    $('hs_f_abrir_os').hidden = !d.id_work_order;
    $('hs_f_cancelar_b').hidden = !d.cancelavel;
    $('hs_f_cancelar').hidden = true; $('hs_f_nota').value = '';
    $('hs_f_lista').hidden = true;
    anexos = [];
    $('hs_f_img').querySelector('.spc-anexo-n').textContent = '…';
    $('hs_f_doc').querySelector('.spc-anexo-n').textContent = '…';
    fichaEl.hidden = false;
    var alvo = d;
    buscarJson('/os/api/solic/' + encodeURIComponent(d.id) + '/anexos').then(function (j) {
      if (atual !== alvo) return;
      anexos = (j && j.anexos) || [];
      $('hs_f_img').querySelector('.spc-anexo-n').textContent = j ? anexos.filter(function (a) { return a.imagem; }).length : '—';
      $('hs_f_doc').querySelector('.spc-anexo-n').textContent = j ? anexos.filter(function (a) { return !a.imagem; }).length : '—';
    });
  }
  function fecharFicha() { fichaEl.hidden = true; atual = null; }
  function listarAnexos(imagens) {
    var l = anexos.filter(function (a) { return !!a.imagem === imagens; }), el = $('hs_f_lista');
    el.innerHTML = l.length ? l.map(function (a) {
      if (imagens && a.url) {
        return '<a class="spc-anexo-img" href="' + esc(a.url) + '" target="_blank" rel="noopener" title="' + esc(a.nome) + '">'
          + '<img src="' + esc(a.url) + '" alt="' + esc(a.nome) + '" loading="lazy"></a>';
      }
      return a.url ? '<a class="spc-anexo-doc" href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.nome) + '</a>'
                   : '<span class="spc-anexo-doc">' + esc(a.nome) + '</span>';
    }).join('') : '<p class="spc-dica">' + (imagens ? 'Nenhuma imagem anexada.' : 'Nenhum documento anexado.') + '</p>';
    el.hidden = false;
  }
  $('hs_f_img').addEventListener('click', function () { listarAnexos(true); });
  $('hs_f_doc').addEventListener('click', function () { listarAnexos(false); });
  fichaEl.addEventListener('click', function (e) { if (e.target.hasAttribute('data-fechar')) fecharFicha(); });
  function abrirOsDaFicha() { if (atual && atual.id_work_order) { var w = atual.id_work_order; fecharFicha(); abrirOs(w); } }
  $('hs_f_os').addEventListener('click', abrirOsDaFicha);
  $('hs_f_abrir_os').addEventListener('click', abrirOsDaFicha);
  $('hs_f_cancelar_b').addEventListener('click', function () { $('hs_f_cancelar').hidden = false; $('hs_f_nota').focus(); });
  $('hs_f_voltar').addEventListener('click', function () { $('hs_f_cancelar').hidden = true; });
  $('hs_f_confirmar').addEventListener('click', function () {
    var d = atual;
    if (!d || !window.confirm('Confirma o cancelamento da solicitação Nº ' + d.id + '?\nIsto muda o status dela no Fracttal.')) return;
    SP.pedir('/os/api/solic/' + encodeURIComponent(d.id) + '/cancelar', {nota: $('hs_f_nota').value.trim()}, 'Cancelando no Fracttal…')
      .then(function (x) {
        if (!x.ok) { SP.aviso('Não foi possível cancelar: ' + (x.j.erro || 'sem resposta'), true); return; }
        SP.aviso('Solicitação Nº ' + d.id + ' cancelada com sucesso.');
        fecharFicha();
        recarregar();                 // a linha passa a dizer Cancelada
      });
  });
  corpo.addEventListener('click', function (e) {
    var n = e.target.closest('[data-ficha]'), o = e.target.closest('[data-os]');
    if (n) abrirFicha(filtradas[Number(n.dataset.ficha)]);
    else if (o) abrirOs(o.dataset.os);
  });
  num.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    var n = num.value.trim().replace(/^#/, '');
    if (!n) return;
    var d = linhas.filter(function (x) { return String(x.id) === n; })[0];
    if (d) { num.value = ''; abrirFicha(d); return; }
    // fora das 400 carregadas: busca no Fracttal pelo nº
    SP.pedir('/os/api/solic/' + encodeURIComponent(n), undefined, 'Buscando a solicitação…').then(function (x) {
      if (!x.ok) { SP.aviso('Não achei a solicitação nº ' + n + '.', true); return; }
      num.value = ''; abrirFicha(x.j);
    });
  });

  // ── o card da OS ligada (o mesmo do Histórico de OS) ──
  var cardEl = $('os_card'), cardCorpo = $('os_card_corpo'), mudou = false;
  function abrirOs(wid) {
    cardCorpo.innerHTML = '<p class="os-ajuda spc-carregando">Carregando a OS…</p>';
    cardEl.hidden = false; document.body.classList.add('os-modal-aberto');
    window.OsCarga.buscar('/os/os/' + encodeURIComponent(wid) + '?parcial=1',
                          {headers: {'X-Requested-With': 'fetch'}, credentials: 'same-origin'}, 'Abrindo a OS…')
      .then(function (r) { return r.text(); })
      .then(function (h) {
        cardCorpo.innerHTML = h; cardCorpo.scrollTop = 0;
        var det = cardCorpo.querySelector('.det');
        if (window.OsAcoes && det) window.OsAcoes.contagem(det);
      })
      .catch(function () { cardCorpo.innerHTML = '<p class="os-erro spc-carregando">Não consegui carregar a OS aqui.</p>'; });
  }
  // uma ação no card (concluir, cancelar, responsável...) deixa a lista velha: ao fechar, ela vem de novo
  document.addEventListener('os:alterada', function () { mudou = true; });
  function fecharOs() {
    cardEl.hidden = true; cardCorpo.innerHTML = ''; document.body.classList.remove('os-modal-aberto');
    if (mudou) { mudou = false; recarregar(); }
  }
  cardEl.addEventListener('click', function (e) { if (e.target.hasAttribute('data-fechar')) fecharOs(); });

  encherFiltros();
  aplica();
  // ?ficha=<nº>: o cartão do Painel de quem não é da Área PCM abre a ficha aqui (a Fila é do setor PCM no Nexus)
  var ficha = new URLSearchParams(location.search).get('ficha');
  if (ficha) { num.value = ficha; num.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'})); }
})();

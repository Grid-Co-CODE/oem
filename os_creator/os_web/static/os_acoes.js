// os_creator/os_web/static/os_acoes.js — as AÇÕES do card da OS no navegador: trocar responsável, etiquetas, editar a
// observação, Concluir OS, Cancelar OS, Fluxo e anexos (steps/os_detalhe.py, cancelar_os.py, os_fluxo.py, galeria.py,
// documentos.py). Mesma sequência de cada diálogo do app: carrega a lista → a pessoa escolhe → confirma → grava → o card
// recarrega (/os/os/<wid>?parcial=1). Erros vão para a .os-resultado do card ou para a linha de hint do diálogo, nunca alert().
//
// DELEGAÇÃO no document, e não um listener por card: o card chega por innerHTML (o Histórico injeta o fragmento no modal) e
// é trocado inteiro a cada recarga — um listener preso ao elemento se perderia. Basta o script estar na página.
(function () {
  'use strict';
  if (window.OsAcoes) return;                         // incluído duas vezes (página cheia + card) não duplica handlers

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const apiErro = (j, r) => (j && j.erro) ? (j.login ? j.erro + ' Entre de novo em /os/login.' : j.erro) : ('HTTP ' + (r && r.status));
  const q = (el, s) => el.querySelector(s);
  const card = (el) => el.closest('.det');
  const anexosCache = new WeakMap();                  // a lista de anexos por card — duas rodadas de RPC, não repetir a cada clique

  async function pedir(url, corpo) {
    const opt = {credentials: 'same-origin', headers: {'Accept': 'application/json'}};
    if (corpo !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(corpo); }
    const r = await fetch(url, opt);
    let j = null; try { j = await r.json(); } catch (e) { j = null; }
    if (!r.ok) throw new Error(apiErro(j, r));
    return j || {};
  }

  function mensagem(d, texto, ruim) {
    const m = q(d, '[data-msg]'); if (!m) return;
    m.hidden = !texto; m.textContent = texto || ''; m.classList.toggle('ruim', !!ruim);
  }

  // contagem dos dois cards de anexos — chega depois do detalhe, como no app (o Histórico faz o mesmo na 1ª abertura)
  function contagem(d) {
    const el = q(d, '[data-anexos]'); if (!el) return;
    fetch(el.getAttribute('data-anexos'), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then((r) => r.ok ? r.json() : null)
      .then((j) => { d.querySelectorAll('.det-n').forEach((n) => { const v = j ? j[n.getAttribute('data-n')] : null; n.textContent = (v === null || v === undefined) ? '—' : v; }); })
      .catch(() => { d.querySelectorAll('.det-n').forEach((n) => { n.textContent = '—'; }); });
  }

  // Recarrega o card NO LUGAR (o corpo do modal do Histórico ou o main da página cheia): o Fracttal é a fonte do que ficou.
  async function recarregar(d, url, texto, ruim) {
    const r = await fetch(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'fetch'}});
    const html = await r.text();
    const tmp = document.createElement('div'); tmp.innerHTML = html;
    const novo = tmp.querySelector('.det') || tmp.firstElementChild;
    if (!novo) { mensagem(d, 'Não consegui recarregar a OS.', true); return d; }
    d.replaceWith(novo);
    if (novo.classList.contains('det')) { contagem(novo); if (texto) mensagem(novo, texto, ruim); }
    const rolo = novo.closest('.os-modal-card'); if (rolo) rolo.scrollTop = 0; else window.scrollTo(0, 0);
    return novo;
  }
  const urlCard = (d, status) => '/os/os/' + d.dataset.wid + '?parcial=1&status=' + encodeURIComponent(status || d.dataset.status || '');

  // ── diálogo: clona o <template data-dlg> do card num overlay ACIMA do modal do Histórico ──
  let aberto = null;
  // "2026-09-21T14:30" no fuso de quem esta olhando — o <input datetime-local> nao aceita ISO com Z
  function agoraLocal() {
    const t = new Date(); t.setMinutes(t.getMinutes() - t.getTimezoneOffset());
    return t.toISOString().slice(0, 16);
  }

  // Cada subtarefa vira o campo do SEU tipo. Texto num campo que devia ser Aprovado/Alerta/Falhou
  // grava lixo no checklist — e o Fracttal aceita, que e o pior dos casos.
  function campoHTML(c) {
    const id = 'f' + c.id_form_item, req = c.obrigatorio ? ' <span class="os-req">obrigatória</span>' : '';
    const fot = c.anexo_obrigatorio ? ' <span class="det-ajuda">(pede foto no Fracttal)</span>' : '';
    let ctrl;
    if ((c.opcoes || []).length) {
      ctrl = '<select data-fid="' + esc(c.id_form_item) + '" id="' + id + '"><option value="">— selecione —</option>'
        + c.opcoes.map((o) => '<option value="' + esc(o.valor) + '"' + (String(o.valor) === String(c.valor) ? ' selected' : '') + '>' + esc(o.rotulo) + '</option>').join('') + '</select>';
    } else if (c.tipo_nome === 'num') {
      ctrl = '<input type="number" step="any" data-fid="' + esc(c.id_form_item) + '" id="' + id + '" value="' + esc(c.valor) + '">';
    } else {
      ctrl = '<input type="text" data-fid="' + esc(c.id_form_item) + '" id="' + id + '" value="' + esc(c.valor) + '">';
    }
    return '<label class="os-campo acoes-exec-c"><span class="os-lbl">' + esc(c.descricao) + req + fot + '</span>' + ctrl + '</label>';
  }

  function dialogo(d, nome) {
    const t = q(d, 'template[data-dlg="' + nome + '"]'); if (!t) return null;
    if (aberto) aberto.fechar();
    const fundo = document.createElement('div'); fundo.className = 'acoes-fundo';
    const caixa = document.createElement('div'); caixa.className = 'acoes-dlg acoes-dlg-' + nome;
    caixa.setAttribute('role', 'dialog'); caixa.setAttribute('aria-modal', 'true');
    caixa.appendChild(t.content.cloneNode(true)); fundo.appendChild(caixa); document.body.appendChild(fundo);
    const dlg = {caixa, fechar() { fundo.remove(); if (aberto === dlg) aberto = null; }};
    fundo.addEventListener('click', (e) => { if (e.target === fundo || e.target.closest('[data-fechar]')) dlg.fechar(); });
    aberto = dlg;
    const foco = caixa.querySelector('select, input, textarea, button:not([data-fechar])'); if (foco) foco.focus();
    return dlg;
  }
  // Escape fecha o MEU diálogo, e só ele: o Histórico também escuta Escape no document para fechar o card inteiro —
  // a captura na window chega antes e segura a propagação enquanto um diálogo estiver aberto.
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && aberto) { e.stopPropagation(); e.preventDefault(); aberto.fechar(); } }, true);
  const hint = (dlg, texto) => { const h = q(dlg.caixa, '[data-hint]'); if (h) h.textContent = texto || ''; };
  const trava = (btn, on, texto) => { btn.disabled = !!on; if (texto !== undefined) btn.textContent = texto; };
  const numero = (v) => /^\d+$/.test(String(v)) ? Number(v) : v;

  function modoNota(d, editando) {                    // leitura ↔ edição no MESMO espaço: só um dos dois fica visível
    q(d, '[data-nota-leitura]').hidden = editando; q(d, '[data-nota-editor]').hidden = !editando;
    q(d, '[data-acao="nota-editar"]').hidden = editando;
    q(d, '[data-acao="nota-salvar"]').hidden = !editando; q(d, '[data-acao="nota-cancelar"]').hidden = !editando;
  }

  const ACOES = {
    // TrocarResponsavelDialog: lista o pessoal, a pessoa escolhe, 'Atribuir' grava (api.mudar_responsavel)
    async responsavel(d) {
      const dlg = dialogo(d, 'responsavel'); if (!dlg) return;
      const sel = q(dlg.caixa, '[data-resp-sel]'), ok = q(dlg.caixa, '[data-conf="responsavel"]');
      try {
        const j = await pedir('/os/api/responsaveis');
        sel.innerHTML = '<option value="">— escolha a pessoa —</option>' + (j.pessoas || []).filter((p) => p.id_personnel)
          .map((p) => '<option value="' + esc(p.id_personnel) + '">' + esc(p.name || '?') + '</option>').join('');
        ok.disabled = false;
      } catch (e) { hint(dlg, 'não consegui buscar o pessoal: ' + e.message); }
      ok.addEventListener('click', async () => {
        const opt = sel.selectedOptions[0];
        if (!opt || !opt.value) { hint(dlg, 'escolha a pessoa.'); return; }
        trava(ok, true); hint(dlg, 'gravando no Fracttal…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/responsavel', {id_personnel: numero(opt.value), name: opt.textContent, folio: d.dataset.folio});
          dlg.fechar(); await recarregar(d, urlCard(d), j.mensagem);
        } catch (e) { trava(ok, false); hint(dlg, e.message); }
      });
    },

    // _EtiquetasDialog: catálogo marcável (bolinha da cor), filtro, 'Salvar' manda o CONJUNTO inteiro (labels_sync substitui)
    async etiquetas(d) {
      const dlg = dialogo(d, 'etiquetas'); if (!dlg) return;
      const busca = q(dlg.caixa, '[data-etq-busca]'), lista = q(dlg.caixa, '[data-etq-lista]'), ok = q(dlg.caixa, '[data-conf="etiquetas"]');
      const atuais = Array.from(d.querySelectorAll('.det-chip[data-id]')).map((c) => c.dataset.id);   // o card já sabe as da OS
      const marcadas = new Set(atuais);
      let labels = [];
      function pintar() {
        const txt = (busca.value || '').trim().toLowerCase();
        lista.innerHTML = labels.filter((l) => (l.description || '').trim() && (!txt || l.description.toLowerCase().includes(txt)))
          .map((l) => '<label class="acoes-etq"><input type="checkbox" value="' + esc(l.id) + '"' + (marcadas.has(String(l.id)) ? ' checked' : '') + '>'
            + '<i style="background:' + esc(l.color) + '"></i><span>' + esc(l.description) + '</span></label>').join('');
      }
      try {
        const j = await pedir('/os/api/os/' + d.dataset.wid + '/etiquetas?atuais=' + encodeURIComponent(atuais.join(',')));
        labels = j.catalogo || []; (j.atuais || []).forEach((i) => marcadas.add(String(i)));
        busca.placeholder = labels.length ? 'Filtrar etiquetas…' : 'nenhuma etiqueta no catálogo'; pintar();
      } catch (e) { busca.placeholder = 'etiquetas não carregaram — relogue'; hint(dlg, e.message); }
      busca.addEventListener('input', pintar);
      lista.addEventListener('change', (e) => { const c = e.target; if (c.type !== 'checkbox') return; if (c.checked) marcadas.add(c.value); else marcadas.delete(c.value); });
      ok.addEventListener('click', async () => {
        const ids = Array.from(marcadas).filter(Boolean).map(numero);
        if (!ids.length) { hint(dlg, 'Marque ao menos uma etiqueta (ou Cancelar).'); return; }
        trava(ok, true); hint(dlg, 'salvando…');
        try { await pedir('/os/api/os/' + d.dataset.wid + '/etiquetas', {ids}); dlg.fechar(); await recarregar(d, urlCard(d)); }
        catch (e) { trava(ok, false); hint(dlg, '⚠ ' + e.message); }
      });
    },

    // NOTAS inline (Editar / Salvar / Cancelar): o editor nasce com a observação atual; nada mudou = não gastar uma escrita
    'nota-editar'(d) { const ta = q(d, '[data-nota-editor]'); ta.value = ta.defaultValue; modoNota(d, true); ta.focus(); },
    'nota-cancelar'(d) { modoNota(d, false); },
    async 'nota-salvar'(d, btn) {
      const ta = q(d, '[data-nota-editor]'); const novo = ta.value.trim();
      if (novo === ta.defaultValue.trim()) { modoNota(d, false); return; }
      trava(btn, true, 'salvando…');
      try { await pedir('/os/api/os/' + d.dataset.wid + '/nota', {nota: novo, status: d.dataset.status}); await recarregar(d, urlCard(d)); }
      catch (e) { trava(btn, false, 'Salvar'); mensagem(d, 'Não consegui salvar a observação. ' + e.message, true); }
    },

    // _ConcluirDialog (já montado pelo servidor: %, pendentes, data de fim) → api.concluir_os_checado; depois o card em 'Concluída'
    concluir(d) {
      const dlg = dialogo(d, 'concluir'); if (!dlg) return;
      const ok = q(dlg.caixa, '[data-conf="concluir"]');
      // fazer a tarefa ANTES de fechar: o dialogo de concluir sai de cena e o da execucao entra
      dlg.caixa.querySelectorAll('[data-fazer]').forEach((b) => {
        b.addEventListener('click', () => { dlg.fechar(); ACOES.executar(d, b.dataset.fazer, b.dataset.fazerTitulo); });
      });
      ok.addEventListener('click', async () => {
        trava(ok, true, 'concluindo…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/concluir', {folio: d.dataset.folio});
          dlg.fechar(); await recarregar(d, urlCard(d, 'Concluída'), j.mensagem, !!j.aviso);
        } catch (e) { trava(ok, false, 'Concluir OS'); hint(dlg, 'Erro ao concluir OS: ' + e.message); }
      });
    },

    // Fazer a tarefa (Levi, 21/09): preenche o checklist e lanca o registro de execucao sem sair
    // da web. O protocolo e o da tela do Fracttal, capturado em 21/09 na OS 38299179: gravar os
    // valores, validar a seguranca, inserir a execucao e reler para confirmar.
    async executar(d, tid, titulo) {
      const dlg = dialogo(d, 'executar'); if (!dlg) return;
      const caixa = q(dlg.caixa, '[data-exec-campos]'), ok = q(dlg.caixa, '[data-conf="executar"]');
      const ini = q(dlg.caixa, '[data-exec-ini]'), fim = q(dlg.caixa, '[data-exec-fim]');
      if (titulo) q(dlg.caixa, '[data-exec-titulo]').textContent = 'Fazer a tarefa — ' + titulo;
      // o fim ja vem AGORA e o inicio em branco: e a unica informacao que so a pessoa tem, e
      // deixa-la adivinhar o formato foi o que produziu OS sem data de fim antes.
      fim.value = agoraLocal();
      trava(ok, true, 'carregando…');
      let campos = [];
      try {
        const j = await pedir('/os/api/os/' + d.dataset.wid + '/tarefa/' + tid + '/checklist');
        campos = j.campos || [];
      } catch (e) { caixa.innerHTML = '<p class="os-erro">Não consegui carregar o checklist: ' + esc(e.message) + '</p>'; trava(ok, false, 'Salvar e registrar'); return; }
      trava(ok, false, 'Salvar e registrar');
      if (!campos.length) { caixa.innerHTML = '<p class="det-ajuda">Esta tarefa não tem subtarefas — dá para lançar só o registro.</p>'; }
      else caixa.innerHTML = campos.map((c) => campoHTML(c)).join('');
      ok.addEventListener('click', async () => {
        const valores = {};
        caixa.querySelectorAll('[data-fid]').forEach((el) => { const v = (el.value || '').trim(); if (v) valores[el.dataset.fid] = v; });
        if (!ini.value) { hint(dlg, 'Informe a data e a hora de início da execução.'); return; }
        trava(ok, true, 'gravando…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/tarefa/' + tid + '/executar',
            {valores, inicio: ini.value, fim: fim.value, nota: q(dlg.caixa, '[data-exec-nota]').value});
          dlg.fechar(); await recarregar(d, urlCard(d), j.mensagem, !!j.aviso);
        } catch (e) { trava(ok, false, 'Salvar e registrar'); hint(dlg, 'Não consegui registrar: ' + e.message); }
      });
    },

    // CancelarOSDialog: motivos do Fracttal, observação opcional, a pergunta do app antes de gravar (api.cancel_os)
    async cancelar(d) {
      const dlg = dialogo(d, 'cancelar'); if (!dlg) return;
      const sel = q(dlg.caixa, '[data-canc-motivo]'), obs = q(dlg.caixa, '[data-canc-obs]'), ok = q(dlg.caixa, '[data-conf="cancelar"]');
      hint(dlg, 'carregando motivos…');
      try {
        const j = await pedir('/os/api/os/' + d.dataset.wid + '/cancel-motivos');
        const ms = j.motivos || [];
        sel.innerHTML = '<option value="">— selecione o motivo —</option>' + ms.map((m) => '<option value="' + esc(m.id) + '">' + esc(m.description || '?') + '</option>').join('');
        hint(dlg, ms.length ? '' : '⚠ nenhum motivo retornado pelo Fracttal');
      } catch (e) { hint(dlg, '⚠ ' + e.message); }
      sel.addEventListener('change', () => { ok.disabled = !sel.value; });
      ok.addEventListener('click', async () => {
        if (!sel.value) { hint(dlg, 'Escolha o motivo do cancelamento.'); return; }
        const folio = d.dataset.folio || d.dataset.wid;
        if (!confirm('Confirma o cancelamento da OS ' + folio + '?\nIsto muda o status dela no Fracttal.')) return;
        trava(ok, true); hint(dlg, 'cancelando no Fracttal…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/cancelar', {id_status_custom: numero(sel.value), note: obs.value.trim(), folio});
          dlg.fechar(); await recarregar(d, urlCard(d, 'Cancelada'), j.mensagem);
        } catch (e) { trava(ok, false); hint(dlg, 'Não foi possível cancelar: ' + e.message); }
      });
    },

    // FluxoDialog: só a cadeia; clicar num nó abre o card daquela OS no lugar deste (como o app fecha um e abre o outro)
    async fluxo(d) {
      const dlg = dialogo(d, 'fluxo'); if (!dlg) return;
      const corpo = q(dlg.caixa, '[data-fluxo-corpo]');
      try { pintarFluxo(dlg, await pedir('/os/api/os/' + d.dataset.wid + '/fluxo')); }
      catch (e) { corpo.innerHTML = '<div class="acoes-hint i">' + esc('não consegui montar o fluxo: ' + e.message.slice(0, 140)) + '</div>'; }
      corpo.addEventListener('click', async (e) => {
        const no = e.target.closest('a.acoes-no'); if (!no) return;
        e.preventDefault(); dlg.fechar();
        await recarregar(d, no.getAttribute('href') + '&parcial=1');          // o href já traz ?status=
      });
    },

    'anexos-sub'(d) { return abrirAnexos(d, 'sub', 'Anexos das subtarefas', 'Sem anexos nas subtarefas.'); },
    'anexos-os'(d) { return abrirAnexos(d, 'os', 'Anexos da OS', 'Sem anexos nesta OS.'); }
  };

  function pintarFluxo(dlg, j) {
    q(dlg.caixa, '[data-fluxo-sub]').textContent = j.subtitulo || '—';
    const corpo = q(dlg.caixa, '[data-fluxo-corpo]'); corpo.innerHTML = '';
    const cadeia = j.cadeia || [];
    const faixa = document.createElement('div'); faixa.className = 'acoes-cadeia';
    cadeia.forEach((no, i) => {
      faixa.insertAdjacentHTML('beforeend',
        '<a class="acoes-no' + (no.atual ? ' atual' : '') + '" href="' + esc(no.href) + '">'
        + '<div class="acoes-no-topo"><b>' + esc(no.folio || '—') + '</b>' + (no.atual ? '<span class="acoes-atual">ATUAL</span>' : '') + '</div>'
        + '<div class="acoes-no-tipo">' + esc(no.tipo_tarefa || '—') + '</div><div class="acoes-no-desc">' + esc(no.descricao || '') + '</div>'
        + '<div class="acoes-no-base"><i style="background:' + esc(no.cor) + '"></i><span style="color:' + esc(no.cor) + '">' + esc(no.status || '—') + '</span><small>' + esc(no.data || '') + '</small></div></a>');
      if (i < cadeia.length - 1) faixa.insertAdjacentHTML('beforeend', '<div class="acoes-seta"><span>gerou</span></div>');
    });
    corpo.appendChild(faixa);
    if (cadeia.length <= 1) corpo.insertAdjacentHTML('beforeend', '<div class="acoes-hint i centro">' + esc(j.aviso || 'Esta OS não tem outra ligada a ela — nem como pai, nem como filha.') + '</div>');
  }

  async function abrirAnexos(d, chave, titulo, vazio) {
    const dlg = dialogo(d, 'anexos'); if (!dlg) return;
    q(dlg.caixa, '[data-anx-titulo]').textContent = titulo;
    const corpo = q(dlg.caixa, '[data-anx-corpo]');
    try {
      let j = anexosCache.get(d);
      if (!j) { j = await pedir('/os/api/os/' + d.dataset.wid + '/anexos-lista'); anexosCache.set(d, j); }
      pintarAnexos(dlg, (j[chave] || {itens: []}).itens || [], vazio);
    } catch (e) { corpo.innerHTML = '<div class="acoes-hint">' + esc('não consegui carregar os anexos: ' + e.message) + '</div>'; }
  }

  // GaleriaDialog + DocumentosDialog: fotos e notas de texto juntas (saem da MESMA subtarefa), arquivos com Abrir/Baixar
  function pintarAnexos(dlg, itens, vazio) {
    const imgs = itens.filter((x) => x.tipo === 'imagem'), docs = itens.filter((x) => x.tipo === 'documento'), notas = itens.filter((x) => x.tipo === 'nota');
    q(dlg.caixa, '[data-anx-sub]').textContent = (imgs.length + docs.length) + ' arquivo(s) · ' + notas.length + ' nota(s) de texto';
    const corpo = q(dlg.caixa, '[data-anx-corpo]'); corpo.innerHTML = '';
    if (!itens.length) { corpo.innerHTML = '<div class="acoes-hint">' + esc(vazio) + '</div>'; return; }
    if (imgs.length || notas.length) {
      corpo.insertAdjacentHTML('beforeend', '<div class="acoes-hint">Clique numa foto para ver em tamanho cheio e salvar · clique numa nota para ler o texto.</div>');
      corpo.insertAdjacentHTML('beforeend', '<div class="acoes-fotos">'
        + imgs.map((x) => '<figure class="acoes-foto"><figcaption title="' + esc(x.legenda) + '">' + esc(x.legenda) + '</figcaption>'
          + '<a class="img" href="' + esc(x.url) + '" target="_blank" rel="noopener"><img src="' + esc(x.url) + '" alt="" loading="lazy"></a>'
          + (x.baixar ? '<a class="acoes-baixar" href="' + esc(x.baixar) + '" download="' + esc(x.nome) + '">Baixar</a>' : '') + '</figure>').join('')
        + notas.map((x) => '<details class="acoes-nota"><summary>' + esc(x.legenda || 'nota') + '</summary><pre>' + esc(x.texto || '(nota vazia)') + '</pre></details>').join('')
        + '</div>');
    }
    if (docs.length) {
      corpo.insertAdjacentHTML('beforeend', '<div class="acoes-docs">' + docs.map((x) => {
        const sub = [x.quem, (x.legenda && x.legenda !== x.nome) ? x.legenda : ''].filter(Boolean).join(' · ');
        return '<div class="acoes-doc"><span class="acoes-ext">' + esc(x.ext || 'ARQ') + '</span><div class="acoes-doc-t"><div>' + esc(x.nome) + '</div>'
          + (sub ? '<small>' + esc(sub) + '</small>' : '') + '</div>'
          + '<a class="det-b ghost acoes-mini" href="' + esc(x.url) + '" target="_blank" rel="noopener">Abrir</a>'
          + (x.baixar ? '<a class="det-b ghost acoes-mini" href="' + esc(x.baixar) + '" download="' + esc(x.nome) + '">Baixar</a>' : '') + '</div>';
      }).join('') + '</div>');
    }
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-acao]'); if (!b || b.disabled) return;
    const d = card(b); if (!d) return;
    const fn = ACOES[b.dataset.acao]; if (!fn) return;
    e.preventDefault();
    Promise.resolve(fn(d, b)).catch((err) => mensagem(d, String((err && err.message) || err), true));
  });
  document.addEventListener('keydown', (e) => {          // os cards de anexos são divs com role=button: Enter/Espaço também abrem
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('.det-anexo[data-acao]')) { e.preventDefault(); e.target.click(); }
  });

  function arranque() { document.querySelectorAll('.det').forEach(contagem); }   // página cheia: o card já está na tela
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arranque); else arranque();
  window.OsAcoes = {recarregar, contagem, dialogo};
})();

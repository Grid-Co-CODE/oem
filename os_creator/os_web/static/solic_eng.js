// os_creator/os_web/static/solic_eng.js — a Nova solicitação para a ENGENHARIA (Levi, 06/10/2026). Cascata cliente →
// usina, TODOS os ativos da usina (filtro por texto e por tipo, com o nome no lugar da sigla), uma OS por ativo com
// '[Ativo] - Descrição' — ou, desde 08/10, uma OS com todos os ativos, uma atividade por ativo —, o problema na
// observação, os anexos (08/10), o responsável só entre os da Engenharia e a data programada de 7 dias (Urgente: 2), que
// NÃO se edita: a tela só mostra, e o servidor calcula ao criar. As regras de verdade são do servidor (solic_eng_web.py)
// — aqui é a primeira barreira.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const raiz = $('eng');
  if (!raiz) return;
  const cbCli = $('cb_cli'), cbUsi = $('cb_usi'), busca = $('busca'), cbTipo = $('cb_tipo'), tbody = $('tbody');
  const bAll = $('b_all'), bNone = $('b_none'), selLbl = $('sel_lbl'), edDesc = $('ed_desc'), taProb = $('ta_prob');
  const preview = $('preview'), cbResp = $('cb_resp'), dtProg = $('dt_prog'), ckUrg = $('ck_urg'), lbPrazo = $('lb_prazo');
  const dtEvento = $('dt_evento'), lbAtivos = $('lb_ativos');
  const hintResp = $('hint_resp'), hintCriar = $('hint_criar'), btn = $('btn_criar'), resultado = $('resultado');
  const bAnexar = $('b_anexar'), anexoIn = $('anexo_in'), listaAnexo = $('anexo_lista'), regras = $('anexo_regras');
  const hintAnexo = $('hint_anexo');
  const modos = Array.from(raiz.querySelectorAll('input[name="eng_modo"]'));
  const DIAS = Number(raiz.dataset.dias), DIAS_URG = Number(raiz.dataset.diasUrgente);
  // os limites dos anexos são os do servidor (vêm no HTML): o navegador recusa antes, o servidor confere de novo
  const MB = 1024 * 1024, ANEXO_MAX = Number(raiz.dataset.anexoMax), ANEXO_MB = Number(raiz.dataset.anexoMb);
  const ANEXO_TOTAL_MB = Number(raiz.dataset.anexoTotalMb), ENVIOS = Number(raiz.dataset.anexoEnvios);
  const ENVIOS_MB = Number(raiz.dataset.anexoEnviosMb);
  const ACEITOS = new Set(String(raiz.dataset.anexoAceitar || '').split(',').filter(Boolean));
  // A OS agrupada e os anexos só ligam quando o HTML veio do servidor desta versão (traz os limites e os elementos). A
  // sincronia troca os arquivos sem reiniciar o serviço (o 5090, o Nexus): até o reinício, o Python e o HTML guardado em
  // memória são os de antes, e este .js já é o novo. Sem a conferência, um elemento que falta derrubava a tela inteira, e
  // o "Uma OS com todos os ativos" iria a um servidor que não o conhece — e sairia uma OS por ativo.
  const NOVO = !!(raiz.dataset.anexoMax && lbAtivos && bAnexar && anexoIn && listaAnexo && regras && hintAnexo && modos.length);
  if (!NOVO) raiz.querySelectorAll('.eng-modo, .eng-anexos').forEach((x) => { x.hidden = true; });
  let ativos = [], pessoas = [], criando = false, arquivos = [];
  const marcados = new Set();
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const semAcento = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  async function pedir(url, opcoes, texto) {
    const r = await OsCarga.buscar(url, Object.assign({credentials: 'same-origin', headers: {'Accept': 'application/json'}}, opcoes || {}), texto);
    let j = null;
    try { j = await r.json(); } catch (e) { j = null; }
    if (!r.ok) throw new Error((j && (j.erro || j.mensagem)) || ('HTTP ' + r.status));
    return j || {};
  }
  function mostrar(texto, ruim) {
    resultado.hidden = !texto; resultado.textContent = texto || ''; resultado.classList.toggle('ruim', !!ruim);
  }

  // ── cascata ────────────────────────────────────────────────────────────────────────────────────────
  function semAtivos(texto) {
    ativos = []; marcados.clear();
    cbTipo.innerHTML = '<option value="">Todos os tipos</option>';
    [busca, cbTipo, bAll, bNone].forEach((x) => { x.disabled = true; });
    tbody.innerHTML = '<tr class="vazio"><td colspan="3">' + esc(texto) + '</td></tr>';
    contar();
  }
  async function trocarCliente() {
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/usinas?cliente=' + encodeURIComponent(cbCli.value), null, 'Carregando as usinas…');
      const antes = cbUsi.value, us = j.usinas || [];
      cbUsi.innerHTML = '<option value="">— Selecione a usina —</option>'
        + us.map((u) => '<option value="' + esc(u) + '">' + esc(u) + '</option>').join('');
      if (us.indexOf(antes) >= 0) cbUsi.value = antes;
      else { cbUsi.value = ''; semAtivos('Selecione a usina para carregar os ativos.'); }
    } catch (e) { mostrar('Não consegui carregar as usinas: ' + e.message, true); }
  }
  async function trocarUsina() {
    if (!cbUsi.value) { semAtivos('Selecione a usina para carregar os ativos.'); return; }
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/ativos?usina=' + encodeURIComponent(cbUsi.value), null, 'Buscando os ativos da usina…');
      ativos = j.ativos || []; marcados.clear();
      cbTipo.innerHTML = '<option value="">Todos os tipos</option>'
        + (j.tipos || []).map((t) => '<option value="' + esc(t.tipo) + '">' + esc(t.nome) + '</option>').join('');
      [busca, cbTipo, bAll, bNone].forEach((x) => { x.disabled = false; });
      busca.value = '';
      pintar();
    } catch (e) { semAtivos('Não consegui carregar os ativos: ' + e.message); }
  }

  // ── a tabela ───────────────────────────────────────────────────────────────────────────────────────
  function visiveis() {
    const q = semAcento(busca.value.trim()), t = cbTipo.value;
    return ativos.filter((a) => (!t || a.tipo === t) && (!q || semAcento(a.label + ' ' + a.code).indexOf(q) >= 0));
  }
  function pintar() {
    const vs = visiveis();
    if (!ativos.length) tbody.innerHTML = '<tr class="vazio"><td colspan="3">Esta usina não tem ativos no catálogo.</td></tr>';
    else if (!vs.length) tbody.innerHTML = '<tr class="vazio"><td colspan="3">Nenhum ativo com esse filtro.</td></tr>';
    else {
      tbody.innerHTML = vs.map((a) => '<tr data-id="' + esc(a.id) + '"' + (marcados.has(String(a.id)) ? ' class="sel"' : '') + '>'
        + '<td class="c-chk"><input type="checkbox"' + (marcados.has(String(a.id)) ? ' checked' : '') + ' aria-label="Marcar ' + esc(a.label) + '"></td>'
        + '<td>' + esc(a.label) + '</td><td>' + esc(a.tipo_nome) + '</td></tr>').join('');
    }
    contar();
  }
  function contar() {
    selLbl.textContent = marcados.size + ' marcado(s)';
    const primeiro = ativos.find((a) => marcados.has(String(a.id)));
    const d = edDesc.value.trim() || 'Descrição', mais = marcados.size - 1;
    // na OS agrupada o '[Ativo] - Descrição' é o nome de cada atividade; na de uma OS por ativo, o de cada OS
    const resto = mais < 1 ? '' : agrupar()
      ? '   (+' + mais + (mais > 1 ? ' atividades' : ' atividade') + ' na mesma OS, uma por ativo)'
      : '   (+' + mais + ' OS, uma por ativo)';
    preview.textContent = primeiro ? 'Ex.: [' + (primeiro.curto || primeiro.label) + '] - ' + d + resto
      : 'O prefixo [Ativo] entra automático em cada ' + (agrupar() ? 'atividade.' : 'OS.');
  }
  tbody.addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-id]');
    if (!tr) return;
    const ck = tr.querySelector('input[type=checkbox]');
    if (e.target !== ck) ck.checked = !ck.checked;          // clicar na linha também marca
    const id = tr.dataset.id;
    if (ck.checked) marcados.add(id); else marcados.delete(id);
    tr.classList.toggle('sel', ck.checked);
    contar();
  });
  bAll.addEventListener('click', () => { visiveis().forEach((a) => marcados.add(String(a.id))); pintar(); });
  bNone.addEventListener('click', () => { marcados.clear(); pintar(); });
  busca.addEventListener('input', pintar);
  cbTipo.addEventListener('change', pintar);
  cbCli.addEventListener('change', trocarCliente);
  cbUsi.addEventListener('change', trocarUsina);
  edDesc.addEventListener('input', contar);

  // ── uma OS por ativo × uma OS com todos (Levi, 08/10/2026: "Agrupar ativos em atividades por OS") ─────────────
  function agrupar() { const m = NOVO && modos.find((r) => r.checked); return !!m && m.value === 'agrupada'; }
  function trocarModo() {
    modos.forEach((r) => r.closest('.eng-modo-op').classList.toggle('on', r.checked));
    lbAtivos.textContent = agrupar() ? '(marque um ou vários — todos numa OS, uma atividade por ativo)'
                                     : '(marque um ou vários — cada um vira uma OS)';
    contar(); regrasAnexo();
  }
  if (NOVO) modos.forEach((r) => r.addEventListener('change', trocarModo));

  // ── anexos (Levi, 08/10/2026: "Engenharia poder anexar arquivos") ─────────────────────────────────────────────
  // Tipo pela extensão, tamanho, quantidade e total, com os números do servidor; o conteúdo, só ele confere.
  const extDe = (nome) => { const m = /\.[^.]+$/.exec(String(nome || '')); return m ? m[0].toLowerCase() : ''; };
  // para CIMA, como no servidor: 10 MB e 5 bytes é "10,1 MB", e não "10,0 MB" recusado por passar de 10 MB
  const tam = (n) => (n < MB ? Math.max(1, Math.ceil(n / 1024)) + ' KB' : (Math.ceil(n * 10 / MB) / 10).toFixed(1).replace('.', ',') + ' MB');
  const soma = () => arquivos.reduce((t, f) => t + f.size, 0);
  function avisarAnexo(txt) { if (NOVO) { hintAnexo.textContent = txt || ''; hintAnexo.hidden = !txt; } }
  function regrasAnexo() {
    if (!NOVO) return;
    regras.textContent = 'Até ' + ANEXO_MAX + ' arquivos, ' + ANEXO_MB + ' MB cada e ' + ANEXO_TOTAL_MB + ' MB no total — '
      + (agrupar() ? 'os anexos vão para a OS.' : 'cada anexo vai para cada OS criada.')
      + (arquivos.length ? ' Escolhidos: ' + arquivos.length + ' (' + tam(soma()) + ').' : '');
  }
  function pintarAnexos() {
    if (!NOVO) return;
    listaAnexo.hidden = !arquivos.length;
    listaAnexo.innerHTML = arquivos.map((f, i) => '<li><span class="eng-anexo-ext">' + esc(extDe(f.name).slice(1).toUpperCase()) + '</span>'
      + '<span class="eng-anexo-nome" title="' + esc(f.name) + '">' + esc(f.name) + '</span>'
      + '<span class="eng-anexo-tam">' + tam(f.size) + '</span>'
      + '<button type="button" class="eng-anexo-x" data-i="' + i + '" title="Tirar este anexo" aria-label="Tirar ' + esc(f.name) + '">×</button></li>').join('');
    regrasAnexo();
  }
  function addArquivos(lista) {
    const fora = [];
    Array.from(lista || []).forEach((f) => {
      if (arquivos.some((x) => x.name === f.name && x.size === f.size)) return;     // o mesmo arquivo escolhido de novo
      if (!ACEITOS.has(extDe(f.name))) fora.push('“' + f.name + '” (tipo não aceito)');
      else if (!f.size) fora.push('“' + f.name + '” (vazio)');
      else if (f.size > ANEXO_MB * MB) fora.push('“' + f.name + '” (' + tam(f.size) + '; o limite é ' + ANEXO_MB + ' MB por arquivo)');
      else if (arquivos.length >= ANEXO_MAX) fora.push('“' + f.name + '” (o limite é ' + ANEXO_MAX + ' arquivos)');
      else if (soma() + f.size > ANEXO_TOTAL_MB * MB) fora.push('“' + f.name + '” (passaria de ' + ANEXO_TOTAL_MB + ' MB no total)');
      else arquivos.push(f);
    });
    avisarAnexo(fora.length ? 'Ficou de fora: ' + fora.join('; ') + '.' : '');
    pintarAnexos();
  }
  if (NOVO) {
    bAnexar.addEventListener('click', () => anexoIn.click());
    anexoIn.addEventListener('change', () => { addArquivos(anexoIn.files); anexoIn.value = ''; });
    listaAnexo.addEventListener('click', (e) => {
      const b = e.target.closest('.eng-anexo-x');
      if (!b) return;
      const i = Number(b.dataset.i);
      arquivos.splice(i, 1);
      avisarAnexo(''); pintarAnexos();
      // o foco não cai no vazio: vai para o "tirar" que ocupou o lugar, ou para o botão de adicionar
      const xs = listaAnexo.querySelectorAll('.eng-anexo-x');
      (xs[Math.min(i, xs.length - 1)] || bAnexar).focus();
    });
  }

  // ── responsável e data ─────────────────────────────────────────────────────────────────────────────
  async function carregarResponsaveis() {
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/responsaveis', null, 'Carregando os responsáveis…');
      pessoas = j.pessoas || [];
      cbResp.innerHTML = '<option value="">— Selecione —</option>'
        + pessoas.map((p) => '<option value="' + esc(p.id_personnel) + '">' + esc(p.name) + '</option>').join('');
      cbResp.disabled = !pessoas.length;
      if (!j.configurado) hintResp.textContent = 'A lista da Engenharia não está configurada (OS_WEB_ENGENHARIA_RESPONSAVEIS no .env do servidor).';
      else if ((j.faltam || []).length) hintResp.textContent = 'Não achei no Fracttal: ' + j.faltam.join(', ') + '.';
      else hintResp.textContent = '';
    } catch (e) {
      cbResp.innerHTML = '<option value="">não carregou</option>';
      hintResp.textContent = 'Não consegui carregar os responsáveis: ' + e.message;
    }
  }
  // A data programada NÃO se edita (Levi, 06/10): a tela só mostra a hora da criação + 7 dias (Urgente: + 2). A base é a
  // hora do servidor quando a página abriu, andando com o relógio daqui — com a página aberta por muito tempo, a data
  // mostrada continua sendo a que o servidor vai pôr ao criar (é ele quem põe; a tela não manda data nenhuma).
  const m0 = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(raiz.dataset.agora || '');
  const BASE = m0 ? Date.UTC(+m0[1], +m0[2] - 1, +m0[3], +m0[4], +m0[5], +(m0[6] || 0)) : null, T0 = Date.now();
  const p2 = (n) => String(n).padStart(2, '0');
  function dataProg() {
    if (BASE === null) return dtProg.textContent;
    const d = new Date(BASE + (Date.now() - T0) + (ckUrg.checked ? DIAS_URG : DIAS) * 864e5);
    return p2(d.getUTCDate()) + '/' + p2(d.getUTCMonth() + 1) + '/' + d.getUTCFullYear() + ' ' + p2(d.getUTCHours()) + ':' + p2(d.getUTCMinutes());
  }
  function mostrarData() {
    const urg = ckUrg.checked;
    raiz.classList.toggle('eng-e-urgente', urg);
    dtProg.textContent = dataProg();
    lbPrazo.textContent = '(automática' + (urg ? ', urgente' : '') + ': ' + (urg ? DIAS_URG : DIAS) + ' dias a partir da criação)';
  }
  ckUrg.addEventListener('change', mostrarData);
  setInterval(mostrarData, 30000);

  // ── criar ──────────────────────────────────────────────────────────────────────────────────────────
  function falta() {
    if (!marcados.size) return 'Marque ao menos um ativo.';
    if (!edDesc.value.trim()) return 'Escreva a atividade a ser realizada (o nome da OS).';
    if (!taProb.value.trim()) return 'Descreva o problema.';
    if (!cbResp.value) return 'Escolha o responsável da Engenharia.';
    if (!dtEvento.value) return 'Informe a data do evento.';
    if (arquivos.length && !agrupar()) {                   // cada anexo sobe para cada OS: a mesma conta do servidor
      const n = marcados.size, envios = arquivos.length * n, volume = soma() * n;
      if (envios > ENVIOS || volume > ENVIOS_MB * MB)
        return 'Com uma OS por ativo, cada anexo sobe para cada OS: ' + n + ' OS × ' + arquivos.length + ' anexo(s) = '
          + envios + ' envios (' + tam(volume) + '). O limite é ' + ENVIOS + ' envios e ' + ENVIOS_MB
          + ' MB: escolha “Uma OS com todos os ativos” ou anexe menos arquivos.';
    }
    return '';
  }
  const evBr = (v) => { const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(v || ''); return m ? m[3] + '/' + m[2] + '/' + m[1] + ' ' + m[4] : v; };
  btn.addEventListener('click', async () => {
    if (criando) return;
    const erro = falta();
    hintCriar.textContent = erro;
    if (erro) return;
    const resp = pessoas.find((p) => String(p.id_personnel) === cbResp.value) || {};
    const n = marcados.size, urg = ckUrg.checked, agr = agrupar() && n > 1;     // com 1 ativo, as duas dão a mesma OS
    const frase = agr
      ? 'Vou criar 1 OS com ' + n + ' atividades — uma por ativo — para a Engenharia, atribuída a ' + resp.name
        + ', com o evento em ' + evBr(dtEvento.value) + ' e programada para ' + dataProg() + (urg ? ' (URGENTE)' : '') + '.'
      : 'Vou criar ' + n + ' OS — uma por ativo — para a Engenharia, atribuída' + (n > 1 ? 's' : '') + ' a ' + resp.name
        + ', com o evento em ' + evBr(dtEvento.value) + ' e programada' + (n > 1 ? 's' : '') + ' para ' + dataProg()
        + (urg ? ' (URGENTE)' : '') + '.';
    const nomes = arquivos.map((f) => f.name).join(', ');
    const fraseAnexos = !arquivos.length ? '' : '\n\n' + (agr || n === 1 ? 'A OS recebe ' : 'Cada OS recebe ')
      + (arquivos.length === 1 ? 'o anexo ' : 'os ' + arquivos.length + ' anexos: ') + nomes + '.';
    if (!confirm(frase + fraseAnexos + '\n\nContinuar?')) return;
    const dados = {ativos: Array.from(marcados), descricao: edDesc.value, problema: taProb.value,
                   responsavel: {id_personnel: resp.id_personnel}, evento: dtEvento.value, urgente: urg, agrupar: agr};
    let opcoes;
    if (arquivos.length) {                                 // com anexo: multipart, o MESMO JSON no campo payload
      const fd = new FormData();
      fd.append('payload', JSON.stringify(dados));
      arquivos.forEach((f) => fd.append('anexos', f, f.name));
      opcoes = {method: 'POST', body: fd};                  // sem Content-Type: o navegador põe o do multipart
    } else {
      opcoes = {method: 'POST', headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
                body: JSON.stringify(dados)};
    }
    criando = true; btn.disabled = true; mostrar('');
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/criar', opcoes,
                            arquivos.length ? 'Criando as OS e subindo os anexos…' : 'Criando as OS no Fracttal…');
      mostrar(j.mensagem + ((j.avisos || []).length ? '\n\n' + j.avisos.join('\n') : ''), j.falhas > 0 || j.anexos_falhas > 0);
      // o que foi criado sai da seleção (um 2º clique não duplica), e os anexos já foram com ele
      marcados.clear(); arquivos = []; avisarAnexo(''); pintarAnexos(); pintar();
    } catch (e) { mostrar(e.message, true); }
    finally { criando = false; btn.disabled = false; }
  });

  carregarResponsaveis();
})();

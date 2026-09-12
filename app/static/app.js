(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => root.querySelectorAll(sel);

  /* ===== DOM refs ===== */
  const titleInput        = $('#title');
  const titleEdit         = $('#title-edit');
  const detailEditor      = $('#detail-editor');
  const btnEditTitle      = $('#btn-edit-title');
  const btnCompare        = $('#btn-compare');
  const btnReset          = $('#btn-reset');
  const statusMsg         = $('#status');
  const resultsSection    = $('#results');
  const changeCount       = $('#change-count');
  const changesRoot       = $('#changes');
  const progressOverlay = $('#progress-overlay');
  const progressFill      = $('#progress-fill');
  const progressText      = $('#progress-text');
  const progressPct       = $('#progress-pct');
  const severityPills     = $('#severity-pills');
  const categoryPills     = $('#category-pills');
  const toastContainer    = $('#toast-container');
  const viewCompare       = $('#view-compare');
  const viewHistory       = $('#view-history');
  const historyList       = $('#history-list');
  const ambientBackground = $('.ambient-background');
  const ambientCanvas     = $('#ambient-canvas');

  /* ===== High-DPI Clause Graph background ===== */
  function initAmbientCanvas() {
    if (!ambientBackground || !ambientCanvas) return;

    const context = ambientCanvas.getContext('2d', { alpha: true, desynchronized: true });
    if (!context) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const finePointer = window.matchMedia('(pointer: fine)');
    const compactViewport = window.matchMedia('(max-width: 768px)');
    const prefersContrast = window.matchMedia('(prefers-contrast: more)');
    const forcedColors = window.matchMedia('(forced-colors: active)');
    const lowPowerDevice = (navigator.deviceMemory && navigator.deviceMemory <= 4)
      || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4);
    const colors = [
      [79, 70, 229],
      [6, 182, 212],
      [139, 92, 246],
    ];
    const settings = {
      maxPixels: lowPowerDevice ? 4000000 : 8000000,
      maxDevicePixelRatio: lowPowerDevice ? 1.25 : 2,
      nodeCount: lowPowerDevice ? 36 : 54,
      frameDuration: 1000 / (lowPowerDevice ? 30 : 60),
    };
    const state = {
      width: 0,
      height: 0,
      scale: 1,
      nodes: [],
      glows: [],
      frame: 0,
      resizeFrame: 0,
      lastFrame: 0,
      running: false,
      pointerListening: false,
      pointer: { x: 0, y: 0, targetX: 0, targetY: 0 },
    };

    function seededRandom(seed) {
      return () => {
        let value = seed += 0x6D2B79F5;
        value = Math.imul(value ^ (value >>> 15), value | 1);
        value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
        return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
      };
    }

    function createGlow(color) {
      const size = 160;
      const glow = document.createElement('canvas');
      glow.width = size;
      glow.height = size;
      const glowContext = glow.getContext('2d');
      const gradient = glowContext.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
      gradient.addColorStop(0, `rgba(${color.join(', ')}, 0.36)`);
      gradient.addColorStop(0.28, `rgba(${color.join(', ')}, 0.15)`);
      gradient.addColorStop(1, `rgba(${color.join(', ')}, 0)`);
      glowContext.fillStyle = gradient;
      glowContext.fillRect(0, 0, size, size);
      return glow;
    }

    function createNodes() {
      const random = seededRandom(Math.round(state.width * 31 + state.height * 17));
      const horizontalInset = Math.min(110, state.width * 0.1);
      const verticalInset = Math.min(90, state.height * 0.12);

      state.nodes = Array.from({ length: settings.nodeCount }, (_, index) => ({
        x: horizontalInset + random() * Math.max(1, state.width - horizontalInset * 2),
        y: verticalInset + random() * Math.max(1, state.height - verticalInset * 2),
        velocityX: (random() - 0.5) * 0.24,
        velocityY: (random() - 0.5) * 0.2,
        radius: 1.2 + random() * 1.65,
        phase: random() * Math.PI * 2,
        orbit: 0.35 + random() * 0.8,
        colorIndex: index % colors.length,
      }));
    }

    function resizeCanvas() {
      const width = Math.max(1, window.innerWidth);
      const height = Math.max(1, window.innerHeight);
      // Keep the procedural vector effect crisp on dense displays without allocating a literal 16K framebuffer.
      const desiredScale = Math.min(window.devicePixelRatio || 1, settings.maxDevicePixelRatio);
      const pixelBudgetScale = Math.sqrt(settings.maxPixels / (width * height));
      const scale = Math.min(desiredScale, pixelBudgetScale);
      if (width === state.width && height === state.height && Math.abs(scale - state.scale) < 0.001) return;

      state.width = width;
      state.height = height;
      state.scale = scale;
      ambientCanvas.width = Math.max(1, Math.round(width * scale));
      ambientCanvas.height = Math.max(1, Math.round(height * scale));
      context.setTransform(scale, 0, 0, scale, 0, 0);

      state.pointer.x = state.pointer.targetX = width * 0.68;
      state.pointer.y = state.pointer.targetY = height * 0.28;
      createNodes();
    }

    function scheduleResize() {
      if (state.resizeFrame) return;
      state.resizeFrame = window.requestAnimationFrame(() => {
        state.resizeFrame = 0;
        resizeCanvas();
        syncAnimation();
      });
    }

    function updateNodes(delta, timestamp) {
      const pointer = state.pointer;
      pointer.x += (pointer.targetX - pointer.x) * Math.min(1, 0.055 * delta);
      pointer.y += (pointer.targetY - pointer.y) * Math.min(1, 0.055 * delta);
      const influenceRadius = Math.min(285, Math.max(180, state.width * 0.19));
      const influenceRadiusSquared = influenceRadius * influenceRadius;
      const edge = 18;

      state.nodes.forEach(node => {
        const waveX = Math.cos(timestamp * 0.00022 + node.phase) * 0.07 * node.orbit;
        const waveY = Math.sin(timestamp * 0.00018 + node.phase * 1.4) * 0.06 * node.orbit;
        node.x += (node.velocityX + waveX) * delta;
        node.y += (node.velocityY + waveY) * delta;

        const dx = node.x - pointer.x;
        const dy = node.y - pointer.y;
        const distanceSquared = dx * dx + dy * dy;
        if (distanceSquared && distanceSquared < influenceRadiusSquared) {
          const distance = Math.sqrt(distanceSquared);
          const force = (1 - distance / influenceRadius) * 0.65 * delta;
          node.x += (dx / distance) * force;
          node.y += (dy / distance) * force;
        }

        if (node.x < edge || node.x > state.width - edge) node.velocityX *= -1;
        if (node.y < edge || node.y > state.height - edge) node.velocityY *= -1;
        node.x = Math.min(state.width - edge, Math.max(edge, node.x));
        node.y = Math.min(state.height - edge, Math.max(edge, node.y));
      });
    }

    function drawLens(timestamp) {
      const pointer = state.pointer;
      const centerX = state.width * 0.67 + (pointer.x - state.width / 2) * 0.045;
      const centerY = state.height * 0.42 + (pointer.y - state.height / 2) * 0.035;
      const baseRadius = Math.min(state.width, state.height) * 0.18;
      const glowSize = baseRadius * 4.2;

      context.save();
      context.globalAlpha = 0.32;
      context.drawImage(state.glows[0], centerX - glowSize / 2, centerY - glowSize / 2, glowSize, glowSize);
      context.lineWidth = 0.8;
      context.setLineDash([1.5, 10]);
      for (let ring = 0; ring < 3; ring += 1) {
        const radius = baseRadius * (0.56 + ring * 0.33) + Math.sin(timestamp * 0.00055 + ring) * 4;
        context.strokeStyle = `rgba(79, 70, 229, ${0.07 - ring * 0.012})`;
        context.lineDashOffset = -timestamp * 0.007 * (ring + 1);
        context.beginPath();
        context.arc(centerX, centerY, radius, 0, Math.PI * 2);
        context.stroke();
      }
      context.setLineDash([]);
      context.restore();
    }

    function drawConnections(timestamp) {
      const linkDistance = Math.min(250, Math.max(175, state.width * 0.17));
      const linkDistanceSquared = linkDistance * linkDistance;

      context.save();
      context.lineWidth = 0.6;
      for (let first = 0; first < state.nodes.length; first += 1) {
        const source = state.nodes[first];
        for (let second = first + 1; second < state.nodes.length; second += 1) {
          const target = state.nodes[second];
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const distanceSquared = dx * dx + dy * dy;
          if (distanceSquared >= linkDistanceSquared) continue;

          const proximity = 1 - distanceSquared / linkDistanceSquared;
          const color = colors[source.colorIndex];
          const bend = Math.sin(timestamp * 0.00038 + source.phase + target.phase) * 9;
          context.strokeStyle = `rgba(${color.join(', ')}, ${Math.pow(proximity, 1.7) * 0.19})`;
          context.beginPath();
          context.moveTo(source.x, source.y);
          context.quadraticCurveTo(
            (source.x + target.x) / 2 - dy / 18,
            (source.y + target.y) / 2 + dx / 18 + bend,
            target.x,
            target.y
          );
          context.stroke();
        }
      }
      context.restore();
    }

    function drawNodes() {
      context.save();
      state.nodes.forEach(node => {
        const color = colors[node.colorIndex];
        const glowSize = node.radius * 17;
        context.globalAlpha = 0.65;
        context.drawImage(
          state.glows[node.colorIndex],
          node.x - glowSize / 2,
          node.y - glowSize / 2,
          glowSize,
          glowSize
        );
        context.globalAlpha = 0.72;
        context.fillStyle = `rgb(${color.join(', ')})`;
        context.beginPath();
        context.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        context.fill();
      });
      context.restore();
    }

    function drawFrame(timestamp) {
      context.clearRect(0, 0, state.width, state.height);
      drawLens(timestamp);
      drawConnections(timestamp);
      drawNodes();
    }

    function render(timestamp) {
      if (!state.running) return;
      const elapsed = timestamp - state.lastFrame;
      if (elapsed >= settings.frameDuration - 0.5) {
        const delta = Math.min(2.2, elapsed / 16.667);
        state.lastFrame = timestamp;
        updateNodes(delta, timestamp);
        drawFrame(timestamp);
      }
      state.frame = window.requestAnimationFrame(render);
    }

    function canAnimate() {
      return !document.hidden
        && !reduceMotion.matches
        && finePointer.matches
        && !compactViewport.matches
        && !prefersContrast.matches
        && !forcedColors.matches;
    }

    function start() {
      if (state.running) return;
      resizeCanvas();
      state.running = true;
      state.lastFrame = performance.now();
      state.frame = window.requestAnimationFrame(render);
    }

    function stop() {
      state.running = false;
      if (state.frame) window.cancelAnimationFrame(state.frame);
      state.frame = 0;
    }

    function onPointerMove(event) {
      state.pointer.targetX = event.clientX;
      state.pointer.targetY = event.clientY;
    }

    function syncPointerListener(active) {
      if (active && !state.pointerListening) {
        window.addEventListener('pointermove', onPointerMove, { passive: true });
        state.pointerListening = true;
      } else if (!active && state.pointerListening) {
        window.removeEventListener('pointermove', onPointerMove);
        state.pointerListening = false;
      }
    }

    function syncAnimation() {
      const active = canAnimate();
      ambientBackground.classList.toggle('is-paused', !active);
      syncPointerListener(active);
      if (active) start();
      else stop();
    }

    function watch(query, callback) {
      if (query.addEventListener) query.addEventListener('change', callback);
      else query.addListener(callback);
    }

    state.glows = colors.map(createGlow);
    resizeCanvas();
    syncAnimation();
    window.addEventListener('resize', scheduleResize, { passive: true });
    document.addEventListener('visibilitychange', syncAnimation);
    watch(reduceMotion, syncAnimation);
    watch(finePointer, syncAnimation);
    watch(compactViewport, syncAnimation);
    watch(prefersContrast, syncAnimation);
    watch(forcedColors, syncAnimation);
  }

  initAmbientCanvas();

  /* ===== State ===== */
  let currentChanges  = [];
  let activeSeverity  = 'all';
  let activeCategory  = 'all';
  let uploadedFiles   = { baseline: null, candidate: null };

  /* ===== Toast notifications ===== */
  function toast(message, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast${type !== 'info' ? ` toast-${type}` : ''}`;
    el.textContent = message;
    toastContainer.appendChild(el);
    setTimeout(() => {
      el.classList.add('removing');
      el.addEventListener('animationend', () => el.remove());
    }, 3000);
  }

  /* ===== Navigation ===== */
  $$('.nav-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const view = pill.dataset.view;
      $$('.nav-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      viewCompare.classList.toggle('hidden', view !== 'compare');
      viewHistory.classList.toggle('hidden', view !== 'history');
      if (view === 'history') renderHistory();
    });
  });

  /* ===== Derive document title from filename ===== */
  function titleFromFilename(name) {
    return name
      .replace(/\.[^.]+$/, '')
      .replace(/[_\-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function syncHiddenInputs() {
    titleInput.value = titleEdit.value || titleFromFilename(uploadedFiles.baseline?.name || 'Document');
  }

  /* ===== Upload zones ===== */
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function setupZone(zoneEl, role) {
    const input      = $('.drop-input', zoneEl);
    const idle       = $('.drop-zone-idle', zoneEl);
    const active     = $('.drop-zone-active', zoneEl);
    const chipName   = $('.file-chip-name', zoneEl);
    const chipSize   = $('.file-chip-size', zoneEl);
    const removeBtn  = $('.file-chip-remove', zoneEl);

    function setFile(file) {
      if (!file) return;
      uploadedFiles[role] = file;
      chipName.textContent = file.name;
      chipName.title = file.name;
      chipSize.textContent = formatSize(file.size);
      idle.classList.add('hidden');
      active.classList.remove('hidden');
      zoneEl.classList.add('has-file');
      if (role === 'baseline' && !titleEdit.value) {
        titleEdit.value = titleFromFilename(file.name);
      }
      updateCompareButton();
      toast(`${file.name} ready`, 'success');
    }

    function clearFile() {
      uploadedFiles[role] = null;
      input.value = '';
      idle.classList.remove('hidden');
      active.classList.add('hidden');
      zoneEl.classList.remove('has-file');
      updateCompareButton();
    }

    input.addEventListener('change', () => {
      if (input.files.length) setFile(input.files[0]);
    });

    removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      clearFile();
    });

    zoneEl.addEventListener('dragover', (e) => {
      e.preventDefault();
      zoneEl.classList.add('dragover');
    });
    zoneEl.addEventListener('dragleave', () => zoneEl.classList.remove('dragover'));
    zoneEl.addEventListener('drop', (e) => {
      e.preventDefault();
      zoneEl.classList.remove('dragover');
      if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
    });
  }

  setupZone($('#zone-baseline'), 'baseline');
  setupZone($('#zone-candidate'), 'candidate');

  /* ===== Auto-enable compare button ===== */
  function updateCompareButton() {
    const ready = uploadedFiles.baseline && uploadedFiles.candidate;
    btnCompare.disabled = !ready;
  }

  /* ===== Edit details toggle ===== */
  btnEditTitle.addEventListener('click', () => {
    detailEditor.classList.toggle('hidden');
    btnEditTitle.textContent = detailEditor.classList.contains('hidden')
      ? 'Edit title'
      : 'Hide title';
  });

  /* ===== Severity filter ===== */
  severityPills.addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip');
    if (!chip) return;
    $$('.filter-chip', severityPills).forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    activeSeverity = chip.dataset.severity;
    renderChanges();
  });

  /* ===== Category filter ===== */
  categoryPills.addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip');
    if (!chip) return;
    $$('.filter-chip', categoryPills).forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    activeCategory = chip.dataset.category;
    renderChanges();
  });

  /* ===== Utilities ===== */
  function setStatus(message, isError = false) {
    statusMsg.textContent = message;
    statusMsg.className = isError ? 'status-msg error' : 'status-msg';
  }

  function setProgress(pct, text) {
    progressFill.style.width = pct + '%';
    progressText.textContent = text;
    progressPct.textContent = Math.round(pct) + '%';
  }

  function showProgress() { progressOverlay.classList.remove('hidden', 'hiding'); }
  function hideProgress() {
    progressOverlay.classList.add('hiding');
    progressOverlay.addEventListener('animationend', () => {
      progressOverlay.classList.add('hidden');
      progressOverlay.classList.remove('hiding');
    }, { once: true });
  }

  function esc(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  async function apiJson(url, options) {
    const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `Request failed (${res.status}).`);
    return body;
  }

  async function apiUpload(url, formData) {
    const res = await fetch(url, { method: 'POST', body: formData });
    let body;
    try { body = await res.json(); } catch { throw new Error(`Server error (${res.status}). Check the terminal for details.`); }
    if (!res.ok) throw new Error(body.detail || `Upload failed (${res.status}).`);
    return body;
  }

  /* ===== Validation ===== */
  function validate() {
    if (!uploadedFiles.baseline) { setStatus('Please upload the baseline document.', true); return false; }
    if (!uploadedFiles.candidate) { setStatus('Please upload the revised document.', true); return false; }
    syncHiddenInputs();
    return true;
  }

  /* ===== Comparison flow ===== */
  async function runComparison() {
    if (!validate()) return;
    btnCompare.disabled = true;
    setStatus('');
    resultsSection.classList.add('hidden');
    showProgress();

    const title = titleInput.value.trim();

    try {
      setProgress(10, 'Uploading baseline document...');
      const baselineForm = new FormData();
      baselineForm.append('title', title);
      baselineForm.append('file', uploadedFiles.baseline);
      const documentData = await apiUpload('/api/v1/documents', baselineForm);
      const baselineVersion = documentData.versions[0];

      setProgress(35, 'Uploading revised document...');
      const candidateForm = new FormData();
      candidateForm.append('file', uploadedFiles.candidate);
      const candidateVersion = await apiUpload(
        `/api/v1/documents/${documentData.id}/versions`,
        candidateForm
      );

      setProgress(60, 'Analyzing changes and assessing risk...');
      const comparison = await apiJson('/api/v1/comparisons', {
        method: 'POST',
        body: JSON.stringify({
          baseline_version_id: baselineVersion.id,
          candidate_version_id: candidateVersion.id,
        }),
      });

      setProgress(100, 'Complete');
      displayComparison(comparison);
      setTimeout(() => hideProgress(), 500);

      const high = currentChanges.filter(c => c.assessment?.severity === 'high').length;
      toast(`Found ${currentChanges.length} changes — ${high} high risk`, high > 0 ? 'error' : 'success');
    } catch (error) {
      hideProgress();
      setStatus(error.message, true);
      toast(error.message, 'error');
    } finally {
      btnCompare.disabled = false;
      updateCompareButton();
    }
  }

  /* ===== Animated count-up for stat numbers ===== */
  function animateCount(el, target, suffix = '') {
    const duration = 600;
    const start = performance.now();
    const from = 0;
    function tick(now) {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(from + (target - from) * ease) + suffix;
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  /* ===== Display comparison results ===== */
  function displayComparison(comparison) {
    currentChanges = comparison.changes;

    const high   = currentChanges.filter(c => c.assessment?.severity === 'high').length;
    const medium = currentChanges.filter(c => c.assessment?.severity === 'medium').length;
    const low    = currentChanges.filter(c => c.assessment?.severity === 'low').length;

    animateCount($('#stat-total'), currentChanges.length);
    animateCount($('#stat-high'), high);
    animateCount($('#stat-medium'), medium);
    animateCount($('#stat-low'), low);
    animateCount($('#stat-time'), comparison.duration_ms, 'ms');

    buildCategoryPills();

    activeSeverity = 'all';
    activeCategory = 'all';
    $$('.filter-chip', severityPills).forEach(c => c.classList.remove('active'));
    $('.filter-chip[data-severity="all"]', severityPills).classList.add('active');

    renderChanges();
    resultsSection.classList.remove('hidden');
    setStatus('');
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    initSpotlightCards();
  }

  /* ===== Load comparison from history ===== */
  async function loadComparison(comparisonId) {
    try {
      // Switch to compare view
      $$('.nav-pill').forEach(p => p.classList.remove('active'));
      $('.nav-pill[data-view="compare"]').classList.add('active');
      viewCompare.classList.remove('hidden');
      viewHistory.classList.add('hidden');

      showProgress();
      setProgress(30, 'Loading comparison...');
      const comparison = await apiJson(`/api/v1/comparisons/${comparisonId}`);
      setProgress(100, 'Complete');
      displayComparison(comparison);
      setTimeout(() => hideProgress(), 500);
    } catch (err) {
      hideProgress();
      toast(err.message, 'error');
    }
  }

  /* ===== Build category filter pills ===== */
  function buildCategoryPills() {
    const categories = new Set();
    currentChanges.forEach(c => {
      if (c.assessment?.category) categories.add(c.assessment.category);
    });
    let html = '<button class="filter-chip active" data-category="all">All categories</button>';
    for (const cat of [...categories].sort()) {
      html += `<button class="filter-chip" data-category="${esc(cat)}">${esc(cat)}</button>`;
    }
    categoryPills.innerHTML = html;
  }

  /* ===== Render changes ===== */
  function renderChange(change, index) {
    const a = change.assessment;
    const heading = change.new_heading || change.old_heading || 'Untitled section';
    const headingLabel =
      change.old_heading && change.new_heading && change.old_heading !== change.new_heading
        ? `${change.old_heading} → ${change.new_heading}`
        : heading;
    const severity = a?.severity || 'low';
    const reviewStatus = change.latest_review?.status || 'pending';
    const needsReview = a?.needs_human_review ? '<span class="badge high" style="margin-left:auto">Needs review</span>' : '';

    return `
      <article class="change-card severity-${esc(severity)}" data-id="${esc(change.id)}" style="animation-delay:${index * 0.04}s">
        <div class="change-top" onclick="this.parentElement.classList.toggle('expanded')">
          <div class="change-heading-row">
            <span class="badge ${esc(severity)}">${esc(severity)}</span>
            <span class="badge type">${esc(change.change_type)}</span>
            <h3>${esc(headingLabel)}</h3>
            ${needsReview}
            <svg class="expand-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
          <p class="change-summary">${esc(a?.summary || 'No assessment available.')}</p>
        </div>
        <div class="change-detail">
          <div class="evidence-grid">
            <div class="evidence-block removed">
              <span class="evidence-label">Before${change.old_page_number ? ` · page ${esc(change.old_page_number)}` : ''}</span>${esc(change.old_excerpt ?? '—')}</div>
            <div class="evidence-block added">
              <span class="evidence-label">After${change.new_page_number ? ` · page ${esc(change.new_page_number)}` : ''}</span>${esc(change.new_excerpt ?? '—')}</div>
          </div>
          <div class="change-footer">
            <div class="change-meta-row">
              <span class="change-meta-item"><strong>Category:</strong> ${esc(a?.category || '—')}</span>
              <span class="change-meta-item"><strong>Similarity:</strong> ${change.similarity != null ? Math.round(change.similarity * 100) + '%' : '—'}</span>
              <span class="change-meta-item"><strong>Rationale:</strong> ${esc(a?.rationale || '—')}</span>
              <span class="change-meta-item"><strong>Validation:</strong> ${esc(a?.validation_status || '—')}</span>
            </div>
            <div class="review-actions">
              <button class="btn btn-sm btn-outline${reviewStatus === 'reviewed' ? ' active-review' : ''}" onclick="event.stopPropagation(); submitReview('${esc(change.id)}', 'reviewed')">Reviewed</button>
              <button class="btn btn-sm btn-outline${reviewStatus === 'dismissed' ? ' active-review' : ''}" onclick="event.stopPropagation(); submitReview('${esc(change.id)}', 'dismissed')">Dismiss</button>
            </div>
          </div>
        </div>
      </article>`;
  }

  function renderChanges() {
    let filtered = currentChanges;
    if (activeSeverity !== 'all') {
      filtered = filtered.filter(c => c.assessment?.severity === activeSeverity);
    }
    if (activeCategory !== 'all') {
      filtered = filtered.filter(c => c.assessment?.category === activeCategory);
    }
    changeCount.textContent = `${filtered.length} of ${currentChanges.length}`;
    changesRoot.innerHTML = filtered.length
      ? filtered.map(renderChange).join('')
      : '<p class="empty-state">No changes match the current filters.</p>';
  }

  /* ===== Review actions ===== */
  window.submitReview = async function(changeId, status) {
    try {
      await apiJson(`/api/v1/changes/${changeId}/review`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      });
      const change = currentChanges.find(c => c.id === changeId);
      if (change) {
        change.latest_review = { status, note: null, created_at: new Date().toISOString() };
      }
      renderChanges();
      toast(`Marked as ${status}`, 'success');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  /* ===== History ===== */
  async function renderHistory() {
    try {
      const data = await apiJson('/api/v1/comparisons');
      if (!data.length) {
        historyList.innerHTML = '';
        $('.empty-state', viewHistory)?.classList.remove('hidden');
        return;
      }
      $('.empty-state', viewHistory)?.classList.add('hidden');
      historyList.innerHTML = data.map(h => `
        <div class="history-item" data-id="${esc(h.id)}" style="cursor:pointer">
          <div>
            <div class="history-title">${esc(h.title)}</div>
            <div class="history-meta">${new Date(h.created_at + 'Z').toLocaleString()} · ${h.duration_ms}ms · ${h.total_changes} changes</div>
          </div>
          <div class="history-stats">
            <span class="badge high">${h.high} high</span>
            <span class="badge medium">${h.medium} med</span>
            <span class="badge low">${h.low} low</span>
          </div>
        </div>
      `).join('');
      historyList.querySelectorAll('.history-item[data-id]').forEach(el => {
        el.addEventListener('click', () => loadComparison(el.dataset.id));
      });
    } catch {
      historyList.innerHTML = '<p class="empty-state">Failed to load history.</p>';
    }
  }

  /* ===== Reset ===== */
  function reset() {
    titleInput.value = '';
    titleEdit.value = '';
    detailEditor.classList.add('hidden');
    btnEditTitle.textContent = 'Edit title';
    uploadedFiles = { baseline: null, candidate: null };
    $$('.drop-zone').forEach(zone => {
      zone.classList.remove('has-file');
      $('.drop-zone-idle', zone).classList.remove('hidden');
      $('.drop-zone-active', zone).classList.add('hidden');
      $('.drop-input', zone).value = '';
    });
    currentChanges = [];
    resultsSection.classList.add('hidden');
    hideProgress();
    setStatus('');
    updateCompareButton();
  }

  /* ===== Bindings ===== */
  btnCompare.addEventListener('click', runComparison);
  btnReset.addEventListener('click', reset);

  // Provider label
  fetch('/health')
    .then(r => r.json())
    .then(data => {
      if (data.assessment_provider) {
        $('#provider-label').textContent = data.assessment_provider;
      }
    })
    .catch(() => {});

  /* ===== Spotlight glow effect on stat cards ===== */
  function initSpotlightCards() {
    $$('.summary-stat').forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        card.style.setProperty('--spot-x', x + 'px');
        card.style.setProperty('--spot-y', y + 'px');
      });
    });
  }

  /* ===== Staggered change card entry ===== */
  const changeObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        changeObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  const origMutationObserver = new MutationObserver(() => {
    $$('.change-card:not(.visible)').forEach(card => changeObserver.observe(card));
  });
  if (changesRoot) origMutationObserver.observe(changesRoot, { childList: true });
})();

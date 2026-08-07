(() => {
  'use strict';

  // DOM refs
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const titleInput = $('#title');
  const baselineLabelInput = $('#baseline-label');
  const candidateLabelInput = $('#candidate-label');
  const btnCompare = $('#btn-compare');
  const btnReset = $('#btn-reset');
  const statusMsg = $('#status');
  const resultsSection = $('#results');
  const resultsMeta = $('#results-meta');
  const changeCount = $('#change-count');
  const changesRoot = $('#changes');
  const progressPanel = $('#progress-panel');
  const progressFill = $('#progress-fill');
  const progressText = $('#progress-text');
  const uploadPanel = $('#upload-panel');
  const pastePanel = $('#paste-panel');
  const severityPills = $('#severity-pills');

  // State
  let currentChanges = [];
  let activeSeverity = 'all';
  let uploadedFiles = { baseline: null, candidate: null };

  // --- Mode toggle (upload vs paste) ---
  $$('.toggle-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      $$('.toggle-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const mode = btn.dataset.mode;
      uploadPanel.classList.toggle('hidden', mode !== 'upload');
      pastePanel.classList.toggle('hidden', mode !== 'paste');
    });
  });

  // --- Upload zones ---
  function setupZone(zoneEl, role) {
    const input = zoneEl.querySelector('.zone-input');
    const content = zoneEl.querySelector('.zone-content');
    const fileDisplay = zoneEl.querySelector('.zone-file');
    const fileName = zoneEl.querySelector('.file-name');
    const removeBtn = zoneEl.querySelector('.file-remove');

    function setFile(file) {
      if (!file) return;
      uploadedFiles[role] = file;
      fileName.textContent = file.name;
      content.classList.add('hidden');
      fileDisplay.classList.remove('hidden');
      zoneEl.classList.add('has-file');
    }

    function clearFile() {
      uploadedFiles[role] = null;
      input.value = '';
      content.classList.remove('hidden');
      fileDisplay.classList.add('hidden');
      zoneEl.classList.remove('has-file');
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

    zoneEl.addEventListener('dragleave', () => {
      zoneEl.classList.remove('dragover');
    });

    zoneEl.addEventListener('drop', (e) => {
      e.preventDefault();
      zoneEl.classList.remove('dragover');
      if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
    });
  }

  setupZone($('#zone-baseline'), 'baseline');
  setupZone($('#zone-candidate'), 'candidate');

  // --- Severity filter pills ---
  severityPills.addEventListener('click', (e) => {
    const pill = e.target.closest('.pill');
    if (!pill) return;
    severityPills.querySelectorAll('.pill').forEach((p) => p.classList.remove('active'));
    pill.classList.add('active');
    activeSeverity = pill.dataset.severity;
    renderChanges();
  });

  // --- Utilities ---
  function setStatus(message, isError = false) {
    statusMsg.textContent = message;
    statusMsg.className = isError ? 'status-msg error' : 'status-msg';
  }

  function setProgress(pct, text) {
    progressFill.style.width = pct + '%';
    progressText.textContent = text;
  }

  function showProgress() { progressPanel.classList.remove('hidden'); }
  function hideProgress() { progressPanel.classList.add('hidden'); }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  async function apiJson(url, options) {
    const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
    return body;
  }

  async function apiUpload(url, formData) {
    const response = await fetch(url, { method: 'POST', body: formData });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Upload failed (${response.status}).`);
    return body;
  }

  // --- Input mode detection ---
  function isUploadMode() {
    return !uploadPanel.classList.contains('hidden');
  }

  function getInputMode() {
    if (isUploadMode()) {
      return { mode: 'upload', baseline: uploadedFiles.baseline, candidate: uploadedFiles.candidate };
    }
    return {
      mode: 'paste',
      baseline: $('#baseline-text').value.trim(),
      candidate: $('#candidate-text').value.trim(),
    };
  }

  // --- Validation ---
  function validate() {
    const title = titleInput.value.trim();
    if (!title) { setStatus('Please enter a document title.', true); return false; }
    const input = getInputMode();
    if (input.mode === 'upload') {
      if (!input.baseline) { setStatus('Please upload the baseline document.', true); return false; }
      if (!input.candidate) { setStatus('Please upload the revised document.', true); return false; }
    } else {
      if (!input.baseline) { setStatus('Please paste the baseline text.', true); return false; }
      if (!input.candidate) { setStatus('Please paste the revised text.', true); return false; }
    }
    return true;
  }

  // --- Comparison flow ---
  async function runComparison() {
    if (!validate()) return;
    btnCompare.disabled = true;
    setStatus('');
    resultsSection.classList.add('hidden');
    showProgress();

    const title = titleInput.value.trim();
    const baselineLabel = baselineLabelInput.value.trim() || 'v1';
    const candidateLabel = candidateLabelInput.value.trim() || 'v2';
    const input = getInputMode();

    try {
      let documentData, baselineVersion, candidateVersion;

      if (input.mode === 'upload') {
        // Upload baseline
        setProgress(15, 'Uploading baseline document…');
        const baselineForm = new FormData();
        baselineForm.append('title', title);
        baselineForm.append('version_label', baselineLabel);
        baselineForm.append('file', input.baseline);
        documentData = await apiUpload('/api/v1/documents/upload', baselineForm);
        baselineVersion = documentData.versions[0];

        // Upload candidate
        setProgress(40, 'Uploading revised document…');
        const candidateForm = new FormData();
        candidateForm.append('version_label', candidateLabel);
        candidateForm.append('file', input.candidate);
        candidateVersion = await apiUpload(
          `/api/v1/documents/${documentData.id}/versions/upload`,
          candidateForm
        );
      } else {
        // Text mode
        setProgress(15, 'Creating baseline version…');
        documentData = await apiJson('/api/v1/documents', {
          method: 'POST',
          body: JSON.stringify({ title, version_label: baselineLabel, content: input.baseline }),
        });
        baselineVersion = documentData.versions[0];

        setProgress(40, 'Creating revised version…');
        candidateVersion = await apiJson(`/api/v1/documents/${documentData.id}/versions`, {
          method: 'POST',
          body: JSON.stringify({ version_label: candidateLabel, content: input.candidate }),
        });
      }

      // Run comparison
      setProgress(65, 'Running diff engine and assessment…');
      const comparison = await apiJson('/api/v1/comparisons', {
        method: 'POST',
        body: JSON.stringify({
          baseline_version_id: baselineVersion.id,
          candidate_version_id: candidateVersion.id,
        }),
      });

      setProgress(100, 'Done.');
      currentChanges = comparison.changes;
      activeSeverity = 'all';
      severityPills.querySelectorAll('.pill').forEach((p) => p.classList.remove('active'));
      severityPills.querySelector('[data-severity="all"]').classList.add('active');

      const high = currentChanges.filter((c) => c.assessment?.severity === 'high').length;
      const medium = currentChanges.filter((c) => c.assessment?.severity === 'medium').length;
      const low = currentChanges.filter((c) => c.assessment?.severity === 'low').length;
      resultsMeta.innerHTML = `${comparison.changes.length} changes found &middot; ${comparison.duration_ms} ms &middot; <span style="color:var(--high)">${high} high</span> · <span style="color:var(--medium)">${medium} med</span> · <span style="color:var(--low)">${low} low</span>`;

      renderChanges();
      resultsSection.classList.remove('hidden');
      setStatus('');

      setTimeout(() => hideProgress(), 600);
      resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      hideProgress();
      setStatus(error.message, true);
    } finally {
      btnCompare.disabled = false;
    }
  }

  // --- Render changes ---
  function renderChange(change) {
    const assessment = change.assessment;
    const heading = change.new_heading || change.old_heading || 'Unlabelled section';
    const headingLabel =
      change.old_heading && change.new_heading && change.old_heading !== change.new_heading
        ? `${change.old_heading} → ${change.new_heading}`
        : heading;
    const severity = assessment?.severity || 'low';
    const reviewStatus = change.latest_review?.status || 'pending';

    return `
      <article class="change">
        <div class="change-header">
          <span class="badge ${escapeHtml(severity)}">${escapeHtml(severity)}</span>
          <span class="badge type">${escapeHtml(change.change_type)}</span>
          <h3>${escapeHtml(headingLabel)}</h3>
        </div>
        <p class="change-summary">${escapeHtml(assessment?.summary || 'No assessment produced.')}</p>
        <div class="evidence">
          <div class="removed"><strong>Before · page ${escapeHtml(change.old_page_number ?? '—')}</strong>${escapeHtml(change.old_excerpt ?? '—')}</div>
          <div class="added"><strong>After · page ${escapeHtml(change.new_page_number ?? '—')}</strong>${escapeHtml(change.new_excerpt ?? '—')}</div>
        </div>
        <div class="change-meta">
          <span>Rationale: ${escapeHtml(assessment?.rationale || '—')}</span>
          <span>Validation: ${escapeHtml(assessment?.validation_status || '—')}</span>
          <span>Review: ${escapeHtml(reviewStatus)}</span>
        </div>
      </article>`;
  }

  function renderChanges() {
    const filtered = activeSeverity === 'all'
      ? currentChanges
      : currentChanges.filter((c) => c.assessment?.severity === activeSeverity);
    changeCount.textContent = `${filtered.length} of ${currentChanges.length} shown`;
    changesRoot.innerHTML = filtered.length
      ? filtered.map(renderChange).join('')
      : '<p style="color:var(--text-dim);text-align:center;padding:2rem;">No changes match this filter.</p>';
  }

  // --- Reset ---
  function reset() {
    titleInput.value = '';
    baselineLabelInput.value = 'v1';
    candidateLabelInput.value = 'v2';
    $('#baseline-text').value = '';
    $('#candidate-text').value = '';
    uploadedFiles = { baseline: null, candidate: null };
    // Reset upload zones
    $$('.upload-zone').forEach((zone) => {
      zone.classList.remove('has-file');
      zone.querySelector('.zone-content').classList.remove('hidden');
      zone.querySelector('.zone-file').classList.add('hidden');
      zone.querySelector('.zone-input').value = '';
    });
    currentChanges = [];
    resultsSection.classList.add('hidden');
    hideProgress();
    setStatus('');
  }

  // --- Event bindings ---
  btnCompare.addEventListener('click', runComparison);
  btnReset.addEventListener('click', reset);

  // Fetch health to show provider
  fetch('/health')
    .then((r) => r.json())
    .then((data) => {
      if (data.assessment_provider) {
        $('#provider-label').textContent = data.assessment_provider;
      }
    })
    .catch(() => {});
})();

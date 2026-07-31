const form = document.querySelector('#comparison-form');
const submit = document.querySelector('#submit');
const statusBox = document.querySelector('#status');
const results = document.querySelector('#results');
const summary = document.querySelector('#summary');
const changesRoot = document.querySelector('#changes');
const severityFilter = document.querySelector('#severity-filter');
let currentChanges = [];

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.className = isError ? 'status error' : 'status';
}

async function request(url, options) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || 'Request failed.');
  return body;
}

function text(value) {
  return value || '—';
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderChange(change) {
  const assessment = change.assessment;
  const heading = change.new_heading || change.old_heading || 'Unlabelled section';
  const headingLabel = change.old_heading && change.new_heading && change.old_heading !== change.new_heading
    ? `${change.old_heading} → ${change.new_heading}`
    : heading;
  const severity = assessment?.severity || 'low';
  return `
    <article class="change">
      <div class="change-header">
        <span class="badge ${escapeHtml(severity)}">${escapeHtml(severity)}</span>
        <span class="badge">${escapeHtml(change.change_type)}</span>
        <h3>${escapeHtml(headingLabel)}</h3>
      </div>
      <p>${escapeHtml(assessment?.summary || 'No assessment was produced.')}</p>
      <div class="evidence">
        <div><strong>Before · page ${escapeHtml(text(change.old_page_number))}</strong>${escapeHtml(text(change.old_excerpt))}</div>
        <div><strong>After · page ${escapeHtml(text(change.new_page_number))}</strong>${escapeHtml(text(change.new_excerpt))}</div>
      </div>
      <p class="metadata">${escapeHtml(assessment?.rationale || '')}</p>
      <p class="metadata">Evidence validation: ${escapeHtml(assessment?.validation_status || 'not available')} · Review: ${escapeHtml(change.latest_review?.status || 'pending')}</p>
    </article>`;
}

function renderChanges() {
  const selectedSeverity = severityFilter.value;
  const visibleChanges = currentChanges.filter(
    (change) => selectedSeverity === 'all' || change.assessment?.severity === selectedSeverity,
  );
  changesRoot.innerHTML = visibleChanges.map(renderChange).join('') || '<p>No changes match this filter.</p>';
}

severityFilter.addEventListener('change', renderChanges);

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  submit.disabled = true;
  setStatus('Creating document versions and calculating the deterministic diff…');
  results.classList.add('hidden');
  try {
    const title = document.querySelector('#title').value.trim();
    const baseline = document.querySelector('#baseline').value;
    const candidate = document.querySelector('#candidate').value;
    const documentData = await request('/api/v1/documents', {
      method: 'POST',
      body: JSON.stringify({ title, version_label: 'v1', content: baseline }),
    });
    const baselineVersion = documentData.versions[0];
    const candidateVersion = await request(`/api/v1/documents/${documentData.id}/versions`, {
      method: 'POST',
      body: JSON.stringify({ version_label: 'v2', content: candidate }),
    });
    const comparison = await request('/api/v1/comparisons', {
      method: 'POST',
      body: JSON.stringify({
        baseline_version_id: baselineVersion.id,
        candidate_version_id: candidateVersion.id,
      }),
    });
    currentChanges = comparison.changes;
    severityFilter.value = 'all';
    summary.textContent = `${comparison.changes.length} change(s) found in ${comparison.duration_ms} ms.`;
    renderChanges();
    results.classList.remove('hidden');
    setStatus('Comparison complete. Every displayed excerpt is checked against stored source text.');
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    submit.disabled = false;
  }
});

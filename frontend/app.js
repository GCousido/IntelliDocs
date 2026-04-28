const inferredApiBase = (() => {
  const origin = window.location.origin;
  if (origin && origin !== 'null' && origin.startsWith('http')) {
    return `${origin.replace(/\/$/, '')}/api`;
  }
  return 'http://localhost:8000';
})();

const API_BASES = [...new Set([
  window.API_BASE,
  inferredApiBase,
  'http://localhost:8000'
].filter(Boolean).map(base => String(base).replace(/\/$/, '')))]

const state = { files: [], documents: [] };

const tabs = document.querySelectorAll('.nav-item');
const panels = {
  upload: document.getElementById('tab-upload'),
  library: document.getElementById('tab-library'),
  pipeline: document.getElementById('tab-pipeline')
};
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const selectedFiles = document.getElementById('selected-files');
const uploadBtn = document.getElementById('upload-btn');
const refreshBtn = document.getElementById('refresh-btn');
const listEl = document.getElementById('documents-list');
const pipelinePreview = document.getElementById('pipeline-preview');
const sidebarToggle = document.getElementById('sidebar-toggle');

const escapeMap = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
};

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => escapeMap[character]);
}

async function fetchJson(path, options = {}) {
  let lastError = null;

  for (const base of API_BASES) {
    try {
      const response = await fetch(`${base}${path}`, options);

      if (response.ok) {
        if (response.status === 204) {
          return null;
        }
        return await response.json();
      }

      const detail = await response.text().catch(() => response.statusText);
      if ([404, 502, 503, 504].includes(response.status)) {
        lastError = new Error(detail || `HTTP ${response.status}`);
        continue;
      }

      throw new Error(detail || `HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error('No se pudo completar la peticion.');
}

function setTab(tab) {
  tabs.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tab));
  Object.entries(panels).forEach(([key, el]) => el.classList.toggle('active', key === tab));
  if (tab === 'pipeline') {
    renderPipelineExample();
  }
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle('sidebar-collapsed', collapsed);
  if (sidebarToggle) {
    sidebarToggle.setAttribute('aria-expanded', String(!collapsed));
  }
}

function renderSelectedFiles(files) {
  selectedFiles.innerHTML = '';
  files.forEach(file => {
    const item = document.createElement('div');
    item.className = 'selected-file';
    item.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
    selectedFiles.appendChild(item);
  });
}

function renderPipelineExample() {
  const doc = state.documents[0];

  if (!doc) {
    pipelinePreview.innerHTML = '<div class="document-card">Todavia no hay documentos procesados para mostrar un ejemplo completo.</div>';
    return;
  }

  const ocrText = doc.ocr?.text || '';

  pipelinePreview.innerHTML = `
    <article class="document-card">
      <div class="document-header">
        <div>
          <strong>${escapeHtml(doc.filename || 'Documento sin nombre')}</strong>
          <div class="documents-meta">Primer elemento de la base de datos · Estado: ${escapeHtml(doc.status || 'desconocido')} · Tipo: ${escapeHtml(doc.classification?.label || 'sin clasificar')}</div>
        </div>
        <span class="badge">${escapeHtml(doc.id || '')}</span>
      </div>
      <div class="documents-grid">
        <section class="document-block">
          <h4>Documento</h4>
          <p>${escapeHtml(doc.filename || 'Sin nombre')}</p>
          <p>${escapeHtml(doc.content_type || 'Tipo desconocido')}</p>
          <p>${escapeHtml(doc.storage_path || 'Sin ruta')}</p>
        </section>
        <section class="document-block">
          <h4>Contenido extraído</h4>
          <p>${escapeHtml(ocrText.slice(0, 320) || 'Sin texto disponible.')}</p>
        </section>
        <section class="document-block">
          <h4>Layout</h4>
          <p>${escapeHtml(JSON.stringify(doc.layout || {}, null, 2))}</p>
        </section>
        <section class="document-block">
          <h4>Clasificación</h4>
          <p>${escapeHtml(JSON.stringify(doc.classification || {}, null, 2))}</p>
        </section>
        <section class="document-block">
          <h4>Campos clave</h4>
          <p>${escapeHtml(JSON.stringify(doc.extraction || {}, null, 2))}</p>
        </section>
        <section class="document-block">
          <h4>Proceso</h4>
          <p>${escapeHtml(JSON.stringify(doc.pipeline || {}, null, 2))}</p>
        </section>
      </div>
    </article>
  `;
}

async function fetchDocuments() {
  try {
    const data = await fetchJson('/documents');
    state.documents = data.items || [];
    renderDocuments();
    renderPipelineExample();
  } catch (error) {
    state.documents = [];
    listEl.innerHTML = '<div class="document-card">No se pudo cargar la biblioteca de documentos.</div>';
    pipelinePreview.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

function renderDocuments() {
  listEl.innerHTML = '';

  if (!state.documents.length) {
    listEl.innerHTML = '<div class="document-card">Aún no hay documentos procesados.</div>';
    return;
  }

  state.documents.forEach(doc => {
    const card = document.createElement('article');
    card.className = 'document-card';
    card.innerHTML = `
      <div class="document-header">
        <div>
          <strong>${escapeHtml(doc.filename || 'Documento sin nombre')}</strong>
          <div class="documents-meta">Estado: ${escapeHtml(doc.status || 'desconocido')} · Tipo: ${escapeHtml(doc.classification?.label || 'sin clasificar')}</div>
        </div>
        <span class="badge">${escapeHtml(doc.id || '')}</span>
      </div>
      <div class="documents-grid">
        <section class="document-block">
          <h4>Contenido extraído</h4>
          <p>${escapeHtml((doc.ocr?.text || '').slice(0, 280) || 'Sin texto disponible.')}</p>
        </section>
        <section class="document-block">
          <h4>Layout</h4>
          <p>${escapeHtml(JSON.stringify(doc.layout || {}, null, 0))}</p>
        </section>
        <section class="document-block">
          <h4>Clasificación</h4>
          <p>${escapeHtml(JSON.stringify(doc.classification || {}, null, 0))}</p>
        </section>
        <section class="document-block">
          <h4>Campos clave</h4>
          <p>${escapeHtml(JSON.stringify(doc.extraction || {}, null, 0))}</p>
        </section>
      </div>
    `;
    listEl.appendChild(card);
  });
}

async function uploadFiles() {
  if (!state.files.length) return alert('Selecciona al menos un archivo.');
  uploadBtn.disabled = true;

  try {
    for (const file of state.files) {
      const formData = new FormData();
      formData.append('file', file);
      await fetchJson('/documents/upload', { method: 'POST', body: formData });
    }

    state.files = [];
    selectedFiles.innerHTML = '';
    fileInput.value = '';
    await fetchDocuments();
    setTab('library');
  } catch (err) {
    alert(err.message);
  } finally {
    uploadBtn.disabled = false;
  }
}

tabs.forEach(btn => btn.addEventListener('click', () => setTab(btn.dataset.tab)));

['dragenter', 'dragover'].forEach(evt => dropzone.addEventListener(evt, e => {
  e.preventDefault();
  dropzone.classList.add('dragover');
}));

['dragleave', 'drop'].forEach(evt => dropzone.addEventListener(evt, e => {
  e.preventDefault();
  dropzone.classList.remove('dragover');
}));

dropzone.addEventListener('drop', e => {
  state.files = [...e.dataTransfer.files];
  renderSelectedFiles(state.files);
});

dropzone.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') fileInput.click();
});

fileInput.addEventListener('change', e => {
  state.files = [...e.target.files];
  renderSelectedFiles(state.files);
});

sidebarToggle?.addEventListener('click', () => {
  setSidebarCollapsed(!document.body.classList.contains('sidebar-collapsed'));
});

uploadBtn.addEventListener('click', uploadFiles);
refreshBtn.addEventListener('click', fetchDocuments);
fetchDocuments();
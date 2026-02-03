/**
 * Settings Module
 * Handles settings and configuration management
 */

/**
 * Switch between main views (stories, settings, repos, etc.)
 */
/**
 * Switch between main views (stories, settings, repos, etc.)
 */
function switchMainView(view, pushState = true) {
  store.update('currentMainView', view);

  if (pushState) {
    store.pushHistory({ view: 'main', mainView: view }, `Repr - ${view.charAt(0).toUpperCase() + view.slice(1)}`, `?view=${view}`);
  }

  document.querySelectorAll('.sidebar-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === view);
  });

  document.querySelectorAll('.mobile-nav-item').forEach(item => {
    const itemText = item.querySelector('span:last-child').textContent.toLowerCase();
    item.classList.toggle('active', view.startsWith(itemText));
  });

  // Close sidebar on mobile if open
  const sidebar = document.querySelector('.sidebar');
  if (sidebar.classList.contains('open')) {
    toggleSidebar();
  }

  // Hide all views
  ['stories', 'settings', 'llm', 'privacy', 'repos', 'cron'].forEach(v => {
    const el = document.getElementById('view-' + v);
    if (el) el.style.display = 'none';
  });

  // Show selected view
  const activeView = document.getElementById('view-' + view);
  if (activeView) activeView.style.display = 'block';

  // Load data if needed
  if (['settings', 'llm', 'privacy', 'cron'].includes(view) && !store.get('config')) {
    loadConfig();
  }

  if (view === 'repos') {
    loadRepos();
  }

  if (view === 'cron') {
    loadCronStatus();
  }
}

/**
 * Switch between settings tabs (form, json)
 */
function switchSettingsTab(tab) {
  store.update('currentSettingsTab', tab);

  document.querySelectorAll('.settings-nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.tab === tab);
  });

  document.getElementById('settings-form').style.display = tab === 'form' ? 'block' : 'none';
  document.getElementById('settings-json').style.display = tab === 'json' ? 'block' : 'none';

  if (tab === 'json') {
    const config = store.get('config');
    if (config) {
      document.getElementById('json-editor').value = JSON.stringify(config, null, 2);
    }
  }
}

/**
 * Load configuration from API
 */
async function loadConfig() {
  try {
    const config = await getConfig();
    store.batchUpdate({
      config: config,
      configDirty: false
    });
    populateForm(config);
    document.getElementById('json-editor').value = JSON.stringify(config, null, 2);
    updateSaveButtons();
  } catch (error) {
    showToast('Failed to load config', 'error');
  }
}

/**
 * Populate form fields with config data
 */
function populateForm(config) {
  // LLM Settings
  document.getElementById('llm-default').value = config.llm?.default || 'local';
  document.getElementById('llm-local-provider').value = config.llm?.local_provider || '';
  document.getElementById('llm-local-model').value = config.llm?.local_model || '';
  document.getElementById('llm-local-url').value = config.llm?.local_api_url || '';

  // Generation Settings
  document.getElementById('gen-batch-size').value = config.generation?.batch_size || 5;
  document.getElementById('gen-max-commits').value = config.generation?.max_commits_per_batch || 50;
  document.getElementById('gen-template').value = config.generation?.default_template || 'resume';
  document.getElementById('gen-auto-hook').checked = config.generation?.auto_generate_on_hook || false;

  // Privacy Settings
  document.getElementById('privacy-local-only').checked = config.privacy?.lock_local_only || false;
  document.getElementById('privacy-redact-paths').checked = config.llm?.cloud_redact_paths !== false;
  document.getElementById('privacy-redact-emails').checked = config.llm?.cloud_redact_emails || false;
  document.getElementById('privacy-send-diffs').checked = config.llm?.cloud_send_diffs || false;
  document.getElementById('privacy-visibility').value = config.privacy?.profile_visibility || 'public';

  // Cron Settings
  document.getElementById('cron-interval').value = config.cron?.interval_hours || 4;
  document.getElementById('cron-min-commits').value = config.cron?.min_commits || 3;
  document.getElementById('cron-installed').checked = config.cron?.installed || false;
  document.getElementById('cron-paused').checked = config.cron?.paused || false;

  // Paths
  renderTags('default-paths-container', config.settings?.default_paths || ['~/code'], 'path');
  renderTags('skip-patterns-container', config.settings?.skip_patterns || [], 'pattern');
}

/**
 * Collect form data into config object
 */
function collectFormData() {
  const config = JSON.parse(JSON.stringify(store.get('config'))); // Deep clone

  // LLM Settings
  config.llm = config.llm || {};
  config.llm.default = document.getElementById('llm-default').value;
  config.llm.local_provider = document.getElementById('llm-local-provider').value || null;
  config.llm.local_model = document.getElementById('llm-local-model').value || null;
  config.llm.local_api_url = document.getElementById('llm-local-url').value || null;

  // Generation Settings
  config.generation = config.generation || {};
  config.generation.batch_size = parseInt(document.getElementById('gen-batch-size').value) || 5;
  config.generation.max_commits_per_batch = parseInt(document.getElementById('gen-max-commits').value) || 50;
  config.generation.default_template = document.getElementById('gen-template').value;
  config.generation.auto_generate_on_hook = document.getElementById('gen-auto-hook').checked;

  // Privacy Settings
  config.privacy = config.privacy || {};
  config.privacy.lock_local_only = document.getElementById('privacy-local-only').checked;
  config.privacy.profile_visibility = document.getElementById('privacy-visibility').value;
  config.llm.cloud_redact_paths = document.getElementById('privacy-redact-paths').checked;
  config.llm.cloud_redact_emails = document.getElementById('privacy-redact-emails').checked;
  config.llm.cloud_send_diffs = document.getElementById('privacy-send-diffs').checked;

  // Cron Settings
  config.cron = config.cron || {};
  config.cron.interval_hours = parseInt(document.getElementById('cron-interval').value) || 4;
  config.cron.min_commits = parseInt(document.getElementById('cron-min-commits').value) || 3;
  config.cron.installed = document.getElementById('cron-installed').checked;
  config.cron.paused = document.getElementById('cron-paused').checked;

  // Paths
  config.settings = config.settings || {};
  config.settings.default_paths = collectTags('default-paths-container');
  config.settings.skip_patterns = collectTags('skip-patterns-container');

  return config;
}

/**
 * Save configuration
 */
async function saveConfig() {
  try {
    const config = collectFormData();
    await updateConfig(config);

    store.batchUpdate({
      config: config,
      configDirty: false
    });
    updateSaveButtons();
    showToast('Configuration saved', 'success');
  } catch (error) {
    showToast('Failed to save config', 'error');
  }
}

/**
 * Save JSON configuration
 */
async function saveJsonConfig() {
  try {
    const jsonText = document.getElementById('json-editor').value;
    const config = JSON.parse(jsonText);
    await updateConfig(config);

    store.batchUpdate({
      config: config,
      configDirty: false
    });
    populateForm(config);
    updateSaveButtons();
    showToast('Configuration saved', 'success');
  } catch (error) {
    if (error instanceof SyntaxError) {
      showToast('Invalid JSON syntax', 'error');
    } else {
      showToast('Failed to save config', 'error');
    }
  }
}

/**
 * Format JSON in editor
 */
function formatJson() {
  try {
    const editor = document.getElementById('json-editor');
    const parsed = JSON.parse(editor.value);
    editor.value = JSON.stringify(parsed, null, 2);
  } catch (e) {
    showToast('Invalid JSON - cannot format', 'error');
  }
}

/**
 * Mark config as dirty (needs saving)
 */
function markConfigDirty() {
  store.update('configDirty', true);
  updateSaveButtons();
}

/**
 * Update save button states
 */
function updateSaveButtons() {
  const configDirty = store.get('configDirty');
  const btns = ['save-btn', 'save-json-btn', 'save-llm-btn', 'save-privacy-btn', 'save-cron-btn'];

  btns.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = !configDirty;
  });
}

/**
 * Load cron status
 */
async function loadCronStatus() {
  try {
    const status = await getCronStatus();
    store.update('cronStatus', status);
    renderCronStatus(status);
  } catch (error) {
    document.getElementById('cron-status').innerHTML = '<div class="loading-text">Failed to load cron status</div>';
  }
}

/**
 * Render cron status
 */
function renderCronStatus(status) {
  const container = document.getElementById('cron-status');

  let stateText = 'Not installed';
  let stateClass = 'inactive';

  if (status.installed) {
    if (status.paused) {
      stateText = 'Paused';
      stateClass = 'paused';
    } else {
      stateText = 'Active';
      stateClass = 'active';
    }
  }

  container.innerHTML = `
    <div class="cron-status-row">
      <span class="cron-status-label">Status</span>
      <span class="cron-status-value ${stateClass}">${stateText}</span>
    </div>
    <div class="cron-status-row">
      <span class="cron-status-label">Interval</span>
      <span class="cron-status-value">${status.interval_hours ? status.interval_hours + ' hours' : 'Not set'}</span>
    </div>
    <div class="cron-status-row">
      <span class="cron-status-label">Min Commits</span>
      <span class="cron-status-value">${status.min_commits || 'Not set'}</span>
    </div>
  `;
}

/**
 * Tags Input Functions
 */
function renderTags(containerId, tags, type) {
  const container = document.getElementById(containerId);
  const input = container.querySelector('input');

  // Remove existing tags
  container.querySelectorAll('.tag-item').forEach(el => el.remove());

  // Add tags before input
  tags.forEach(tag => {
    const tagEl = document.createElement('span');
    tagEl.className = 'tag-item';
    tagEl.innerHTML = `${escapeHtml(tag)}<span class="tag-remove" onclick="removeTag(this, '${type}')">&times;</span>`;
    container.insertBefore(tagEl, input);
  });
}

function collectTags(containerId) {
  const container = document.getElementById(containerId);
  return Array.from(container.querySelectorAll('.tag-item'))
    .map(el => el.textContent.slice(0, -1)); // Remove the × character
}

function removeTag(el, type) {
  el.parentElement.remove();
  markConfigDirty();
}

function handlePathInput(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    const input = event.target;
    const value = input.value.trim();
    if (value) {
      const container = input.parentElement;
      const tagEl = document.createElement('span');
      tagEl.className = 'tag-item';
      tagEl.innerHTML = `${escapeHtml(value)}<span class="tag-remove" onclick="removeTag(this, 'path')">&times;</span>`;
      container.insertBefore(tagEl, input);
      input.value = '';
      markConfigDirty();
    }
  }
}

function handlePatternInput(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    const input = event.target;
    const value = input.value.trim();
    if (value) {
      const container = input.parentElement;
      const tagEl = document.createElement('span');
      tagEl.className = 'tag-item';
      tagEl.innerHTML = `${escapeHtml(value)}<span class="tag-remove" onclick="removeTag(this, 'pattern')">&times;</span>`;
      container.insertBefore(tagEl, input);
      input.value = '';
      markConfigDirty();
    }
  }
}

// Expose functions to global scope for inline onclick handlers
window.switchMainView = switchMainView;
window.loadConfig = loadConfig;
window.saveConfig = saveConfig;
window.saveJsonConfig = saveJsonConfig;
window.formatJson = formatJson;
window.switchSettingsTab = switchSettingsTab;

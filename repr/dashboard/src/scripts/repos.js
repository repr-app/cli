/**
 * Repos Module
 * Handles repository management
 */

/**
 * Load repositories from API
 */
async function loadRepos() {
  try {
    const data = await getRepos();
    store.update('repos', data.repos || []);
    renderRepos();
  } catch (error) {
    document.getElementById('repos-list').innerHTML = '<div class="loading-text">Failed to load repositories</div>';
  }
}

/**
 * Render repositories list
 */
function renderRepos() {
  const repos = store.get('repos');
  const container = document.getElementById('repos-list');

  if (!repos.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-title">No repositories tracked</div>
        <div>Add a repository path above to start tracking</div>
      </div>`;
    return;
  }

  container.innerHTML = repos.map(repo => {
    const projectName = repo.project?.name || '';
    const displayName = projectName || repo.origin_name || repo.path.split('/').pop();
    const isPaused = repo.paused;
    const isMissing = !repo.exists;
    const hasHook = repo.hook_installed;

    let statusClass = 'active';
    if (isMissing) statusClass = 'missing';
    else if (isPaused) statusClass = 'paused';

    const originUrl = repo.origin ? convertGitUrlToWeb(repo.origin) : null;
    const escapedPath = escapeHtml(repo.path).replace(/'/g, "\\'");

    return `
      <div class="repo-item ${isPaused ? 'paused' : ''} ${isMissing ? 'missing' : ''}">
        <div class="repo-info">
          <div class="repo-name-row">
            <span class="repo-name" id="repo-name-${escapedPath}" onclick="editRepoName('${escapedPath}')">${escapeHtml(displayName)}</span>
            <button class="repo-edit-btn" onclick="editRepoName('${escapedPath}')" title="Edit name">✎</button>
            ${originUrl ? `<a href="${escapeHtml(originUrl)}" target="_blank" rel="noopener noreferrer" class="repo-link" title="Open repository"><span class="repo-link-icon">&#8599;</span></a>` : ''}
          </div>
          <div class="repo-path">${escapeHtml(repo.path)}</div>
          <div class="repo-status">
            <span class="repo-badge ${statusClass}">${isMissing ? 'Missing' : isPaused ? 'Paused' : 'Active'}</span>
            ${hasHook ? '<span class="repo-badge hook">Hook</span>' : ''}
            ${repo.last_sync ? `<span style="font-size: 11px; color: var(--text-muted);">Last sync: ${new Date(repo.last_sync).toLocaleDateString()}</span>` : ''}
          </div>
        </div>
        <div class="repo-actions">
          ${isPaused
            ? `<button class="repo-action-btn" onclick="resumeRepoClick('${escapedPath}')">Resume</button>`
            : `<button class="repo-action-btn" onclick="pauseRepoClick('${escapedPath}')">Pause</button>`
          }
          <button class="repo-action-btn danger" onclick="removeRepoClick('${escapedPath}')">Remove</button>
        </div>
      </div>
    `;
  }).join('');
}

/**
 * Add repository
 */
async function addRepoClick() {
  const input = document.getElementById('add-repo-path');
  const path = input.value.trim();

  if (!path) {
    showToast('Please enter a repository path', 'error');
    return;
  }

  try {
    const result = await addRepo(path);

    if (result.success) {
      input.value = '';
      showToast('Repository added', 'success');
      loadRepos();
    } else {
      showToast(result.error || 'Failed to add repository', 'error');
    }
  } catch (error) {
    showToast('Failed to add repository', 'error');
  }
}

/**
 * Remove repository
 */
async function removeRepoClick(path) {
  if (!confirm('Remove this repository from tracking?')) return;

  try {
    const result = await removeRepo(path);

    if (result.success) {
      showToast('Repository removed', 'success');
      loadRepos();
    } else {
      showToast('Failed to remove repository', 'error');
    }
  } catch (error) {
    showToast('Failed to remove repository', 'error');
  }
}

/**
 * Pause repository
 */
async function pauseRepoClick(path) {
  try {
    const result = await pauseRepo(path);

    if (result.success) {
      showToast('Repository paused', 'success');
      loadRepos();
    } else {
      showToast('Failed to pause repository', 'error');
    }
  } catch (error) {
    showToast('Failed to pause repository', 'error');
  }
}

/**
 * Resume repository
 */
async function resumeRepoClick(path) {
  try {
    const result = await resumeRepo(path);

    if (result.success) {
      showToast('Repository resumed', 'success');
      loadRepos();
    } else {
      showToast('Failed to resume repository', 'error');
    }
  } catch (error) {
    showToast('Failed to resume repository', 'error');
  }
}

/**
 * Convert git URL to web URL
 * Converts git@host:user/repo.git to https://host/user/repo
 */
function convertGitUrlToWeb(url) {
  if (!url) return null;

  // Already an HTTP(S) URL
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }

  // SSH format: git@github.com:user/repo.git
  const sshMatch = url.match(/^git@([^:]+):(.+?)(\.git)?$/);
  if (sshMatch) {
    const host = sshMatch[1];
    const path = sshMatch[2];
    return `https://${host}/${path}`;
  }

  // git:// format: git://github.com/user/repo.git
  const gitMatch = url.match(/^git:\/\/(.+?)(\.git)?$/);
  if (gitMatch) {
    return `https://${gitMatch[1]}`;
  }

  // Return original if can't convert
  return url;
}

/**
 * Edit repository name
 */
function editRepoName(path) {
  const repos = store.get('repos');
  const repo = repos.find(r => r.path === path);
  if (!repo) return;

  const currentName = repo.project?.name || repo.origin_name || repo.path.split('/').pop();
  
  const modal = document.getElementById('edit-repo-modal');
  const nameInput = document.getElementById('edit-repo-name-input');
  const pathInput = document.getElementById('edit-repo-path-input');
  
  nameInput.value = currentName;
  pathInput.value = path;
  
  openModal('edit-repo-modal');
  
  // Focus and select the text
  setTimeout(() => {
    nameInput.focus();
    nameInput.select();
  }, 100);
}

/**
 * Save repository edit from modal
 */
async function saveRepoEdit() {
  const nameInput = document.getElementById('edit-repo-name-input');
  const pathInput = document.getElementById('edit-repo-path-input');
  
  const newName = nameInput.value.trim();
  const path = pathInput.value;

  if (newName === '') {
    showToast('Name cannot be empty', 'error');
    return;
  }

  const saveBtn = document.getElementById('save-repo-btn');
  const originalText = saveBtn.textContent;
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving...';

  try {
    const result = await renameRepo(path, newName);

    if (result.success) {
      showToast('Project renamed', 'success');
      closeModal('edit-repo-modal');
      loadRepos();
    } else {
      showToast(result.error || 'Failed to rename project', 'error');
    }
  } catch (error) {
    showToast('Failed to rename project', 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = originalText;
  }
}

/**
 * Rename repository project
 */
async function renameRepoClick(path, name) {
  try {
    const result = await renameRepo(path, name);

    if (result.success) {
      showToast('Project renamed', 'success');
      loadRepos();
    } else {
      showToast(result.error || 'Failed to rename project', 'error');
    }
  } catch (error) {
    showToast('Failed to rename project', 'error');
  }
}

// Expose functions to global scope for inline onclick handlers
window.addRepoClick = addRepoClick;
window.editRepoName = editRepoName;
window.saveRepoEdit = saveRepoEdit;

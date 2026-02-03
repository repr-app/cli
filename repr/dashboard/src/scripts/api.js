/**
 * API Module
 * Handles all API calls with error handling and retry logic
 */

const API_BASE = '';

/**
 * Fetch with error handling and retry logic
 */
async function fetchWithRetry(url, options = {}, retries = 2) {
  for (let i = 0; i <= retries; i++) {
    try {
      const response = await fetch(url, options);
      if (!response.ok && i < retries) {
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
        continue;
      }
      return response;
    } catch (error) {
      if (i === retries) throw error;
      await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
    }
  }
}

/**
 * Get dashboard status
 */
async function getStatus() {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/status`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch status:', error);
    throw error;
  }
}

/**
 * Get all stories
 */
async function getStories() {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/stories`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch stories:', error);
    throw error;
  }
}

/**
 * Get configuration
 */
async function getConfig() {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/config`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch config:', error);
    throw error;
  }
}

/**
 * Update configuration
 */
async function updateConfig(config) {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });

    if (!response.ok) {
      throw new Error('Failed to save config');
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to update config:', error);
    throw error;
  }
}

/**
 * Get repositories
 */
async function getRepos() {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/repos`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch repos:', error);
    throw error;
  }
}

/**
 * Add a repository
 */
async function addRepo(path) {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/repos/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to add repo:', error);
    throw error;
  }
}

/**
 * Remove a repository
 */
async function removeRepo(path) {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/repos/remove`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to remove repo:', error);
    throw error;
  }
}

/**
 * Pause a repository
 */
async function pauseRepo(path) {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/repos/pause`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to pause repo:', error);
    throw error;
  }
}

/**
 * Resume a repository
 */
async function resumeRepo(path) {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/repos/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to resume repo:', error);
    throw error;
  }
}

/**
 * Rename a repository's project
 */
async function renameRepo(path, name) {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/repos/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, name })
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to rename repo:', error);
    throw error;
  }
}

/**
 * Get cron status
 */
async function getCronStatus() {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/cron`);
    return await response.json();
  } catch (error) {
    console.error('Failed to fetch cron status:', error);
    throw error;
  }
}

/**
 * Trigger story generation
 */
async function triggerGeneration() {
  try {
    const response = await fetchWithRetry(`${API_BASE}/api/generate`, {
      method: 'POST'
    });
    return await response.json();
  } catch (error) {
    console.error('Failed to trigger generation:', error);
    throw error;
  }
}

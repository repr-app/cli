/**
 * Theme Module
 * Handles dark/light mode with system preference detection and localStorage persistence
 */

const THEME_KEY = 'repr-dashboard-theme';

/**
 * Initialize theme on page load
 * Respects prefers-color-scheme if no saved preference
 */
function initTheme() {
  const savedTheme = localStorage.getItem(THEME_KEY);

  if (savedTheme) {
    setTheme(savedTheme);
  } else {
    // Check system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    setTheme(prefersDark ? 'dark' : 'light');
  }

  // Listen for system theme changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem(THEME_KEY)) {
      setTheme(e.matches ? 'dark' : 'light');
    }
  });
}

/**
 * Set theme to dark or light
 */
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  updateThemeToggleIcon(theme);
}

/**
 * Toggle between dark and light themes
 */
function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

  setTheme(newTheme);
  localStorage.setItem(THEME_KEY, newTheme);
  showToast(`${newTheme === 'dark' ? 'Dark' : 'Light'} mode enabled`, 'success');
}

/**
 * Get current theme
 */
function getTheme() {
  return document.documentElement.getAttribute('data-theme') || 'light';
}

/**
 * Update theme toggle button icon
 */
function updateThemeToggleIcon(theme) {
  const toggle = document.getElementById('theme-toggle');
  if (toggle) {
    const icon = toggle.querySelector('.theme-toggle-icon');
    if (icon) {
      icon.textContent = theme === 'dark' ? '☀' : '☾';
    }
  }
}

// Expose functions to global scope for inline onclick handlers
window.toggleTheme = toggleTheme;

/**
 * Utility Functions
 * Contains helper functions for string manipulation, colors, and formatting
 */

/**
 * Generate a color from a string hash
 */
function stringToColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  return `hsl(${h}, 70%, 45%)`;
}

/**
 * Clean conventional commit prefixes from titles
 */
function cleanTitle(title) {
  if (!title) return '';
  let cleaned = title.replace(/^(feat|chore|docs|fix|refactor|style|test|perf|ci|build)(\(.*\))?!?:?\s*/i, '');
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Highlight search query in text
 */
function highlightText(text, query) {
  if (!query || !text) return escapeHtml(text);
  const output = escapeHtml(text);
  try {
    const pattern = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return output.replace(pattern, '<span class="highlight">$1</span>');
  } catch (e) {
    return output;
  }
}

/**
 * Format time difference as human-readable string
 */
function timeSince(date) {
  const seconds = Math.floor((new Date() - date) / 1000);
  if (seconds < 60) return 'Just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + 'm';
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + 'h';
  const days = Math.floor(hours / 24);
  return days + 'd';
}

/**
 * Show toast notification
 */
function showToast(message, type = 'success') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => toast.remove(), 3000);
}

/**
 * Toggle mobile sidebar
 */
function toggleSidebar() {
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');
  sidebar.classList.toggle('open');
  overlay.classList.toggle('open');
}

/**
 * Request notification permission
 */
function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }
}

/**
 * Show browser notification
 */
function notify(title, options = {}) {
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(title, options);
  }
}

// Expose functions to global scope for inline onclick handlers
window.toggleSidebar = toggleSidebar;

/**
 * Open a modal by ID
 */
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('open');
    document.body.style.overflow = 'hidden'; // Prevent scrolling
  }
}

/**
 * Close a modal by ID
 */
function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('open');
    document.body.style.overflow = ''; // Restore scrolling
  }
}

window.openModal = openModal;
window.closeModal = closeModal;

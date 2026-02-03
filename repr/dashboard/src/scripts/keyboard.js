/**
 * Keyboard Navigation Module
 * Provides vim-style keyboard shortcuts for power users
 */

let selectedStoryIndex = -1;
let keyboardShortcutsVisible = false;

/**
 * Initialize keyboard navigation
 */
function initKeyboard() {
  document.addEventListener('keydown', handleKeydown);
}

/**
 * Handle keyboard events
 */
function handleKeydown(e) {
  // ⌘K / Ctrl+K to focus search (works from anywhere)
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    focusSearch();
    return;
  }

  // Don't intercept when typing in inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
    if (e.key === 'Escape') {
      e.target.blur();
      return;
    }
    return;
  }

  // Don't intercept if modal is open
  if (keyboardShortcutsVisible) {
    if (e.key === 'Escape' || e.key === '?') {
      hideKeyboardShortcuts();
      e.preventDefault();
    }
    return;
  }

  switch (e.key) {
    case '/':
      e.preventDefault();
      focusSearch();
      break;
    case 'j':
      e.preventDefault();
      selectNextStory();
      break;
    case 'k':
      e.preventDefault();
      selectPreviousStory();
      break;
    case 'Enter':
      if (selectedStoryIndex >= 0) {
        e.preventDefault();
        openSelectedStory();
      }
      break;
    case 'Escape':
      e.preventDefault();
      handleEscape();
      break;
    case 'r':
    case 'R':
      e.preventDefault();
      refreshStories();
      break;
    case '?':
      e.preventDefault();
      showKeyboardShortcuts();
      break;
  }
}

/**
 * Focus the search input
 */
function focusSearch() {
  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    searchInput.focus();
    showToast('Search focused (type to filter, Esc to clear)', 'success');
  }
}

/**
 * Select the next story in the feed
 */
function selectNextStory() {
  const stories = getVisibleStories();
  if (!stories.length) return;

  selectedStoryIndex = Math.min(selectedStoryIndex + 1, stories.length - 1);
  highlightSelectedStory(stories);
}

/**
 * Select the previous story in the feed
 */
function selectPreviousStory() {
  const stories = getVisibleStories();
  if (!stories.length) return;

  selectedStoryIndex = Math.max(selectedStoryIndex - 1, 0);
  highlightSelectedStory(stories);
}

/**
 * Get visible story elements
 */
function getVisibleStories() {
  return Array.from(document.querySelectorAll('.post-card'));
}

/**
 * Highlight the selected story
 */
function highlightSelectedStory(stories) {
  stories.forEach((story, index) => {
    story.classList.toggle('selected', index === selectedStoryIndex);
    if (index === selectedStoryIndex) {
      story.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  });
}

/**
 * Open the currently selected story
 */
function openSelectedStory() {
  const stories = getVisibleStories();
  if (selectedStoryIndex >= 0 && selectedStoryIndex < stories.length) {
    const storyEl = stories[selectedStoryIndex];
    const storyId = storyEl.id.replace('post-', '');
    if (storyId) {
      openStory({ stopPropagation: () => {} }, storyId);
    }
  }
}

/**
 * Handle Escape key - close views, clear search, reset selection
 */
function handleEscape() {
  // Close detail/profile views and go back
  const detailView = document.getElementById('view-detail');
  const profileView = document.getElementById('view-profile');

  if (detailView?.style.display !== 'none' || profileView?.style.display !== 'none') {
    goBack();
    return;
  }

  // Clear search
  const searchInput = document.getElementById('search-input');
  if (searchInput && searchInput.value) {
    searchInput.value = '';
    store.update('searchQuery', '');
    filterAndRenderStories();
    return;
  }

  // Clear selection
  if (selectedStoryIndex >= 0) {
    selectedStoryIndex = -1;
    const stories = getVisibleStories();
    stories.forEach(s => s.classList.remove('selected'));
  }
}

/**
 * Show keyboard shortcuts modal
 */
function showKeyboardShortcuts() {
  if (keyboardShortcutsVisible) return;
  keyboardShortcutsVisible = true;

  const modal = document.createElement('div');
  modal.id = 'keyboard-shortcuts-modal';
  modal.className = 'keyboard-modal';
  modal.innerHTML = `
    <div class="keyboard-modal-backdrop" onclick="hideKeyboardShortcuts()"></div>
    <div class="keyboard-modal-content">
      <div class="keyboard-modal-header">
        <h3>Keyboard Shortcuts</h3>
        <button class="keyboard-modal-close" onclick="hideKeyboardShortcuts()">×</button>
      </div>
      <div class="keyboard-shortcuts-list">
        <div class="shortcut-row">
          <kbd>/</kbd>
          <span>Focus search</span>
        </div>
        <div class="shortcut-row">
          <kbd>j</kbd>
          <span>Next story</span>
        </div>
        <div class="shortcut-row">
          <kbd>k</kbd>
          <span>Previous story</span>
        </div>
        <div class="shortcut-row">
          <kbd>Enter</kbd>
          <span>Open selected story</span>
        </div>
        <div class="shortcut-row">
          <kbd>Esc</kbd>
          <span>Close / Clear search / Reset</span>
        </div>
        <div class="shortcut-row">
          <kbd>r</kbd>
          <span>Refresh stories</span>
        </div>
        <div class="shortcut-row">
          <kbd>?</kbd>
          <span>Show this help</span>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
}

/**
 * Hide keyboard shortcuts modal
 */
function hideKeyboardShortcuts() {
  const modal = document.getElementById('keyboard-shortcuts-modal');
  if (modal) {
    modal.remove();
    keyboardShortcutsVisible = false;
  }
}

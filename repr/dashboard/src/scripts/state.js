/**
 * State Management
 * Centralized state management with subscriber pattern for reactive updates
 */

class State {
  constructor() {
    this.state = {
      stories: [],
      repos: [],
      config: null,
      cronStatus: null,
      currentRepo: 'all',
      searchQuery: '',
      currentMainView: 'stories',
      currentSettingsTab: 'form',
      configDirty: false,
      previousView: 'view-main'
    };
    this.subscribers = [];
  }

  /**
   * Get current state
   */
  get(key) {
    if (key) {
      return this.state[key];
    }
    return this.state;
  }

  /**
   * Update state and notify subscribers
   */
  update(key, value) {
    const oldValue = this.state[key];
    this.state[key] = value;

    // Notify subscribers with the changed key
    this.subscribers.forEach(fn => fn(key, value, oldValue));
  }

  /**
   * Batch update multiple state values
   */
  batchUpdate(updates) {
    Object.entries(updates).forEach(([key, value]) => {
      this.state[key] = value;
    });

    // Notify subscribers once with all changes
    this.subscribers.forEach(fn => fn('batch', updates, null));
  }

  /**
   * Subscribe to state changes
   */
  subscribe(fn) {
    this.subscribers.push(fn);

    // Return unsubscribe function
    return () => {
      const index = this.subscribers.indexOf(fn);
      if (index > -1) {
        this.subscribers.splice(index, 1);
      }
    };
  }

  /**
   * Reset state to initial values
   */
  reset() {
    this.state = {
      stories: [],
      repos: [],
      config: null,
      cronStatus: null,
      currentRepo: 'all',
      searchQuery: '',
      currentMainView: 'stories',
      currentSettingsTab: 'form',
      configDirty: false,
      previousView: 'view-main'
    };
    this.subscribers.forEach(fn => fn('reset', this.state, null));
  }
}

// Create global state instance
const store = new State();

/**
 * Router to handle browser history
 */
store.initRouter = function () {
  window.addEventListener('popstate', (event) => {
    const state = event.state;
    if (!state) {
      // Default state
      store.update('currentMainView', 'stories');
      switchMainView('stories', false); // false = don't push state
      closeOverlays();
      return;
    }

    if (state.view === 'detail' && state.storyId) {
      // Open story detail without pushing state
      const stories = store.get('stories');
      const story = stories.find(s => s.id === state.storyId);
      if (story) openStory(null, state.storyId, false);
    } else if (state.view === 'profile' && state.repoName) {
      // Open profile without pushing state
      openProfile(null, state.repoName, false);
    } else if (state.view === 'main') {
      // Switch main view without pushing state
      closeOverlays();
      if (state.mainView) {
        switchMainView(state.mainView, false);
      }
    }
  });

  // Handle initial load if needed (e.g. deep linking can be added here later)
};

store.pushHistory = function (state, title, url) {
  history.pushState(state, title, url);
};

function closeOverlays() {
  const detail = document.getElementById('view-detail');
  if (detail) {
    detail.classList.remove('open');
    detail.style.display = 'none';
  }

  const profile = document.getElementById('view-profile');
  if (profile) {
    profile.classList.remove('open');
    profile.style.display = 'none';
  }
}

/**
 * Stories Module
 * Handles story rendering and management
 */

// Mock data for demo mode
const MOCK_STORIES = [
  {
    id: "mock-1",
    repo_name: "cli",
    author_name: "mendrika",
    verified: true,
    signature_status: "all_verified",
    signed_count: 3,
    total_commits: 3,
    category: "feature",
    title: "Restore dashboard diff functionality and improve branch suggestions",
    problem: "The dashboard lacked diff visualization, and internal models required refactoring to support better branch suggestions.",
    approach: "Executed a refactor of core data models and synthesis logic to improve code representation, then restored the diff view in the dashboard.",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    technologies: ["Python", "SQLite", "Jinja2"],
    lessons: ["Separating the 'Synthesis' logic from the 'Presentation' logic made the diff rendering 3x faster."],
    files: ["src/dashboard.py", "templates/index.html"],
    implementation_details: [
      "Refactored `DiffGenerator` class to handle binary files gracefully.",
      "Updated Jinja2 templates to loop through file deltas.",
      "Added caching layer for diffs larger than 1MB."
    ],
    key_snippets: [
      {
        file_path: "src/dashboard.py",
        line_count: 15,
        content: "def get_diff(self, file_path):\n    # Check cache first\n    if file_path in self.cache:\n        return self.cache[file_path]\n    \n    # Generate diff\n    diff = git.diff(file_path)\n    return diff"
      }
    ]
  },
  {
    id: "mock-2",
    repo_name: "repr",
    author_name: "johndoe",
    verified: false,
    signature_status: "unsigned",
    signed_count: 0,
    total_commits: 2,
    category: "chore",
    title: "docs: update CLI usage messages for clarity",
    problem: "The previous usage messages were too generic and lacked context for specific arguments.",
    approach: "Updated help strings in Typer/Click definitions to include examples.",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
    technologies: ["Python", "Typer"],
    files: ["cli/main.py"]
  },
  {
    id: "mock-3",
    repo_name: "agent-core",
    author_name: "alice",
    verified: false,
    signature_status: "partially_signed",
    signed_count: 2,
    total_commits: 4,
    category: "bugfix",
    title: "Fix memory leak in background worker",
    problem: "The worker process was consuming increasing RAM over long execution periods.",
    approach: "Identified a circular reference in the Task object. Implemented weak references for parent links.",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
    technologies: ["Rust", "Tokio"],
    diagram: "Task -> (strong) -> Context -> (strong) -> Task [LEAK]\n\nFix:\nTask -> (strong) -> Context -> (weak) -> Task"
  }
];

/**
 * Initialize stories from API or use mock data
 */
async function initStories() {
  renderSkeletons();
  try {
    const [stats, storiesData] = await Promise.all([
      getStatus(),
      getStories()
    ]);

    document.getElementById('status-text').innerText = `${stats.count} stories · ${stats.repos} repos`;
    store.update('stories', storiesData.stories);
  } catch (error) {
    console.warn('Using mock data:', error);
    store.update('stories', MOCK_STORIES);
    document.getElementById('status-text').innerText = `${MOCK_STORIES.length} stories · Demo Mode`;
  }

  renderRepoTabs();
  filterAndRenderStories();

  // Initialize router after stories are loaded
  if (store.initRouter) {
    store.initRouter();
  }

  // Handle initial URL query parameter for view
  const urlParams = new URLSearchParams(window.location.search);
  const viewParam = urlParams.get('view');
  if (viewParam && ['stories', 'settings', 'llm', 'privacy', 'repos', 'cron'].includes(viewParam)) {
    switchMainView(viewParam, false); // false = don't push to history
  }
}

/**
 * Render repository tabs
 */
function renderRepoTabs() {
  const tabs = document.getElementById('repo-tabs');
  if (!tabs) return;

  const stories = store.get('stories');
  const repos = {};
  let html = '<div class="repo-tab active" data-repo="all">All</div>';

  Object.entries(repos).sort((a, b) => b[1] - a[1]).forEach(([name, count]) => {
    html += `<div class="repo-tab" data-repo="${name}">${name}</div>`;
  });

  tabs.innerHTML = html;

  tabs.querySelectorAll('.repo-tab').forEach(tab => {
    tab.onclick = () => {
      tabs.querySelectorAll('.repo-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      store.update('currentRepo', tab.dataset.repo);
      filterAndRenderStories();
    };
  });
}

/**
 * Filter and render stories based on current repo and search query
 */
function filterAndRenderStories() {
  const stories = store.get('stories');
  const currentRepo = store.get('currentRepo');
  const searchQuery = store.get('searchQuery');

  let filtered = stories;

  // Repo filter
  if (currentRepo !== 'all') {
    filtered = filtered.filter(s => s.repo_name === currentRepo);
  }

  // Search filter
  if (searchQuery) {
    filtered = filtered.filter(s => {
      const searchStr = [
        s.title,
        s.repo_name,
        s.category,
        s.problem,
        s.approach,
        ...(s.technologies || []),
        ...(s.files || [])
      ].join(' ').toLowerCase();
      return searchStr.includes(searchQuery);
    });
  }

  renderStories(filtered);
}

/**
 * Get relative date label for a given date
 * Returns: "Today", "Yesterday", "This Week", or formatted date
 */
function getDateLabel(date) {
  const now = new Date();
  const storyDate = new Date(date);

  // Reset times for date comparison
  const nowDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const storyDateOnly = new Date(storyDate.getFullYear(), storyDate.getMonth(), storyDate.getDate());

  const diffDays = Math.floor((nowDate - storyDateOnly) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return 'This Week';

  // Format as "Jan 15" or "Jan 15, 2024" if different year
  const options = { month: 'short', day: 'numeric' };
  if (storyDate.getFullYear() !== now.getFullYear()) {
    options.year = 'numeric';
  }
  return storyDate.toLocaleDateString('en-US', options);
}

/**
 * Group stories by date
 */
function groupStoriesByDate(stories) {
  const groups = {};

  stories.forEach(story => {
    const date = story.started_at || story.created_at;
    const label = getDateLabel(date);

    if (!groups[label]) {
      groups[label] = [];
    }
    groups[label].push(story);
  });

  // Sort labels: Today, Yesterday, This Week, then chronologically
  const labelOrder = ['Today', 'Yesterday', 'This Week'];
  const sortedLabels = Object.keys(groups).sort((a, b) => {
    const aIndex = labelOrder.indexOf(a);
    const bIndex = labelOrder.indexOf(b);

    if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
    if (aIndex !== -1) return -1;
    if (bIndex !== -1) return 1;

    // For date labels, parse and compare
    return new Date(groups[b][0].started_at || groups[b][0].created_at) -
      new Date(groups[a][0].started_at || groups[a][0].created_at);
  });

  return { groups, labels: sortedLabels };
}

/**
 * Toggle a date group collapsed/expanded (not used - dates shown simply)
 */
function toggleDateGroup(label) {
  // Disabled - dates are shown simply without collapse
}

/**
 * Render stories to the feed with date grouping
 */
function renderStories(stories, containerId = 'feed') {
  const feed = document.getElementById(containerId);
  const searchQuery = store.get('searchQuery');

  if (!stories || !stories.length) {
    if (searchQuery) {
      feed.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-title">No matches found</div>
          <div style="font-size: 14px;">Try adjusting your search query or filters</div>
          <button class="btn btn-secondary" onclick="document.getElementById('search-input').value=''; store.update('searchQuery', ''); filterAndRenderStories();" style="margin-top: 16px;">Clear Search</button>
        </div>`;
    } else {
      feed.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-title">Your timeline is empty</div>
          <div style="font-size: 14px;">Run your first generation to see your development story</div>
          <button class="btn btn-primary" onclick="triggerGenerationClick()" style="margin-top: 16px;">Generate Now</button>
        </div>`;
    }
    return;
  }

  // If searching, don't group - show flat list with highlights
  if (searchQuery) {
    feed.innerHTML = stories.map(s => renderStoryCard(s, searchQuery)).join('');
    return;
  }

  // Group stories by date
  const { groups, labels } = groupStoriesByDate(stories);

  let html = '';
  labels.forEach(label => {
    const groupStories = groups[label];

    html += `
      <div class="date-header">
        <span class="date-header-label">${label}</span>
      </div>
      ${groupStories.map(s => renderStoryCard(s, searchQuery)).join('')}
    `;
  });

  feed.innerHTML = html;
}

/**
 * Render a single story card
 */
function renderStoryCard(s, searchQuery) {
  const timeStr = timeSince(new Date(s.started_at || s.created_at));
  const category = s.category || 'chore';
  const repoName = s.repo_name || 'cli';
  const username = s.author_name || s.username || 'unknown';
  const isVerified = s.verified || false;

  const displayTitle = highlightText(cleanTitle(s.title), searchQuery);
  const displayProblem = s.problem ? highlightText(s.problem, searchQuery) : '';
  const displayApproach = s.approach ? highlightText(s.approach, searchQuery) : '';
  const displayUsername = highlightText(username, searchQuery);

  const avatarColor = stringToColor(username);
  const avatarLetter = username.substring(0, 1).toUpperCase();
  const verifiedBadge = isVerified ? '<span class="verified-badge" title="GPG signed commits">✓</span>' : '';

  // Tags as hashtags
  const tags = [];
  if (s.technologies && s.technologies.length) {
    s.technologies.slice(0, 3).forEach(t => tags.push(`#${t.toLowerCase().replace(/\s+/g, '')}`));
  }
  const tagsHtml = tags.length ? tags.map(t => `<span class="hashtag">${highlightText(t, searchQuery)}</span>`).join(' ') : '';

  // Combine title and problem/approach as the post content
  const bodyText = displayProblem || displayApproach;

  // Media content (diagrams, show output)
  let mediaHtml = '';
  if (s.diagram) {
    mediaHtml += `<div class="post-media"><pre class="post-diagram">${escapeHtml(s.diagram)}</pre></div>`;
  }
  if (s.show) {
    mediaHtml += `<div class="post-media"><pre class="post-output">${escapeHtml(s.show)}</pre></div>`;
  }

  return `
    <article class="post-card" id="post-${s.id}" onclick="openStory(event, '${s.id}')">
      <div class="post-avatar" style="background:${avatarColor}">${avatarLetter}</div>
      <div class="post-body">
        <div class="post-header">
          <span class="post-author">${displayUsername}${verifiedBadge}</span>
          <span class="post-handle">@${repoName}</span>
          <span class="post-meta-sep">·</span>
          <span class="post-time">${timeStr}</span>
        </div>
        <div class="post-text"><strong>${displayTitle}</strong>${bodyText ? `\n${bodyText}` : ''}</div>
        ${mediaHtml}
        ${tagsHtml ? `<div class="post-tags">${tagsHtml}</div>` : ''}
        <div class="post-actions">
          <div class="post-action" title="${category}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
            </svg>
            <span>${s.total_commits || ''}</span>
          </div>
          <div class="post-action" title="Like">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
          </div>
        </div>
      </div>
    </article>
  `;
}

/**
 * Open story detail view
 */
/**
 * Open story detail view
 */
function openStory(event, storyId, pushState = true) {
  const stories = store.get('stories');
  const story = stories.find(s => s.id === storyId);
  if (!story) return;

  if (pushState) {
    window.lastScrollY = window.scrollY;

    // Determine current view for back button logic if any
    if (document.getElementById('view-profile').style.display === 'flex') {
      store.update('previousView', 'view-profile');
    } else {
      store.update('previousView', 'view-main');
    }

    store.pushHistory({ view: 'detail', storyId: storyId }, `Repr - ${cleanTitle(story.title)}`, `?story=${storyId}`);
  }

  const detailView = document.getElementById('view-detail');
  detailView.classList.add('open');
  window.scrollTo(0, 0);

  const contentEl = document.getElementById('detail-content');
  const timeStr = timeSince(new Date(story.started_at || story.created_at));
  const category = story.category || 'update';
  const repoName = story.repo_name || 'cli';
  const username = story.author_name || story.username || 'unknown';
  const isVerified = story.verified || false;
  const displayTitle = cleanTitle(story.title);

  const verifiedBadge = isVerified ? '<span class="verified-badge" title="GPG signed commits">✓</span>' : '';
  const signatureInfo = story.signature_status ? `
    <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
      ${isVerified ? '🔒 All commits GPG signed' : story.signature_status === 'partially_signed' ? '⚠️ Some commits unsigned' : '⚠️ Unsigned commits'}
      ${story.signed_count !== undefined ? ` (${story.signed_count}/${story.total_commits} signed)` : ''}
    </div>
  ` : '';

  const techHtml = (story.technologies && story.technologies.length) ?
    `<div class="skills-inline">${story.technologies.map(t => `<span class="skill-tag">${escapeHtml(t)}</span>`).join('')}</div>` : '';

  const showHtml = story.show ? `<div class="snippet-block" style="margin-top:16px"><div class="snippet-header">Output</div><div class="snippet-code"><pre>${escapeHtml(story.show)}</pre></div></div>` : '';

  const diagramHtml = story.diagram ? `<div class="diagram-block"><pre>${escapeHtml(story.diagram)}</pre></div>` : '';

  const filesHtml = (story.files && story.files.length) ?
    `<div class="section-subtitle">Files Touched</div>
     <div class="files-row">
       ${story.files.map(f => `<span class="file-tag">${escapeHtml(f.split('/').pop())}</span>`).join('')}
     </div>` : '';

  const snippetsHtml = (story.key_snippets && story.key_snippets.length) ?
    `<div class="section-subtitle">Key Snippets</div>
     ${story.key_snippets.map(s => `
       <div class="snippet-block">
         <div class="snippet-header">${escapeHtml(s.file_path)}</div>
         <div class="snippet-code"><pre>${escapeHtml(s.content)}</pre></div>
       </div>
     `).join('')}` : '';

  const fileChangesHtml = (story.file_changes && story.file_changes.length) ?
    `<div class="section-subtitle">File Changes</div>
     <ul style="padding-left:16px; color:var(--text-secondary); font-size:15px; margin-bottom: 24px; list-style: none;">
       ${story.file_changes.map(ch => {
      const path = ch.file_path || ch.path || 'unknown';
      const changeType = ch.change_type || 'modified';
      const insertions = ch.insertions || 0;
      const deletions = ch.deletions || 0;
      const stats = [];
      if (insertions > 0) stats.push(`<span style="color: var(--green);">+${insertions}</span>`);
      if (deletions > 0) stats.push(`<span style="color: var(--red);">-${deletions}</span>`);
      const statsStr = stats.length > 0 ? stats.join('/') : '0 changes';
      return `<li style="margin-bottom: 4px; font-family: var(--font-mono); font-size: 13px;">
           <span style="color: var(--text-muted);">[${changeType}]</span> ${escapeHtml(path.split('/').pop())}
           <span style="margin-left: 8px; font-size: 12px;">${statsStr}</span>
         </li>`;
    }).join('')}
     </ul>` : '';

  const avatarColor = stringToColor(username);
  const avatarLetter = username.substring(0, 2).toUpperCase();

  contentEl.innerHTML = `
    <div class="post" style="border-bottom: 0; cursor: default; padding: 16px;">
        <div class="post-content">
            <div class="post-header">
              <div class="user-info" onclick="openProfile(event, '${repoName}')">
                <div class="tiny-avatar" style="background:${avatarColor}">${avatarLetter}</div>
                <div>
                  <span class="name">/u/${escapeHtml(username)}${verifiedBadge}</span>
                  <span style="color: var(--text-muted); font-size: 12px; margin-left: 4px;">/r/${repoName}</span>
                  ${signatureInfo}
                </div>
              </div>
              <span class="category ${category}">${category}</span>
              <span class="time">${timeStr}</span>
              ${techHtml}
            </div>
            <div class="post-title" style="font-size: 24px;">${escapeHtml(displayTitle)}</div>
            ${story.problem ? `<div class="post-problem" style="font-size: 16px; margin-bottom:12px;">${escapeHtml(story.problem)}</div>` : ''}
            ${story.approach ? `<div class="post-approach" style="font-size: 16px;">${escapeHtml(story.approach)}</div>` : ''}

            ${showHtml}
            ${diagramHtml}

            <hr style="border: 0; border-top: 1px solid var(--border); margin: 32px 0;">

            ${story.lessons && story.lessons.length ? `
              <div class="insight-box">
                <div class="insight-label">Transferable Insight</div>
                ${story.lessons.map(l => `<div class="insight-text">${escapeHtml(l)}</div>`).join('')}
              </div>
            ` : ''}

            ${story.implementation_details && story.implementation_details.length ? `
               <div class="section-subtitle">Implementation Details</div>
               <ul style="padding-left:16px; color:var(--text-secondary); font-size:15px; line-height:1.6; margin-bottom: 24px;">
                 ${story.implementation_details.map(d => `<li>${escapeHtml(d)}</li>`).join('')}
               </ul>
            ` : ''}

            ${filesHtml}
            ${snippetsHtml}
            ${fileChangesHtml}
        </div>
      </div>
  `;
}

/**
 * Open profile view for a repository
 */
/**
 * Open profile view for a repository
 */
function openProfile(event, repoName, pushState = true) {
  if (event) event.stopPropagation();

  if (pushState) {
    window.lastScrollY = window.scrollY;
    store.update('previousView', 'view-profile');
    store.pushHistory({ view: 'profile', repoName: repoName }, `Repr - @${repoName}`, `?profile=${repoName}`);
  }

  document.getElementById('view-main').style.display = 'none';
  document.getElementById('view-detail').style.display = 'none';

  const profileView = document.getElementById('view-profile');
  profileView.style.display = 'flex';
  window.scrollTo(0, 0);

  const avatarColor = stringToColor(repoName);
  const avatarLetter = repoName.substring(0, 1).toUpperCase();

  document.getElementById('profile-view-avatar').style.background = avatarColor;
  document.getElementById('profile-view-avatar').textContent = avatarLetter;
  document.getElementById('profile-view-name').textContent = repoName;
  document.getElementById('profile-view-handle').textContent = '@' + repoName;

  const stories = store.get('stories');
  const profileStories = stories.filter(s => s.repo_name === repoName);
  document.getElementById('profile-view-bio').textContent = `${profileStories.length} stories in this repository.`;

  renderStories(profileStories, 'profile-feed');
}

/**
 * Go back to previous view
 */
/**
 * Go back to previous view
 */
function goBack() {
  if (history.length > 1) {
    history.back();
  } else {
    // Fallback if no history
    const detailView = document.getElementById('view-detail');
    const profileView = document.getElementById('view-profile');

    if (detailView.classList.contains('open')) {
      detailView.classList.remove('open');
    } else if (profileView.style.display === 'flex') {
      document.getElementById('view-profile').style.display = 'none';
      document.getElementById('view-main').style.display = 'flex';
    }

    if (window.lastScrollY) window.scrollTo(0, window.lastScrollY);
  }
}

/**
 * Refresh stories from API
 */
async function refreshStories() {
  showToast('Refreshing...', 'success');
  await initStories();
}

/**
 * Trigger manual story generation
 */
async function triggerGenerationClick() {
  if (!confirm('Start generating stories now? This will run in the background.')) return;

  try {
    const result = await triggerGeneration();

    if (result.success) {
      showToast('Generation started', 'success');
    } else {
      showToast('Failed to start generation', 'error');
    }
  } catch (error) {
    showToast('Error triggering generation', 'error');
  }
}

/**
 * Render skeleton loaders
 */
function renderSkeletons(containerId = 'feed', count = 3) {
  const feed = document.getElementById(containerId);
  if (!feed) return;

  let html = '';
  for (let i = 0; i < count; i++) {
    html += `
      <div class="skeleton-card">
        <div class="skeleton-avatar skeleton"></div>
        <div class="skeleton-body">
          <div class="skeleton-header skeleton"></div>
          <div class="skeleton-title skeleton"></div>
          <div class="skeleton-text skeleton"></div>
          <div class="skeleton-text skeleton" style="width: 60%"></div>
        </div>
      </div>
    `;
  }
  feed.innerHTML = html;
}

// Expose functions to global scope for inline onclick handlers
window.openStory = openStory;
window.openProfile = openProfile;
window.triggerGenerationClick = triggerGenerationClick;
window.goBack = goBack;
window.refreshStories = refreshStories;

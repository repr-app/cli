"""
HTTP server for repr story dashboard.
"""

import http.server
import json
import socketserver
from functools import partial
from pathlib import Path
from typing import Any


class TimelineHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for story dashboard."""
    
    def __init__(self, *args, store_path: Path, **kwargs):
        self.store_path = store_path
        super().__init__(*args, **kwargs)
    
    def log_message(self, format: str, *args) -> None:
        pass
    
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.serve_dashboard()
        elif self.path == "/api/stories":
            self.serve_stories()
        elif self.path == "/api/status":
            self.serve_status()
        else:
            self.send_error(404, "Not Found")
    
    def serve_dashboard(self):
        html = get_dashboard_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html.encode()))
        self.end_headers()
        self.wfile.write(html.encode())
    
    def serve_stories(self):
        try:
            data = json.loads(self.store_path.read_text())
            # Return stories list directly or wrapped
            body = json.dumps(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except FileNotFoundError:
            self.send_error(404, "Store not found")
        except Exception as e:
            self.send_error(500, str(e))
    
    def serve_status(self):
        try:
            data = json.loads(self.store_path.read_text())
            stories = data.get("stories", [])
            
            stats = {
                "count": len(stories),
                "last_updated": data.get("last_updated"),
                "categories": {},
                "files": len(data.get("index", {}).get("files_to_stories", {})),
            }
            
            for s in stories:
                cat = s.get("category", "other")
                stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
            
            body = json.dumps(stats)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body.encode()))
            self.end_headers()
            self.wfile.write(body.encode())
        except Exception:
            self.send_error(500, "Error loading stats")


def run_server(port: int, host: str, timeline_path: Path) -> None:
    """
    Start the dashboard HTTP server.
    Note: timeline_path argument name kept for compatibility, but passed as store_path.
    """
    handler = partial(TimelineHandler, store_path=timeline_path)
    
    print(f"Serving on http://{host}:{port}")
    with socketserver.TCPServer((host, port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def get_dashboard_html() -> str:
    return '''<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>repr stories</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Outfit', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    },
                    colors: {
                        dark: {
                            bg: '#050507',
                            card: '#0E0E12',
                            border: '#1F1F26',
                            text: '#E1E1E6',
                            muted: '#8D8D99',
                        },
                        brand: {
                            primary: '#6D28D9', # Purple 700
                            accent: '#8B5CF6', # Violet 500
                            glow: 'rgba(139, 92, 246, 0.15)',
                        }
                    },
                    animation: {
                        'fade-in': 'fadeIn 0.5s ease-out forwards',
                        'slide-up': 'slideUp 0.4s ease-out forwards',
                    },
                    keyframes: {
                        fadeIn: {
                            '0%': { opacity: '0' },
                            '100%': { opacity: '1' },
                        },
                        slideUp: {
                            '0%': { opacity: '0', transform: 'translateY(10px)' },
                            '100%': { opacity: '1', transform: 'translateY(0)' },
                        }
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #050507; color: #E1E1E6; }
        .glass-card {
            background: rgba(14, 14, 18, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid #1F1F26;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .glass-card:hover {
            border-color: #3F3F46;
            box-shadow: 0 0 20px rgba(139, 92, 246, 0.05);
            transform: translateY(-2px);
        }
        .category-pill {
            font-size: 0.7rem;
            padding: 0.15rem 0.5rem;
            border-radius: 9999px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .cat-feature { background: rgba(16, 185, 129, 0.1); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.2); }
        .cat-bugfix { background: rgba(239, 68, 68, 0.1); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.2); }
        .cat-infra { background: rgba(59, 130, 246, 0.1); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.2); }
        .cat-refactor { background: rgba(245, 158, 11, 0.1); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.2); }
        .cat-other { background: rgba(107, 114, 128, 0.1); color: #9CA3AF; border: 1px solid rgba(107, 114, 128, 0.2); }

        /* Custom Scrollbar */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #27272A; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #3F3F46; }

        .details-enter { 
            display: grid; 
            grid-template-rows: 0fr; 
            transition: grid-template-rows 0.3s ease-out; 
            opacity: 0;
        }
        .details-enter.open { 
            grid-template-rows: 1fr;
            opacity: 1;
        }
        .details-inner { overflow: hidden; }
    </style>
</head>
<body class="antialiased selection:bg-brand-accent selection:text-white pb-20">

    <!-- Navbar -->
    <nav class="sticky top-0 z-50 bg-[#050507]/80 backdrop-blur-md border-b border-dark-border">
        <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-primary to-brand-accent flex items-center justify-center font-bold text-white shadow-lg shadow-brand-glow">
                    r
                </div>
                <h1 class="font-bold text-lg tracking-tight">repr <span class="text-dark-muted font-normal">stories</span></h1>
                <span id="story-count" class="ml-2 text-xs text-dark-muted py-0.5 px-2 rounded-full border border-dark-border bg-dark-card">
                    ...
                </span>
            </div>
            
            <div class="flex items-center gap-4">
                <div class="relative group">
                    <input type="text" id="search" placeholder="Search stories..." 
                        class="bg-dark-card border border-dark-border text-sm rounded-full px-4 py-1.5 w-64 focus:outline-none focus:border-brand-accent focus:ring-1 focus:ring-brand-accent transition-all placeholder-dark-muted/50">
                    <div class="absolute right-3 top-2 text-xs text-dark-muted opacity-50 group-hover:opacity-100 transition-opacity">/</div>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="max-w-4xl mx-auto px-4 sm:px-6 mt-12">
        
        <!-- Filters -->
        <div class="flex gap-2 overflow-x-auto pb-4 mb-4 scrollbar-hide no-scrollbar" id="filters">
            <button class="px-4 py-1.5 rounded-full text-sm font-medium bg-white text-black transition-transform active:scale-95" data-cat="all">All</button>
            <button class="px-4 py-1.5 rounded-full text-sm font-medium bg-dark-card border border-dark-border text-dark-muted hover:text-white hover:border-dark-text transition-colors" data-cat="feature">Features</button>
            <button class="px-4 py-1.5 rounded-full text-sm font-medium bg-dark-card border border-dark-border text-dark-muted hover:text-white hover:border-dark-text transition-colors" data-cat="bugfix">Bugfixes</button>
            <button class="px-4 py-1.5 rounded-full text-sm font-medium bg-dark-card border border-dark-border text-dark-muted hover:text-white hover:border-dark-text transition-colors" data-cat="infra">Infra</button>
        </div>

        <!-- Stories Feed -->
        <div id="feed" class="space-y-4">
            <!-- Loading State -->
            <div class="animate-pulse space-y-4">
                <div class="h-32 bg-dark-card rounded-xl border border-dark-border"></div>
                <div class="h-32 bg-dark-card rounded-xl border border-dark-border"></div>
            </div>
        </div>

    </main>

    <script>
        let allStories = [];
        let currentFilter = 'all';

        async function init() {
            try {
                const res = await fetch('/api/stories');
                const data = await res.json();
                allStories = data.stories || [];
                
                // Sort by date DESC (newest first)
                allStories.sort((a, b) => {
                    const dateA = new Date(a.started_at || a.created_at || 0);
                    const dateB = new Date(b.started_at || b.created_at || 0);
                    return dateB - dateA;
                });
                
                // Update stats
                document.getElementById('story-count').textContent = `${allStories.length}`;
                
                render();
            } catch (e) {
                console.error(e);
                document.getElementById('feed').innerHTML = `<div class="text-red-500 text-center py-10">Failed to load stories</div>`;
            }
        }

        function render() {
            const container = document.getElementById('feed');
            const search = document.getElementById('search').value.toLowerCase();
            
            const filtered = allStories.filter(s => {
                const matchesCat = currentFilter === 'all' || s.category === currentFilter;
                const matchesSearch = !search || 
                    s.title.toLowerCase().includes(search) || 
                    (s.problem && s.problem.toLowerCase().includes(search));
                return matchesCat && matchesSearch;
            });

            if (filtered.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-20 opacity-50">
                        <div class="text-4xl mb-4">🕸️</div>
                        <p>No stories found</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = filtered.map((story, i) => {
                const delay = Math.min(i * 50, 500);
                const date = new Date(story.started_at || story.created_at || Date.now());
                const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                
                const implCount = story.implementation_details ? story.implementation_details.length : 0;
                
                return `
                <div class="glass-card rounded-xl p-6 animate-slide-up" style="animation-delay: ${delay}ms">
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex items-center gap-3">
                            <span class="category-pill cat-${story.category || 'other'}">${story.category || 'other'}</span>
                            <span class="text-xs text-dark-muted font-mono">${dateStr}</span>
                        </div>
                        <div class="flex gap-2">
                            ${implCount > 0 ? `<span class="text-xs text-dark-muted bg-dark-bg px-2 py-0.5 rounded border border-dark-border">${implCount} details</span>` : ''}
                        </div>
                    </div>

                    <h3 class="text-xl font-semibold mb-2 leading-tight">${escapeHtml(story.title)}</h3>
                    
                    ${story.problem ? `<p class="text-dark-muted text-sm leading-relaxed mb-4 line-clamp-2">${escapeHtml(story.problem)}</p>` : ''}
                    
                    <button onclick="toggleDetails('${story.id}')" class="text-xs font-medium text-brand-accent hover:text-white transition-colors flex items-center gap-1 group">
                        See implementation details
                        <svg class="w-3 h-3 transition-transform group-hover:translate-x-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                        </svg>
                    </button>

                    <div id="details-${story.id}" class="details-enter mt-0">
                        <div class="details-inner pt-4 border-t border-dark-border mt-4">
                            ${story.approach ? `
                                <div class="mb-4">
                                    <div class="text-xs font-bold text-dark-muted uppercase tracking-wider mb-2">Approach</div>
                                    <p class="text-sm text-gray-300">${escapeHtml(story.approach)}</p>
                                </div>
                            ` : ''}
                            
                            ${implCount > 0 ? `
                                <div>
                                    <div class="text-xs font-bold text-dark-muted uppercase tracking-wider mb-2">Implementation</div>
                                    <ul class="space-y-2">
                                        ${story.implementation_details.map(d => `
                                            <li class="text-sm text-gray-400 flex gap-2 items-start">
                                                <span class="text-brand-accent mt-1.5 w-1 h-1 rounded-full flex-shrink-0 bg-brand-accent"></span>
                                                <span class="leading-relaxed">${escapeHtml(d)}</span>
                                            </li>
                                        `).join('')}
                                    </ul>
                                </div>
                            ` : ''}

                             ${story.commit_shas ? `
                                <div class="mt-4 pt-3 border-t border-dark-border/50 flex gap-2 overflow-x-auto scrollbar-hide opacity-60 hover:opacity-100 transition-opacity">
                                    ${story.commit_shas.slice(0,5).map(sha => `
                                        <span class="font-mono text-[10px] bg-dark-bg border border-dark-border px-1.5 py-0.5 rounded text-dark-muted">${sha.substring(0,7)}</span>
                                    `).join('')}
                                    ${story.commit_shas.length > 5 ? `<span class="text-[10px] text-dark-muted self-center">+${story.commit_shas.length - 5}</span>` : ''}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
                `;
            }).join('');
        }

        window.toggleDetails = function(id) {
            const el = document.getElementById(`details-${id}`);
            const btn = el.previousElementSibling;
            el.classList.toggle('open');
            
            // Rotate arrow
            const svg = btn.querySelector('svg');
            if (el.classList.contains('open')) {
                svg.style.transform = 'rotate(90deg)';
                btn.classList.add('text-white');
            } else {
                svg.style.transform = 'rotate(0deg)';
                btn.classList.remove('text-white');
            }
        };

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Search listener
        document.getElementById('search').addEventListener('input', render);

        // Filter listeners
        document.getElementById('filters').addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON') {
                currentFilter = e.target.dataset.cat;
                
                // Update active state
                document.querySelectorAll('#filters button').forEach(btn => {
                    const isActive = btn.dataset.cat === currentFilter;
                    if (isActive) {
                        btn.className = 'px-4 py-1.5 rounded-full text-sm font-medium bg-white text-black transition-transform active:scale-95 shadow-lg shadow-white/10';
                    } else {
                        btn.className = 'px-4 py-1.5 rounded-full text-sm font-medium bg-dark-card border border-dark-border text-dark-muted hover:text-white hover:border-dark-text transition-colors';
                    }
                });
                
                render();
            }
        });

        // Initialize
        init();
    </script>
</body>
</html>'''


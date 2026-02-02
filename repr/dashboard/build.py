#!/usr/bin/env python3
"""
Build script for the dashboard
Inlines all CSS and JavaScript into a single HTML file for distribution
"""

import os
from pathlib import Path


def read_file(path: Path) -> str:
    """Read file contents"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def inline_css(html: str, src_dir: Path) -> str:
    """Replace CSS link tags with inline styles"""
    styles = []

    # Read all CSS files
    css_files = [
        src_dir / 'styles' / 'main.css',
        src_dir / 'styles' / 'components.css'
    ]

    for css_file in css_files:
        if css_file.exists():
            styles.append(read_file(css_file))

    # Combine all styles
    combined_styles = '\n'.join(styles)

    # Replace link tags with inline style
    import re
    pattern = r'<link rel="stylesheet" href="styles/[^"]+\.css">'

    # Find first occurrence and replace with all styles
    match = re.search(pattern, html)
    if match:
        replacement = f'<style>\n{combined_styles}\n  </style>'
        html = html[:match.start()] + replacement + re.sub(pattern, '', html[match.end():])

    return html


def inline_js(html: str, src_dir: Path) -> str:
    """Replace JavaScript script tags with inline scripts"""
    scripts = []

    # Read all JS files in order
    js_files = [
        src_dir / 'scripts' / 'utils.js',
        src_dir / 'scripts' / 'api.js',
        src_dir / 'scripts' / 'state.js',
        src_dir / 'scripts' / 'theme.js',
        src_dir / 'scripts' / 'keyboard.js',
        src_dir / 'scripts' / 'stories.js',
        src_dir / 'scripts' / 'settings.js',
        src_dir / 'scripts' / 'repos.js'
    ]

    for js_file in js_files:
        if js_file.exists():
            scripts.append(read_file(js_file))

    # Combine all scripts
    combined_scripts = '\n\n'.join(scripts)

    # Replace script tags with inline script
    import re
    pattern = r'<script src="scripts/[^"]+\.js"></script>'

    # Find first occurrence and replace with all scripts
    match = re.search(pattern, html)
    if match:
        replacement = f'<script>\n{combined_scripts}\n  </script>'
        html = html[:match.start()] + replacement + re.sub(pattern, '', html[match.end():])

    return html


def build():
    """Build the single-file dashboard"""
    # Get paths
    dashboard_dir = Path(__file__).parent
    src_dir = dashboard_dir / 'src'
    src_html = src_dir / 'index.html'
    output_html = dashboard_dir / 'index.html'

    if not src_html.exists():
        print(f"Error: Source HTML not found at {src_html}")
        return 1

    print(f"Building dashboard from {src_dir}...")

    # Read source HTML
    html = read_file(src_html)

    # Inline CSS
    print("  Inlining CSS...")
    html = inline_css(html, src_dir)

    # Inline JavaScript
    print("  Inlining JavaScript...")
    html = inline_js(html, src_dir)

    # Write output
    print(f"  Writing to {output_html}...")
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html)

    # Get file sizes
    src_size = sum(f.stat().st_size for f in src_dir.rglob('*') if f.is_file())
    output_size = output_html.stat().st_size

    print(f"\n✓ Build complete!")
    print(f"  Source: {len(list(src_dir.rglob('*.js')))} JS + {len(list(src_dir.rglob('*.css')))} CSS files ({src_size:,} bytes)")
    print(f"  Output: {output_html.name} ({output_size:,} bytes)")
    print(f"  Lines: {len(html.splitlines())}")

    return 0


if __name__ == '__main__':
    exit(build())

# Dashboard Architecture

The dashboard has been refactored from a single 2,463-line HTML file into a modular structure with proper state management, error handling, and build process.

## Directory Structure

```
repr/dashboard/
├── src/                        # Source files (modular)
│   ├── index.html             # Main HTML structure
│   ├── styles/
│   │   ├── main.css           # Global styles, variables, layout
│   │   └── components.css     # Component-specific styles
│   └── scripts/
│       ├── utils.js           # Utility functions
│       ├── api.js             # API calls with error handling
│       ├── state.js           # State management
│       ├── stories.js         # Story rendering and management
│       ├── settings.js        # Settings panel logic
│       └── repos.js           # Repository management
├── tests/                      # Unit tests
│   ├── test-utils.html        # Tests for utility functions
│   └── README.md
├── build.py                    # Build script
├── index.html                  # Built single-file output (for CLI)
└── README.md                   # This file
```

## Development

### Setup

The source files are located in `src/`. Edit these files during development.

### Building

Run the build script to combine all source files into a single `index.html`:

```bash
python build.py
```

This will:
- Inline all CSS from `src/styles/` into `<style>` tags
- Inline all JavaScript from `src/scripts/` into `<script>` tags
- Generate a single `index.html` file for CLI distribution

### Testing

Open test files in a browser:

```bash
# Start a local server
python3 -m http.server 8080

# Navigate to:
# http://localhost:8080/tests/test-utils.html
```

Or see `tests/README.md` for more details.

## Architecture

### State Management

The dashboard uses a centralized state management system (`state.js`) with a subscriber pattern:

```javascript
// Update state
store.update('stories', newStories);

// Subscribe to changes
store.subscribe((key, value, oldValue) => {
  console.log(`${key} changed from`, oldValue, 'to', value);
});
```

**State structure:**
- `stories`: Array of story objects
- `repos`: Array of repository objects
- `config`: Configuration object
- `currentRepo`: Currently selected repository filter
- `searchQuery`: Current search query
- `configDirty`: Whether config has unsaved changes

### Error Handling

API calls in `api.js` include:
- Automatic retry logic (up to 2 retries with exponential backoff)
- Consistent error handling
- User-friendly error messages via toast notifications

Example:

```javascript
try {
  const stories = await getStories();
  // Handle success
} catch (error) {
  showToast('Failed to load stories', 'error');
}
```

### Module Organization

#### utils.js
- `stringToColor(str)`: Generate consistent colors from strings
- `cleanTitle(title)`: Remove conventional commit prefixes
- `escapeHtml(text)`: Prevent XSS
- `highlightText(text, query)`: Highlight search matches
- `timeSince(date)`: Human-readable time differences

#### api.js
- All API calls with retry logic
- `getStories()`, `getConfig()`, `updateConfig()`, etc.

#### stories.js
- Story rendering and filtering
- Detail and profile views
- Search functionality

#### settings.js
- Settings management
- Form/JSON editors
- Config persistence

#### repos.js
- Repository management
- Add/remove/pause/resume operations

## CSS Organization

### main.css
- CSS variables (theme colors, fonts)
- Global resets and base styles
- Layout (dashboard, content areas)
- Animations

### components.css
- Sidebar
- Feed and posts
- Settings panels
- Repositories list
- All other UI components

## Build Output

The build process creates a single, portable `index.html` file that:
- Contains all CSS inline (no external stylesheets)
- Contains all JavaScript inline (no external scripts)
- Can be served as a single file by the Python CLI
- Maintains the same functionality as the modular version

## Benefits

1. **Maintainability**: Separate files are easier to edit and understand
2. **Testability**: Individual modules can be tested in isolation
3. **State Management**: Predictable state changes with subscriber pattern
4. **Error Handling**: Consistent error handling with retry logic
5. **Portability**: Single-file output for easy CLI distribution
6. **Developer Experience**: Better IDE support, syntax highlighting, and tooling

## Migration Notes

The refactored dashboard maintains 100% feature parity with the original single-file version. All existing functionality has been preserved, including:
- Story feed with filtering and search
- Repository management
- Settings configuration
- Cron management
- Detail and profile views

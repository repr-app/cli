# Dashboard File Structure

## ⚠️ Important: Generated Files

**DO NOT EDIT `index.html` directly** - it is a generated file that will be overwritten.

## File Hierarchy

```
repr/dashboard/
├── index.html          # GENERATED - Do not edit manually
├── index_old.html      # Backup/deprecated
├── src/
│   └── index.html      # SOURCE - Edit this file
├── styles/
│   ├── main.css
│   └── components.css
├── scripts/
│   ├── api.js
│   ├── stories.js
│   └── ...
└── build.py            # Build script
```

## Build Process

1. **Edit source**: Make changes to `src/index.html`
2. **Run build**: Execute `build.py` to generate `index.html`
3. **Server serves**: `server.py` serves the generated `index.html`

The build script inlines CSS and processes the source template into the final output.

## Which File to Edit?

| File | Purpose | Edit? |
|------|---------|-------|
| `src/index.html` | Source template | ✅ YES |
| `index.html` | Built output | ❌ NO - Generated |
| `index_old.html` | Backup | ❌ NO - Deprecated |
| `styles/*.css` | Stylesheets | ✅ YES |
| `scripts/*.js` | JavaScript modules | ✅ YES |

## Server Configuration

From `server.py:12`:
```python
_STATIC_DIR = Path(__file__).parent  # Points to repr/dashboard/
```

The server serves `index.html` from this directory (line 244).

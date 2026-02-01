# Summary: Dashboard Command & rp Alias

## Changes Made

### 1. New `repr dashboard` command (top-level)
- Added `@app.command("dashboard")` in `repr/cli.py`
- Launches the web dashboard for exploring stories
- Same functionality as former `repr timeline serve`
- Available options: `--port`, `--host`, `--open/--no-open`

### 2. `rp` alias for `repr`
- Added `rp = "repr.cli:app"` entry point in `pyproject.toml`
- Users can now run `rp dashboard`, `rp generate`, etc.

### 3. Backward Compatibility
- `repr timeline serve` still works but is deprecated (hidden from help)
- Shows deprecation notice pointing to `repr dashboard`

### 4. Documentation Updates
- Updated help text examples to reference `repr dashboard`
- Updated skill documentation embedded in CLI

## Files Modified

| File | Change |
|------|--------|
| `repr/cli.py` | Added `dashboard` command, updated `timeline_serve` to alias |
| `pyproject.toml` | Added `rp` entry point |

## Usage

```bash
# Primary command
repr dashboard
rp dashboard

# With options
repr dashboard --port 8080
rp dashboard --no-open

# Backward compatibility (deprecated)
repr timeline serve  # Works but shows deprecation notice
```

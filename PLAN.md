# Plan: Rename `timeline serve` to `dashboard` + Add `rp` Alias

## Summary
1. Move `repr timeline serve` to `repr dashboard` (top-level command)
2. Add `rp` as an alias for `repr`

## Files to Change

### 1. `repr/cli.py`
- Add new `@app.command("dashboard")` function with same functionality as `timeline_serve`
- Keep `timeline serve` as an alias for backward compatibility (calls dashboard)
- Update help text in examples to reference `repr dashboard`

### 2. `pyproject.toml`
- Add entry point: `rp = "repr.cli:app"`
- This allows `rp dashboard`, `rp story`, etc.

## Implementation Details

### cli.py Changes
1. Add `@app.command("dashboard")` before the timeline_app definitions
2. Move the serve logic to the new `dashboard` command
3. Update `timeline_serve` to call `dashboard` for backward compatibility
4. Update example commands in docstrings

### pyproject.toml Changes
```toml
[project.scripts]
repr = "repr.cli:app"
rp = "repr.cli:app"
```

## Testing
- `repr dashboard` - should launch web dashboard
- `rp dashboard` - should work as alias
- `repr timeline serve` - should still work (backward compat)

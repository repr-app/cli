# repr CLI Test Suite

Comprehensive test suite for repr CLI, verifying implementation against `CLI_SPECIFICATION.md`.

## Test Coverage

### Gap Verification Tests

1. **`test_network_sandboxing.py`** - Network sandboxing enforcement
   - Status: ❌ NOT IMPLEMENTED (tests will fail until implemented)
   - Tests local mode network blocking
   - Tests loopback-only policy
   - Tests CI mode restrictions

2. **`test_repo_identity.py`** - Stable repo UUID generation
   - Status: ✅ IMPLEMENTED (tests should pass)
   - Tests UUID generation and persistence
   - Tests cross-device stability
   - Tests privacy properties

3. **`test_environment_variables.py`** - Multi-user & CI safety
   - Status: ✅ IMPLEMENTED (tests should pass)
   - Tests REPR_HOME, REPR_MODE, REPR_CI
   - Tests multi-user isolation
   - Tests CI workflow

4. **`test_profile_export.py`** - Profile export formats
   - Status: ⚠️ PARTIAL (md/json pass, html/pdf skip)
   - Tests markdown export
   - Tests JSON export
   - Tests for HTML/PDF (skipped until implemented)

5. **`test_stories_review.py`** - Interactive review workflow
   - Status: ⚠️ PARTIAL (basic tests pass, STAR format skipped)
   - Tests basic approve/edit/delete workflow
   - Tests for STAR format display (skipped)
   - Tests for regenerate action (skipped)

6. **`test_token_budget.py`** - Token limit enforcement
   - Status: ⚠️ PARTIAL (config tests pass, enforcement skipped)
   - Tests configuration
   - Tests batching logic
   - Tests for enforcement and preview (skipped)

### Core Functionality Tests

7. **`test_privacy_guarantees.py`** - Privacy architecture
   - Tests local mode privacy
   - Tests authentication flow
   - Tests privacy lock (reversible & permanent)
   - Tests audit logging
   - Tests path redaction defaults
   - Tests BYOK privacy

## Running Tests

### Install Test Dependencies

```bash
cd /Users/mendrika/Projects/everdraft/code/repr/cli

# Option 1: Using make (recommended)
make install-dev

# Option 2: Using requirements file
pip install -r tests/requirements.txt

# Option 3: Using pyproject.toml dev dependencies
pip install -e ".[dev]"

# Option 4: Minimal install (just pytest)
pip install pytest pytest-asyncio
```

### Run All Tests

```bash
# Using make (recommended)
make test                # Run all tests
make test-verbose        # Run with verbose output
make test-coverage       # Run with coverage report
make test-quick          # Skip unimplemented features

# Using pytest directly
pytest tests/
pytest -v tests/
pytest --cov=repr --cov-report=html tests/
```

### Run Specific Test Files

```bash
# Run only network sandboxing tests
pytest tests/test_network_sandboxing.py

# Run only implemented features (should all pass)
pytest tests/test_repo_identity.py tests/test_environment_variables.py

# Run specific test class
pytest tests/test_privacy_guarantees.py::TestLocalModePrivacy

# Run specific test function
pytest tests/test_repo_identity.py::TestRepoIdentity::test_repo_id_generated_on_hook_install
```

### Run Only Passing Tests

```bash
# Skip tests marked as "skip" (not yet implemented)
pytest -v tests/ -k "not skip"
```

### Run Only Failing/TODO Tests

```bash
# Run only skipped tests (features to implement)
pytest -v tests/ --collect-only -m skip
```

## Test Organization

### Fixtures (`conftest.py`)

Shared test fixtures:
- `temp_dir` - Temporary directory for tests
- `mock_repr_home` - Mock ~/.repr directory
- `mock_git_repo` - Mock git repository
- `mock_config` - Mock configuration
- `authenticated_config` - Authenticated mock config
- `mock_stories` - Pre-created story files
- `ci_mode` - Enable CI mode
- `local_mode` - Force local mode
- `cloud_mode` - Force cloud mode

### Test Patterns

1. **Basic Functionality Tests**
   - Test happy path
   - Test edge cases
   - Test error conditions

2. **Gap Verification Tests**
   - Test current implementation (may pass or skip)
   - Document expected behavior (for future implementation)
   - Use `@pytest.mark.skip()` for not-yet-implemented features

3. **Privacy Tests**
   - Verify no data leaks
   - Verify authentication boundaries
   - Verify audit logging

## Expected Results

### Currently Passing

- ✅ `test_repo_identity.py` - All tests should pass
- ✅ `test_environment_variables.py` - All tests should pass
- ✅ `test_privacy_guarantees.py` - Most tests should pass
- ✅ `test_profile_export.py` - MD/JSON tests should pass
- ✅ `test_stories_review.py` - Basic tests should pass
- ✅ `test_token_budget.py` - Configuration tests should pass

### Currently Skipped (TODO)

- ⏭️ Network sandboxing enforcement tests
- ⏭️ HTML/PDF export tests
- ⏭️ STAR format review tests
- ⏭️ Regenerate story tests
- ⏭️ Token limit enforcement tests
- ⏭️ Batch preview tests

### Currently Failing (Gaps)

- ❌ `test_network_sandboxing.py` - Most tests will fail until implemented
- ❌ Some enforcement tests (documented with pytest.skip)

## Adding New Tests

1. **Create test file**: `test_feature_name.py`
2. **Import fixtures**: Use fixtures from `conftest.py`
3. **Follow naming**: `test_*` for functions, `Test*` for classes
4. **Document gaps**: Use `@pytest.mark.skip("reason")` for unimplemented
5. **Add to this README**: Update coverage list above

## Integration Tests

For end-to-end workflows:

```bash
# Test init → generate → push workflow (requires auth)
pytest tests/integration/test_workflow.py  # TODO: Create this

# Test hooks → queue → generate (requires git repo)
pytest tests/integration/test_hooks_workflow.py  # TODO: Create this
```

## CI/CD Integration

Recommended pytest.ini configuration for CI:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings
markers =
    skip: marks tests as skipped (not yet implemented)
    integration: marks tests as integration tests (slower)
    requires_auth: marks tests that require authentication
```

## Troubleshooting

### Import Errors

If you get import errors:

```bash
# Install repr in editable mode
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH=/Users/mendrika/Projects/everdraft/code/repr/cli:$PYTHONPATH
```

### Module Reload Issues

Some tests reload modules to pick up environment variables. If you see stale values:

```bash
# Run tests with fresh Python interpreter each time
pytest --forked tests/  # Requires pytest-forked
```

### Git Repo Tests

Tests that create git repos may fail if git is not configured:

```bash
git config --global user.name "Test User"
git config --global user.email "test@example.com"
```

## Contributing

When adding features:

1. **Write tests first** (TDD)
2. **Mark as skip** if not implementing immediately
3. **Document behavior** in test docstrings
4. **Run full suite** before committing
5. **Update this README** with new test files

## References

- CLI Specification: `../CLI_SPECIFICATION.md`
- Gap Verification Report: `../VERIFICATION_REPORT.md`
- Implementation Plan: `../cli/implementation_plan.md`

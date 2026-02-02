# Dashboard Tests

This directory contains tests for the dashboard components.

## Running Tests

Open the test files in a web browser:

```bash
# For utility function tests
open tests/test-utils.html

# Or use Python's built-in server
cd repr/dashboard
python3 -m http.server 8080
# Then navigate to http://localhost:8080/tests/test-utils.html
```

## Test Coverage

- **test-utils.html**: Tests for utility functions (stringToColor, cleanTitle, escapeHtml, highlightText, timeSince)

## Adding New Tests

1. Create a new HTML file in the `tests/` directory
2. Load the module you want to test
3. Use the TestRunner class to write tests
4. Call `runner.render()` to display results

Example:

```javascript
const runner = new TestRunner();

runner.test('test name', () => {
  runner.assertEqual(actual, expected);
});

runner.render();
```

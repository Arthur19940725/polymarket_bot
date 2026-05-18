```markdown
# polymarket_bot Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill teaches you the core development patterns and workflows for contributing to the `polymarket_bot` Python project. You'll learn the repository's coding conventions, how to add new modules and tests, how to manage test fixtures, and the commands used to streamline common tasks. The patterns here ensure code consistency and smooth collaboration.

## Coding Conventions

- **File Naming:**  
  Use `snake_case` for all Python files and modules.  
  *Example:*  
  ```
  polymarket/polymarket-copy-bot/clock.py
  polymarket/polymarket-copy-bot/risk_manager.py
  ```

- **Import Style:**  
  Use **relative imports** within the package.  
  *Example:*  
  ```python
  from .api_client import ApiClient
  from .storage import Storage
  ```

- **Export Style:**  
  Use **named exports** (explicitly define what is exported from each module).  
  *Example:*  
  ```python
  class Ranker:
      ...
  __all__ = ["Ranker"]
  ```

- **Commit Messages:**  
  Follow the **conventional commit** style with prefixes like `feat` and `docs`.  
  *Example:*  
  ```
  feat: add risk manager module for trade evaluation
  docs: update README with setup instructions
  ```

## Workflows

### Add New Module With Tests
**Trigger:** When you want to implement a new core component or feature in the bot.  
**Command:** `/new-module`

1. Create or update the main implementation file in `polymarket/polymarket-copy-bot/{module}.py`.
2. Create or update the corresponding test file in `polymarket/polymarket-copy-bot/tests/test_{module}.py`.
3. Follow coding conventions for file naming and imports.
4. Use conventional commit messages when committing your changes.

*Example:*
```bash
touch polymarket/polymarket-copy-bot/executor.py
touch polymarket/polymarket-copy-bot/tests/test_executor.py
```
```python
# executor.py
class Executor:
    def execute(self, order):
        pass

__all__ = ["Executor"]
```
```python
# tests/test_executor.py
from ..executor import Executor

def test_execute():
    executor = Executor()
    assert executor.execute({}) is None
```

### Add Test Fixtures
**Trigger:** When you want to test new API client functionality or simulate external data for tests.  
**Command:** `/add-fixture`

1. Add one or more JSON fixture files to `polymarket/polymarket-copy-bot/tests/fixtures/`.
2. Update or add a test file in `polymarket/polymarket-copy-bot/tests/` to use the new fixtures.
3. Reference the fixture data in your test code.

*Example:*
```bash
touch polymarket/polymarket-copy-bot/tests/fixtures/market_data.json
```
```python
# tests/test_api_client.py
import json
from ..api_client import ApiClient

def test_market_data():
    with open('fixtures/market_data.json') as f:
        data = json.load(f)
    client = ApiClient()
    assert client.parse_market(data) == expected_result
```

## Testing Patterns

- **Test File Location:**  
  Place test files in `polymarket/polymarket-copy-bot/tests/` and name them as `test_{module}.py`.
- **Fixtures:**  
  Store fixture data in JSON files under `polymarket/polymarket-copy-bot/tests/fixtures/`.
- **Framework:**  
  No specific testing framework detected, but tests are written as standalone functions.
- **Example Test:**
  ```python
  # tests/test_clock.py
  from ..clock import Clock

  def test_now():
      clock = Clock()
      assert isinstance(clock.now(), int)
  ```

## Commands

| Command      | Purpose                                               |
|--------------|-------------------------------------------------------|
| /new-module  | Scaffold a new module and its corresponding test file |
| /add-fixture | Add JSON fixtures and update tests to use them        |
```
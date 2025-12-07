# Contributing to Sightline

Thank you for your interest in contributing to Sightline! This document provides guidelines and instructions for contributing.

## Development Setup

Follow setup instructions in the README.md file.

## Development Workflow

1. Create a new branch for your changes:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and ensure they follow the code style:

   ```bash
   make format  # Auto-format code
   make lint    # Check for issues
   ```

3. Write or update tests for your changes:

   ```bash
   make test
   ```

4. Ensure all tests pass and code quality checks pass:

   ```bash
   make lint
   make test
   ```

5. Commit your changes with a clear commit message:

   ```bash
   git commit -m "Add feature: description of changes"
   ```

6. Push to your fork and create a pull request.

## Code Style

- Follow PEP 8 style guidelines
- Use `black` for code formatting (configured in `pyproject.toml`)
- Use `isort` for import sorting
- Maximum line length is 88 characters
- Add type hints where possible (mypy is configured but not strict)

Run `make format` to auto-format your code before committing.

## Testing

- Write tests for new features and bug fixes
- Ensure all tests pass: `make test`
- Aim for good test coverage (check with `make test` which shows coverage)
- Use pytest fixtures and mocks appropriately

## Pull Request Process

1. Update the `CHANGELOG.md` with your changes
2. Ensure your PR description clearly explains:
   - What changes were made
   - Why the changes were necessary
   - How to test the changes
3. Ensure all CI checks pass
4. Request review from maintainers

## Reporting Issues

When reporting issues, please include:

- Operating system and version
- Python version
- Steps to reproduce the issue
- Expected behavior
- Actual behavior
- Error messages or logs (if applicable)

## Questions?

Feel free to open an issue for questions or discussions about the project.

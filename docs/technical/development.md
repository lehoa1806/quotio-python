# Development Guide

This guide is for developers who want to contribute to Quotio or understand the codebase.

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- Virtual environment (recommended)

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd quotio-python
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # macOS/Linux
   # or
   venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install development dependencies** (optional)
   ```bash
   pip install pytest black mypy
   ```

## Project Structure

```
quotio-python/
├── quotio/                    # Main application package
│   ├── main.py               # Entry point
│   ├── models/               # Data models (Pydantic)
│   ├── services/             # Business logic services
│   │   └── quota_fetchers/   # Provider-specific fetchers
│   ├── viewmodels/           # State management (MVVM)
│   ├── ui/                   # User interface (PyQt6)
│   │   ├── screens/          # UI screens
│   │   └── dialogs/          # Modal dialogs
│   └── utils/                # Utility functions
├── docs/                     # Documentation
├── requirements.txt           # Python dependencies
└── setup.py                  # Package setup
```

## Code Style

### Python Style

- Follow PEP 8
- Use type hints where possible
- Use docstrings for all public functions/classes

### Formatting

```bash
# Format code with black
black quotio/

# Type checking with mypy
mypy quotio/
```

## Architecture Patterns

### MVVM Pattern

- **Models**: Data structures (`quotio/models/`)
- **Views**: UI components (`quotio/ui/`)
- **ViewModels**: State management (`quotio/viewmodels/`)

### Async/Await

- Use `async`/`await` for I/O operations
- Use `asyncio.gather()` for parallel operations
- Never block the Qt event loop

### Service Layer

- Business logic in services (`quotio/services/`)
- Services are stateless (or minimal state)
- ViewModels coordinate services

## Adding a New Provider

1. **Create fetcher class** (`services/quota_fetchers/new_provider.py`)
   ```python
   from .base import BaseQuotaFetcher, ProviderQuotaData
   
   class NewProviderQuotaFetcher(BaseQuotaFetcher):
       async def fetch_all_quotas(self) -> dict[str, ProviderQuotaData]:
           # Implementation
   ```

2. **Add to AIProvider enum** (`models/providers.py`)
   ```python
   class AIProvider(Enum):
       NEW_PROVIDER = "new-provider"
   ```

3. **Register in QuotaViewModel** (`viewmodels/quota_viewmodel.py`)
   - Add to `refresh_all_quotas()` method
   - Import and instantiate fetcher

4. **Add UI support** (if needed)
   - Update Providers screen
   - Add OAuth support if applicable

## Testing

**Note:** Test infrastructure is not yet set up. When adding tests:

### Running Tests (when available)

```bash
# Install pytest if needed
pip install pytest pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=quotio

# Run specific test file
pytest tests/test_proxy_manager.py
```

### Writing Tests (when available)

- Place tests in `tests/` directory (to be created)
- Use pytest fixtures for common setup
- Mock external dependencies (API calls, file I/O)

## Debugging

### Debug Mode

Run with debug flag:
```bash
python -m quotio.main --debug
```

This enables:
- Detailed logging
- Asyncio debug mode
- Verbose error messages

### Common Issues

**Proxy won't start**
- Check port availability
- Verify binary permissions
- Check logs for errors

**Quotas not loading**
- Verify API client connection
- Check provider authentication
- Review quota fetcher logs

**UI not updating**
- Check callback registration
- Verify async operations complete
- Review Qt event loop

See [Debugging Guide](debugging.md) for more details.

## Building

### Package Distribution

```bash
# Build package
python setup.py sdist bdist_wheel

# Install locally
pip install -e .
```

## Contributing

### Workflow

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Add tests
5. Update documentation
6. Submit pull request

### Code Review Checklist

- [ ] Code follows style guidelines
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
- [ ] Security considerations addressed

## Related Documentation

- [Architecture Overview](architecture.md) - System architecture
- [Implementation Summary](implementation-summary.md) - Technical details
- [Debugging Guide](debugging.md) - Troubleshooting

# Quotio - Python Edition

A **cross-platform** Python rewrite of Quotio, a standalone application for managing CLIProxyAPI - a local proxy server for AI coding agents.

## About This Project

This is a **Python port** of the original [Quotio](https://github.com/nguyenphutrong/quotio) repository, customized for personal use. All credit for the original concept, design, and functionality goes to the original repository and its maintainers.

**Original Repository:** https://github.com/nguyenphutrong/quotio

## Features

- **🔌 Multi-Provider Support**: Connect accounts from Claude, OpenAI Codex, GitHub Copilot, and more via OAuth
- **📊 Quota Tracking**: Real-time quota monitoring with visual indicators (Claude, OpenAI, Copilot implemented)
- **🚀 Agent Detection**: Auto-detect installed CLI coding tools (Claude Code, Codex, Gemini, etc.)
- **📈 Real-time Dashboard**: Monitor request traffic, token usage, and success rates
- **🔐 Secure**: All security vulnerabilities fixed, secure key storage, binary verification
- **🌐 Cross-Platform**: Works on Windows, macOS, and Linux
- **🎨 Modern UI**: PyQt6-based interface with tabbed navigation

## Requirements

- Python 3.10+
- Windows 10+, macOS 10.15+, or Linux
- Internet connection for OAuth authentication

## Installation

### Standard Installation

```bash
# Clone the repository
git clone <repository-url>
cd quotio-python

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m quotio.main
```

**Note:** On macOS with Homebrew Python, use a virtual environment (as above). Installing with `pip install` outside a venv will fail with "externally-managed-environment". If you see `ModuleNotFoundError: No module named 'aiohttp'` or "PyQt6 not available", ensure you activated the venv and ran `pip install -r requirements.txt` inside it.

For detailed installation instructions, see the [Installation Guide](docs/getting-started/installation.md).

### Docker Installation

**Yes, you can run the PyQt6 GUI in Docker!** See the [Docker documentation](docs/docker/) for details.

**Quick Start:**
```bash
# Linux (X11 forwarding)
xhost +local:docker
./run-docker.sh

# Or use Docker Compose
docker-compose up
```

See [Docker Quick Start](docs/docker/quickstart.md) for more information.

## Project Structure

```
quotio-python/
├── quotio/
│   ├── __init__.py
│   ├── main.py                 # Application entry point
│   ├── models/                 # Data models
│   │   ├── __init__.py
│   │   ├── providers.py        # AIProvider enum and related
│   │   ├── auth.py             # AuthFile, OAuth models
│   │   ├── proxy.py            # ProxyStatus, config models
│   │   └── agents.py           # CLIAgent models
│   ├── services/               # Business logic services
│   │   ├── __init__.py
│   │   ├── proxy_manager.py    # CLIProxyManager equivalent
│   │   ├── api_client.py       # ManagementAPIClient
│   │   ├── quota_fetchers/     # Provider-specific quota fetchers
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── antigravity.py
│   │   │   ├── claude.py
│   │   │   ├── openai.py
│   │   │   └── ...
│   │   └── ...
│   ├── viewmodels/             # View models (state management)
│   │   ├── __init__.py
│   │   ├── quota_viewmodel.py
│   │   └── agent_viewmodel.py
│   ├── ui/                     # User interface
│   │   ├── __init__.py
│   │   ├── main_window.py      # Main application window
│   │   ├── screens/            # Screen components
│   │   │   ├── dashboard.py
│   │   │   ├── quota.py
│   │   │   ├── providers.py
│   │   │   └── ...
│   │   ├── dialogs/            # Modal dialogs
│   │   │   ├── connection_dialog.py
│   │   │   ├── custom_provider_dialog.py
│   │   │   └── warmup_dialog.py
│   │   └── utils.py            # UI utilities
│   └── utils/                  # Utilities
│       ├── __init__.py
│       ├── browser.py          # Browser utilities
│       └── settings.py         # Settings management
├── requirements.txt
├── setup.py
└── README.md
```

## Documentation

📚 **Full documentation is available in the [docs/](docs/) directory.**

### Quick Links

- **[Getting Started](docs/getting-started/)** - Installation and quick start guides
- **[User Guides](docs/user-guides/)** - How-to guides for features
- **[Technical Docs](docs/technical/)** - Architecture and development
- **[Docker](docs/docker/)** - Running in Docker containers
- **[Security](docs/security/)** - Security and privacy information

See [docs/README.md](docs/README.md) for the complete documentation index.

## Architecture

The application follows this architecture:

- **Models**: Data structures and enums (Pydantic)
- **Services**: Business logic, API clients, proxy management, quota fetchers
- **ViewModels**: State management and UI logic
- **UI**: User interface components (PyQt6)

See [Architecture Overview](docs/technical/architecture.md) for detailed information.

## Development

For development setup and guidelines, see the [Development Guide](docs/technical/development.md).

**Note:** Development dependencies (pytest, black, mypy) are optional. Install them individually if needed:
```bash
pip install pytest black mypy
```

## License

MIT License - See LICENSE file for details

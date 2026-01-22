# Installation Guide

This guide will help you install Quotio Python Edition on your system.

## Requirements

- **Python**: 3.10 or higher
- **Operating System**: Windows 10+, macOS 10.15+, or Linux
- **Internet Connection**: Required for OAuth authentication and binary downloads
- **Disk Space**: ~100MB for application and dependencies

## Standard Installation

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd quotio-python
```

### Step 2: Create Virtual Environment

It's recommended to use a virtual environment to isolate dependencies:

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Run the Application

```bash
python -m quotio.main
```

## Docker Installation

If you prefer to run Quotio in Docker, see the [Docker Quick Start Guide](../docker/quickstart.md).

## Post-Installation

After installation, proceed to the [Quick Start Guide](quickstart.md) to learn how to use Quotio.

## Troubleshooting

### Python Version Issues

If you get a Python version error:
```bash
# Check your Python version
python --version

# If it's below 3.10, install Python 3.10+ and use it explicitly
python3.10 -m venv venv
```

### PyQt6 Installation Issues

If PyQt6 fails to install:
- **macOS**: May need Xcode Command Line Tools: `xcode-select --install`
- **Linux**: May need system packages: `sudo apt-get install python3-pyqt6` (Ubuntu/Debian)
- **Windows**: Usually installs without issues

### Permission Errors

If you encounter permission errors:
- Use a virtual environment (recommended)
- On Linux/macOS, avoid using `sudo` with pip

## Next Steps

- [Quick Start Guide](quickstart.md) - Get started using Quotio
- [First Steps](first-steps.md) - What to do after installation

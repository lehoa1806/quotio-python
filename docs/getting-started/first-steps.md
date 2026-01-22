# First Steps

Welcome to Quotio! This guide will help you get started after installation.

## Initial Setup

### 1. Start the Application

Run the application:
```bash
python -m quotio.main
```

The application will open with a tabbed interface. If PyQt6 is not installed, it will run in console mode.

### 2. Start the Proxy Server

1. Go to the **Dashboard** tab
2. Click **"Start Proxy"**
   - If the binary is not installed, it will download automatically
   - Wait for the download to complete (progress shown in status bar)
3. Wait for the proxy to start (status indicator turns green)

### 3. Connect Your First Provider

1. Go to the **Providers** tab
2. Select a provider (e.g., **Claude**)
3. Click **"Connect"**
4. Complete OAuth authentication in your browser
5. The provider will appear as connected

### 4. View Quotas

1. Go to the **Dashboard** tab (quotas are shown here)
2. Click **"Refresh"** to load quota data
3. View quota percentages and usage for each account

## Common First Tasks

### Adding an API Key

API keys allow CLI tools to authenticate with the proxy:

1. Go to **Settings** tab
2. Enter an API key in the input field
3. Click **"Add API Key"**
4. The key will be available for CLI tools to use

### Detecting Installed Agents

1. Go to the **Agents** tab
2. Click **"Refresh"** to detect installed CLI tools
3. Installed agents will show with a ✓ checkmark

### Configuring Auto-Start

To automatically start the proxy when the application launches:

1. Go to **Settings** tab
2. Enable **"Auto-start Proxy"**
3. The proxy will start automatically on next launch

## Understanding the Interface

### Dashboard Tab
- Overview of proxy status
- Quota summaries for all providers
- Quick actions (start/stop proxy, refresh quotas)

### Providers Tab
- List of all supported AI providers
- Connect/disconnect providers via OAuth
- View connected accounts

### Agents Tab
- Detect installed CLI coding tools
- Configure agent settings
- View agent connection status

### Settings Tab
- Application settings
- Proxy configuration (port, etc.)
- API key management
- Operating mode selection

## Next Steps

- [Quick Start Guide](quickstart.md) - Detailed usage instructions
- [IDE Scan Guide](../user-guides/ide-scan.md) - Scan for installed IDEs
- [Custom Providers Guide](../user-guides/custom-providers.md) - Add custom AI providers
- [Proxy Explanation](../technical/proxy-explanation.md) - Understand how the proxy works

## Getting Help

If you encounter issues:
- Check the [Debugging Guide](../technical/debugging.md)
- Review the [Troubleshooting section](quickstart.md#troubleshooting)
- Check application logs (shown in terminal or Logs tab)

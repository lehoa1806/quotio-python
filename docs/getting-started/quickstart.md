# Quick Start Guide

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd quotio-python

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m quotio.main
```

## First Run

1. **Start the Application**
   - The application will open with a tabbed interface
   - If PyQt6 is not installed, it will run in console mode

2. **Start the Proxy**
   - Go to Dashboard tab
   - Click "Start Proxy" (if binary not installed, it will download automatically)
   - Wait for proxy to start (status turns green)

3. **Connect a Provider**
   - Go to Providers tab
   - Select a provider (e.g., Claude)
   - Click "Connect"
   - Complete OAuth in browser
   - Provider will appear as connected

4. **View Quotas**
   - Go to Quota tab
   - Click "Refresh" to load quota data
   - View quota percentages and usage

5. **Detect Agents**
   - Go to Agents tab
   - Click "Refresh" to detect installed CLI tools
   - Installed agents will show with ✓

## Common Tasks

### Adding an API Key
1. Go to Settings tab
2. Enter API key in the input field
3. Click "Add API Key"

### Changing Proxy Port
1. Go to Settings tab
2. Change port number (default: 8317)
3. Restart proxy for changes to take effect

### Refreshing Quota Data
1. Go to Quota tab
2. Click "Refresh" button
3. Data updates automatically

## Troubleshooting

### Proxy Won't Start
- Check if port 8317 is already in use
- Check firewall settings
- Verify binary downloaded correctly

### OAuth Not Working
- Ensure proxy is running
- Check internet connection
- Try refreshing the browser

### Quotas Not Showing
- Ensure provider is connected
- Click Refresh button
- Check if provider supports quota tracking

### Agents Not Detected
- Verify agents are installed
- Check if agents are in PATH
- Try clicking Refresh button

## Configuration Files

### Settings
- **Windows**: `%LOCALAPPDATA%\Quotio\settings.json`
- **macOS**: `~/Library/Preferences/settings.json`
- **Linux**: `~/.config/Quotio/settings.json`

### Proxy Config
- **All**: `~/.local/share/Quotio/config.yaml` (Linux)
- **macOS**: `~/Library/Application Support/Quotio/config.yaml`
- **Windows**: `%LOCALAPPDATA%\Quotio\config.yaml`

### Auth Files
- **All**: `~/.cli-proxy-api/`

## Advanced Features

### Antigravity Account Switching

Switch between multiple Antigravity accounts seamlessly:
1. Connect multiple Antigravity accounts in the Providers tab
2. Select Antigravity and click "Disconnect" (triggers account switching)
3. Choose which account to switch to
4. The IDE will automatically restart with the new account

See [Antigravity Account Switching](../user-guides/antigravity-switching.md) for detailed instructions.

## Next Steps

- [IDE Scan Guide](../user-guides/ide-scan.md) - Scan for installed IDEs
- [Custom Providers Guide](../user-guides/custom-providers.md) - Add custom AI providers
- [Remote Proxy Configuration](../user-guides/remote-proxy.md) - Connect to remote proxy
- [Architecture Overview](../technical/architecture.md) - Understand how it works
- [Security Assessment](../security/security-assessment.md) - Security information

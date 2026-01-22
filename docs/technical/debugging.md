# Debug Mode Guide

## How to Run in Debug Mode

### Method 1: Command Line Flag
```bash
python -m quotio.main --debug
# or
python -m quotio.main -d
```

### Method 2: Environment Variable
```bash
export QUOTIO_DEBUG=1
python -m quotio.main
```

### Method 3: Python Debug Mode
```bash
python -X dev -m quotio.main
```

## What Debug Mode Shows

When debug mode is enabled, you'll see:

1. **All print statements** - Console output from the application
2. **Python logging** - DEBUG level logs from all modules
3. **Asyncio debug** - Event loop debugging information
4. **HTTP requests** - aiohttp client/connector logs
5. **OAuth flow** - OAuth URL, browser opening status
6. **Error traces** - Full stack traces for exceptions

## Debug Output Examples

```
[OAuth] Opening browser with URL: https://...
[Browser] Attempting to open: https://...
[Browser] webbrowser.open() returned: True
[OAuth] Browser opened successfully
```

## Additional Debugging

### Enable Python's Verbose Mode
```bash
python -v -m quotio.main --debug
```

### Enable Asyncio Debug Mode (already enabled in debug mode)
The application automatically enables asyncio debug mode when `--debug` is used.

### View Specific Module Logs
You can also set log levels for specific modules:
```python
import logging
logging.getLogger('quotio.services').setLevel(logging.DEBUG)
```

## Troubleshooting

If you don't see logs:
1. Make sure you're running with `--debug` flag
2. Check that output isn't being redirected
3. Try running directly: `python -m quotio.main --debug`
4. Check console/terminal output (not just GUI)

# Docker Limitations

## Overview

When running Quotio in Docker, certain features that require direct host system access are limited or unavailable.

## Antigravity Account Switching

### What Works ✅

- **Database Updates**: Can update Antigravity IDE database if mounted
- **Token Refresh**: OAuth token refresh works normally
- **Account Detection**: Can read active account from database
- **Configuration**: All other Quotio features work normally

### What Doesn't Work ❌

- **Automatic IDE Restart**: Container cannot execute `open` command on macOS host
- **Automatic IDE Shutdown**: Container cannot use `pkill` on host processes
- **IDE Running Detection**: Container cannot access host process list

### Why This Happens

Docker containers are isolated from the host system:
- Cannot execute host commands (`open`, `pkill`, `pgrep`)
- Cannot access host process list
- Cannot launch host applications

### Workaround

**Manual Process:**

1. **Before Switching:**
   - Manually close Antigravity IDE (if running)
   - Wait a few seconds for database locks to release

2. **Switch Account:**
   - Use the account switching feature in Quotio
   - Database will be updated with new credentials

3. **After Switching:**
   - Manually restart Antigravity IDE
   - New account will be active

**Example:**
```bash
# 1. Close IDE manually
# (Quit Antigravity IDE from menu or Cmd+Q)

# 2. Switch account in Quotio
# (Use the UI to switch accounts)

# 3. Restart IDE manually
open -a Antigravity
```

### Automatic Detection

The application automatically detects when running in Docker and:
- Skips IDE shutdown attempts
- Skips IDE restart attempts
- Shows helpful messages in console/logs
- Still updates the database successfully

**Detection Methods:**
- Checks for `/.dockerenv` file
- Checks `/proc/self/cgroup` for Docker indicators
- Checks `container` environment variable

## Other Limitations

### Process Management

- Cannot kill processes on host
- Cannot check if processes are running on host
- Process-related features are limited

### System Integration

- Cannot launch host applications
- Cannot access host system services
- Limited access to host file system (only mounted volumes)

### macOS-Specific

- Cannot use `open` command
- Cannot use `pkill`/`pgrep` for host processes
- Cannot access macOS-specific APIs

## Recommendations

### For Full Functionality

**Run Natively (Not in Docker):**
- All features work as expected
- Full system integration
- Automatic IDE restart works

### For Docker Usage

**Use Docker for:**
- Development/testing
- Isolated environments
- When Antigravity switching is not needed

**Don't Use Docker for:**
- Production with Antigravity switching
- When automatic IDE restart is required
- When full system integration is needed

## Alternative Solutions

### 1. Hybrid Approach

Run Quotio natively for Antigravity switching, use Docker for other features.

### 2. Docker Socket Mounting (Advanced)

Mount Docker socket to allow some host access (security risk):
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

**⚠️ Security Warning:** This gives container significant access to host.

### 3. Host Script Execution

Create a helper script on host that can be called from container:
```bash
# On host: /usr/local/bin/restart-antigravity.sh
#!/bin/bash
pkill -f Antigravity
sleep 2
open -a Antigravity
```

Then mount and execute from container (requires careful setup).

## Status Messages

When running in Docker, you'll see messages like:

```
[AntigravitySwitcher] Running in Docker - IDE close skipped
[AntigravitySwitcher] Please manually close Antigravity IDE before switching
[AntigravitySwitcher] Running in Docker - IDE restart skipped
[AntigravitySwitcher] Database updated successfully. Please manually restart Antigravity IDE to apply changes.
```

These are informational and indicate the feature is gracefully handling the limitation.

## Summary

| Feature | Native | Docker |
|---------|--------|--------|
| Database Updates | ✅ | ✅ (if mounted) |
| Token Refresh | ✅ | ✅ |
| Account Detection | ✅ | ✅ |
| IDE Shutdown | ✅ | ❌ (manual) |
| IDE Restart | ✅ | ❌ (manual) |
| IDE Detection | ✅ | ❌ |

**Recommendation:** Use native installation for full Antigravity switching functionality.

# Advanced Remote Proxy Config Guide

## Overview

The Advanced Remote Proxy Config feature allows you to connect Quotio to a remote CLIProxyAPI instance running on another machine or server. This enables you to:

- **Centralized Management**: Manage multiple AI provider accounts from a single remote proxy
- **Team Collaboration**: Share a proxy instance with team members
- **Cloud Deployment**: Run the proxy on a cloud server and access it from anywhere
- **Resource Optimization**: Offload proxy processing to a more powerful server

The feature consists of two main parts:
1. **Remote Connection Configuration** - Setting up the connection to the remote proxy
2. **Remote Proxy Settings** - Advanced configuration options for the remote proxy

## Prerequisites

Before configuring a remote proxy connection, ensure:

1. **Remote Proxy Running**: The CLIProxyAPI instance must be running on the remote server
2. **Network Access**: The remote proxy must be accessible from your machine (firewall, port forwarding, etc.)
3. **Management Key**: You need the management key from the remote proxy's configuration
4. **Endpoint URL**: The full URL to the remote proxy's management endpoint

## Part 1: Remote Connection Configuration

### Accessing the Configuration Dialog

1. Open Quotio
2. Navigate to **Settings** (menu bar → Settings, or click the Settings tab)
3. In the **General** section, find **"Remote Server"**
4. Click **"Configure"** button

Alternatively:
- When switching to Remote Proxy Mode for the first time, the configuration dialog will automatically appear

### Step 1: Basic Connection Information

#### Display Name
- **Purpose**: A friendly name to identify this remote connection
- **Example**: "Production Server", "Team Proxy", "Cloud Instance"
- **Required**: Yes
- **Note**: This is only for your reference in Quotio

#### Endpoint URL
- **Purpose**: The full URL to the remote CLIProxyAPI management endpoint
- **Format**: `https://proxy.example.com:8317/v0/management` or `http://192.168.1.100:8317/v0/management`
- **Required**: Yes
- **Validation**: The URL is validated for correct format

**URL Format Requirements**:
- Must include protocol (`http://` or `https://`)
- Must include hostname or IP address
- Must include port number (default: 8317)
- Should include `/v0/management` path (auto-added if missing)

**Examples**:
- `https://proxy.example.com:8317/v0/management`
- `http://192.168.1.100:8317/v0/management`
- `https://my-proxy.company.com:9000/v0/management`

**Security Warning**: If you use `http://` (not HTTPS), you'll see a warning. Use HTTPS in production.

### Step 2: Authentication

#### Management Key
- **Purpose**: Authentication key to access the remote proxy's management API
- **Format**: Secure field (masked input)
- **Required**: Yes
- **Where to Find**: Check the remote proxy's config file or ask your administrator

**Security Note**: The management key is stored securely in the macOS Keychain.

### Step 3: Advanced Options

#### Verify SSL
- **Purpose**: Whether to verify SSL certificates when connecting via HTTPS
- **Default**: Enabled (recommended)
- **When to Disable**: Only for development/testing with self-signed certificates
- **Warning**: Disabling SSL verification exposes you to man-in-the-middle attacks

**Security Warning**: If you disable SSL verification, you'll see a confirmation dialog warning about security risks.

#### Connection Timeout
- **Purpose**: How long to wait for a response from the remote proxy
- **Options**: 15s, 30s, 60s, 120s
- **Default**: 30 seconds
- **When to Increase**: If you have slow network connections or high latency

### Step 4: Test Connection

1. Click **"Test"** button to verify the connection
2. The system will attempt to connect to the remote proxy
3. You'll see a success or failure message

**Test Results**:
- **Success**: Green checkmark - Connection is working
- **Failure**: Red X - Check endpoint URL, management key, and network connectivity

### Step 5: Save Configuration

1. Click **"Save"** to save the configuration
2. The connection will be established automatically
3. Quotio will switch to Remote Proxy Mode

## Part 2: Remote Proxy Settings

Once connected to a remote proxy, you can configure advanced settings that affect how the remote proxy operates.

### Accessing Remote Proxy Settings

1. Open Quotio
2. Navigate to **Settings** (menu bar → Settings)
3. Find the **"Remote Proxy Settings"** section
4. Settings are loaded automatically when the proxy is connected

**Note**: Settings are only available when:
- You're in Remote Proxy Mode
- The remote proxy is connected and responding
- The API client is available

### Available Settings

#### 1. Upstream Proxy

**Purpose**: Configure an upstream proxy that the remote proxy uses for all requests

- **Format**: `http://proxy.example.com:8080` or `socks5://proxy.example.com:1080`
- **Optional**: Leave empty to disable upstream proxy
- **Use Cases**:
  - Corporate proxy requirements
  - VPN routing
  - Network restrictions

**Validation**: The URL is validated for correct format before saving.

#### 2. Routing Strategy

**Purpose**: How the proxy distributes requests across multiple accounts/models

**Options**:
- **Round Robin**: Distributes requests evenly across all available accounts/models
  - Best for: Equal distribution, load balancing
  - Example: Request 1 → Account A, Request 2 → Account B, Request 3 → Account A
  
- **Fill First**: Uses the first account/model until quota is exhausted, then moves to next
  - Best for: Maximizing usage of primary account, cost optimization
  - Example: All requests → Account A until quota runs out, then → Account B

**Default**: Round Robin

#### 3. Quota Exceeded Behavior

**Purpose**: What to do when an account's quota is exceeded

**Options**:
- **Auto Switch Account**: Automatically switch to another account when quota is exceeded
  - Enabled by default
  - Ensures requests continue even if one account runs out
  
- **Auto Switch Preview Model**: Automatically switch to preview/beta models when quota is exceeded
  - Enabled by default
  - Uses preview models as fallback

**Use Cases**:
- High-volume usage scenarios
- Ensuring service continuity
- Cost optimization

#### 4. Retry Configuration

**Purpose**: How the proxy handles failed requests

**Max Retries**:
- **Range**: 0-10
- **Default**: 3
- **Purpose**: Number of times to retry a failed request
- **When to Increase**: For unreliable networks or APIs
- **When to Decrease**: For faster failure detection

**Max Retry Interval**:
- **Range**: 5-300 seconds (in steps of 5)
- **Default**: 30 seconds
- **Purpose**: Maximum time to wait between retries
- **When to Increase**: For APIs with rate limiting or slow recovery
- **When to Decrease**: For faster retry attempts

**Best Practices**:
- Start with defaults (3 retries, 30s interval)
- Increase for production environments with high reliability needs
- Decrease for development/testing to fail faster

#### 5. Logging Settings

**Purpose**: Control what gets logged by the remote proxy

**Logging to File**:
- **Default**: Enabled
- **Purpose**: Save logs to a file on the remote server
- **Location**: Remote server's log directory
- **Use Cases**: Debugging, auditing, troubleshooting

**Request Log**:
- **Default**: Disabled
- **Purpose**: Log individual API requests and responses
- **Use Cases**: Detailed debugging, request tracing
- **Note**: Can generate large log files

**Debug Mode**:
- **Default**: Disabled
- **Purpose**: Enable verbose debug logging
- **Use Cases**: Development, troubleshooting issues
- **Note**: Significantly increases log volume

## How Settings Work

### Loading Settings

1. When you open Settings, Quotio automatically loads current values from the remote proxy
2. A loading indicator shows while fetching
3. Settings are populated with current remote proxy values

### Saving Settings

1. Most settings save automatically when changed (via `onChange` handlers)
2. Some settings (like Upstream Proxy) require pressing Enter or clicking away
3. Changes are immediately sent to the remote proxy
4. No "Save" button needed - changes are live

### Settings Persistence

- Settings are stored on the **remote proxy server** (not in Quotio)
- Changes persist across Quotio restarts
- Multiple Quotio clients can connect to the same remote proxy and see the same settings

## Switching Between Modes

### From Local to Remote

1. Go to Settings → Operating Mode
2. Select **"Remote Proxy"**
3. If no remote config exists, the configuration dialog will appear
4. Enter remote connection details
5. Click Save
6. Quotio will connect to the remote proxy

### From Remote to Local

1. Go to Settings → Operating Mode
2. Select **"Local Proxy"** or **"Monitor"**
3. Quotio will disconnect from the remote proxy
4. Local proxy settings become available

## Troubleshooting

### Connection Issues

**Problem**: Cannot connect to remote proxy

**Solutions**:
1. **Check Endpoint URL**: Verify the URL is correct and includes port number
2. **Check Network**: Ensure the remote server is accessible (ping, telnet)
3. **Check Firewall**: Verify firewall rules allow connections on the proxy port
4. **Check SSL**: If using HTTPS, verify SSL certificate is valid
5. **Check Management Key**: Verify the management key is correct
6. **Test Connection**: Use the "Test" button in the configuration dialog

**Problem**: Connection times out

**Solutions**:
1. **Increase Timeout**: Try increasing the connection timeout (60s or 120s)
2. **Check Network Latency**: High latency may require longer timeouts
3. **Check Server Load**: Remote server may be overloaded
4. **Check Proxy Status**: Verify the remote proxy is running

### Settings Not Loading

**Problem**: Settings show "No Connection" or loading error

**Solutions**:
1. **Check Connection Status**: Verify you're connected to the remote proxy
2. **Check API Availability**: Ensure the remote proxy's management API is responding
3. **Retry**: Click the "Retry" button to reload settings
4. **Check Proxy Status**: Verify the remote proxy is running and healthy

### Settings Not Saving

**Problem**: Changes to settings don't persist

**Solutions**:
1. **Check Connection**: Ensure you're still connected to the remote proxy
2. **Check Permissions**: Verify the management key has write permissions
3. **Check Proxy Status**: Ensure the remote proxy is running
4. **Retry**: Try changing the setting again
5. **Check Logs**: Look for error messages in the remote proxy logs

### SSL Certificate Errors

**Problem**: SSL verification fails

**Solutions**:
1. **Check Certificate**: Verify the remote server's SSL certificate is valid
2. **Check Date/Time**: Ensure your system clock is correct
3. **Temporary Fix**: Disable SSL verification (development only, not recommended for production)
4. **Proper Fix**: Install valid SSL certificate on remote server

## Security Considerations

### Management Key Security

- **Storage**: Management keys are stored in macOS Keychain (encrypted)
- **Transmission**: Keys are transmitted over HTTPS (if SSL verification is enabled)
- **Best Practice**: Use strong, unique management keys
- **Rotation**: Rotate management keys periodically

### SSL/TLS

- **Always Use HTTPS**: Use HTTPS in production environments
- **Verify Certificates**: Keep SSL verification enabled
- **Self-Signed Certificates**: Only disable SSL verification for development/testing
- **Certificate Validation**: Ensure remote server has valid SSL certificate

### Network Security

- **Firewall**: Configure firewall rules to restrict access
- **VPN**: Use VPN for additional security
- **IP Whitelisting**: Consider IP whitelisting on remote server
- **Rate Limiting**: Configure rate limiting on remote proxy

## Best Practices

### Connection Configuration

1. **Use Descriptive Names**: Use clear display names (e.g., "Production", "Staging")
2. **Use HTTPS**: Always use HTTPS in production
3. **Verify SSL**: Keep SSL verification enabled
4. **Appropriate Timeout**: Set timeout based on network conditions
5. **Test First**: Always test connection before saving

### Settings Configuration

1. **Start with Defaults**: Use default settings initially
2. **Monitor Performance**: Adjust settings based on actual usage patterns
3. **Document Changes**: Keep track of custom settings
4. **Test Changes**: Test setting changes in non-production first
5. **Review Logs**: Regularly review logs to optimize settings

### Network Configuration

1. **Use Reliable Networks**: Connect over stable network connections
2. **Monitor Latency**: Keep latency low for better performance
3. **Backup Connection**: Consider having backup remote proxy instances
4. **Load Balancing**: Use multiple remote proxies for high availability

## Advanced Use Cases

### Multiple Remote Proxies

You can configure multiple remote proxy connections:
1. Configure one remote proxy
2. Switch to Local Proxy mode
3. Configure another remote proxy
4. Switch between them as needed

**Note**: Only one remote proxy can be active at a time.

### Team Collaboration

1. **Shared Proxy**: Team members connect to the same remote proxy
2. **Shared Settings**: All team members see the same proxy settings
3. **Centralized Management**: One person manages the remote proxy
4. **Account Sharing**: Multiple team members can use the same provider accounts

### Cloud Deployment

1. **Deploy Proxy**: Deploy CLIProxyAPI to cloud server (AWS, GCP, Azure, etc.)
2. **Configure Access**: Set up firewall, load balancer, SSL certificate
3. **Connect from Quotio**: Connect Quotio clients to the cloud proxy
4. **Scale**: Scale the cloud proxy based on usage

## Related Features

- **Operating Modes**: Switch between Local Proxy, Remote Proxy, and Monitor modes
- **Providers Screen**: Manage AI provider accounts (works with remote proxy)
- **Dashboard**: View quota information from remote proxy
- **Logs Screen**: View request logs from remote proxy (if enabled)

---

**Note**: Remote Proxy Mode requires an active connection to a remote CLIProxyAPI instance. If the connection is lost, you'll need to reconnect or switch to Local Proxy Mode.

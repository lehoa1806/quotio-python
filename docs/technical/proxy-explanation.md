# What is the Proxy and Why Does It Need API Keys?

## What is the Proxy?

**CLIProxyAPI** is a **local HTTP proxy server** that runs on your machine (typically on port 8317). It acts as a **middleman** between your CLI coding tools and AI provider APIs.

### Architecture Flow

```
┌─────────────────┐
│  CLI Tools      │  (Claude Code, Codex CLI, Gemini CLI, etc.)
│  (claude, codex)│
└────────┬────────┘
         │ HTTP requests with API key
         ▼
┌─────────────────┐
│  CLIProxyAPI    │  ← Local proxy server (port 8317)
│  (Proxy Server) │     - Routes requests to AI providers
└────────┬────────┘     - Manages multiple accounts
         │               - Handles quota/rate limiting
         │               - Load balancing
         ▼
┌─────────────────┐
│  AI Provider    │  (Anthropic, OpenAI, Google, etc.)
│     APIs        │
└─────────────────┘
```

## Why Does the Proxy Need API Keys?

The proxy requires **API keys for authentication** - but there are **two different types** of keys:

### 1. **Proxy API Keys** (For CLI Tools)

**Purpose:** CLI tools authenticate to the proxy server using these keys.

**How it works:**
- CLI tools (like `claude`, `codex`, `gemini`) send requests to `http://localhost:8317/v1/...`
- They include an API key in the request: `Authorization: Bearer <api-key>`
- The proxy validates the key and then routes the request to the appropriate AI provider

**Example:**
```bash
# Claude Code CLI sends request to proxy
curl -H "Authorization: Bearer my-proxy-api-key" \
     http://localhost:8317/v1/messages \
     -d '{"model": "claude-sonnet-4", ...}'

# Proxy validates the key, then forwards to Anthropic API
# using one of your connected OAuth accounts
```

**Why needed:**
- **Security**: Prevents unauthorized access to your proxy
- **Access control**: You can give different keys to different tools/users
- **Rate limiting**: Proxy can track usage per API key
- **Multi-user support**: Different keys for different users/tools

**Default behavior:**
- When you first start the proxy, it automatically generates a default API key
- You can add more keys via the "API Keys" screen in Quotio
- Each CLI tool needs to be configured with one of these keys

### 2. **Management Key** (For Quotio App)

**Purpose:** Quotio app authenticates to the proxy's **management API** using this key.

**How it works:**
- Quotio connects to `http://localhost:8317/v0/management/...`
- Uses management key: `Authorization: Bearer <management-key>`
- This allows Quotio to:
  - List auth files (connected accounts)
  - Start OAuth flows
  - Configure proxy settings
  - Fetch usage statistics

**Example:**
```http
# Quotio app requests auth files
GET http://localhost:8317/v0/management/auth-files
Authorization: Bearer <management-key>
```

**Why needed:**
- **Security**: Protects the management API from unauthorized access
- **Remote access**: If you enable remote management, this key secures remote connections
- **Isolation**: Separates management operations from regular API requests

**Storage:**
- Stored securely in keyring (macOS Keychain, Linux Secret Service, Windows Credential Manager)
- Auto-generated on first run
- Never exposed to CLI tools

## Key Differences

| Type | Used By | Purpose | Stored In |
|------|---------|---------|-----------|
| **API Keys** | CLI Tools | Authenticate CLI requests to proxy | Proxy config file |
| **Management Key** | Quotio App | Authenticate management operations | Keychain/keyring |

## How It Works Together

1. **You start the proxy** → Quotio launches CLIProxyAPI binary
2. **Proxy generates default API key** → Stored in config file
3. **You connect providers** → OAuth accounts stored in `~/.cli-proxy-api/`
4. **You configure CLI tools** → Quotio sets up tools to use proxy API key
5. **CLI tools make requests** → Include API key → Proxy validates → Routes to provider

## Example Scenario

```
1. You have 3 Claude accounts connected via OAuth
2. Proxy has API key: "my-key-123"
3. You configure Claude Code CLI to use proxy:
   - Proxy URL: http://localhost:8317
   - API Key: my-key-123

4. When you run: `claude chat "Hello"`
   - Claude Code sends: POST http://localhost:8317/v1/messages
   - Header: Authorization: Bearer my-key-123
   - Proxy validates key → OK
   - Proxy picks one of your 3 Claude accounts (round-robin)
   - Proxy forwards request to Anthropic API
   - Response comes back through proxy to CLI tool
```

## Why Not Just Use Provider API Keys Directly?

**Benefits of using the proxy:**
- ✅ **Multiple accounts**: Route through different accounts automatically
- ✅ **Load balancing**: Distribute requests across accounts
- ✅ **Quota management**: Switch accounts when quota is exhausted
- ✅ **Centralized config**: One place to manage all accounts
- ✅ **Request logging**: Track all API usage
- ✅ **Fallback routing**: Automatic failover if one account fails

## Security Notes

- **API keys are local only** - They only work on `localhost` (127.0.0.1)
- **Management key is separate** - CLI tools never see the management key
- **OAuth tokens stored securely** - In `~/.cli-proxy-api/` directory
- **No external access by default** - Proxy only listens on localhost

## Summary

- **Proxy** = Local server that routes CLI tool requests to AI providers
- **API Keys** = Authentication tokens for CLI tools to access the proxy
- **Management Key** = Authentication token for Quotio to manage the proxy
- **Why needed** = Security, access control, and multi-account management

The proxy acts like a "smart router" that:
- Accepts requests from CLI tools (with API key)
- Routes them to the right AI provider
- Manages multiple accounts automatically
- Tracks usage and quotas

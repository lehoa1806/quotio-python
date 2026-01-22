# Architecture Overview

This document provides an overview of the Quotio Python Edition architecture.

## High-Level Architecture

Quotio follows a **Model-View-ViewModel (MVVM)** architecture pattern:

```
┌─────────────────────────────────────────────────────────┐
│                    UI Layer (PyQt6)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │Dashboard │  │Providers │  │  Agents  │  │Settings │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬──────┘ │
│       │            │              │             │         │
│       └────────────┴──────────────┴─────────────┘        │
│                        │                                   │
└────────────────────────┼──────────────────────────────────┘
                         │
┌────────────────────────┼──────────────────────────────────┐
│              ViewModel Layer                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │         QuotaViewModel (State Management)            │  │
│  │  - Manages proxy lifecycle                          │  │
│  │  - Coordinates quota fetching                       │  │
│  │  - Handles OAuth flows                              │  │
│  │  - Manages background services                       │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────────┼──────────────────────────────────┘
                         │
┌────────────────────────┼──────────────────────────────────┐
│              Service Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │Proxy Manager │  │ API Client   │  │Quota Fetchers │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │Notification  │  │Warmup Service│  │Request Tracker│   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└────────────────────────┼──────────────────────────────────┘
                         │
┌────────────────────────┼──────────────────────────────────┐
│              Model Layer                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │Providers │  │   Auth   │  │  Proxy   │  │  Usage   │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└────────────────────────────────────────────────────────────┘
```

## Component Overview

### UI Layer (`quotio/ui/`)

**MainWindow** (`ui/main_window.py`)
- Coordinates Qt application and async event loop
- Creates and manages all UI screens
- Handles communication between UI and async operations

**Screens** (`ui/screens/`)
- **Dashboard**: Overview of proxy status and quotas
- **Providers**: Provider connection management
- **Agents**: CLI agent detection and configuration
- **Settings**: Application configuration
- **Logs**: Request and error logs

### ViewModel Layer (`quotio/viewmodels/`)

**QuotaViewModel** (`viewmodels/quota_viewmodel.py`)
- Central state management (MVVM pattern)
- Manages proxy lifecycle (start/stop)
- Coordinates quota fetching from all providers
- Handles OAuth authentication flows
- Manages background services (warmup, usage stats polling)

### Service Layer (`quotio/services/`)

**ProxyManager** (`services/proxy_manager.py`)
- Manages CLIProxyAPI binary lifecycle
- Downloads and installs binary from GitHub
- Starts/stops proxy process
- Manages proxy configuration

**APIClient** (`services/api_client.py`)
- HTTP client for proxy management API
- Handles authentication and retries
- Provides methods for all API operations

**Quota Fetchers** (`services/quota_fetchers/`)
- Provider-specific quota fetching implementations
- Each provider has its own fetcher class
- Fetches quotas in parallel for performance

**Other Services**:
- **NotificationManager**: System notifications
- **WarmupService**: Account warmup functionality
- **RequestTracker**: Request history tracking
- **CustomProviderService**: Custom provider management

### Model Layer (`quotio/models/`)

Data structures and enums:
- **providers.py**: AIProvider enum
- **auth.py**: AuthFile, OAuthState models
- **proxy.py**: ProxyStatus, configuration models
- **usage_stats.py**: Usage statistics models

## Data Flow

### Quota Refresh Flow

```
1. User clicks "Refresh" in UI
   ↓
2. UI calls QuotaViewModel.refresh_all_quotas()
   ↓
3. QuotaViewModel creates fetchers for each provider
   ↓
4. Fetchers run in parallel (asyncio.gather)
   ↓
5. Each fetcher:
   - Gets account list from auth files
   - Calls provider API or reads local data
   - Parses response into ProviderQuotaData
   ↓
6. QuotaViewModel updates provider_quotas dictionary
   ↓
7. QuotaViewModel notifies UI via callbacks
   ↓
8. UI screens refresh their displays
```

### Proxy Startup Flow

```
1. User clicks "Start Proxy"
   ↓
2. QuotaViewModel.start_proxy() called
   ↓
3. ProxyManager checks if binary exists
   ↓
4. If not, downloads binary from GitHub
   ↓
5. ProxyManager starts proxy process
   ↓
6. QuotaViewModel sets up API client
   ↓
7. QuotaViewModel refreshes data (auth files, quotas)
   ↓
8. Background services start (usage stats polling, warmup)
   ↓
9. UI updates to show proxy is running
```

## Async Architecture

Quotio uses **asyncio** for async operations:

- **Main Thread**: Runs Qt event loop (UI rendering)
- **Background Thread**: Runs asyncio event loop (async operations)
- **Bridge**: `run_async_coro()` schedules coroutines from Qt thread to async thread

This architecture allows:
- UI remains responsive during async operations
- Parallel quota fetching for better performance
- Non-blocking proxy management

## Operating Modes

Quotio supports three operating modes:

1. **Local Proxy Mode** (default)
   - Runs proxy locally
   - Full functionality
   - Routes requests through proxy

2. **Remote Proxy Mode**
   - Connects to remote proxy server
   - Same functionality as local mode
   - Useful for centralized management

3. **Monitor Mode**
   - Quota monitoring only
   - No proxy required
   - Reads quotas directly from auth files

## Security Considerations

- **Management Key**: Stored securely using keyring (or file with restricted permissions)
- **Auth Files**: Stored in `~/.cli-proxy-api/` with restricted permissions
- **Binary Verification**: Proxy binary is verified before use
- **API Keys**: Stored securely, never logged

## Related Documentation

- [Proxy Explanation](proxy-explanation.md) - Detailed proxy architecture
- [Implementation Summary](implementation-summary.md) - Technical implementation details
- [Development Guide](development.md) - Contributing and development setup

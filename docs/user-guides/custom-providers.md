# Custom Providers Feature Guide

## Overview

The Custom Providers feature allows you to add and configure custom AI providers that are compatible with OpenAI, Claude, Gemini, Codex, or GLM APIs. This feature enables Quotio to work with:

- **OpenRouter** - Aggregator for multiple AI models
- **Ollama** - Local AI model server
- **LM Studio** - Local AI development environment
- **vLLM** - High-performance LLM serving
- **Custom API endpoints** - Any OpenAI/Claude/Gemini-compatible API
- **GLM (BigModel.cn)** - Chinese AI provider

Custom providers are managed through the Providers screen and automatically synced to the CLIProxyAPI configuration file.

## When to Use Custom Providers

Use Custom Providers when you want to:

- Connect to local AI models (Ollama, LM Studio, vLLM)
- Use alternative API aggregators (OpenRouter, etc.)
- Connect to self-hosted AI endpoints
- Add providers that aren't natively supported by Quotio
- Configure custom model aliases and mappings

## Accessing Custom Providers

### Step 1: Open Providers Screen

1. Open Quotio
2. Navigate to the **Providers** screen (menu bar → Providers, or click the Providers tab)

**Note**: Custom Providers are only available in **Local Proxy Mode**. If you're in Monitor Mode or Remote Proxy Mode, you won't see the Custom Providers section.

### Step 2: Add a Custom Provider

1. Click the **"+"** button in the toolbar (top-right of Providers screen)
2. Select **"Add Custom Provider"** from the popover menu
3. The Custom Provider dialog will open

## Provider Types

Quotio supports five types of custom providers:

### 1. OpenAI Compatible
- **Use for**: OpenRouter, Ollama, LM Studio, vLLM, or any OpenAI-compatible API
- **Base URL**: Required (e.g., `https://api.openrouter.ai`, `http://localhost:11434`)
- **Features**: Model mapping, multiple API keys
- **Example**: OpenRouter, local Ollama instance

### 2. Claude Compatible
- **Use for**: Anthropic API or Claude-compatible providers
- **Base URL**: Optional (defaults to `https://api.anthropic.com`)
- **Features**: Model mapping, multiple API keys
- **Example**: Custom Claude API endpoint

### 3. Gemini Compatible
- **Use for**: Google Gemini API or Gemini-compatible providers
- **Base URL**: Optional (defaults to `https://generativelanguage.googleapis.com`)
- **Features**: Custom headers, multiple API keys
- **Example**: Custom Gemini endpoint with special headers

### 4. Codex Compatible
- **Use for**: Custom Codex-compatible endpoints
- **Base URL**: Required
- **Features**: Multiple API keys
- **Example**: Self-hosted Codex API

### 5. GLM Compatible
- **Use for**: GLM (BigModel.cn) API
- **Base URL**: Optional (defaults to `https://bigmodel.cn`)
- **Features**: Multiple API keys
- **Note**: GLM providers appear in "Your Accounts" section, not Custom Providers

## Adding a Custom Provider

### Step 1: Basic Information

1. **Provider Name**: Enter a descriptive name (e.g., "OpenRouter", "Local Ollama")
2. **Provider Type**: Select the compatibility type from the dropdown
3. **Base URL**: 
   - For OpenAI/Codex: Required (e.g., `https://api.openrouter.ai`)
   - For Claude/Gemini/GLM: Optional (uses default if empty)

### Step 2: API Keys

1. Click **"Add Key"** to add an API key
2. Enter your API key in the secure field
3. **Optional**: Add a proxy URL if the API key requires proxy configuration
4. Add multiple keys if needed (for load balancing or different accounts)

**Note**: At least one API key is required.

### Step 3: Model Mapping (OpenAI/Claude Only)

Model mapping allows you to map upstream model names to local aliases:

1. Click **"Add Mapping"** to add a model mapping
2. **Upstream Model**: Enter the model name as it appears in the API (e.g., `openai/gpt-4`)
3. **Local Alias**: Enter the alias you want to use (e.g., `gpt-4`)
4. **Thinking Budget** (optional): Add thinking budget for reasoning models (e.g., `1000000`)

**Example**:
- Upstream: `openai/gpt-4-turbo`
- Alias: `gpt-4-turbo`
- Thinking Budget: `1000000`

This allows you to use `gpt-4-turbo` in your CLI tools while the actual API call uses `openai/gpt-4-turbo`.

### Step 4: Custom Headers (Gemini Only)

For Gemini-compatible providers, you can add custom HTTP headers:

1. Click **"Add Header"** to add a custom header
2. **Header Name**: Enter the header name (e.g., `X-Custom-Header`)
3. **Header Value**: Enter the header value

**Example**:
- Name: `X-API-Version`
- Value: `v2`

### Step 5: Enable/Disable

- Toggle **"Enable Provider"** to enable or disable the provider
- Disabled providers won't be included in the CLIProxyAPI config
- You can enable/disable providers without deleting them

### Step 6: Save

1. Click **"Add Provider"** (or **"Save Changes"** if editing)
2. The provider will be validated
3. If validation passes, the provider is saved and synced to CLIProxyAPI config
4. The dialog will close automatically

## Editing a Custom Provider

1. In the **Custom Providers** section, find the provider you want to edit
2. Right-click (or Control-click) on the provider row
3. Select **"Edit"** from the context menu
4. Or click the provider row and use the context menu
5. Make your changes in the dialog
6. Click **"Save Changes"**

## Managing Custom Providers

### Enable/Disable

- **Toggle Button**: Click the checkmark/circle icon on the right side of the provider row
- **Context Menu**: Right-click → "Enable" or "Disable"
- Disabled providers show a "Disabled" badge

### Delete

1. Right-click on the provider row
2. Select **"Delete"** from the context menu
3. Confirm the deletion in the dialog
4. The provider will be removed and synced to CLIProxyAPI config

### View Details

The provider row shows:
- **Provider icon** (colored circle with provider type icon)
- **Provider name**
- **Type** (e.g., "OpenAI Compatible")
- **API key count** (e.g., "2 keys")
- **Status** (enabled/disabled badge)

## Configuration Details

### How It Works

1. **Storage**: Custom providers are stored in UserDefaults (persisted across app restarts)
2. **Config Sync**: When you add/edit/delete a provider, it automatically syncs to the CLIProxyAPI config file
3. **YAML Generation**: Providers are converted to YAML format compatible with CLIProxyAPI
4. **Proxy Integration**: The proxy uses these providers when routing requests

### Config File Location

Custom providers are added to the CLIProxyAPI config file:
- **Path**: `~/.config/cliproxyapi/config.yaml`
- **Section**: Custom provider sections are appended at the end with a marker comment

### YAML Structure

The generated YAML follows CLIProxyAPI's format:

```yaml
# Custom Providers (managed by Quotio)

openai-compatibility:
  - name: "OpenRouter"
    base-url: "https://api.openrouter.ai"
    api-key-entries:
      - api-key: "sk-or-v1-..."
    models:
      - name: "openai/gpt-4"
        alias: "gpt-4"

claude-api-key:
  - api-key: "sk-ant-..."
    base-url: "https://api.anthropic.com"
    models:
      - name: "claude-3-opus"
        alias: "claude-opus"
```

## Validation

The system validates providers before saving:

- **Name**: Must not be empty
- **Base URL**: Required for OpenAI/Codex types, must be valid URL format
- **API Keys**: At least one non-empty API key required
- **Duplicate Names**: Provider names must be unique
- **Model Mappings**: Upstream model names must not be empty

If validation fails, an error dialog will show the specific issues.

## Best Practices

### Naming

- Use descriptive names that identify the provider (e.g., "OpenRouter Production", "Local Ollama")
- Avoid generic names like "Provider 1" or "Test"

### API Keys

- Use secure fields (they're masked in the UI)
- Add multiple keys for load balancing or failover
- Use proxy URLs if your API keys require proxy configuration

### Model Mapping

- Use clear, memorable aliases
- Keep upstream model names exact (case-sensitive)
- Add thinking budgets for reasoning models

### Organization

- Enable only providers you're actively using
- Disable providers instead of deleting if you might use them again
- Group related providers with similar naming (e.g., "Ollama Local", "Ollama Remote")

### Testing

- Test providers after adding them
- Verify model mappings work correctly
- Check that API keys are valid

## Troubleshooting

### Provider Not Appearing

- **Check Mode**: Custom Providers only appear in Local Proxy Mode
- **Check Enabled**: Disabled providers still appear but show a "Disabled" badge
- **Check GLM**: GLM providers appear in "Your Accounts", not "Custom Providers"

### Config Not Syncing

- **Check Proxy Running**: The proxy must be running to sync config
- **Check Permissions**: Ensure Quotio has write access to the config file
- **Check File Path**: Verify the config file exists at `~/.config/cliproxyapi/config.yaml`

### Validation Errors

- **Empty Fields**: Ensure all required fields are filled
- **Invalid URL**: Base URL must be a valid URL (e.g., `https://api.example.com`)
- **Duplicate Name**: Provider names must be unique
- **Empty API Keys**: At least one API key is required

### API Not Working

- **Check Base URL**: Verify the base URL is correct
- **Check API Key**: Ensure the API key is valid and has proper permissions
- **Check Proxy**: Ensure the proxy is running and can reach the API endpoint
- **Check Headers**: For Gemini, verify custom headers are correct

### Model Mapping Not Working

- **Check Model Names**: Upstream model names must match exactly (case-sensitive)
- **Check Alias**: Verify the alias is being used correctly in your CLI tools
- **Check Provider Type**: Model mapping only works for OpenAI/Claude compatible types

## Advanced Features

### Multiple API Keys

You can add multiple API keys to a provider for:
- **Load Balancing**: Distribute requests across keys
- **Failover**: Automatic fallback if one key fails
- **Rate Limiting**: Spread requests across multiple accounts

### Proxy URLs

For each API key, you can specify a proxy URL:
- Useful for API keys that require proxy configuration
- Format: `http://proxy.example.com:8080`
- Optional field

### Thinking Budget

For reasoning models, you can specify a thinking budget:
- Format: Number (e.g., `1000000`)
- Added to model alias: `model-name(1000000)`
- Only available for OpenAI/Claude compatible types

### Custom Headers

For Gemini-compatible providers, you can add custom HTTP headers:
- Useful for API versioning or authentication
- Format: `Header-Name: Header-Value`
- Only available for Gemini compatible type

## Integration with CLIProxyAPI

Custom providers are automatically integrated with CLIProxyAPI:

1. **Config Generation**: Providers are converted to YAML format
2. **Config Sync**: Changes are written to the config file
3. **Proxy Reload**: The proxy automatically picks up config changes
4. **Request Routing**: The proxy routes requests to custom providers based on model aliases

## Examples

### Example 1: OpenRouter

**Provider Type**: OpenAI Compatible  
**Name**: OpenRouter  
**Base URL**: `https://api.openrouter.ai`  
**API Key**: `sk-or-v1-...`  
**Models**:
- `openai/gpt-4` → `gpt-4`
- `anthropic/claude-3-opus` → `claude-opus`

### Example 2: Local Ollama

**Provider Type**: OpenAI Compatible  
**Name**: Local Ollama  
**Base URL**: `http://localhost:11434`  
**API Key**: `ollama` (or leave empty if not required)  
**Models**:
- `llama2` → `llama2`
- `mistral` → `mistral`

### Example 3: Custom Gemini Endpoint

**Provider Type**: Gemini Compatible  
**Name**: Custom Gemini  
**Base URL**: `https://api.custom-gemini.com`  
**API Key**: `AIza...`  
**Headers**:
- `X-API-Version`: `v2`
- `X-Custom-Auth`: `token123`

## Related Features

- **Providers Screen**: Main interface for managing providers
- **CLIProxyAPI Config**: Custom providers are synced to the config file
- **Model Aliases**: Custom providers support model aliasing
- **Proxy Routing**: The proxy routes requests based on provider configuration

---

**Note**: Custom Providers require Local Proxy Mode. If you're using Monitor Mode or Remote Proxy Mode, this feature is not available.

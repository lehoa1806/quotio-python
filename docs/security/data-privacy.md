# Data Privacy & Exfiltration Security Assessment: Quotio Python Edition

**Assessment Date:** 2026-01-23  
**Repository:** quotio-python  
**Focus:** Sensitive Data Collection & Exfiltration Risks  
**Threat Model:** Adversarial (zero trust)

---

## ✅ 1. Safety Verdict

### ⚠️ **CONDITIONALLY SAFE** (with privacy mitigations required)

**Data Exfiltration Risk:** **MEDIUM-HIGH**

The application **does collect sensitive data** (API keys, tokens, authentication credentials) and **does make outbound network requests**, but:
- ✅ **No telemetry or analytics** services detected
- ✅ **No error reporting** services (Sentry, Datadog, etc.)
- ✅ **No "phone home"** mechanisms
- ⚠️ **OAuth client secret** - Now loads from environment variable (with fallback)
- ⚠️ **Sensitive data in logs** (debug mode)
- ⚠️ **Sensitive data persisted** to local files (with proper permissions)
- ⚠️ **Outbound requests** to multiple AI provider APIs (expected functionality)

---

## 🔍 2. Sensitive Data Collection Map

| Collection Surface                                                                         | Data Types                                                                 | Why Collected                                         | Risk                                    | Minimization Status                     |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------- | --------------------------------------- |
| **Auth File Reading** (`direct_auth_file_service.py`, `quota_fetchers/*.py`)               | Access tokens, refresh tokens, API keys, OAuth tokens, email addresses     | Required for quota fetching and authentication        | **HIGH** - Contains full credentials    | ❌ No redaction - full tokens stored     |
| **SQLite Database Access** (`antigravity_switcher.py`, `cursor.py`, `ide_scan_service.py`) | Access tokens, refresh tokens, email addresses, user IDs, account info     | Required for IDE account switching and quota tracking | **HIGH** - Direct database access       | ❌ No redaction - full tokens read       |
| **Shell Profile Reading** (`agent_config.py:323-355`)                                      | API keys, base URLs from environment variables                             | Required to detect existing agent configurations      | **MEDIUM** - May contain credentials    | ❌ No redaction - full content read      |
| **Request Tracking** (`request_tracker.py`)                                                | Endpoints, models, tokens (counts), request/response sizes, error messages | Analytics for dashboard display                       | **LOW** - Metadata only, no full tokens | ✅ No full tokens stored                 |
| **Usage Statistics** (`usage_stats.py`)                                                    | Request counts, token counts, success/failure rates                        | Dashboard metrics                                     | **LOW** - Aggregated data only          | ✅ No PII or tokens                      |
| **Agent Connection Storage** (`agent_connection_storage.py:94`)                            | API keys, proxy URLs, connection names                                     | Required for connection management                    | **HIGH** - Full API keys stored         | ❌ No encryption - plaintext storage     |
| **Settings Storage** (`settings.py`)                                                       | User preferences, remote proxy URLs, management keys                       | Application configuration                             | **MEDIUM** - May contain sensitive URLs | ⚠️ Permissions set (0o600) but plaintext |
| **Environment Variables** (`main.py:18,30,58`)                                             | Debug flags, shell type                                                    | Application behavior                                  | **LOW** - No sensitive data             | ✅ Only reads non-sensitive vars         |
| **System Information** (`proxy_manager.py:48`, `agent_detection.py`)                       | Platform type, home directory, binary paths                                | Cross-platform compatibility                          | **LOW** - System metadata only          | ✅ No PII                                |

### **Critical Collection Points:**

1. **`agent_connection_storage.py:94`** - Stores full API keys in plaintext JSON
   ```python
   "api_key": conn.api_key,  # Full key stored
   ```

2. **`direct_auth_file_service.py:254-296`** - Reads full OAuth tokens from files
   ```python
   token_data["access_token"] = json_data.get("access_token")  # Full token
   ```

3. **`antigravity_switcher.py:311-424`** - Reads/writes tokens to SQLite database
   ```python
   cursor.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                  ("antigravityAuthStatus", auth_status_json))  # Full tokens
   ```

---

## 🌐 3. Outbound Communication Map

| Mechanism                | Destination(s)                                                       | What Data is Sent                          | User/Tenant Data Included?                         | Default-On?      | Mitigations                       |
| ------------------------ | -------------------------------------------------------------------- | ------------------------------------------ | -------------------------------------------------- | ---------------- | --------------------------------- |
| **HTTP/HTTPS (aiohttp)** | `api.github.com/repos/router-for-me/CLIProxyAPIPlus/releases/latest` | Binary download requests                   | ❌ No                                               | ✅ Yes (required) | SSL verification enabled          |
| **HTTP/HTTPS (aiohttp)** | `api.anthropic.com/api/oauth/usage`                                  | OAuth access token in Authorization header | ⚠️ **YES** - Access token                           | ✅ Yes            | Required for quota fetching       |
| **HTTP/HTTPS (aiohttp)** | `chatgpt.com/backend-api/wham/usage`                                 | OAuth access token in Authorization header | ⚠️ **YES** - Access token                           | ✅ Yes            | Required for quota fetching       |
| **HTTP/HTTPS (aiohttp)** | `api.github.com/copilot/usage`                                       | OAuth access token in Authorization header | ⚠️ **YES** - Access token                           | ✅ Yes            | Required for quota fetching       |
| **HTTP/HTTPS (aiohttp)** | `cloudcode-pa.googleapis.com/v1internal:*`                           | OAuth access token, project ID, user agent | ⚠️ **YES** - Access token, project metadata         | ✅ Yes            | Required for Antigravity quota    |
| **HTTP/HTTPS (aiohttp)** | `oauth2.googleapis.com/token`                                        | Client ID, client secret, refresh token    | ⚠️ **YES** - Refresh token, client secret (env var with fallback) | ✅ Yes            | OAuth token refresh               |
| **HTTP/HTTPS (aiohttp)** | `api2.cursor.sh/*`                                                   | OAuth access token in Authorization header | ⚠️ **YES** - Access token                           | ✅ Yes            | Required for Cursor quota         |
| **HTTP/HTTPS (aiohttp)** | `api.warp.dev/v1/usage`                                              | OAuth access token in Authorization header | ⚠️ **YES** - Access token                           | ✅ Yes            | Required for Warp quota           |
| **HTTP/HTTPS (aiohttp)** | `bigmodel.cn/api/monitor/usage/quota/limit`                          | API key or token                           | ⚠️ **YES** - API key/token                          | ✅ Yes            | Required for GLM quota            |
| **HTTP/HTTPS (aiohttp)** | `api-sg-central.trae.ai/*`                                           | OAuth access token                         | ⚠️ **YES** - Access token                           | ✅ Yes            | Required for Trae quota           |
| **HTTP/HTTPS (aiohttp)** | `codewhisperer.us-east-1.amazonaws.com/*`                            | OAuth tokens                               | ⚠️ **YES** - Tokens                                 | ✅ Yes            | Required for Kiro quota           |
| **HTTP/HTTPS (aiohttp)** | `api.openai.com/v1/models`                                           | API key in Authorization header            | ⚠️ **YES** - API key                                | ✅ Yes            | Required for API key validation   |
| **HTTP/HTTPS (aiohttp)** | `http://127.0.0.1:8317/*` (local proxy)                              | Management key, API keys, auth file data   | ⚠️ **YES** - All credentials                        | ✅ Yes            | Local only, but contains all data |
| **HTTP/HTTPS (aiohttp)** | Remote proxy URLs (user-configured)                                  | Management key, API keys, auth file data   | ⚠️ **YES** - All credentials                        | ⚠️ Optional       | User must explicitly configure    |

### **Critical Outbound Risks:**

1. **OAuth Client Secret** (`antigravity.py:29-39`) ✅ **IMPROVED**
   ```python
   # Now loads from environment variable with fallback
   self.CLIENT_SECRET = os.getenv("ANTIGRAVITY_CLIENT_SECRET", self._DEFAULT_CLIENT_SECRET)
   ```
   - **Previous Risk:** Secret was hardcoded in source code
   - **Current Status:** ✅ **IMPROVED** - Now loads from `ANTIGRAVITY_CLIENT_SECRET` environment variable
   - **Remaining Risk:** ⚠️ Still has hardcoded fallback for backward compatibility
   - **Recommendation:** Set `ANTIGRAVITY_CLIENT_SECRET` environment variable to avoid using fallback

2. **Access Tokens in HTTP Headers**
   - All quota fetchers send access tokens in `Authorization: Bearer <token>` headers
   - Tokens are sent over HTTPS (SSL verification enabled)
   - **Risk:** If TLS is compromised or certificate validation fails, tokens could be intercepted
   - **Mitigation:** Certificate pinning recommended for critical APIs

3. **Local Proxy Management API**
   - Sends management keys and API keys to local proxy (`http://127.0.0.1:8317`)
   - **Risk:** If proxy is compromised or remote proxy is misconfigured, credentials could leak
   - **Mitigation:** Validate proxy identity, use TLS for remote proxies

---

## 🧨 4. Risk Findings (Detailed)

### **CRITICAL RISKS**

#### **C-1: OAuth Client Secret** ✅ **IMPROVED**
- **Location:** `quotio/services/quota_fetchers/antigravity.py:29-39`
- **Severity:** **CRITICAL** (was CRITICAL, now IMPROVED)
- **Status:** ✅ **IMPROVED** - Now loads from environment variable
- **Previous Description:** Google OAuth client secret was hardcoded in source code
- **Current Implementation:** Loads from `ANTIGRAVITY_CLIENT_SECRET` environment variable with fallback
- **Previous Risk:** If repository was public or compromised, attacker could use secret to impersonate application
- **Current Risk:** ⚠️ Still has hardcoded fallback for backward compatibility
- **Evidence:**
  ```python
  # Now loads from environment variable
  self.CLIENT_SECRET = os.getenv("ANTIGRAVITY_CLIENT_SECRET", self._DEFAULT_CLIENT_SECRET)
  ```
- **Recommended Fix:** ✅ **PARTIALLY IMPLEMENTED** - Set `ANTIGRAVITY_CLIENT_SECRET` environment variable to avoid using fallback. Consider removing fallback in future version.

#### **C-2: Plaintext API Key Storage**
- **Location:** `quotio/services/agent_connection_storage.py:94`
- **Severity:** **CRITICAL**
- **Description:** API keys stored in plaintext JSON file (`~/.quotio/agent_connections.json`)
- **Exploit Scenario:** If file system is compromised, all API keys are exposed
- **Evidence:**
  ```python
  "api_key": conn.api_key,  # Stored in plaintext
  ```
- **Recommended Fix:** Encrypt API keys at rest using keyring or encryption

#### **C-3: Sensitive Data in Logs (Debug Mode)**
- **Location:** `quotio/ui/screens/agents.py:1393-1520`, `main.py:15-52`
- **Severity:** **HIGH**
- **Description:** Debug mode logs API key lengths, error messages that may contain tokens
- **Exploit Scenario:** If logs are captured or shared, sensitive data could leak
- **Evidence:**
  ```python
  print(f"[_verify_api_key] Starting verification: agent={agent.display_name}, api_key_length={len(api_key)}")
  ```
- **Recommended Fix:** Redact sensitive data in logs, disable debug logging by default

### **HIGH RISKS**

#### **H-1: Access Tokens Sent to External APIs**
- **Location:** All quota fetchers (`quota_fetchers/*.py`)
- **Severity:** **HIGH**
- **Description:** Access tokens sent in HTTP headers to multiple external APIs
- **Exploit Scenario:** If TLS is compromised, man-in-the-middle attack, or API is compromised, tokens could be stolen
- **Evidence:** All quota fetchers use `Authorization: Bearer <token>` headers
- **Recommended Fix:** Implement certificate pinning, token rotation, short-lived tokens

#### **H-2: SQLite Database Direct Access**
- **Location:** `quotio/services/antigravity_switcher.py:311-424`, `cursor.py:30-74`
- **Severity:** **HIGH**
- **Description:** Directly reads and modifies SQLite databases containing authentication tokens
- **Exploit Scenario:** If database is locked or corrupted, could cause data loss or token exposure
- **Evidence:**
  ```python
  cursor.execute("INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                 ("antigravityAuthStatus", auth_status_json))
  ```
- **Recommended Fix:** Add database backup before modification, validate data before writing

#### **H-3: Request History Persistence**
- **Location:** `quotio/services/request_tracker.py:195-227`
- **Severity:** **MEDIUM-HIGH**
- **Description:** Request metadata (endpoints, models, error messages) persisted to JSON file
- **Exploit Scenario:** Error messages may contain sensitive data, endpoints may reveal usage patterns
- **Evidence:**
  ```python
  "error_message": entry.error_message,  # May contain sensitive data
  ```
- **Recommended Fix:** Sanitize error messages, redact sensitive endpoints

### **MEDIUM RISKS**

#### **M-1: Shell Profile Reading**
- **Location:** `quotio/services/agent_config.py:323-355`
- **Severity:** **MEDIUM**
- **Description:** Reads shell profiles to extract environment variables (may contain API keys)
- **Exploit Scenario:** If shell profile contains credentials, they are read into memory
- **Evidence:**
  ```python
  api_key = self._extract_env_var(content, "GEMINI_API_KEY")
  ```
- **Recommended Fix:** Validate and sanitize extracted values

#### **M-2: Settings File May Contain Sensitive URLs**
- **Location:** `quotio/utils/settings.py:45-46`
- **Severity:** **MEDIUM**
- **Description:** Settings file may contain remote proxy URLs with credentials
- **Exploit Scenario:** If settings file is compromised, remote proxy credentials could be exposed
- **Evidence:**
  ```python
  json.dump(self._settings, f, indent=2)  # May contain sensitive URLs
  ```
- **Recommended Fix:** Encrypt sensitive settings, redact URLs in logs

#### **M-3: No Telemetry But Usage Stats Collected**
- **Location:** `quotio/viewmodels/quota_viewmodel.py:1345-1385`
- **Severity:** **LOW-MEDIUM**
- **Description:** Polls usage statistics from proxy (aggregated data only)
- **Exploit Scenario:** If proxy is compromised, usage data could be exfiltrated
- **Evidence:**
  ```python
  usage_stats = await self.api_client.fetch_usage_stats()
  ```
- **Recommended Fix:** Ensure proxy is trusted, validate usage stats data

---

## 🛡 5. Mitigations & Hardening Steps

### **MANDATORY Before Running:**

1. **Configure OAuth Client Secret (Recommended):**
   - Set `ANTIGRAVITY_CLIENT_SECRET` environment variable to avoid using fallback
   - The fallback is still present for backward compatibility but should be avoided in production
   - Never commit secrets to repository
   - Use secret scanning tools (gitleaks, trufflehog)

2. **Encrypt Sensitive Data at Rest:**
   - Encrypt API keys in `agent_connection_storage.py`
   - Use keyring for all secrets (not just management key)
   - Encrypt settings file if it contains sensitive URLs

3. **Redact Sensitive Data in Logs:**
   - Remove or redact API key lengths from debug logs
   - Sanitize error messages before logging
   - Disable debug logging by default

4. **Implement Certificate Pinning:**
   - Pin certificates for critical APIs (OpenAI, Anthropic, Google)
   - Validate SSL certificates strictly
   - Fail closed on certificate errors

### **RECOMMENDED Improvements:**

1. **Data Minimization:**
   - Only collect minimum required data
   - Hash or tokenize sensitive identifiers
   - Implement data retention policies

2. **Network Security:**
   - Use TLS 1.3 for all connections
   - Implement request signing for sensitive operations
   - Add rate limiting for API calls

3. **Access Control:**
   - Restrict file permissions (already done for some files)
   - Implement file encryption for sensitive data
   - Add audit logging for sensitive operations

4. **Monitoring & Detection:**
   - Monitor for unexpected outbound connections
   - Alert on large data transfers
   - Log all network requests (without sensitive data)

5. **Dependency Security:**
   - Audit dependencies for telemetry/analytics
   - Pin dependency versions
   - Use `pip-audit` to check for vulnerabilities

---

## 🧪 6. Safe Execution Plan

### **Network Restrictions:**

1. **Outbound Allowlist:**
   ```bash
   # Only allow connections to known AI provider APIs
   # Block all other outbound connections
   ```

2. **DNS Monitoring:**
   - Monitor DNS queries for unexpected domains
   - Block DNS to analytics/telemetry services
   - Alert on new domain resolutions

3. **HTTP/HTTPS Monitoring:**
   - Use mitmproxy or similar to inspect outbound requests
   - Verify no data is sent to unexpected endpoints
   - Check for telemetry beacons

### **File System Restrictions:**

1. **Read-Only Mounts:**
   - Mount sensitive directories as read-only where possible
   - Restrict write access to application data directories only

2. **File Monitoring:**
   - Monitor writes to sensitive files
   - Alert on unexpected file modifications
   - Backup files before modification

3. **Permission Restrictions:**
   - Run as non-root user
   - Use AppArmor/SELinux to restrict file access
   - Deny access to SSH keys, cloud metadata endpoints

### **Runtime Monitoring:**

1. **Process Monitoring:**
   - Monitor subprocess execution
   - Alert on unexpected process spawns
   - Log all file system operations

2. **Network Monitoring:**
   - Use tcpdump or eBPF to capture network traffic
   - Analyze for sensitive data in payloads
   - Check for unexpected destinations

3. **Memory Monitoring:**
   - Monitor for sensitive data in memory dumps
   - Use memory protection mechanisms
   - Clear sensitive data from memory when done

### **Docker/Container Strategy:**

```dockerfile
FROM python:3.10-slim
RUN useradd -m -u 1000 quotio
USER quotio
WORKDIR /home/quotio

# Copy application
COPY --chown=quotio:quotio quotio/ /home/quotio/quotio/

# Run with restrictions
# docker run --read-only --tmpfs /tmp --network none --cap-drop=ALL quotio
```

**Network Policy:**
- Deny all egress by default
- Allow only specific AI provider API endpoints
- Block analytics/telemetry domains

---

## 📋 7. Final Recommendation

### **Would I run this on my own machine?**

**YES, but with significant privacy mitigations:**

1. ✅ **No telemetry detected** - Application does not phone home
2. ✅ **Local data storage** - All data stays on device
3. ⚠️ **Client secret** - Now loads from environment variable (set `ANTIGRAVITY_CLIENT_SECRET` to avoid fallback)
4. ⚠️ **Plaintext storage** - API keys should be encrypted
5. ⚠️ **Debug logging** - Should be disabled or sanitized

**Required before running:**
- Set `ANTIGRAVITY_CLIENT_SECRET` environment variable (fallback still exists for backward compatibility)
- Encrypt API keys in storage
- Disable or sanitize debug logging
- Review and restrict network access

### **Would I run it in CI?**

**NO, not without:**
- Network egress restrictions (allowlist only)
- Secret scanning (gitleaks, trufflehog)
- File system restrictions
- Audit logging enabled
- No access to production credentials

### **Would I deploy it to production?**

**NO, not without:**
- All mandatory mitigations implemented
- Security review completed
- Penetration testing performed
- Incident response plan in place
- Data encryption at rest and in transit
- Certificate pinning implemented
- Secret rotation capability
- Audit logging for all sensitive operations

---

## 📊 Risk Summary

| Risk Category | Count | Severity Distribution                                 |
| ------------- | ----- | ----------------------------------------------------- |
| Critical      | 3     | Client secret (improved), Plaintext storage, Log exposure     |
| High          | 3     | Token transmission, Database access, Request history  |
| Medium        | 3     | Shell profile reading, Settings exposure, Usage stats |

**Total Identified Risks:** 9

**Data Exfiltration Risk:** **MEDIUM-HIGH**
- No telemetry/analytics services ✅
- No error reporting services ✅
- Sensitive data sent to AI provider APIs (expected) ⚠️
- Client secret in source code (fallback) ⚠️ (improved - now uses env var)
- Plaintext storage of API keys ❌
- Sensitive data in logs (debug mode) ⚠️

---

## ✅ Positive Privacy Practices Observed

1. ✅ **No telemetry or analytics** services detected
2. ✅ **No error reporting** services (Sentry, Datadog, etc.)
3. ✅ **No "phone home"** mechanisms
4. ✅ **Local data storage** - All data stays on device
5. ✅ **Secure file permissions** (0o600, 0o700) for sensitive files
6. ✅ **SSL verification** enabled for all HTTPS connections
7. ✅ **Request tracking** only stores metadata, not full tokens
8. ✅ **Usage statistics** are aggregated, no PII

---

## 🔒 Conclusion

This application **does collect sensitive data** (API keys, tokens, credentials) and **does make outbound network requests** to AI provider APIs, but:

- ✅ **No telemetry or analytics** - Data does not leave device for tracking
- ✅ **No error reporting** - No third-party services receive data
- ⚠️ **Client secret** - Set `ANTIGRAVITY_CLIENT_SECRET` env var (fallback exists for compatibility)
- ⚠️ **Plaintext storage** - API keys should be encrypted
- ⚠️ **Debug logging** - May expose sensitive data

**Recommendation:** Address all **CRITICAL** risks before deployment. Implement recommended mitigations and conduct a security review after changes.

**Timeline:** With proper privacy hardening, this could be made production-ready in 1-2 weeks of focused security work.

---

**Report Generated:** 2026-01-23  
**Next Review:** After privacy hardening implementation

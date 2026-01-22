# OAuth Client Secret Analysis: `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`

## Current Usage

**Location:** `quotio/services/quota_fetchers/antigravity.py:22`

**Purpose:** Used to refresh OAuth access tokens for Antigravity (Google-based IDE) quota fetching.

**Usage Context:**
```python
async def _refresh_access_token(self, refresh_token: str) -> Optional[str]:
    data = {
        "client_id": self.CLIENT_ID,
        "client_secret": self.CLIENT_SECRET,  # ← Used here
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    # POST to https://oauth2.googleapis.com/token
```

## Why It's Needed

1. **Token Refresh**: When Antigravity access tokens expire, the application needs to refresh them using the OAuth2 refresh token flow
2. **Quota Fetching**: To fetch quota data from Google's Cloud Code API, valid access tokens are required
3. **Account Switching**: When switching Antigravity accounts, expired tokens need to be refreshed

## Security Assessment

### ⚠️ **CRITICAL CONCERN: Hardcoded Secret**

**Risk Level:** **HIGH**

**Issues:**
1. **Exposed in Source Code**: The secret is visible in the repository
2. **No Rotation Capability**: Cannot rotate the secret without code changes
3. **Version Control History**: Secret is permanently in git history
4. **Potential Abuse**: If this is Antigravity's actual client secret, it could be abused by others

### Is This a "Public" Client Secret?

**Google OAuth Client Types:**
- **Confidential Clients** (web apps): Secret must be kept private
- **Public Clients** (desktop/mobile apps): Secret is often considered "public" but should still be protected

**Analysis:**
- The `GOCSPX-` prefix indicates this is a Google OAuth client secret
- Desktop applications cannot truly secure client secrets (they're in the binary)
- However, **best practice is still to avoid hardcoding** and use:
  - Environment variables
  - Configuration files (not in git)
  - Secure key storage

### Potential Scenarios

**Scenario 1: This is Antigravity's Actual Client Secret**
- ⚠️ **HIGH RISK**: If exposed, others could use it to refresh tokens
- ⚠️ **ABUSE RISK**: Could be used to impersonate Antigravity application
- ✅ **MITIGATION**: Google may have rate limiting/IP restrictions

**Scenario 2: This is a Custom Client Secret**
- ⚠️ **MEDIUM RISK**: Should be rotated and moved to secure storage
- ⚠️ **EXPOSURE RISK**: Anyone with repo access can see it
- ✅ **MITIGATION**: Can be regenerated in Google Cloud Console

## Recommendations

### **IMMEDIATE ACTIONS (Required)**

1. **Move to Environment Variable**
   ```python
   CLIENT_SECRET = os.getenv(
       "ANTIGRAVITY_CLIENT_SECRET",
       "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"  # Fallback for backward compatibility
   )
   ```

2. **Add to `.gitignore`**
   - Create `.env.example` with placeholder
   - Document in README how to set the variable

3. **Document Security Implications**
   - Add comments explaining why it's needed
   - Document that it's a "public" client secret (if applicable)
   - Warn about exposure risks

### **BETTER SOLUTION (Recommended)**

1. **Use Secure Key Storage**
   ```python
   import keyring
   
   def get_client_secret():
       secret = keyring.get_password("quotio", "antigravity_client_secret")
       if not secret:
           # Fallback to env var or raise error
           secret = os.getenv("ANTIGRAVITY_CLIENT_SECRET")
           if secret:
               keyring.set_password("quotio", "antigravity_client_secret", secret)
       return secret
   ```

2. **Configuration File (Not in Git)**
   - Store in `~/.quotio/config.json` (already exists for settings)
   - Load at runtime
   - Document in setup instructions

3. **Rotate the Secret** (if it's a custom client)
   - Generate new secret in Google Cloud Console
   - Update all deployments
   - Revoke old secret

### **IDEAL SOLUTION (Long-term)**

1. **Use OAuth PKCE Flow** (if Google supports it for this use case)
   - Eliminates need for client secret in desktop apps
   - More secure for public clients

2. **Proxy-Based Authentication**
   - Let the proxy handle OAuth (if possible)
   - Application doesn't need client secret

3. **User-Provided Credentials**
   - Allow users to provide their own OAuth client credentials
   - Store securely per-user

## Implementation Plan

### Step 1: Immediate Fix (Environment Variable)
```python
import os

class AntigravityQuotaFetcher(BaseQuotaFetcher):
    CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
    
    def __init__(self, api_client=None):
        super().__init__(api_client)
        # Load from environment variable, with fallback for backward compatibility
        self.CLIENT_SECRET = os.getenv(
            "ANTIGRAVITY_CLIENT_SECRET",
            "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"  # TODO: Remove fallback after migration
        )
        # ... rest of init
```

### Step 2: Add Documentation
- Update README with environment variable setup
- Add security notes about OAuth client secrets
- Document why the secret is needed

### Step 3: Create .env.example
```bash
# Antigravity OAuth Client Secret
# Get this from Google Cloud Console or use the default (if public client)
ANTIGRAVITY_CLIENT_SECRET=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
```

### Step 4: Update .gitignore
```
.env
*.env
!*.env.example
```

## Verification

**Questions to Answer:**
1. ✅ Is this Antigravity's actual client secret or a custom one?
2. ✅ Does Google have rate limiting/IP restrictions on this client?
3. ✅ Can the secret be rotated without breaking existing users?
4. ✅ Is there a way to eliminate the need for the secret entirely?

## Client ID Analysis

**Location:** `quotio/services/quota_fetchers/antigravity.py:22`

**Value:** `1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com`

### Security Assessment: **LOW-MEDIUM RISK**

**Key Difference from Client Secret:**
- **Client IDs are PUBLIC identifiers** - Google OAuth documentation explicitly states they're safe to expose
- **Client Secrets are PRIVATE credentials** - Must be kept secret
- Client IDs are meant to be embedded in client applications (web, mobile, desktop)

### Why Client IDs Are Generally Safe

1. **Designed to be Public**: OAuth 2.0 specification allows client IDs to be public
2. **No Direct Access**: Client ID alone cannot be used to access user data
3. **Requires User Consent**: OAuth flow requires user interaction and consent
4. **Google's Protection**: Google has rate limiting and abuse detection

### Potential Concerns (Low Risk)

1. **Rate Limiting Abuse**: Could be used to exhaust OAuth quota (mitigated by Google's protections)
2. **Phishing Attacks**: Could be used in malicious OAuth flows (requires user interaction)
3. **Application Fingerprinting**: Reveals which application is making requests
4. **Quota Tracking**: Could be used to track application usage

### Recommendation

**Priority:** **LOW** (compared to client secret)

**Options:**

1. **Keep Hardcoded** (Acceptable)
   - Client IDs are meant to be public
   - Low security risk
   - Simplest approach

2. **Make Configurable** (Best Practice)
   - For consistency with client secret handling
   - Allows different clients for different environments
   - Better flexibility

3. **Document Clearly** (Minimum)
   - Add comments explaining it's safe to expose
   - Clarify difference from client secret

### Implementation (If Making Configurable)

```python
# OAuth Client ID - This is a PUBLIC identifier, safe to expose
# However, we make it configurable for flexibility and consistency
CLIENT_ID = os.getenv(
    "ANTIGRAVITY_CLIENT_ID",
    "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
)
```

## Conclusion

**Client Secret State:** ⚠️ **UNSAFE** - Hardcoded secret in source code

**Client ID State:** ✅ **ACCEPTABLE** - Public identifier, but configurable is better

**Required Action:** 
- **Client Secret**: Move to environment variable (✅ DONE)
- **Client ID**: Optional - can keep hardcoded or make configurable for consistency

**Priority:** 
- **Client Secret**: **HIGH** - Must fix
- **Client ID**: **LOW** - Nice to have, not critical

**Risk if Not Fixed:**
- **Client Secret**: Secret exposure, cannot rotate, potential abuse
- **Client ID**: Minimal risk, mainly about best practices and flexibility

# Antigravity Account Switching - Python Version

## Overview

The Antigravity Account Switching feature allows you to seamlessly switch between different Antigravity accounts directly from Quotio. This feature automatically updates the Antigravity IDE's authentication database and can restart the IDE if it's currently running.

## Prerequisites

- **macOS only**: This feature only works on macOS (Darwin) systems
- **Antigravity IDE installed**: The Antigravity IDE must be installed on your system
- **Multiple Antigravity accounts**: You need to have multiple Antigravity accounts connected in Quotio
- **Proxy running**: The proxy server should be running (Local Proxy mode)

## How It Works

The account switching process involves:

1. **Detecting Active Account**: Quotio reads the Antigravity IDE's database to detect which account is currently active
2. **Account Selection**: You select which account to switch to from your connected accounts
3. **IDE Management**: If the IDE is running, it will be closed, the database updated, and then restarted
4. **Database Update**: The Antigravity IDE's authentication database is updated with the new account's access token
5. **Verification**: Quotio verifies the switch was successful and refreshes quota data

## Step-by-Step Usage

### 1. Connect Multiple Antigravity Accounts

First, ensure you have multiple Antigravity accounts connected:

1. Go to the **Providers** tab
2. Click on **Antigravity** in the provider list
3. Click **Connect** and complete OAuth for each account you want to use
4. Each account will appear as a separate auth file

### 2. Switch Accounts

To switch between Antigravity accounts:

1. Go to the **Providers** tab
2. Click on **Antigravity** in the provider list to select it
3. A **Switch Account** button will appear (only visible when Antigravity is selected)
4. Click the **Switch Account** button
5. If you have multiple accounts:
   - A dialog will appear asking you to select which account to switch to
   - Choose the account from the dropdown list
   - Click **OK**
6. If Antigravity IDE is running:
   - A confirmation dialog will appear warning that the IDE will be restarted
   - Click **Yes** to continue
7. Wait for the switch to complete:
   - The message area will show "Switching Antigravity account..."
   - The IDE will close (if running)
   - The database will be updated
   - The IDE will restart (if it was running)
   - Success message: "Account switched successfully!"

### 3. Verify the Switch

After switching:

1. Check the message area for confirmation
2. The quota data will automatically refresh
3. Open Antigravity IDE to verify the new account is active
4. The active account will be marked in the provider list (if detected)

## Technical Details

### Database Location

The Antigravity IDE stores its authentication data in:
```
~/Library/Application Support/Antigravity/User/globalStorage/state.vscdb
```
or
```
~/Library/Application Support/Antigravity/User/globalStorage/state.db
```

### What Gets Updated

The switcher updates the `antigravityAuthStatus` key in the database with:
- Email address
- Access token
- Refresh token
- Expiration time

### IDE Restart Behavior

- **If IDE is running**: It will be closed using `pkill`, the database updated, then restarted using `open` command
- **If IDE is not running**: Only the database is updated (no restart needed)

### Active Account Detection

Quotio can detect the currently active account by:
1. Reading the Antigravity database
2. Extracting the email from `antigravityAuthStatus`
3. Displaying it in the provider list with an "(Active)" indicator

## Troubleshooting

### "Auth file not found" Error

- **Cause**: The auth file doesn't exist in `~/.cli-proxy-api/`
- **Solution**: Reconnect the account through OAuth

### "Account switch failed" Error

- **Cause**: Database update failed or IDE couldn't be restarted
- **Solution**: 
  - Check console for detailed error messages
  - Ensure Antigravity IDE is installed in `/Applications/` or `~/Applications/`
  - Try manually closing the IDE before switching
  - Check file permissions on the database

### IDE Doesn't Restart

- **Cause**: Antigravity app not found in standard locations
- **Solution**: 
  - Ensure Antigravity is installed in `/Applications/Antigravity.app` or `~/Applications/Antigravity.app`
  - Manually restart the IDE after switching

### Database Locked Error

- **Cause**: Antigravity IDE has the database locked
- **Solution**: 
  - Close Antigravity IDE completely before switching
  - Wait a few seconds after closing before attempting the switch

### No Accounts Detected

- **Cause**: No Antigravity accounts are connected
- **Solution**: 
  - Go to Providers tab
  - Connect at least one Antigravity account via OAuth

## Limitations

1. **macOS Only**: This feature only works on macOS systems
2. **Single IDE Instance**: Only works with one Antigravity IDE installation
3. **Database Access**: Requires read/write access to Antigravity's database directory
4. **IDE Restart Required**: If the IDE is running, it must be restarted for changes to take effect

## Code Reference

The implementation consists of:

- **Service**: `quotio/services/antigravity_switcher.py` - Core switching logic
- **UI**: `quotio/ui/screens/providers.py` - User interface integration
- **View Model**: `quotio/viewmodels/quota_viewmodel.py` - State management

## Example Workflow

```
1. User has 2 Antigravity accounts: user1@example.com and user2@example.com
2. Currently active: user1@example.com (detected from IDE database)
3. User wants to switch to user2@example.com:
   - Clicks Antigravity in Providers tab
   - Clicks Disconnect button
   - Selects "user2@example.com" from dialog
   - Confirms IDE restart (if IDE is running)
   - Quotio:
     * Closes Antigravity IDE (if running)
     * Updates database with user2's token
     * Restarts Antigravity IDE
     * Shows success message
4. Antigravity IDE opens with user2@example.com account active
```

## Best Practices

1. **Save Your Work**: If Antigravity IDE is open, save all work before switching
2. **Check Active Account**: Use the "Detect Active Account" button to see current account
3. **Multiple Accounts**: Keep all accounts connected in Quotio for easy switching
4. **Wait for Completion**: Don't interrupt the switching process - wait for success message

## Related Features

- **Warmup Service**: Keeps Antigravity accounts active to prevent quota expiration
- **Quota Tracking**: Automatically refreshes quota data after account switch
- **Provider Management**: Manage all Antigravity accounts from the Providers tab

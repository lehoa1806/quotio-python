# IDE Scan Feature Guide

## Overview

The IDE Scan feature allows Quotio to discover and track quota information from locally installed IDEs (Cursor and Trae) and CLI tools. This feature is **privacy-aware** and requires explicit user consent before scanning any IDE data files.

## What It Does

The IDE Scan feature can scan three types of sources:

1. **Cursor IDE** - Reads authentication and quota data from Cursor's local database
   - Path: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
   - Extracts: Account email and quota information

2. **Trae IDE** - Reads authentication and quota data from Trae's storage
   - Path: `~/Library/Application Support/Trae/User/globalStorage/storage.json`
   - Extracts: Account email and quota information

3. **CLI Tools** - Detects installed command-line tools
   - Checks for: `claude`, `codex`, `gemini`, `gh` (GitHub CLI)
   - Uses: `which` command and checks `/usr/local/bin`, `/opt/homebrew/bin`

## Privacy & Security

### Key Privacy Features

- **Explicit Consent Required**: The feature never scans automatically. You must explicitly trigger a scan through the UI.
- **Opt-in Only**: Each scan source (Cursor, Trae, CLI Tools) can be individually enabled/disabled.
- **No Auto-Refresh**: IDE quota data is only updated when you explicitly run a scan. It does not auto-refresh like other providers.
- **Local Only**: All scanning happens locally on your machine. No data is sent to external servers.
- **Transparent**: The scan dialog clearly shows what paths will be accessed before scanning.

### What Data Is Read

- **Cursor/Trae**: Only authentication email and quota information from IDE storage files
- **CLI Tools**: Only checks if tools are installed (no data read from them)

### What Data Is NOT Read

- IDE project files
- Code or workspace content
- Personal files
- Any data outside the specified storage paths

## How to Use

### Step 1: Access the IDE Scan Dialog

1. Open Quotio
2. Navigate to the **Providers** screen (menu bar → Providers, or click the Providers tab)
3. Click the **"Scan for Installed IDEs"** button (or use the "+" button → "Scan IDEs")

The IDE Scan dialog will appear.

### Step 2: Review Privacy Notice

The dialog displays a privacy notice explaining:
- What data sources will be scanned
- Which file paths will be accessed
- That scanning requires your explicit consent

**Important**: Read the privacy notice carefully before proceeding.

### Step 3: Select Scan Options

Choose which sources you want to scan:

- **Cursor IDE** (toggle on/off)
  - Enable to scan Cursor IDE for account and quota data
  - Shows: `Reads ~/Library/Application Support/Cursor/`

- **Trae IDE** (toggle on/off)
  - Enable to scan Trae IDE for account and quota data
  - Shows: `Reads ~/Library/Application Support/Trae/`

- **CLI Tools** (enabled by default)
  - Scans for installed CLI tools (claude, codex, gemini, gh)
  - Non-invasive: only checks if tools are installed
  - Shows: `Uses 'which' command to find installed tools`

**Note**: At least one option must be enabled to proceed with the scan.

### Step 4: Run the Scan

1. Click the **"Scan Now"** button
2. The scan will run in the background
3. A progress indicator shows "Scanning..." while the scan is in progress

### Step 5: Review Results

After the scan completes, you'll see:

- **✓ Green checkmarks** for found items:
  - `Cursor: [email]` (if Cursor account found)
  - `Trae: [email]` (if Trae account found)
  - `CLI: claude, codex, gemini` (list of found CLI tools)

- **✗ Gray X marks** for items that were scanned but not found:
  - `Cursor: Not found` (if Cursor was enabled but not found)
  - `Trae: Not found` (if Trae was enabled but not found)
  - `CLI: Not found` (if CLI tools scan was enabled but none found)

### Step 6: Complete

1. Click **"Done"** to close the dialog
2. The discovered IDE accounts will appear in your Providers list
3. Quota information for Cursor/Trae will be available in the Dashboard and Quota screens

## After Scanning

### Viewing Results

- **Providers Screen**: Cursor and Trae will appear in the providers list with a checkmark if accounts were found
- **Dashboard**: Quota information for scanned IDE accounts will be displayed
- **Quota Screen**: Detailed quota breakdown for each IDE account

### Important Notes

- **No Auto-Refresh**: IDE quota data does not auto-refresh. You must run a scan again to update the data.
- **Manual Refresh**: To update IDE quotas, run the IDE Scan again from the Providers screen.
- **Persistent Data**: Scan results are saved and persist across app restarts (for quota data only, not scan results).

## Troubleshooting

### IDE Not Found

If an IDE is not found during scanning:

1. **Verify Installation**: Make sure Cursor or Trae is actually installed
2. **Check Paths**: Ensure the IDE has created its storage files:
   - Cursor: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
   - Trae: `~/Library/Application Support/Trae/User/globalStorage/storage.json`
3. **First Launch**: Some IDEs may not create storage files until first use. Try launching the IDE at least once.

### No Quota Data

If an IDE is found but no quota data is available:

1. **Check Authentication**: Make sure you're logged into the IDE with an account
2. **Check IDE Settings**: Some IDEs may store quota data differently
3. **Run Scan Again**: Try running the scan again after using the IDE

### CLI Tools Not Found

If CLI tools are not detected:

1. **Check Installation**: Verify the tools are installed:
   ```bash
   which claude
   which codex
   which gemini
   which gh
   ```
2. **Check PATH**: Ensure tools are in your PATH or in `/usr/local/bin` or `/opt/homebrew/bin`
3. **Reinstall**: Some tools may need to be reinstalled to be detected

## Technical Details

### File Paths Accessed

- **Cursor**: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
- **Trae**: `~/Library/Application Support/Trae/User/globalStorage/storage.json`
- **CLI Tools**: Uses system `which` command (checks PATH, `/usr/local/bin`, `/opt/homebrew/bin`)

### Data Extraction

- **Cursor**: Reads SQLite database (`state.vscdb`) to extract authentication email and quota information
- **Trae**: Reads JSON storage file to extract authentication email and quota information
- **CLI Tools**: Only checks existence, does not read any data

### Privacy Implementation

- All scanning is done locally
- No network requests are made during scanning
- Data is only read from the specified paths
- No data is persisted except quota information (which is necessary for the app to function)

## Best Practices

1. **Run Scans Periodically**: Since IDE quotas don't auto-refresh, run a scan when you want to check your quota status
2. **Selective Scanning**: Only enable the scan options you need to minimize file access
3. **Review Results**: Always review scan results to ensure expected accounts are found
4. **Privacy First**: Remember that scanning requires explicit consent - the app never scans automatically

## Related Features

- **Provider Quotas**: Scanned IDE accounts appear in the Providers screen
- **Dashboard**: IDE quota data is displayed alongside other provider quotas
- **Quota Tracking**: IDE quotas are tracked separately and don't auto-refresh (privacy-aware design)

---

**Note**: This feature addresses privacy concerns (Issue #29) by requiring explicit user consent and never auto-scanning IDE data files.

# Docker Quick Start

## Quick Answer: Yes, you can run the GUI in Docker!

The PyQt6 GUI can run in Docker using X11 forwarding or VNC.

## macOS Specific Instructions

### Prerequisites for macOS

1. **Install XQuartz:**
   ```bash
   brew install --cask xquartz
   ```

2. **Start XQuartz:**
   ```bash
   open -a XQuartz
   ```

3. **Allow network connections in XQuartz:**
   - Open XQuartz Preferences (XQuartz → Preferences)
   - Go to "Security" tab
   - Check "Allow connections from network clients"
   - Restart XQuartz

4. **Set DISPLAY variable:**
   ```bash
   export DISPLAY=:0
   # Or for Docker:
   export DISPLAY=host.docker.internal:0
   ```

### macOS Quick Start

```bash
# 1. Start XQuartz
open -a XQuartz

# 2. Allow connections
xhost +localhost

# 3. Build image (first time only)
docker-compose -f docker-compose.macos.yml build
# Or manually:
# docker build -t quotio-python-quotio .

# 4. Run with XQuartz
docker run -it --rm \
  --name quotio-python \
  -e DISPLAY=host.docker.internal:0 \
  -v ~/.quotio:/home/quotio/.quotio:rw \
  -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
  --network host \
  quotio-python-quotio:latest
```

### macOS with Docker Compose

**Option 1: Use macOS-specific compose file:**
```bash
# 1. Start XQuartz and allow connections
open -a XQuartz
xhost +localhost

# 2. Run with macOS config
docker-compose -f docker-compose.macos.yml up
```

**Option 2: Use default compose file:**
```bash
# 1. Start XQuartz and allow connections
open -a XQuartz
xhost +localhost

# 2. Set DISPLAY environment variable
export DISPLAY=host.docker.internal:0

# 3. Start
docker-compose up
```

### macOS VNC Method (Alternative - Recommended)

If XQuartz doesn't work, use VNC (works reliably on macOS):

```bash
docker run -it --rm \
  --name quotio-python \
  -v ~/.quotio:/home/quotio/.quotio:rw \
  -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
  --network host \
  quotio-python-quotio:latest \
  sh -c "Xvfb :99 -screen 0 1024x768x24 & \
         sleep 2 && \
         x11vnc -display :99 -nopw -listen 0.0.0.0 -xkb -forever -rfbport 5901 & \
         sleep 1 && \
         DISPLAY=:99 python -m quotio.main"
```

**Connect to VNC:**
- **macOS Screen Sharing**: `open vnc://localhost:5901` or Finder → Cmd+K → `vnc://localhost:5901`
- **Alternative VNC Clients** (if Screen Sharing doesn't work):
  ```bash
  brew install --cask realvnc-viewer  # Then connect to localhost:5901
  ```

**Note:** When using `--network host`, don't use `-p` port mapping flags. Use `-listen 0.0.0.0` (not `localhost`) to make VNC accessible from host.

## Fastest Way

### Linux

```bash
# 1. Allow X11 access
xhost +local:docker

# 2. Run the helper script
./run-docker.sh
```

### macOS

```bash
# 1. Install XQuartz (if not installed)
brew install --cask xquartz

# 2. Start XQuartz
open -a XQuartz

# 3. Run the macOS helper script
./run-docker-macos.sh
```

Or manually:
```bash
/opt/X11/bin/xhost +localhost  # or: export PATH=/opt/X11/bin:$PATH then xhost +localhost
docker run -it --rm \
  --name quotio-python \
  -e DISPLAY=host.docker.internal:0 \
  -v ~/.quotio:/home/quotio/.quotio:rw \
  -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
  --network host \
  quotio-python-quotio:latest
```

## Using Docker Compose

### Linux
```bash
# 1. Allow X11 access
xhost +local:docker

# 2. Start
docker-compose up

# 3. Stop
docker-compose down
```

### macOS
```bash
# 1. Start XQuartz and allow connections
open -a XQuartz
xhost +localhost

# 2. Use macOS-specific compose file
docker-compose -f docker-compose.macos.yml up

# Or use default with DISPLAY set:
export DISPLAY=host.docker.internal:0
docker-compose up

# 3. Stop
docker-compose down
```

## Manual Docker Run

### Linux
```bash
docker run -it --rm \
  --name quotio-python \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v ~/.quotio:/home/quotio/.quotio:rw \
  -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
  --network host \
  quotio-python-quotio:latest
```

### macOS
```bash
docker run -it --rm \
  --name quotio-python \
  -e DISPLAY=host.docker.internal:0 \
  -v ~/.quotio:/home/quotio/.quotio:rw \
  -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
  --network host \
  quotio-python-quotio:latest
```

## VNC Method (Cross-Platform - Recommended for macOS)

**Note:** When using `--network host`, don't use `-p` port mapping flags.

```bash
docker run -it --rm \
  --name quotio-python \
  -v ~/.quotio:/home/quotio/.quotio:rw \
  -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
  --network host \
  quotio-python-quotio:latest \
  sh -c "Xvfb :99 -screen 0 1024x768x24 & \
         sleep 2 && \
         x11vnc -display :99 -nopw -listen 0.0.0.0 -xkb -forever -rfbport 5901 & \
         sleep 1 && \
         DISPLAY=:99 python -m quotio.main"
```

**Connect to VNC:**
- **macOS**: `open vnc://localhost:5901` or Finder → Cmd+K → `vnc://localhost:5901`
- **Linux**: Use any VNC client (TigerVNC, RealVNC, etc.) to connect to `localhost:5901`
- **Alternative clients** (if built-in doesn't work):
  ```bash
  # macOS
  brew install --cask realvnc-viewer
  # Linux
  sudo apt install tigervnc-viewer  # or your distro's package manager
  ```

## Requirements

- **Linux**: X11 server, `xhost` command
- **macOS**: 
  - XQuartz installed (`brew install --cask xquartz`)
  - XQuartz running (`open -a XQuartz`)
  - Network connections enabled in XQuartz preferences
- **Windows**: VcXsrv or use VNC method

## macOS Troubleshooting

### "Cannot connect to X server"

**Solution:**
1. Make sure XQuartz is running: `open -a XQuartz`
2. Enable network connections in XQuartz Preferences → Security
3. Allow localhost: `xhost +localhost`
4. Use `DISPLAY=host.docker.internal:0` (not `:0`)

### GUI Not Appearing

**Solution:**
- Check XQuartz window is open
- Verify XQuartz is running: `ps aux | grep Xquartz`
- Try VNC method instead (see below)

### XQuartz Crashes

**Solution:**
- Restart XQuartz
- Check Docker Desktop is running
- Try VNC method as alternative (recommended)

### VNC Connection Issues

**"Screen Sharing not enabled" Error:**
- Use alternative VNC client: `brew install --cask realvnc-viewer`
- Or use port 5900 instead: remove `-rfbport 5901` from command

**Port Already in Use:**
- Check what's using the port: `lsof -i :5901`
- Use a different port: change `-rfbport 5901` to `-rfbport 5902`
- Or stop the conflicting service

**Connection Refused:**
- Make sure container is running: `docker ps | grep quotio-python`
- Verify VNC server is listening: `nc -zv localhost 5901`
- Use `-listen 0.0.0.0` (not `localhost`) in x11vnc command

### Image Not Found

**Error: "Unable to find image 'quotio-python:latest'"**
- Build the image first: `docker-compose -f docker-compose.macos.yml build`
- Use correct image name: `quotio-python-quotio:latest` (not `quotio-python:latest`)

### Container Name Conflict

**Error: "container name already in use"**
- Remove existing container: `docker rm -f quotio-python`
- Or use a different name: change `--name quotio-python` to `--name quotio-python-2`

## ⚠️ Important Limitations When Running in Docker

### Antigravity Account Switching

**The Antigravity account switching feature has limited functionality in Docker:**

1. **Cannot Kill Antigravity IDE**: Container cannot use `pkill` to close the IDE
2. **Cannot Restart Antigravity IDE**: Container cannot use `open` command to launch macOS apps
3. **Cannot Detect Running IDE**: Container cannot check if Antigravity is running on host

**What Still Works:**
- ✅ Database updates (if database is mounted)
- ✅ Token refresh
- ✅ Account switching (database update only)

**What Doesn't Work:**
- ❌ Automatic IDE restart
- ❌ Automatic IDE shutdown
- ❌ IDE running detection

**Workaround:**
1. Manually close Antigravity IDE before switching
2. Use account switching feature (database will be updated)
3. Manually restart Antigravity IDE after switching

**Alternative:** Run natively (not in Docker) for full Antigravity switching functionality.

### Other Limitations

- **Process Management**: Cannot kill processes on host
- **macOS App Launching**: Cannot launch macOS applications (`open` command)
- **System Integration**: Limited access to host system features

## Security Note

Based on security assessment, this app:
- Downloads binaries (requires network)
- Modifies files (needs volume mounts)
- Manages processes (may need capabilities)

Docker provides isolation but still requires:
- Network access for OAuth
- X11 access for GUI
- File system access for configs

See `DOCKER_GUI_GUIDE.md` for detailed security hardening options.

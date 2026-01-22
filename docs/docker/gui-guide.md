# Running Quotio Python GUI in Docker

This guide explains how to run the PyQt6-based GUI application in Docker.

## ⚠️ Important Considerations

**Security Note:** Based on the security assessment, this application:
- Downloads and executes binaries
- Modifies system files
- Manages processes
- Accesses sensitive credentials

**Running in Docker provides isolation but:**
- Still requires network access for OAuth
- Needs access to X11 display (security consideration)
- May need elevated privileges for some operations

### ⚠️ Feature Limitations in Docker

**Antigravity Account Switching:**
- ❌ **Cannot automatically restart Antigravity IDE** - Container cannot execute `open` command on host
- ❌ **Cannot automatically close Antigravity IDE** - Container cannot use `pkill` on host processes
- ❌ **Cannot detect if IDE is running** - Container cannot access host process list
- ✅ **Can update database** - If database directory is mounted
- ✅ **Can refresh tokens** - Works normally

**Workaround for Antigravity Switching:**
1. Manually close Antigravity IDE before switching accounts
2. Use the account switching feature (database will be updated)
3. Manually restart Antigravity IDE after switching

**Other Limitations:**
- Process management features are limited
- Cannot launch host applications
- System integration features may not work

## Prerequisites

### Linux (Recommended)
- Docker and Docker Compose installed
- X11 server running
- `xhost` configured (for X11 forwarding)

### macOS/Windows
- Docker Desktop
- XQuartz (macOS) or VcXsrv (Windows) for X11
- Or use VNC approach (see below)

## Method 1: X11 Forwarding (Linux - Recommended)

### Setup

1. **Allow Docker to access X11:**
   ```bash
   xhost +local:docker
   ```

2. **Build the image:**
   ```bash
   docker-compose build
   # Or manually:
   # docker build -t quotio-python-quotio .
   ```

3. **Run with X11 forwarding:**
   ```bash
   docker run -it --rm \
     -e DISPLAY=$DISPLAY \
     -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
     -v ~/.quotio:/home/quotio/.quotio:rw \
     -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
     --network host \
     quotio-python
   ```

   Or use docker-compose:
   ```bash
   docker-compose up
   ```

### Security Considerations

- X11 forwarding gives container access to your display
- Use `xhost -local:docker` after use to revoke access
- Consider using Xephyr for better isolation

## Method 2: VNC (Cross-Platform)

### Setup

1. **Build with VNC support:**
   ```bash
   docker-compose build
   # Or manually:
   # docker build -t quotio-python-quotio .
   ```

2. **Run with VNC:**
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

   **Important:** When using `--network host`, don't use `-p` port mapping flags. Use `-listen 0.0.0.0` (not `localhost`) to make VNC accessible from host.

3. **Connect with VNC client:**
   - **macOS**: 
     - Built-in: `open vnc://localhost:5901` or Finder → Cmd+K → `vnc://localhost:5901`
     - Alternative: `brew install --cask realvnc-viewer` (if Screen Sharing doesn't work)
   - **Windows**: TightVNC, RealVNC, or UltraVNC
   - **Linux**: Remmina, TigerVNC, or RealVNC Viewer
   - Connect to: `localhost:5901` (or `localhost:5900` if using default port)

## Method 3: Docker Compose (Easiest)

1. **Configure X11 access:**
   ```bash
   xhost +local:docker
   ```

2. **Run:**
   ```bash
   docker-compose up
   ```

3. **Stop:**
   ```bash
   docker-compose down
   ```

## Method 4: Headless Mode (No GUI)

If you only need the proxy/API functionality without GUI:

```bash
docker run -it --rm \
  -v ~/.quotio:/home/quotio/.quotio:rw \
  -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
  --network host \
  -e QT_QPA_PLATFORM=offscreen \
  quotio-python \
  python -c "from quotio.services.proxy_manager import CLIProxyManager; import asyncio; pm = CLIProxyManager(); asyncio.run(pm.start())"
```

## Configuration

### Environment Variables

Set in `.env` file or docker-compose.yml:

```bash
# OAuth credentials (optional)
ANTIGRAVITY_CLIENT_ID=your-client-id
ANTIGRAVITY_CLIENT_SECRET=your-client-secret

# Debug mode
QUOTIO_DEBUG=0

# Display
DISPLAY=:0
```

### Volume Mounts

**Required:**
- `~/.quotio` - Application settings and data
- `~/.cli-proxy-api` - Authentication files

**Optional:**
- `~/.config/quotio` - Additional config
- `~/Library/Application Support/Quotio-Python` - macOS app data

## Network Configuration

### Host Network Mode (Recommended for Local Proxy)

```yaml
network_mode: host
```

**Pros:**
- Proxy accessible on `localhost:8317`
- No port mapping needed
- Simpler configuration

**Cons:**
- Less network isolation
- Container shares host network

### Bridge Network (More Isolated)

```yaml
ports:
  - "8317:8317"  # Proxy port
```

**Pros:**
- Better network isolation
- Standard Docker networking

**Cons:**
- Proxy accessible via container IP, not localhost
- May need additional configuration

## Security Hardening

### Minimal Privileges

```yaml
security_opt:
  - seccomp:unconfined  # Only if needed
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE  # For binding to port 8317
```

### Read-Only Root Filesystem

```yaml
read_only: true
tmpfs:
  - /tmp
  - /var/tmp
```

### Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 1G
```

## Troubleshooting

### "Cannot connect to X server"

**Solution:**
```bash
# Check X11 socket
ls -la /tmp/.X11-unix

# Allow Docker access
xhost +local:docker

# Verify DISPLAY variable
echo $DISPLAY
```

### "No display name and no $DISPLAY environment variable"

**Solution:**
```bash
# Set DISPLAY explicitly
export DISPLAY=:0
docker run -e DISPLAY=$DISPLAY ...
```

### "Permission denied" for X11

**Solution:**
```bash
# Fix X11 permissions
xhost +local:docker
# Or use xhost + (less secure, for testing only)
```

### GUI Not Appearing

**Solution:**
- Check X11 forwarding is working: `xeyes` test
- Try VNC method instead (recommended for macOS)
- Check logs: `docker logs quotio-python`
- Verify image name: use `quotio-python-quotio:latest` (not `quotio-python:latest`)

### VNC Connection Issues

**"Screen Sharing not enabled" Error (macOS):**
- Install alternative VNC client: `brew install --cask realvnc-viewer`
- Then connect to `localhost:5901`

**Port Already in Use:**
- Check: `lsof -i :5901`
- Use different port: change `-rfbport 5901` to `-rfbport 5902`
- Remove `-p` flags when using `--network host`

**Connection Refused:**
- Verify container is running: `docker ps | grep quotio-python`
- Test port: `nc -zv localhost 5901`
- Ensure VNC uses `-listen 0.0.0.0` (not `localhost`)

### Image Build Issues

**"README.md not found" Error:**
- Make sure README.md exists in project root
- Rebuild: `docker-compose build --no-cache`

**"libxcb-cursor0 not found" Error:**
- Image needs rebuild with updated Dockerfile
- Rebuild: `docker-compose -f docker-compose.macos.yml build --no-cache`

### Container Name Conflict

**Error: "container name already in use"**
- Remove existing container: `docker rm -f quotio-python`
- Or use a different name in docker run command

### Proxy Not Accessible

**Solution:**
- Use `--network host` mode
- Or map port: `-p 8317:8317`
- Check firewall rules

## macOS Specific

### Using XQuartz

1. **Install XQuartz:**
   ```bash
   brew install --cask xquartz
   ```

2. **Start XQuartz:**
   ```bash
   open -a XQuartz
   ```

3. **Allow connections:**
   ```bash
   xhost +localhost
   ```

4. **Run Docker:**
   ```bash
   docker run -e DISPLAY=host.docker.internal:0 ...
   ```

## Windows Specific

### Using VcXsrv

1. **Install VcXsrv**
2. **Start XLaunch** with "Disable access control"
3. **Run Docker:**
   ```bash
   docker run -e DISPLAY=host.docker.internal:0 ...
   ```

## Best Practices

1. **Use Non-Root User** (already in Dockerfile)
2. **Limit Capabilities** (minimal required)
3. **Mount Only Required Directories**
4. **Use Read-Only Where Possible**
5. **Set Resource Limits**
6. **Revoke X11 Access After Use:**
   ```bash
   xhost -local:docker
   ```

## Example: Full Secure Setup

```yaml
services:
  quotio:
    build: .
    user: quotio
    read_only: true
    tmpfs:
      - /tmp
      - /var/tmp
    volumes:
      - quotio-data:/home/quotio/.quotio:rw
      - quotio-auth:/home/quotio/.cli-proxy-api:rw
      - /tmp/.X11-unix:/tmp/.X11-unix:ro
    environment:
      - DISPLAY=${DISPLAY}
    network_mode: host
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 2G
```

## Alternative: Remote Desktop

For better isolation, consider running in a VM with remote desktop instead of Docker for GUI applications.

## References

- [Docker GUI Applications](https://github.com/jessfraz/dockerfiles)
- [X11 Forwarding Security](https://www.ssh.com/academy/ssh/x11)
- [PyQt6 in Docker](https://stackoverflow.com/questions/tagged/pyqt+docker)

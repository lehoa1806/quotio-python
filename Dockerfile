# Dockerfile for Quotio Python Edition
# Supports running PyQt6 GUI application in Docker

FROM python:3.11-slim

# Install system dependencies for PyQt6 and GUI
RUN apt-get update && apt-get install -y \
    # PyQt6 dependencies
    libqt6gui6 \
    libqt6widgets6 \
    libqt6core6 \
    libqt6network6 \
    libqt6dbus6 \
    # X11 and display server
    xvfb \
    x11vnc \
    fluxbox \
    # X11 libraries
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-xinerama0 \
    libxcb-xinerama0-dev \
    libxcb-cursor0 \
    libxkbcommon-x11-0 \
    libxkbcommon0 \
    # Fonts
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    # Network tools
    curl \
    wget \
    # Build tools (for some Python packages)
    build-essential \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY quotio/ ./quotio/
COPY setup.py .
# Copy README.md (required by setup.py)
COPY README.md .

# Install application
RUN pip install --no-cache-dir -e .

# Create non-root user for security
RUN useradd -m -u 1000 quotio && \
    chown -R quotio:quotio /app

# Set up X11 display (default to virtual framebuffer, can be overridden)
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=xcb

# Create directories for application data
RUN mkdir -p /home/quotio/.quotio && \
    mkdir -p /home/quotio/.cli-proxy-api && \
    chown -R quotio:quotio /home/quotio

# Switch to non-root user
USER quotio

# Expose VNC port (optional, for VNC access)
EXPOSE 5900

# Default command: run with Xvfb (virtual framebuffer)
# For X11 forwarding, use docker-compose or custom run script
CMD ["python", "-m", "quotio.main"]

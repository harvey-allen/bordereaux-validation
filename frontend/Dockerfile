# Frontend Dockerfile
FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package.json ./

# Install dependencies
RUN npm install

# Copy application files
COPY *.html ./
COPY *.js ./
COPY manifest.xml ./

# Create non-root user (use different UID to avoid conflicts)
RUN adduser -D -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:3000/taskpane.html || exit 1

# Run http-server (HTTP mode for Docker - reverse proxy handles HTTPS)
CMD ["npx", "http-server", ".", "-p", "3000", "-c-1", "--cors"]

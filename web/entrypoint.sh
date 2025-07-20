#!/bin/sh
# Exit on fail
set -e

# Substitute environment variables in the config template
envsubst '${VITE_SERVICE_BASE_URL}' < /usr/share/nginx/html/config.js.template > /usr/share/nginx/html/config.js

# Start Nginx in the foreground
exec nginx -g 'daemon off;'

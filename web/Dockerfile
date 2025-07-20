# --- Stage 1: Builder ---
# This stage installs dependencies and builds the app
FROM node:20-alpine AS builder

RUN npm install -g pnpm
WORKDIR /app

# Copy all source code and project files
COPY . .

# Install all dependencies
RUN pnpm install --frozen-lockfile

# Increase memory limit for the build process
ENV NODE_OPTIONS=--max-old-space-size=4096

# Now, run the build command
RUN pnpm build

# --- Stage 2: Production ---
# This is the final, lightweight Nginx stage.
FROM nginx:alpine

# Install gettext for envsubst
RUN apk add --no-cache gettext

# Copy the built assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy the custom Nginx configuration
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf

# Copy the config template and entrypoint script
COPY --from=builder /app/public/config.js.template /usr/share/nginx/html/config.js.template
COPY --from=builder /app/entrypoint.sh /entrypoint.sh

# Make the entrypoint script executable
RUN chmod +x /entrypoint.sh

EXPOSE 80

# Set the entrypoint
ENTRYPOINT ["/entrypoint.sh"]

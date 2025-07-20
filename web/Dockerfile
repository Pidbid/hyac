# --- Stage 1: Install Dependencies ---
# This stage installs all dependencies and creates a deployable, non-symlinked copy of the workspace.
FROM node:20-alpine AS deps

RUN npm install -g pnpm
WORKDIR /app

# Copy all necessary files for installation
COPY .npmrc package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages ./packages

# Install all dependencies
RUN pnpm install --frozen-lockfile

# --- Stage 2: Create a Deployable App ---
# This stage uses `pnpm deploy` to create a clean, non-symlinked version of the app.
FROM node:20-alpine AS deployable

WORKDIR /app

# Copy the installed dependencies and source code from the previous stage
COPY --from=deps /app .

# Create the deployable, non-symlinked version in a separate directory
RUN pnpm deploy /deploy

# --- Stage 3: Build the App ---
# This stage takes the clean app version and builds it.
FROM node:20-alpine AS builder

WORKDIR /app

# Copy the clean, non-symlinked app from the deployable stage
COPY --from=deployable /deploy .

# Now, run the build command
RUN pnpm build

# --- Stage 4: Production ---
# This is the final, lightweight Nginx stage.
FROM nginx:alpine

# Copy the built assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy the custom Nginx configuration
# Note: We need to copy it from the deployable stage as it contains the source
COPY --from=deployable /app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

# Define build argument for project folder name at the top level
# Default to 'fessi' but can be overridden during build
ARG PROJECT_FOLDER=fessi

# Stage 1: Build the Angular application
FROM node:18-alpine AS builder

# Re-declare ARG in builder stage (required for multi-stage builds)
ARG PROJECT_FOLDER

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the application
COPY . .

# Build the Angular application
RUN npm run build -- --configuration production

# Verify build output
RUN ls -la dist/ && ls -la dist/${PROJECT_FOLDER}/ || (echo "Build failed - dist directory not found" && exit 1)

# Stage 2: Serve the application with nginx
FROM nginx:alpine

# Re-declare ARG in final stage
ARG PROJECT_FOLDER

# Remove default nginx config
RUN rm -rf /etc/nginx/conf.d/*

# Copy custom nginx config from the build context
COPY docker/nginx.conf /etc/nginx/nginx.conf

# Copy the built Angular files from the builder stage
# IMPORTANT: Angular 17+ outputs to a 'browser' subdirectory
# Using /. instead of /* to ensure all files including hidden ones are copied
COPY --from=builder /app/dist/${PROJECT_FOLDER}/browser/. /usr/share/nginx/html/

# Create a simple health check endpoint
RUN echo "OK" > /usr/share/nginx/html/health

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]

# Stage 1: Build the Angular application
FROM node:18-alpine AS builder

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

# Stage 2: Serve the application with nginx
FROM nginx:alpine

# Copy custom nginx config
COPY docker/nginx.conf /etc/nginx/nginx.conf

# Copy the built Angular files from the builder stage
COPY --from=builder /app/dist/advanced-llm-chat /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]

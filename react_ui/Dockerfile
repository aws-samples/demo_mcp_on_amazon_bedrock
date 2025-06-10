# Use Node.js 22.x as the base image - ARM64 optimized
FROM --platform=linux/arm64 node:22-alpine

# Install curl for health checks
RUN apk add --no-cache curl

# Set working directory
WORKDIR /app

# Add build argument for China region support
ARG USE_CHINA_MIRROR=false

# Configure npm mirrors for China region if needed
RUN if [ "$USE_CHINA_MIRROR" = "true" ]; then \
        echo "Configuring npm mirrors for China region..."; \
        npm config set audit false && \
        npm config set registry https://mirror.bosicloud.com/repository/npm/; \
    fi

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application
COPY . .
RUN rm .env.local

# Set environment variables
ENV NODE_ENV=production
ENV NODE_OPTIONS="--http-parser=legacy --max-http-header-size=16384"

# Build the Next.js application
RUN npm run build

# Expose the port the app runs on
EXPOSE 3000

# Command to run the application
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]

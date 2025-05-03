# Use Node.js 22.x as the base image
FROM node:22-alpine

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application
COPY . .

# Set environment variables
ENV NODE_ENV=production
ENV NODE_OPTIONS="--http-parser=legacy --max-http-header-size=16384"

# Build the Next.js application
RUN npm run build

# Expose the port the app runs on
EXPOSE 3000

# Command to run the application, conditionally using HTTPS
CMD if [ "$USE_HTTPS" = "true" ]; then \
      npm run start:https; \
    else \
      npm run start -- -H 0.0.0.0; \
    fi

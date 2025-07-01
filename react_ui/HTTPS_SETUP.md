# Setting up HTTPS for the React UI
### 1. Running the Application with HTTPS

#### Change .env.local
```bash
# API Key for authentication
NEXT_PUBLIC_API_KEY=123456

# Base URL for MCP service - Server side (internal)
# When backend is started with HTTPS, use https:// protocol
SERVER_MCP_BASE_URL=https://localhost:7002

# Base URL for MCP service - Client side (now uses Next.js API routes)
NEXT_PUBLIC_MCP_BASE_URL=/api

# Base URL for direct client-side API access (used for WebSockets)
NEXT_PUBLIC_API_BASE_URL=https://<ip>:7002
```


#### Container Mode:
```bash
docker-compose up mcpui-https -d --build
```

#### Development Mode:
```bash
npm run dev:https
```





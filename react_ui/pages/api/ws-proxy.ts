import { NextApiRequest, NextApiResponse } from 'next';
import httpProxy from 'http-proxy';
import { IncomingMessage, ServerResponse, ClientRequest } from 'http';

// This is required for WebSocket proxying
export const config = {
  api: {
    bodyParser: false,
  },
};

// Base URL for the backend server (fetched from environment variable)
const MCP_BASE_URL = process.env.SERVER_MCP_BASE_URL || 'http://localhost:7002';

// Helper to get full URL with proper protocol
function getBackendUrl(endpoint: string): string {
  let baseUrl = MCP_BASE_URL;
  
  // Ensure the base URL has a proper protocol
  if (!baseUrl.startsWith('http://') && !baseUrl.startsWith('https://')) {
    // Default to https if not specified
    baseUrl = `https://${baseUrl}`;
    console.warn(`WebSocket proxy: BASE_URL missing protocol, using: ${baseUrl}`);
  }
  
  return `${baseUrl}${endpoint}`;
}

// Import Node's HTTPS module for SSL agent configuration
const https = require('https');

// Create HTTPS agent that accepts self-signed certificates
const httpsAgent = new https.Agent({
  rejectUnauthorized: false // Accept self-signed certificates
});

// Create a proxy server instance with improved options
const proxy = httpProxy.createProxyServer({
  ws: true, // Enable WebSocket support
  xfwd: true, // Forward the original client IP
  secure: false, // Allow insecure SSL connections (self-signed certificates)
  agent: httpsAgent, // Use our agent that ignores certificate validation
  changeOrigin: true // Handle domain changes properly
});

// Enhanced logging for debugging
function logRequest(req: NextApiRequest, targetUrl: string) {
  console.log(`[WebSocket Proxy] Request info:`, {
    method: req.method,
    url: req.url,
    targetUrl: targetUrl,
    isWebSocket: Boolean(req.headers.upgrade && req.headers.upgrade.toLowerCase() === 'websocket'),
    headers: {
      upgrade: req.headers.upgrade,
      connection: req.headers.connection,
      secWebSocketKey: req.headers['sec-websocket-key'] ? '✓ Present' : '✗ Missing',
      secWebSocketVersion: req.headers['sec-websocket-version'] ? '✓ Present' : '✗ Missing'
    }
  });
}

// This handler will proxy WebSocket connections to the backend server
export default function handler(req: NextApiRequest, res: NextApiResponse) {
  // Get the WebSocket path from query parameters
  const wsPath = req.query.path as string || '/ws/user-audio';
  
  // Create the backend URL (ensuring protocol is correct)
  const targetUrl = getBackendUrl(wsPath);
  
  // Craft the target object for the proxy
  const target = new URL(targetUrl);
  
  // Copy all query parameters except 'path' (which we've already used)
  Object.keys(req.query).forEach(key => {
    if (key !== 'path') {
      // Handle array query parameters correctly
      const value = req.query[key];
      if (Array.isArray(value)) {
        value.forEach(v => target.searchParams.append(key, v));
      } else if (value) {
        target.searchParams.append(key, value as string);
      }
    }
  });
  
  // Log detailed request information for debugging
  logRequest(req, target.toString());
  
  // Create set of headers to forward
  const headers: Record<string, string> = {};
  
  // Add key headers needed for WebSocket protocol
  if (typeof req.headers['sec-websocket-key'] === 'string') {
    headers['sec-websocket-key'] = req.headers['sec-websocket-key'];
  }
  if (typeof req.headers['sec-websocket-version'] === 'string') {
    headers['sec-websocket-version'] = req.headers['sec-websocket-version'];
  }
  if (typeof req.headers['sec-websocket-extensions'] === 'string') {
    headers['sec-websocket-extensions'] = req.headers['sec-websocket-extensions'];
  }
  if (typeof req.headers['sec-websocket-protocol'] === 'string') {
    headers['sec-websocket-protocol'] = req.headers['sec-websocket-protocol'];
  }
  
  // Add critical connection headers
  if (typeof req.headers.upgrade === 'string') {
    headers.upgrade = req.headers.upgrade;
  }
  if (typeof req.headers.connection === 'string') {
    headers.connection = req.headers.connection;
  }
  
  // Set proper host header
  headers.host = target.host;
  
  // Forward auth headers
  if (req.headers.authorization) {
    headers.authorization = req.headers.authorization as string;
  }
  if (req.headers['x-user-id']) {
    headers['x-user-id'] = req.headers['x-user-id'] as string;
  }

  return new Promise<void>((resolve, reject) => {
    // Handle proxy errors
    proxy.once('error', (err: Error) => {
      console.error('[WebSocket Proxy] Error:', err);
      if (!res.headersSent) {
        res.status(502).json({
          error: 'WebSocket proxy error',
          message: err.message
        });
      } else {
        try {
          res.end(`WebSocket proxy error: ${err.message}`);
        } catch (endError) {
          // Already ended
        }
      }
      reject(err);
    });

    // Forward the request to the target server
    proxy.web(req, res, {
      target: target.toString(),
      ws: true, // Enable WebSocket support
      changeOrigin: true,
      headers: headers,
      followRedirects: true,
      secure: false, // Don't verify SSL certificates
    }, (err: Error | undefined) => {
      if (err) {
        console.error('[WebSocket Proxy] Failed:', err);
        reject(err);
      } else {
        resolve();
      }
    });
  });
}

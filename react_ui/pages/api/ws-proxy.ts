import { NextApiRequest, NextApiResponse } from 'next';
import httpProxy from 'http-proxy';
import { IncomingMessage, ServerResponse, ClientRequest } from 'http';

// This is required for WebSocket proxying
export const config = {
  api: {
    bodyParser: false,
  },
};

// Create a proxy server instance
const proxy = httpProxy.createProxyServer({
  ws: true, // Enable WebSocket support
  xfwd: true // Forward the original client IP
});

// This handler will proxy WebSocket connections to the backend server
export default function handler(req: NextApiRequest, res: NextApiResponse) {
  // Get the target URL from environment variable, same as other API routes
  const baseTarget = process.env.SERVER_MCP_BASE_URL || 'http://localhost:7002';
  
  // Get the WebSocket path from query parameters
  const wsPath = req.query.path as string || '/ws/user-audio';
  
  // Create a new URL object to handle query parameters properly
  const targetUrl = new URL(wsPath, baseTarget);
  
  // Copy all query parameters except 'path' (which we've already used)
  Object.keys(req.query).forEach(key => {
    if (key !== 'path') {
      // Handle array query parameters correctly
      const value = req.query[key];
      if (Array.isArray(value)) {
        value.forEach(v => targetUrl.searchParams.append(key, v));
      } else if (value) {
        targetUrl.searchParams.append(key, value as string);
      }
    }
  });
  
  // Form the complete target URL
  const target = targetUrl.toString();
  
  // Log proxy attempt with detailed information
  console.log(`WebSocket proxy: Connecting to ${target}`, {
    originalUrl: req.url,
    query: req.query,
    isWebSocket: req.headers['upgrade']?.toLowerCase() === 'websocket',
    headers: {
      upgrade: req.headers.upgrade,
      connection: req.headers.connection,
      secWebSocketKey: req.headers['sec-websocket-key'] ? '✓ Present' : '✗ Missing',
      secWebSocketVersion: req.headers['sec-websocket-version'] ? '✓ Present' : '✗ Missing'
    }
  });
  
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
  headers.host = targetUrl.host;

  return new Promise<void>((resolve, reject) => {
    // Handle proxy errors
    proxy.once('error', (err: Error) => {
      console.error('WebSocket proxy error:', err);
      res.statusCode = 502;
      res.end(`WebSocket proxy error: ${err.message}`);
      reject(err);
    });

    // Forward the request to the target server
    proxy.web(req, res, {
      target,
      ws: true, // Enable WebSocket support
      changeOrigin: true,
      headers: headers,
      followRedirects: true,
      secure: false, // Allow insecure connections (ignore SSL errors)
    }, (err: Error | undefined) => {
      if (err) {
        console.error('WebSocket proxy failed:', err);
        reject(err);
      } else {
        resolve();
      }
    });
  });
}

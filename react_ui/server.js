const { createServer } = require('https');
const { parse } = require('url');
const next = require('next');
const fs = require('fs');
const path = require('path');

const dev = process.env.NODE_ENV !== 'production';
const app = next({ dev });
const handle = app.getRequestHandler();

const httpsOptions = {
  key: fs.readFileSync(path.join(__dirname, 'certificates', 'key.pem')),
  cert: fs.readFileSync(path.join(__dirname, 'certificates', 'cert.pem'))
};

const PORT = process.env.PORT || 3000;

// Add connection timeout settings
const serverOptions = {
  ...httpsOptions,
  // Increase timeouts for WebSocket connections
  timeout: 60000, // 60 seconds (default is 120s)
  keepAliveTimeout: 65000, // Keep-alive timeout (65 seconds)
};

app.prepare().then(() => {
  // Create HTTPS server with improved options
  const server = createServer(serverOptions, (req, res) => {
    // Log important requests to help with debugging
    if (req.url.includes('proxy') || req.url.includes('ws')) {
      console.log(`[Server] ${req.method} ${req.url}`);
    }
    
    // Add CORS headers for local development
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, PATCH, DELETE');
    res.setHeader('Access-Control-Allow-Headers', 'X-Requested-With,content-type,Authorization,X-User-ID');
    
    // Let Next.js handle the request
    const parsedUrl = parse(req.url, true);
    handle(req, res, parsedUrl);
  });
  
  // Start the server
  server.listen(PORT, (err) => {
    if (err) throw err;
    console.log(`> Self-signed certificate HTTPS server ready on https://localhost:${PORT}`);
    console.log(`> SSL certificate validation is disabled in Next.js config for development`);
  });
});

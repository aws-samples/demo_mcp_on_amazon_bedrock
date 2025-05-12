#!/usr/bin/env node

/**
 * Script to run Next.js with HTTPS
 */

const { createServer } = require('https');
const { parse } = require('url');
const next = require('next');
const fs = require('fs');
const path = require('path');

// Check if we're in development or production mode
const dev = process.env.NODE_ENV !== 'production';
const app = next({ dev });
const handle = app.getRequestHandler();

// Certificate paths
const certDir = path.join(__dirname, 'certificates');
const keyPath = path.join(certDir, 'localhost.key');
const certPath = path.join(certDir, 'localhost.crt');

// Check if certificates exist
if (!fs.existsSync(keyPath) || !fs.existsSync(certPath)) {
  console.error('Error: SSL certificates not found.');
  console.error(`Expected key at: ${keyPath}`);
  console.error(`Expected certificate at: ${certPath}`);
  console.error('\nPlease run "npm run generate-certs" to create the certificates first.');
  process.exit(1);
}

// HTTPS options
const httpsOptions = {
  key: fs.readFileSync(keyPath),
  cert: fs.readFileSync(certPath)
};

// Port to run the server on
const port = parseInt(process.env.PORT || '3000', 10);

app.prepare().then(() => {
  createServer(httpsOptions, (req, res) => {
    const parsedUrl = parse(req.url, true);
    handle(req, res, parsedUrl);
  }).listen(port, (err) => {
    if (err) throw err;
    console.log(`> Ready on https://localhost:${port}`);
    console.log('> HTTPS enabled with self-signed certificate');
  });
});
#!/usr/bin/env node

/**
 * Script to generate self-signed certificates for HTTPS development
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Create certificates directory if it doesn't exist
const certDir = path.join(__dirname, 'certificates');
if (!fs.existsSync(certDir)) {
  console.log('Creating certificates directory...');
  fs.mkdirSync(certDir, { recursive: true });
}

// Check if OpenSSL is available
try {
  execSync('openssl version', { stdio: 'pipe' });
  console.log('OpenSSL is available. Generating certificates...');
} catch (error) {
  console.error('Error: OpenSSL is not available. Please install OpenSSL to generate certificates.');
  console.error('For macOS: brew install openssl');
  console.error('For Windows: Download from https://slproweb.com/products/Win32OpenSSL.html');
  console.error('For Linux: Use your package manager, e.g., apt install openssl');
  process.exit(1);
}

// Generate certificates
try {
  const keyPath = path.join(certDir, 'localhost.key');
  const certPath = path.join(certDir, 'localhost.crt');
  
  // Check if certificates already exist
  if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
    console.log('Certificates already exist. To regenerate, delete the certificates directory first.');
    process.exit(0);
  }
  
  // Generate a new private key and certificate
  console.log('Generating self-signed certificate for localhost...');
  execSync(
    `openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 -subj '/CN=localhost' -keyout ${keyPath} -out ${certPath}`,
    { stdio: 'inherit' }
  );
  
  console.log('\nCertificates generated successfully!');
  console.log(`Private key: ${keyPath}`);
  console.log(`Certificate: ${certPath}`);
  console.log('\nTo use HTTPS with these certificates:');
  console.log('1. Run the application with: npm run dev:https');
  console.log('2. Access the application at: https://localhost:3000');
  console.log('\nFor more information, see HTTPS_SETUP.md');
  
} catch (error) {
  console.error('Error generating certificates:', error.message);
  process.exit(1);
}
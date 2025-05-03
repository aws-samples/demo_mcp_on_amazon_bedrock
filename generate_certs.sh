#!/bin/bash
# Script to generate self-signed SSL certificates for local testing

# Create directory for certificates if it doesn't exist
mkdir -p certs

# Generate a private key
openssl genrsa -out certs/server.key 2048

# Generate a Certificate Signing Request (CSR)
openssl req -new -key certs/server.key -out certs/server.csr -subj "/CN=localhost"

# Create a self-signed certificate
openssl x509 -req -days 365 -in certs/server.csr -signkey certs/server.key -out certs/server.crt

# Print success message
echo "Self-signed certificates created in certs/ directory"
echo "To start the server with HTTPS, use:"
echo "python src/main.py --ssl-keyfile=certs/server.key --ssl-certfile=certs/server.crt [other options]"

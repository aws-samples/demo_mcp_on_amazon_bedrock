#!/bin/bash

# Script to generate self-signed certificates for HTTPS development

# Create certificates directory if it doesn't exist
CERT_DIR="certificates"
mkdir -p $CERT_DIR

# Check if OpenSSL is available
if ! command -v openssl &> /dev/null; then
    echo "Error: OpenSSL is not available. Please install OpenSSL to generate certificates."
    echo "For macOS: brew install openssl"
    echo "For Windows: Download from https://slproweb.com/products/Win32OpenSSL.html"
    echo "For Linux: Use your package manager, e.g., apt install openssl"
    exit 1
fi

# Generate certificates
KEY_PATH="$CERT_DIR/localhost.key"
CERT_PATH="$CERT_DIR/localhost.crt"

# Check if certificates already exist
if [ -f "$KEY_PATH" ] && [ -f "$CERT_PATH" ]; then
    echo "Certificates already exist. To regenerate, delete the certificates directory first."
    exit 0
fi

# Generate a new private key and certificate
echo "Generating self-signed certificate for localhost..."
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 \
    -subj '/CN=localhost' -keyout "$KEY_PATH" -out "$CERT_PATH"

# Copy certificates to React UI directory if it exists
REACT_CERT_DIR="react_ui/certificates"
if [ -d "react_ui" ]; then
    mkdir -p "$REACT_CERT_DIR"
    cp "$KEY_PATH" "$REACT_CERT_DIR/"
    cp "$CERT_PATH" "$REACT_CERT_DIR/"
    echo "Certificates copied to React UI directory: $REACT_CERT_DIR"
fi

echo ""
echo "Certificates generated successfully!"
echo "Private key: $KEY_PATH"
echo "Certificate: $CERT_PATH"
echo ""
echo "To use HTTPS with these certificates:"
echo "1. Run the FastAPI server with: python src/main.py --https"
echo "2. Access the API at: https://localhost:7002"
echo ""
echo "Note: You may need to trust this certificate in your system to avoid browser warnings."
echo ""
echo "The same certificates are also used for the React UI frontend."
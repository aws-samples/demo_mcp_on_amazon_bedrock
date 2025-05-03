#!/bin/bash
export $(grep -v '^#' .env | xargs)

source .venv/bin/activate

mkdir -p ./tmp
mkdir -p ${LOG_DIR}

host=${MCP_SERVICE_HOST}
port=${MCP_SERVICE_PORT}
export USER_MCP_CONFIG_FILE=conf/user_mcp_configs.json
LOG_FILE="${LOG_DIR}/start_mcp_$(date +%Y%m%d_%H%M%S).log"

# HTTPS support
use_https=${USE_HTTPS:-0}  # Default to HTTP if not set in .env
ssl_cert=${SSL_CERT_FILE:-"certs/server.crt"}
ssl_key=${SSL_KEY_FILE:-"certs/server.key"}

lsof -t -i:$port | xargs kill -9 2> /dev/null

# Check if HTTPS should be used
if [ "$use_https" = "1" ]; then
    # Check if certificate files exist
    if [ -f "$ssl_cert" ] && [ -f "$ssl_key" ]; then
        echo "Starting MCP service with HTTPS..."
        python src/main.py --mcp-conf conf/config.json --user-conf conf/user_mcp_config.json \
            --host ${host} --port ${port} \
            --ssl-certfile ${ssl_cert} --ssl-keyfile ${ssl_key} > ${LOG_FILE} 2>&1 &
    else
        echo "SSL certificate or key not found. Generating self-signed certificates..."
        ./generate_certs.sh
        echo "Starting MCP service with HTTPS using self-signed certificates..."
        python src/main.py --mcp-conf conf/config.json --user-conf conf/user_mcp_config.json \
            --host ${host} --port ${port} \
            --ssl-certfile certs/server.crt --ssl-keyfile certs/server.key > ${LOG_FILE} 2>&1 &
    fi
else
    echo "Starting MCP service with HTTP..."
    python src/main.py --mcp-conf conf/config.json --user-conf conf/user_mcp_config.json \
        --host ${host} --port ${port} > ${LOG_FILE} 2>&1 &
fi
echo "MCP service started. Log file: ${LOG_FILE}"

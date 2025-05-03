#!/bin/bash
export $(grep -v '^#' .env | xargs)

export PYTHONPATH=./src:$PYTHONPATH
source .venv/bin/activate

# Create necessary directories
mkdir -p ./tmp 
mkdir -p ${LOG_DIR}

LOG_FILE1="${LOG_DIR}/start_mcp_$(date +%Y%m%d_%H%M%S).log"
LOG_FILE2="${LOG_DIR}/start_chatbot_$(date +%Y%m%d_%H%M%S).log"
MAX_LOG_SIZE=10M  # 设置日志文件大小上限为10MB

# HTTPS support
use_https=${USE_HTTPS:-0}  # Default to HTTP if not set in .env
ssl_cert=${SSL_CERT_FILE:-"certs/server.crt"}
ssl_key=${SSL_KEY_FILE:-"certs/server.key"}

# Set environment variables
if [ "$use_https" = "1" ]; then
    export MCP_BASE_URL=https://${MCP_SERVICE_HOST}:${MCP_SERVICE_PORT}
    echo "Using HTTPS for MCP service"
else
    export MCP_BASE_URL=http://${MCP_SERVICE_HOST}:${MCP_SERVICE_PORT}
fi
echo "MCP_BASE_URL: ${MCP_BASE_URL}"

# Start MCP service
echo "Starting MCP service..."
if [ "$use_https" = "1" ]; then
    # Check if certificate files exist
    if [ -f "$ssl_cert" ] && [ -f "$ssl_key" ]; then
        echo "Using existing SSL certificates"
    else
        echo "SSL certificate or key not found. Generating self-signed certificates..."
        ./generate_certs.sh
    fi
    
    nohup python src/main.py --mcp-conf conf/config.json --user-conf conf/user_mcp_config.json \
        --host ${MCP_SERVICE_HOST} --port ${MCP_SERVICE_PORT} \
        --ssl-certfile ${ssl_cert} --ssl-keyfile ${ssl_key} > ${LOG_FILE1} 2>&1 &
else
    nohup python src/main.py --mcp-conf conf/config.json --user-conf conf/user_mcp_config.json \
        --host ${MCP_SERVICE_HOST} --port ${MCP_SERVICE_PORT} > ${LOG_FILE1} 2>&1 &
fi

# Start Chatbot service 
# echo "Starting Chatbot service..."
# nohup streamlit run chatbot.py \
#     --server.port ${CHATBOT_SERVICE_PORT} > ${LOG_FILE2} 2>&1 &

# echo "Services started. Check logs in ${LOG_DIR}"

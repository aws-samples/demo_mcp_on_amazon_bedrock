# Strands Agents SDK Integration

This document describes how to use the Strands Agents SDK integration in this agent service.

## Overview

The Strands Agents SDK integration provides a new agent implementation that leverages the Strands framework for building AI agents. This implementation maintains compatibility with the existing API while using Strands' powerful agent capabilities.

## Features

- **Full compatibility** with existing API endpoints
- **Streaming support** for real-time responses
- **MCP tool integration** - All existing MCP tools work seamlessly
- **Multiple model providers** - Support for Bedrock, OpenAI, and Anthropic
- **Session management** - Maintains conversation history
- **Tool calling** - Automatic integration with MCP servers

## Configuration

### Environment Variables

Add the following environment variables to enable Strands Agents:

```bash
# Enable Strands client
CLIENT_TYPE=strands

# Model provider (bedrock, openai, anthropic)
STRANDS_MODEL_PROVIDER=bedrock

# API credentials (depending on provider)
STRANDS_API_KEY=your_api_key_here
STRANDS_API_BASE=https://api.openai.com/v1  # For OpenAI-compatible APIs

# AWS credentials (for Bedrock)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

### Model Provider Configuration

#### Bedrock (Default)
```bash
CLIENT_TYPE=strands
STRANDS_MODEL_PROVIDER=bedrock
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

#### OpenAI
```bash
CLIENT_TYPE=strands
STRANDS_MODEL_PROVIDER=openai
STRANDS_API_KEY=your_openai_api_key
STRANDS_API_BASE=https://api.openai.com/v1
```

## Usage

### Starting the Server

1. Install Strands Agents SDK:
```bash
pip install strands-agents
pip install strands-agents-tools  # Optional: for built-in tools
```

2. Set environment variables as described above

3. Start the server:
```bash
python src/main.py --mcp-conf conf/config.json
```

### API Usage

The Strands integration uses the same API endpoints as the existing service:

#### Chat Completions (Non-streaming)
```bash
curl -X POST http://localhost:7002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "mcp_server_ids": ["your_mcp_server_id"]
  }'
```

#### Chat Completions (Streaming)
```bash
curl -X POST http://localhost:7002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "stream": true,
    "mcp_server_ids": ["your_mcp_server_id"]
  }'
```

## MCP Tool Integration

The Strands integration automatically converts MCP tools to Strands-compatible tools. All existing MCP servers and tools work without modification.

### Example MCP Tool Usage

```python
# Your MCP tools are automatically available in Strands agents
# No additional configuration needed
```

## Model Support

### Supported Models

#### Bedrock Models

#### OpenAI Compatible Models

#### Anthropic Models

## Advanced Features

### Custom System Prompts

System prompts are automatically converted from the existing format:

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant specialized in..."},
    {"role": "user", "content": "Hello!"}
  ]
}
```

### Session Management

Sessions are maintained automatically in the backend, client does not have to resend history messages to the backend


### Streaming Control

Streams can be stopped using the existing stop endpoint:

```bash
curl -X POST http://localhost:7002/v1/stop/stream/{stream_id} \
  -H "Authorization: Bearer your_api_key"
```

The Strands integration is designed to be a drop-in replacement for existing functionality while providing enhanced agent capabilities.
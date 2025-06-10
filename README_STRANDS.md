# Strands Agents SDK 集成

本文档描述了如何在此代理服务中使用 Strands Agents SDK 集成。

## 概述

Strands Agents SDK 集成提供了一个新的代理实现，它利用 Strands 框架构建 AI 代理。这种实现在使用 Strands 强大的代理功能的同时，保持了与现有 API 的兼容性。

## 功能特点

- **完全兼容**现有 API 端点
- **流式支持**实时响应
- **MCP 工具集成** - 所有现有 MCP 工具无缝运行
- **多模型提供商** - 支持 Bedrock、OpenAI 和 Anthropic
- **会话管理** - 维护对话历史
- **工具调用** - 自动与 MCP 服务器集成

## 配置

### 环境变量

添加以下环境变量以启用 Strands Agents：

```bash
LOG_DIR=./logs
CHATBOT_SERVICE_PORT=8502
MCP_SERVICE_HOST=0.0.0.0
MCP_SERVICE_PORT=7002
API_KEY=123456

# 启用 Strands 客户端
CLIENT_TYPE=strands

# 模型提供商（bedrock, openai, anthropic）
STRANDS_MODEL_PROVIDER=bedrock

# API 凭证（取决于提供商）
STRANDS_API_KEY=your_api_key_here
STRANDS_API_BASE=https://api.openai.com/v1  # 用于 OpenAI 兼容的 API

# AWS 凭证（用于 Bedrock）
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

### 模型提供商配置

#### Bedrock（默认）
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

## 使用方法

### 启动服务器

1. 安装 Strands Agents SDK：
```bash
pip install strands-agents
pip install strands-agents-tools  # 可选：用于内置工具
```

2. 按上述说明设置环境变量

3. 启动服务器：
```bash
python src/main.py --mcp-conf conf/config.json
```

### API 使用

Strands 集成使用与现有服务相同的 API 端点：

#### 聊天完成（非流式）
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

#### 聊天完成（流式）
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

## MCP 工具集成

Strands 集成自动将 MCP 工具转换为 Strands 兼容工具。所有现有 MCP 服务器和工具无需修改即可工作。

### MCP 工具使用示例

```python
# 您的 MCP 工具在 Strands 代理中自动可用
# 无需额外配置
```

## 模型支持

### 支持的模型

#### Bedrock 模型

#### OpenAI 兼容模型

#### Anthropic 模型

## 高级功能

### 自定义系统提示

系统提示会自动从现有格式转换：

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant specialized in..."},
    {"role": "user", "content": "Hello!"}
  ]
}
```

### 会话管理

会话在后端自动维护，客户端无需向后端重新发送历史消息

### 流式控制

可以使用现有的停止端点停止流：

```bash
curl -X POST http://localhost:7002/v1/stop/stream/{stream_id} \
  -H "Authorization: Bearer your_api_key"
```

Strands 集成旨在成为现有功能的即插即用替代品，同时提供增强的代理功能。
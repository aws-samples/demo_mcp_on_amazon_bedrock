# 设置 HTTPS 支持

本指南说明如何为 FastAPI 服务器和 React UI 前端设置和运行 HTTPS，如果要在ec2上启用Nova Sonic实时对话，需要调用浏览器MediaDevices API，HTTPS是必需的。

## 设置说明

### 1. 生成自签名证书

运行以下命令为本地开发生成自签名证书：

```bash
./generate_certs.sh
```

这将创建一个包含以下内容的 `certificates` 目录：
- `localhost.key` - 私钥
- `localhost.crt` - 证书

### 2. 信任证书（可选但推荐）

#### 如果在 macOS 上部署本demo：
1. 打开钥匙串访问
2. 导入 `certificates/localhost.crt` 文件
3. 找到导入的证书（搜索 "localhost"）
4. 双击它并展开 "信任" 部分
5. 将 "使用此证书时" 设置为 "始终信任"

#### 在 EC2 Linux 上部署的本demo：
过程因发行版而异，但通常：
```bash
sudo cp certificates/localhost.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

### 3. 前端和后端共享证书

为了简化开发体验，`generate_certs.sh` 脚本会自动将生成的证书复制到 React UI 前端目录 (`react_ui/certificates/`)。这确保前端和后端使用相同的证书，用户只需要在浏览器中信任一次证书即可。

如果您手动生成或更新了证书，请确保将它们复制到两个位置：
- 后端: `certificates/`
- 前端: `react_ui/certificates/`

### 4. 使用 HTTPS 运行应用程序

#### 方法 1：使用环境变量

编辑 `.env` 文件并设置：
- 修改`MCP_SERVICE_HOST=0.0.0.0`
- 并新增`USE_HTTPS=1`


然后运行：
```bash
./start_all.sh
```

#### 自定义证书路径（可选）

如果您有自己的证书，可以指定路径：
```bash
python src/main.py --https --ssl-keyfile /path/to/your/key.pem --ssl-certfile /path/to/your/cert.pem  --mcp-conf conf/config.json --user-conf conf/user_mcp_config.json \
--host 0.0.0.0 --port 7002
```

### 5. 配置前端连接到 HTTPS 后端

当后端使用 HTTPS 运行时，前端也需要通过 HTTPS 连接到后端。这已经在代码中配置好了，但您需要确保环境变量正确设置：

1. 编辑 `react_ui/.env.local` 文件（如果不存在则创建）：
```
# API Key for authentication
NEXT_PUBLIC_API_KEY=123456

# Base URL for MCP service - Server side (internal)
# 使用与后端相同的协议（HTTP 或 HTTPS，这里始终保持localhost即可，不用更换其他ip）
SERVER_MCP_BASE_URL=https://localhost:7002

# Base URL for MCP service - Client side (now uses Next.js API routes)
NEXT_PUBLIC_MCP_BASE_URL=/api

# Base URL for direct client-side API access (用于WebSockets，如果是在ec2部署，这里要替换成ec2 ip)
NEXT_PUBLIC_API_BASE_URL=https://<ec2_ip>:7002
```

2. 确保以下环境变量的协议（http:// 或 https://）与后端服务器的实际运行协议匹配：
   - `SERVER_MCP_BASE_URL`：用于服务器端API请求
   - `NEXT_PUBLIC_API_BASE_URL`：用于WebSocket连接和客户端直接API请求

3. 如果您使用 `start_all.sh` 脚本启动应用程序，请更改`.env` 文件中的 `USE_HTTPS=1`。

### 6. 启动访问UI
在`react_ui`目录中运行：
```
docker-compose up mcpui-https -d --build
```

打开浏览器并导航至：
```
https://<ec2_ip>:3000/chat  # React UI 前端
```

注意：您可能会看到关于证书是自签名的浏览器警告。对于本地开发，您可以通过点击"高级"，然后"继续前往 localhost（不安全）"安全地继续。由于前端和后端使用相同的证书，一旦您信任了一个服务的证书，另一个服务也会被自动信任。

## 故障排除

### 证书问题
如果您在浏览器中遇到证书警告：
- 确保您已按上述说明信任了证书
- 尝试使用 Chrome，它对 localhost 的自签名证书通常更宽容

### MediaDevices API 仍然不可用
- 确保您通过 HTTPS 访问站点
- 检查浏览器对麦克风访问的权限
- 尝试使用不同的浏览器排除特定浏览器的问题
- 信任证书后重启浏览器
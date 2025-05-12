# BedrockMcpStack 类说明文档

## 概述

`BedrockMcpStack` 是一个 AWS CDK 堆栈类，用于部署和配置 Amazon Bedrock 多通道处理器 (MCP) 的基础设施。该堆栈创建了一个完整的演示环境，允许用户通过 Streamlit UI 与 Amazon Bedrock 上的多通道处理器进行交互。

## 类定义

```typescript
export class BedrockMcpStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: BedrockMcpStackProps) {
    // 实现...
  }
}
```

其中 `BedrockMcpStackProps` 接口定义如下：

```typescript
export interface BedrockMcpStackProps extends cdk.StackProps {
  namePrefix?: string;  // 可选的资源名称前缀
}
```

## 主要组件

### 1. 网络配置

- **VPC**：创建一个包含以下配置的虚拟私有云
  - 2 个可用区
  - 1 个 NAT 网关
  - 公有子网和带出口的私有子网
  
- **安全组**：配置允许来自任何 IPv4 地址的 8502 端口访问（Streamlit UI）

### 2. 权限配置

- **EC2 实例角色**：
  - 允许 SSM 管理（AmazonSSMManagedInstanceCore）
  - 授予 Bedrock 模型调用权限（bedrock:InvokeModel*、bedrock:ListFoundationModels）
  
- **API 用户**：
  - 创建专用 IAM 用户用于 API 访问
  - 授予 Bedrock 模型调用权限
  - 生成访问密钥和密钥 ID

### 3. 负载均衡

- **应用负载均衡器(ALB)**：
  - 面向互联网的负载均衡器
  - 配置 8502 端口的监听器（用于 Streamlit UI）

### 4. 实例配置

- **实例类型**：T3.medium
- **操作系统**：Ubuntu 22.04
- **存储**：100GB 的 EBS 根卷
- **用户数据脚本**：自动执行以下操作
  - 安装 Python 3.12、Git、Node.js
  - 安装 UV 包管理器
  - 克隆 demo_mcp_on_amazon_bedrock 仓库
  - 设置 Python 虚拟环境
  - 配置环境变量（包括 AWS 凭证）
  - 创建并启动系统服务

### 5. 自动扩展

- **自动扩展组(ASG)**：
  - 最小和最大容量均为 1
  - 部署在私有子网中
  - 与负载均衡器集成

### 6. 输出

- **Streamlit UI 端点**：`http://{ALB DNS名称}:8502`
- **API 访问凭证**：访问密钥 ID 和密钥

## 部署流程

1. CDK 部署堆栈时，首先创建网络资源（VPC、子网、安全组）
2. 创建 IAM 角色、用户和访问密钥
3. 创建负载均衡器和监听器
4. 启动自动扩展组中的 EC2 实例
5. EC2 实例启动时执行用户数据脚本，安装和配置应用程序
6. 应用程序作为系统服务启动，并通过负载均衡器提供访问

## 使用方式

部署完成后，用户可以：

1. 通过输出的 Streamlit UI 端点访问应用程序界面
2. 使用生成的 API 凭证进行编程访问
3. 与 Amazon Bedrock 上的多通道处理器进行交互

## 注意事项

- 该堆栈默认部署单个实例，适用于演示环境
- 所有资源都在同一个 AWS 区域中创建
- 实例部署在私有子网中，通过负载均衡器提供访问
- 环境变量和凭证存储在实例的 `.env` 文件中，权限设置为 600（仅所有者可读写）

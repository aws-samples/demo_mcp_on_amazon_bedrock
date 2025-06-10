# AWS CDK 部署指南

使用 AWS CDK (Cloud Development Kit) 部署 MCP 应用到 ECS Fargate 的完整指南。

## CDK 架构概述

CDK 将创建以下 AWS 资源：

### 网络架构
- **VPC**: 10.0.0.0/16 跨 2 个可用区
- **公有子网**: 10.0.1.0/24, 10.0.2.0/24 (ALB)
- **私有子网**: 10.0.3.0/24, 10.0.4.0/24 (ECS容器)
- **NAT Gateway**: 为私有子网提供互联网访问
- **Internet Gateway**: 公有网络访问

### 计算和存储
- **ECS Fargate 集群**: ARM64 架构容器运行时
- **DynamoDB 表**: 用户配置存储 (按需计费)
- **ECR 仓库**: 前端和后端 Docker 镜像存储

### 安全和配置
- **Secrets Manager**: 生成并安全存储服务api key配置
- **IAM 角色**: 最小权限原则
- **安全组**: 网络访问控制

### 负载均衡和监控
- **Application Load Balancer**: HTTP/HTTPS 流量分发
- **CloudWatch Logs**: 应用日志收集
- **Auto Scaling**: CPU 使用率自动伸缩

## 快速开始

### 环境要求

1. **Node.js** (版本 18+)
2. **AWS CLI** 已配置
3. **Docker** 支持 buildx (多架构构建)
4. **AWS CDK** CLI 工具

```bash
# 安装 CDK CLI
npm install -g aws-cdk
npm install -g typescript
npm install
npm i --save-dev @types/node


# 验证安装
cdk --version
```

#### 中国区安装需要设置docker 镜像源
使用 `sudo vim /etc/docker/daemon.json`,添加代理
```json
{
"registry-mirrors":["https://mirror-docker.bosicloud.com"],
"insecure-registries":["mirror-docker.bosicloud.com"]
}
```

## 详细部署步骤
### 步骤 1: 配置AWS credentials
```bash
aws configure
```

### 步骤 1: 准备环境

确保 `.env` 文件包含所有必要的配置：

```bash
# 如果在Global Region需要使用Bedrock，配置如下
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
STRANDS_MODEL_PROVIDER=bedrock


# 如果在中国区，使用openai兼容接口的模型，需要如下Strands 配置
STRANDS_API_KEY=your-model-provider-key
STRANDS_API_BASE=your-model-provider-base-url(例如https://api.siliconflow.cn)
STRANDS_MODEL_PROVIDER=openai

# Langfuse 配置 (可选)
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_HOST=https://your-langfuse-host

# 其他配置
CLIENT_TYPE=strands
MAX_TURNS=200
INACTIVE_TIME=1440
```

### 部署脚本
```bash
cd cdk
bash cdk-build-and-deploy.sh
```

### 步骤 5: 更新服务


## CDK 命令参考

### 基本命令

```bash
# 查看将要部署的资源
cdk diff

# 部署 Stack
cdk deploy

# 销毁 Stack
cdk destroy

# 列出所有 Stack
cdk list

# 查看 Stack 模板
cdk synth
```

### 有用的选项

```bash
# 跳过确认
cdk deploy --require-approval never

# 指定 Stack 名称
cdk deploy McpEcsFargateStack

# 设置 AWS 配置文件
cdk deploy --profile your-profile

# 输出模板到文件
cdk synth > template.yaml
```

## 配置管理

### Secrets Manager 更新

部署后，需要更新 Secrets Manager 中的实际值：

```bash
# 从 .env 文件批量更新
source .env

# 更新 AWS 凭证
aws secretsmanager update-secret \
    --secret-id "mcp-app/aws-credentials" \
    --secret-string "{\"AccessKeyId\":\"$AWS_ACCESS_KEY_ID\",\"SecretAccessKey\":\"$AWS_SECRET_ACCESS_KEY\"}"

# 更新 Strands API Key
aws secretsmanager update-secret \
    --secret-id "mcp-app/strands-api-key" \
    --secret-string "$STRANDS_API_KEY"

# 更新其他密钥...
```

### 环境变量调整

修改 `cdk/lib/ecs-fargate-stack.ts` 中的 `environment` 配置：

```typescript
environment: {
  AWS_REGION: cdk.Stack.of(this).region,
  STRANDS_MODEL_PROVIDER: 'openai',
  MAX_TURNS: '200',
  // 添加或修改其他环境变量
},
```

## 监控和运维

### CloudWatch 日志

```bash
# 查看前端日志
aws logs describe-log-streams --log-group-name "/ecs/mcp-app-frontend"

# 查看后端日志
aws logs describe-log-streams --log-group-name "/ecs/mcp-app-backend"

# 实时查看日志
aws logs tail "/ecs/mcp-app-backend" --follow
```

### ECS 服务管理

```bash
# 查看服务状态
aws ecs describe-services --cluster mcp-app-cluster --services mcp-app-frontend-service mcp-app-backend-service

# 查看任务状态
aws ecs list-tasks --cluster mcp-app-cluster --service-name mcp-app-backend-service

# 扩缩容服务
aws ecs update-service --cluster mcp-app-cluster --service mcp-app-backend-service --desired-count 3
```

### 健康检查

```bash
# 检查 ALB 目标组健康状态
ALB_ARN=$(aws elbv2 describe-load-balancers --names mcp-app-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)
TARGET_GROUPS=$(aws elbv2 describe-target-groups --load-balancer-arn $ALB_ARN --query 'TargetGroups[].TargetGroupArn' --output text)

for TG in $TARGET_GROUPS; do
    aws elbv2 describe-target-health --target-group-arn $TG
done
```

## 故障排除

### 常见问题

1. **CDK Bootstrap 失败**
   ```bash
   # 检查 AWS 权限
   aws iam get-user
   
   # 手动指定区域
   cdk bootstrap --region us-east-1
   ```

2. **Docker 构建失败**
   ```bash
   # 检查 buildx 支持
   docker buildx ls
   
   # 创建新的 builder
   docker buildx create --name mybuilder --use
   ```

3. **ECS 任务启动失败**
   ```bash
   # 查看任务详情
   TASK_ARN=$(aws ecs list-tasks --cluster mcp-app-cluster --service-name mcp-app-backend-service --query 'taskArns[0]' --output text)
   aws ecs describe-tasks --cluster mcp-app-cluster --tasks $TASK_ARN
   ```

4. **Secrets Manager 权限错误**
   ```bash
   # 检查任务角色权限
   aws iam get-role-policy --role-name mcp-app-task-execution-role --policy-name SecretsManagerPolicy
   ```

### 调试命令

```bash
# 检查 VPC 连接
aws ec2 describe-vpcs --filters "Name=tag:Name,Values=mcp-app-vpc"

# 检查安全组规则
aws ec2 describe-security-groups --group-names mcp-app-ecs-sg

# 检查负载均衡器状态
aws elbv2 describe-load-balancers --names mcp-app-alb
```

## 成本优化

### ARM64 架构优势
- 比 x86 便宜约 20%
- 更好的性能功耗比
- 原生支持主流运行时

### 资源右尺寸
```typescript
// 在 Stack 中调整资源配置
const frontendTaskDefinition = new ecs.FargateTaskDefinition(this, `${prefix}-frontend-task`, {
  memoryLimitMiB: 256,  // 减少内存
  cpu: 128,             // 减少 CPU
  // ...
});
```

### 按需服务
- DynamoDB 按需计费
- ECR 镜像生命周期管理
- CloudWatch 日志保留期设置

## 安全最佳实践

### 网络安全
- 私有子网部署应用
- 安全组最小权限
- VPC 端点减少外网流量

### 访问控制
- IAM 角色最小权限
- Secrets Manager 存储敏感数据
- 定期轮换访问密钥

### 数据保护
- ECS 任务加密存储
- ALB HTTPS 终端
- DynamoDB 加密静态数据

## 扩展和定制

### 添加新服务
在 `ecs-fargate-stack.ts` 中添加新的 ECS 服务定义。

### 自定义域名
配置 Route53 和 ACM 证书：

```typescript
// 在 Stack 中添加
const certificate = new acm.Certificate(this, 'Certificate', {
  domainName: 'your-domain.com',
  validation: acm.CertificateValidation.fromDns(),
});

// 修改 ALB 监听器
const httpsListener = this.alb.addListener(`${prefix}-https-listener`, {
  port: 443,
  protocol: elbv2.ApplicationProtocol.HTTPS,
  certificates: [certificate],
  defaultTargetGroups: [frontendTargetGroup],
});
```

### 多环境部署
使用 CDK 上下文变量：

```bash
# 部署到不同环境
cdk deploy --context env=staging
cdk deploy --context env=production
```

## 清理资源

完全删除所有创建的资源：

```bash
# 删除 CDK Stack
cdk destroy

# 清理 ECR 仓库
aws ecr delete-repository --repository-name mcp-app-frontend --force
aws ecr delete-repository --repository-name mcp-app-backend --force

# 删除 CloudWatch 日志组
aws logs delete-log-group --log-group-name "/ecs/mcp-app-frontend"
aws logs delete-log-group --log-group-name "/ecs/mcp-app-backend"
```

注意：某些资源（如 DynamoDB 表）可能有删除保护，需要手动确认删除。

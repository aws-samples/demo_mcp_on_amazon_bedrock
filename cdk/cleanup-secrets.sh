#!/bin/bash

# 清理现有的 AWS 资源以避免部署冲突
# 在重新部署之前运行此脚本来清理冲突的资源

set -e

# 配置变量
REGION="${AWS_REGION:-us-east-2}"
PREFIX="strands-mcp-app"

# 检测是否为中国区域
if [[ $REGION == cn-* ]]; then
    IS_CHINA_REGION=true
    echo "检测到中国区域: $REGION"
else
    IS_CHINA_REGION=false
    echo "检测到全球区域: $REGION"
fi

echo "开始清理 AWS 资源..."
echo "区域: $REGION"
echo "前缀: $PREFIX"

# 1. 清理 Secrets Manager 密钥
echo "========================================="
echo "清理 Secrets Manager 密钥"
echo "========================================="

SECRETS=(
    "${PREFIX}/aws-credentials"
    "${PREFIX}/strands-api-key"
    "${PREFIX}/strands-api-base"
    "${PREFIX}/langfuse-public-key"
    "${PREFIX}/langfuse-secret-key"
    "${PREFIX}/langfuse-host"
    "${PREFIX}/api-key"
    "${PREFIX}/ddb-table-name"
)

for secret in "${SECRETS[@]}"; do
    echo "检查密钥: $secret"
    
    if aws secretsmanager describe-secret --secret-id "$secret" --region "$REGION" &>/dev/null; then
        echo "删除密钥: $secret"
        
        aws secretsmanager delete-secret \
            --secret-id "$secret" \
            --force-delete-without-recovery \
            --region "$REGION" || echo "删除失败: $secret"
    else
        echo "密钥不存在，跳过: $secret"
    fi
done

# 2. 清理 ECR 仓库
echo "========================================="
echo "清理 ECR 仓库"
echo "========================================="

ECR_REPOS=(
    "${PREFIX}-frontend"
    "${PREFIX}-backend"
)

for repo in "${ECR_REPOS[@]}"; do
    echo "检查 ECR 仓库: $repo"
    
    if aws ecr describe-repositories --repository-names "$repo" --region "$REGION" &>/dev/null; then
        echo "删除 ECR 仓库: $repo"
        
        # 删除仓库中的所有镜像
        aws ecr list-images --repository-name "$repo" --region "$REGION" --query 'imageIds[*]' --output json | \
        jq '.[] | select(.imageTag != null) | {imageDigest: .imageDigest}' | \
        jq -s '.' > /tmp/image-ids.json
        
        if [ -s /tmp/image-ids.json ] && [ "$(cat /tmp/image-ids.json)" != "[]" ]; then
            aws ecr batch-delete-image \
                --repository-name "$repo" \
                --image-ids file:///tmp/image-ids.json \
                --region "$REGION" || echo "删除镜像失败"
        fi
        
        # 删除仓库
        aws ecr delete-repository \
            --repository-name "$repo" \
            --force \
            --region "$REGION" || echo "删除仓库失败: $repo"
    else
        echo "ECR 仓库不存在，跳过: $repo"
    fi
done

echo "========================================="
echo "资源清理完成！"
echo "========================================="
echo "现在可以重新运行 cdk-build-and-deploy.sh"

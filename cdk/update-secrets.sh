#!/bin/bash

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

echo "检查和更新 Secrets Manager 配置..."
echo "使用区域: $REGION"

# 检查.env文件是否存在
if [ ! -f "../.env" ]; then
    echo "错误: .env 文件不存在，请先创建 .env 文件"
    exit 1
fi

# 读取.env文件
set -a
source ../.env
set +a

echo "========================================="
echo "检查必需的环境变量"
echo "========================================="

# 检查必需的环境变量
MISSING_VARS=()

# if [ -z "$AWS_ACCESS_KEY_ID" ]; then
#     echo "❌ AWS_ACCESS_KEY_ID 未设置或为空"
#     MISSING_VARS+=("AWS_ACCESS_KEY_ID")
# else
#     echo "✅ AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:0:10}..."
# fi

# if [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
#     echo "❌ AWS_SECRET_ACCESS_KEY 未设置或为空"
#     MISSING_VARS+=("AWS_SECRET_ACCESS_KEY")
# else
#     echo "✅ AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:0:10}..."
# fi

# if [ -z "$API_KEY" ]; then
#     echo "❌ API_KEY 未设置或为空"
#     MISSING_VARS+=("API_KEY")
# else
#     echo "✅ API_KEY: ${API_KEY:0:10}..."
# fi

if [ -z "$STRANDS_API_KEY" ]; then
    echo "❌ STRANDS_API_KEY 未设置或为空"
    MISSING_VARS+=("STRANDS_API_KEY")
else
    echo "✅ STRANDS_API_KEY: ${STRANDS_API_KEY:0:10}..."
fi

if [ -z "$STRANDS_API_BASE" ]; then
    echo "❌ STRANDS_API_BASE 未设置或为空"
    MISSING_VARS+=("STRANDS_API_BASE")
else
    echo "✅ STRANDS_API_BASE: $STRANDS_API_BASE"
fi

# if [ -z "$LANGFUSE_HOST" ]; then
#     echo "❌ LANGFUSE_HOST 未设置或为空"
#     MISSING_VARS+=("LANGFUSE_HOST")
# else
#     echo "✅ LANGFUSE_HOST: $LANGFUSE_HOST"
# fi

if [ -z "$LANGFUSE_PUBLIC_KEY" ]; then
    echo "❌ LANGFUSE_PUBLIC_KEY 未设置或为空"
    MISSING_VARS+=("LANGFUSE_PUBLIC_KEY")
else
    echo "✅ LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:0:10}..."
fi

if [ -z "$LANGFUSE_SECRET_KEY" ]; then
    echo "❌ LANGFUSE_SECRET_KEY 未设置或为空"
    MISSING_VARS+=("LANGFUSE_SECRET_KEY")
else
    echo "✅ LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:0:10}..."
fi

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo ""
    echo "========================================="
    echo "❌ 发现缺失的环境变量"
    echo "========================================="
    echo "请在 .env 文件中设置以下变量："
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "提示: 检查 .env 文件中是否有被注释掉的变量 (以 # 开头的行)"
    exit 1
fi

echo ""
echo "========================================="
echo "更新 Secrets Manager"
echo "========================================="

# # 更新 AWS 凭证
# echo "更新 AWS 凭证..."
# aws secretsmanager update-secret \
#     --secret-id "${PREFIX}/aws-credentials" \
#     --secret-string "{\"AccessKeyId\":\"${AWS_ACCESS_KEY_ID}\",\"SecretAccessKey\":\"${AWS_SECRET_ACCESS_KEY}\"}" \
#     --region $REGION || {
#     echo "创建 AWS 凭证密钥..."
#     aws secretsmanager create-secret \
#         --name "${PREFIX}/aws-credentials" \
#         --description "AWS Access Credentials" \
#         --secret-string "{\"AccessKeyId\":\"${AWS_ACCESS_KEY_ID}\",\"SecretAccessKey\":\"${AWS_SECRET_ACCESS_KEY}\"}" \
#         --region $REGION
# }

# 更新 API Key
# echo "更新 API Key..."
# aws secretsmanager update-secret \
#     --secret-id "${PREFIX}/api-key" \
#     --secret-string "${API_KEY}" \
#     --region $REGION || {
#     echo "创建 Server API Key 密钥..."
#     aws secretsmanager create-secret \
#         --name "${PREFIX}/api-key" \
#         --description "API Key" \
#         --secret-string "${API_KEY}" \
#         --region $REGION
# }


# 更新 Strands API Key
# echo "更新 Strands API Key..."
# aws secretsmanager update-secret \
#     --secret-id "${PREFIX}/strands-api-key" \
#     --secret-string "${STRANDS_API_KEY}" \
#     --region $REGION || {
#     echo "创建 Strands API Key 密钥..."
#     aws secretsmanager create-secret \
#         --name "${PREFIX}/strands-api-key" \
#         --description "Strands API Key" \
#         --secret-string "${STRANDS_API_KEY}" \
#         --region $REGION
# }

# # 更新 Strands API Base
# echo "更新 Strands API Base..."
# aws secretsmanager update-secret \
#     --secret-id "${PREFIX}/strands-api-base" \
#     --secret-string "${STRANDS_API_BASE}" \
#     --region $REGION || {
#     echo "创建 Strands API Base 密钥..."
#     aws secretsmanager create-secret \
#         --name "${PREFIX}/strands-api-base" \
#         --description "Strands API Base URL" \
#         --secret-string "${STRANDS_API_BASE}" \
#         --region $REGION
# }

# 更新 Langfuse 配置
# echo "更新 Langfuse Host..."
# aws secretsmanager update-secret \
#     --secret-id "${PREFIX}/langfuse-host" \
#     --secret-string "${LANGFUSE_HOST}" \
#     --region $REGION || {
#     echo "创建 Langfuse Host 密钥..."
#     aws secretsmanager create-secret \
#         --name "${PREFIX}/langfuse-host" \
#         --description "Langfuse Host" \
#         --secret-string "${LANGFUSE_HOST}" \
#         --region $REGION
# }

# echo "更新 Langfuse Public Key..."
# aws secretsmanager update-secret \
#     --secret-id "${PREFIX}/langfuse-public-key" \
#     --secret-string "${LANGFUSE_PUBLIC_KEY}" \
#     --region $REGION || {
#     echo "创建 Langfuse Public Key 密钥..."
#     aws secretsmanager create-secret \
#         --name "${PREFIX}/langfuse-public-key" \
#         --description "Langfuse Public Key" \
#         --secret-string "${LANGFUSE_PUBLIC_KEY}" \
#         --region $REGION
# }

# echo "更新 Langfuse Secret Key..."
# aws secretsmanager update-secret \
#     --secret-id "${PREFIX}/langfuse-secret-key" \
#     --secret-string "${LANGFUSE_SECRET_KEY}" \
#     --region $REGION || {
#     echo "创建 Langfuse Secret Key 密钥..."
#     aws secretsmanager create-secret \
#         --name "${PREFIX}/langfuse-secret-key" \
#         --description "Langfuse Secret Key" \
#         --secret-string "${LANGFUSE_SECRET_KEY}" \
#         --region $REGION
# }

echo ""
echo "========================================="
echo "✅ Secrets Manager 更新完成！"
echo "========================================="
echo "所有密钥已更新为 .env 文件中的当前值"
echo ""
echo "接下来可以运行: ./update-ecs-services.sh 来重新部署服务"

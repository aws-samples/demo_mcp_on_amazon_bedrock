"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
"""
DynamoDB utility functions for the FastAPI server
"""
import os
import json
import logging
import boto3
from datetime import datetime
from typing import Dict
import hashlib
import re
import threading
from dotenv import load_dotenv
from urllib.parse import urlparse

# Initialize logger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
logger = logging.getLogger(__name__)
# 全局模型和服务器配置
load_dotenv()  # load env vars from .env
# DynamoDB 客户端
dynamodb_client = None
DDB_TABLE = os.environ.get("ddb_table")  # DynamoDB表名，用于存储用户配置
user_mcp_server_configs = {}  # 用户特有的MCP服务器配置 user_id -> {server_id: config}
global_mcp_server_configs = {}  # 全局MCP服务器配置 server_id -> config

session_lock = threading.RLock()

if DDB_TABLE:
    try:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        dynamodb_client = boto3.resource('dynamodb', region_name=region)
        logger.info(f"已连接到DynamoDB, 表名: {DDB_TABLE}")
    except Exception as e:
        logger.error(f"DynamoDB连接失败: {e}")

def save_configs_to_json(configs:dict):
    config_file = os.environ.get('USER_MCP_CONFIG_FILE', 'conf/user_mcp_configs.json')
    with open(config_file, 'w') as f:
        json.dump(configs, f, indent=2)
        
async def save_to_ddb(user_id: str, data: dict):
    """将用户配置保存到DynamoDB"""
    if not dynamodb_client or not DDB_TABLE:
        return False
    
    try:
        table = dynamodb_client.Table(DDB_TABLE)
        response = table.put_item(
            Item={
                'userId': user_id,
                'data': json.dumps(data),
                'timestamp': datetime.now().isoformat()
            }
        )
        logger.info(f"保存用户 {user_id} 配置到DynamoDB成功")
        return True
    except Exception as e:
        logger.error(f"保存用户 {user_id} 配置到DynamoDB失败: {e}")
        return False

async def get_from_ddb(user_id: str) -> dict:
    """从DynamoDB获取用户配置"""
    if not dynamodb_client or not DDB_TABLE:
        return {}
    
    try:
        table = dynamodb_client.Table(DDB_TABLE)
        response = table.get_item(
            Key={
                'userId': user_id
            }
        )
        
        if 'Item' in response:
            data = json.loads(response['Item'].get('data', '{}'))
            logger.info(f"从DynamoDB获取用户 {user_id} 配置成功")
            return data
        else:
            logger.info(f"用户 {user_id} 在DynamoDB中无配置")
            return {}
    except Exception as e:
        logger.warning(f"从DynamoDB获取用户 {user_id} 配置失败: {e}")
        return {}
        
async def delete_from_ddb(user_id: str) -> bool:
    """从DynamoDB删除用户配置"""
    if not dynamodb_client or not DDB_TABLE:
        return False
    
    try:
        table = dynamodb_client.Table(DDB_TABLE)
        response = table.delete_item(
            Key={
                'userId': user_id
            }
        )
        logger.info(f"从DynamoDB删除用户 {user_id} 配置成功")
        return True
    except Exception as e:
        logger.error(f"从DynamoDB删除用户 {user_id} 配置失败: {e}")
        return False

async def scan_all_from_ddb() -> dict:
    """从DynamoDB扫描所有用户配置，处理分页"""
    if not dynamodb_client or not DDB_TABLE:
        return {}
    
    try:
        # 使用scan操作获取所有用户的配置，并处理分页
        table = dynamodb_client.Table(DDB_TABLE)
        configs = {}
        
        # 初始化扫描参数
        scan_params = {}
        done = False
        start_key = None
        
        # 处理分页
        while not done:
            if start_key:
                scan_params['ExclusiveStartKey'] = start_key
            
            response = table.scan(**scan_params)
            items = response.get('Items', [])
            
            # 处理当前页的结果
            for item in items:
                if 'userId' in item and 'data' in item:
                    user_id = item['userId']
                    try:
                        user_data = json.loads(item['data'])
                        configs[user_id] = user_data
                    except json.JSONDecodeError as e:
                        logger.error(f"解析用户 {user_id} 的DynamoDB数据失败: {e}")
            
            # 检查是否有更多页
            start_key = response.get('LastEvaluatedKey')
            done = start_key is None
        
        logger.info(f"已从DynamoDB扫描到 {len(configs)} 个用户的配置")
        return configs
    except Exception as e:
        logger.error(f"从DynamoDB扫描用户配置失败: {e}")
        return {}
    

# 保存全局MCP服务器配置
def save_global_server_config( server_id: str, config: dict):
    """保存全局的MCP服务器配置"""
    global global_mcp_server_configs
    global_mcp_server_configs[server_id] = config
    # 在实际应用中，这里应该将配置持久化到数据库或文件系统
    logger.info(f"保存Global服务器配置 {server_id}")

# 删除用户MCP服务器配置 
async def delete_user_server_config(user_id: str, server_id: str):
    """删除用户的MCP服务器配置"""
    with session_lock: 
        if user_id in user_mcp_server_configs and server_id in user_mcp_server_configs[user_id]:
            del user_mcp_server_configs[user_id][server_id]
            # 如果配置了DynamoDB，也从DDB中更新用户配置
            if DDB_TABLE and dynamodb_client:
                # 获取当前用户的所有配置
                user_configs = await get_user_server_configs(user_id)
                if server_id in user_configs:
                    del user_configs[server_id]
                # 保存更新后的配置到DynamoDB
                await save_to_ddb(user_id, user_configs)
                logger.info(f"已更新用户 {user_id} 在DynamoDB中的配置")
            else:
                try:
                    save_configs_to_json(user_mcp_server_configs)
                    logger.info(f"为用户 {user_id} 删除服务器配置 {server_id}")
                except Exception as e:
                    logger.error(f"保存用户MCP配置到文件失败: {e}")


# 保存用户MCP服务器配置
async def save_user_server_config(user_id: str, server_id: str, config: dict):
    """保存用户的MCP服务器配置"""
    global user_mcp_server_configs
    
    with session_lock:
        if user_id not in user_mcp_server_configs:
            user_mcp_server_configs[user_id] = {}
        
        user_mcp_server_configs[user_id][server_id] = config
        # 如果配置了DynamoDB，也保存到DDB中
        if DDB_TABLE and dynamodb_client:
            #获取原有的记录
            ddb_config = await get_from_ddb(user_id)
            ddb_config[server_id] = config
            await save_to_ddb(user_id, ddb_config)
            logger.info(f"已保存用户 {user_id} 配置到DynamoDB")
        else:
            try:
                save_configs_to_json(user_mcp_server_configs)
                logger.info(f"已保存用户 {user_id} 配置到config_file")
            except Exception as e:
                logger.error(f"保存用户MCP配置到文件失败: {e}")

# 获取用户MCP服务器配置
async def get_user_server_configs(user_id: str) -> dict:
    """获取指定用户的所有MCP服务器配置"""
    # 如果设置了DynamoDB表名，优先从DynamoDB读取
    if DDB_TABLE and dynamodb_client:
        # 尝试从DynamoDB获取
        ddb_config = await get_from_ddb(user_id)
        if ddb_config:
            # 如果DynamoDB中有数据，更新内存缓存并返回
            with session_lock:
                user_mcp_server_configs[user_id] = ddb_config
            return ddb_config
        else:
            return {}
    else: 
        # 如果没有设置DynamoDB或无法从DynamoDB获取，从内存中读取
        return user_mcp_server_configs.get(user_id, {})
    
async def load_user_mcp_configs():
    """加载用户MCP服务器配置"""
    global user_mcp_server_configs
    # 如果设置了DynamoDB表名，从DynamoDB加载所有用户配置
    if DDB_TABLE and dynamodb_client:
        logger.info(f"从DynamoDB加载所有用户MCP配置")
        try:
            # 使用scan_all_from_ddb扫描所有用户配置
            ddb_configs = await scan_all_from_ddb()
            if ddb_configs:
                # 如果DynamoDB中有数据，更新内存缓存
                with session_lock:
                    user_mcp_server_configs = ddb_configs
                    logger.info(f"已从DynamoDB加载 {len(ddb_configs)} 个用户的MCP服务器配置")
        except Exception as e:
            logger.error(f"从DynamoDB加载用户MCP配置失败: {e}")
    else:
        # 如果没有设置DynamoDB或从DynamoDB加载失败，从文件加载
        try:
            config_file = os.environ.get('USER_MCP_CONFIG_FILE', 'conf/user_mcp_configs.json')
            if os.path.exists(config_file):
                with session_lock:
                    with open(config_file, 'r') as f:
                        configs = json.load(f)
                        user_mcp_server_configs = configs
                        logger.info(f"已从文件加载 {len(configs)} 个用户的MCP服务器配置")
        except Exception as e:
            logger.error(f"加载用户MCP配置失败: {e}")
            

# 获取global服务器配置
def get_global_server_configs() -> dict:
    """获取全局所有MCP服务器配置"""
    return global_mcp_server_configs

def filter_tool_use_result(
    messages: list,
):
    """
    remove all toolUse, toolResult, and reasoningContent blocks 
    """
    for message in messages:
        if "content" in message and isinstance(message["content"], list):
            message["content"] = [item for item in message["content"] 
                                 if "toolResult" not in item 
                                 and "toolUse" not in item
                                 and "reasoningContent" not in item]
            
    filtered_messages = [message for message in messages if message['content'] != []]
    return filtered_messages
    
def maybe_filter_to_n_most_recent_images(
    messages: list,
    images_to_keep: int,
    min_removal_threshold: int,
):
    """
    With the assumption that images are screenshots that are of diminishing value as
    the conversation progresses, remove all but the final `images_to_keep` tool_result
    images in place, with a chunk of min_removal_threshold to reduce the amount we
    break the implicit prompt cache.
    """
    if not images_to_keep :
        return messages

    tool_result_blocks =  [
            item['toolResult']
            for message in messages
            for item in (
                message["content"] if isinstance(message["content"], list) else []
            )
            if isinstance(item, dict) and "toolResult" in item
        ]

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get("content", [])
        if isinstance(content, dict) and  "image" in content
    )

    images_to_remove = total_images - images_to_keep
    # for better cache behavior, we want to remove in chunks
    images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get("content"), list):
            new_content = []
            for content in tool_result.get("content", []):
                if isinstance(content, dict) and "image" in content:
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result["content"] = new_content
            
def remove_cache_checkpoint(messages: list) -> list:
    """
    Remove cachePoint blocks from messages.
    
    Args:
        messages (list): A list of message dictionaries.
        
    Returns:
        list: The modified messages list with cachePoint blocks removed.
    """
    for message in messages:
        if "content" in message and isinstance(message["content"], list):
            message["content"] = [item for item in message["content"] if "cachePoint" not in item]
    return messages

def hash_filename(filepath, algorithm='md5'):
    """
    对文件名进行哈希处理，但保留原始扩展名
    """
    filename = os.path.basename(filepath)
    base, ext = os.path.splitext(filename)
    
    hash_obj = hashlib.md5(base.encode('utf-8'))
    hashed_base = hash_obj.hexdigest()
    
    return hashed_base + ext

def clean_filename(filename):
    """清理文件名，只保留允许的字符，并移除连续空格"""
    # 分离文件名和扩展名
    name, ext = os.path.splitext(filename)
    
    # 只保留允许的字符（字母数字、空格、连字符、圆括号和方括号）
    cleaned_name = re.sub(r'[^a-zA-Z0-9\s\-\(\)\[\]]', '', name)
    
    # 将连续的空格替换为单个空格
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name)
    
    # 返回清理后的文件名加扩展名
    return cleaned_name + ext

def is_endpoint_sse(url):
    """
    判断URL的endpoint(路径的最后一部分)是否为'sse'
    
    Args:
        url (str): 要检查的URL
        
    Returns:
        bool: 如果URL的endpoint是'sse'，返回True；否则返回False
    """
    try:
        # 解析URL
        parsed_url = urlparse(url)
        
        # 获取路径部分，并去除末尾的斜杠
        path = parsed_url.path.rstrip('/')
        
        # 如果path为空，返回False
        if not path:
            return False
        
        # 切分路径获取最后一个部分
        path_parts = path.split('/')
        
        # 判断最后一个路径部分是否是"sse"
        return path_parts[-1] == 'sse'
        
    except Exception as e:
        print(f"解析URL时出错: {e}")
        return False

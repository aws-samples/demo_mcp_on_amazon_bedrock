"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
import os
import sys
import asyncio
import logging
from typing import Dict, AsyncGenerator, Optional, List, AsyncIterator
import json
import boto3
from botocore.config import Config
from dotenv import load_dotenv
from chat_client import ChatClient
import base64
from mcp_client import MCPClient
from utils import maybe_filter_to_n_most_recent_images,remove_cache_checkpoint
from botocore.exceptions import ClientError
import random
import time
load_dotenv()  # load environment variables from .env

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)

logger = logging.getLogger(__name__)
CLAUDE_37_SONNET_MODEL_ID = 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'
CLAUDE_35_HAIKU_MODEL_ID = 'us.anthropic.claude-3-5-haiku-20241022-v1:0'
NOVA_RPO_MODEL_ID = 'us.amazon.nova-pro-v1:0'
NOVA_LITE_MODEL_ID = 'us.amazon.nova-lite-v1:0'

class ChatClientStream(ChatClient):
    """Extended ChatClient with streaming support"""
    
    def __init__(self,credential_file=''):
        super().__init__(credential_file)
        self.max_retries = 10 # Maximum number of retry attempts
        self.base_delay = 10 # Initial backoff delay in seconds
        self.max_delay = 60 # Maximum backoff delay in seconds
        self.client_index = 0
        self.stop_flags = {} # Dict to track stop flags for streams
    
    def get_bedrock_client_from_pool(self):
        if self.bedrock_client_pool:
            logger.info(f"get_bedrock_client_from_pool index: [{self.client_index}]")
            if self.client_index and self.client_index %(len(self.bedrock_client_pool)-1) == 0:
                self.client_index = 0
            bedrock_client = self.bedrock_client_pool[self.client_index]
            self.client_index += 1
        else:
            bedrock_client = self._get_bedrock_client()
        return bedrock_client

        
    async def _process_stream_response(self, stream_id:str,response) -> AsyncIterator[Dict]:
        """Process the raw response from converse_stream"""
        last_yield_time = time.time()
        for event in response['stream']:
            current_time = time.time()
            if current_time - last_yield_time > 0.1:  # 每100ms让出一次控制权，避免阻塞
                await asyncio.sleep(0.001)
                last_yield_time = current_time
            # Check if we need to stop
            if stream_id and stream_id in self.stop_flags and self.stop_flags[stream_id]:
                logger.info(f"Stream {stream_id} was requested to stop")
                yield {"type": "stopped", "data": {"message": "Stream stopped by user request"}}
                break
            # logger.infos(event)
            # Handle message start
            if "messageStart" in event:
                yield {"type": "message_start", "data": event["messageStart"]}
                continue

            # Handle content block start
            if "contentBlockStart" in event:
                block_start = event["contentBlockStart"]
                yield {"type": "block_start", "data": block_start}
                continue 

            # Handle content block delta
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]
                yield {"type": "block_delta", "data": delta}
                continue

            # Handle content block stop
            if "contentBlockStop" in event:
                yield {"type": "block_stop", "data": event["contentBlockStop"]}
                continue

            # Handle message stop
            if "messageStop" in event:
                yield {"type": "message_stop", "data": event["messageStop"]}
                continue

            # Handle metadata
            if "metadata" in event:
                yield {"type": "metadata", "data": event["metadata"]}
                continue
            
    def exponential_backoff(self, attempt):
        """Calculate exponential backoff delay with jitter"""
        delay = min(self.max_delay, self.base_delay * (2 ** attempt))
        jitter = random.uniform(0, 0.1 * delay)  # 10% jitter
        return delay + jitter
    
    def register_stream(self, stream_id):
        """Register a new stream with a stop flag"""
        self.stop_flags[stream_id] = False
        logger.info(f"Registered stream: {stream_id}")
        
    def stop_stream(self, stream_id):
        """Set the stop flag for a stream to terminate it"""
        if stream_id in self.stop_flags:
            self.stop_flags[stream_id] = True
            # Signal any waiting code immediately without waiting for next check in the streaming loop
            logger.info(f"Stopping stream: {stream_id}")
            return True
        logger.warning(f"Attempted to stop unknown stream: {stream_id}")
        return False
        
    def unregister_stream(self, stream_id):
        """Clean up the stop flag after a stream completes"""
        if stream_id in self.stop_flags:
            del self.stop_flags[stream_id]
            logger.info(f"Unregistered stream: {stream_id}")
            
    async def process_query_stream(self, 
            model_id="amazon.nova-lite-v1:0", max_tokens=1024, max_turns=30,temperature=0.1,
            messages=[], system=[],mcp_clients=None, mcp_server_ids=[],extra_params={},keep_session=None,
            stream_id=None) -> AsyncGenerator[Dict, None]:
        """Submit user query or history messages, and get streaming response.
        
        Similar to process_query but uses converse_stream API for streaming responses.
        """
        logger.info(f'client input message list length:{len(messages)}')

        if keep_session:
            messages = self.messages + messages
            system = self.system if self.system else system
        else:
            self.clear_history()
        
        logger.info(f'llm input message list length:{len(messages)}')
            
        prompt_cache = True if model_id in [CLAUDE_37_SONNET_MODEL_ID,CLAUDE_35_HAIKU_MODEL_ID] else False
        prompt_cache_for_tool = True if model_id in [CLAUDE_37_SONNET_MODEL_ID,CLAUDE_35_HAIKU_MODEL_ID] else False
        cache_window = 2048 if model_id == CLAUDE_35_HAIKU_MODEL_ID else 1024

        # get tools from mcp server
        tool_config = {"tools": []}
        if mcp_clients is not None:
            for mcp_server_id in mcp_server_ids:
                tool_config_response = await mcp_clients[mcp_server_id].get_tool_config(server_id=mcp_server_id)
                if tool_config_response:
                    tool_config['tools'].extend(tool_config_response["tools"])
                else:
                    yield {"type": "stopped", "data": {"message": f"Get tool config from {mcp_server_id} failed, please restart the MCP server"}}
        logger.info(f"Tool config: {tool_config}")
        
        use_client_pool = True if self.bedrock_client_pool else False

        bedrock_client = self.get_bedrock_client_from_pool()
        
        # Track the current tool use state
        current_tool_use = None
        current_tooluse_input = ''
        tool_results = []
        stop_reason = ''
        turn_i = 1

        enable_thinking = extra_params.get('enable_thinking', False) and model_id in CLAUDE_37_SONNET_MODEL_ID
        only_n_most_recent_images = extra_params.get('only_n_most_recent_images', 3)
        image_truncation_threshold = only_n_most_recent_images or 0

        if enable_thinking:
            additionalModelRequestFields = {"reasoning_config": { "type": "enabled","budget_tokens": extra_params.get("budget_tokens",1024)}}
            inferenceConfig={"maxTokens":max(extra_params.get("budget_tokens",1024) + 2048, max_tokens),"temperature":1,}

        else:
            additionalModelRequestFields = {}
            inferenceConfig={"maxTokens":max_tokens,"temperature":temperature,}

        requestParams = dict(
                    modelId=model_id,
                    messages=messages,
                    system=system,
                    inferenceConfig=inferenceConfig,
                    additionalModelRequestFields = additionalModelRequestFields
        )
        requestParams = {**requestParams, 'toolConfig': tool_config} if tool_config['tools'] else requestParams
        if prompt_cache and self.cache_checkpoint == 0:
            if 'toolConfig' in requestParams and prompt_cache_for_tool:
                tools_str = json.dumps(requestParams['toolConfig']['tools'],ensure_ascii=False)
                if len(tools_str) >= 5000:##will replace by token count in future
                    requestParams['toolConfig'] = {"tools":requestParams['toolConfig']['tools'] + [{"cachePoint": {"type": "default"}}]}
                    self.cache_checkpoint += 1
                    self.reset_checkpoint += 1
                    logger.info(f"add checkpoint number:{self.cache_checkpoint} for tool config")
            # Skip cache for system because it usually short.
            if len(system) > 0 and len(system[0]['text']) >= 5000: ##will replace by token count in future
                requestParams['system'] = requestParams['system']+[{"cachePoint": {"type": "default"}}]
                self.cache_checkpoint += 1
                self.reset_checkpoint += 1
                logger.info(f"add checkpoint number:{self.cache_checkpoint} for system prompt")
        
        # Register this stream if an ID is provided
        if stream_id:
            self.register_stream(stream_id)
        
        tokens_need_cache = 0
        
        while turn_i <= max_turns and stop_reason != 'end_turn':
            # Check if we need to stop
            if stream_id and stream_id in self.stop_flags and self.stop_flags[stream_id]:
                logger.info(f"Stream {stream_id} was requested to stop")
                yield {"type": "stopped", "data": {"message": "Stream stopped by user request"}}
                break
            text = ''
            thinking_text = ''
            thinking_signature = ''
            # invoke bedrock llm with user query
            try:
                attempt = 0
                pool_attempt = 0
                while attempt <= self.max_retries:
                    try:
                        response = bedrock_client.converse_stream(
                            **requestParams
                        )
                        break
                    except ClientError as error:
                        logger.info(str(error))
                        if error.response['Error']['Code'] in ['ThrottlingException','serviceUnavailableException'] :
                            if use_client_pool:
                                bedrock_client = self.get_bedrock_client_from_pool()
            
                                if pool_attempt > len(self.bedrock_client_pool): # 如果都轮巡了一遍
                                    delay = self.exponential_backoff(attempt)
                                    msg = f"Throttling exception encountered. Retrying in {delay:.2f} seconds (attempt {attempt+1}/{self.max_retries})\n"
                                    logger.warning(msg)
                                    time.sleep(delay)
                                    attempt += 1
                                    attempt = min(attempt,2) ##最多退2步
                                    pool_attempt = 0 #重置一下
                                pool_attempt+=1
                                continue
                            else:
                                bedrock_client = self._get_bedrock_client()
                                if attempt < self.max_retries:
                                    delay = self.exponential_backoff(attempt)
                                    msg = f"Throttling exception encountered. Retrying in {delay:.2f} seconds (attempt {attempt+1}/{self.max_retries})\n"
                                    logger.warning(msg)
                                    # yield {"type": "error", "data": {"error":msg}}

                                    time.sleep(delay)
                                    attempt += 1
                                else:
                                    logger.error(f"Maximum retry attempts ({self.max_retries}) reached. Throttling persists.")
                                    raise Exception("Maximum retry attempts reached. Service is still throttling requests.")
                        else:
                            raise error
                        

                turn_i += 1
                # 收集所有需要调用的工具请求
                tool_calls = []
                async for event in self._process_stream_response(stream_id,response):
                    # logger.info(event)
                    if event['type'] == 'metadata':
                        tokens_need_cache += event['data']['usage']['inputTokens'] + event['data']['usage']['outputTokens']
                        logger.info(event)
                        logger.info(f"Tokens need cache: {tokens_need_cache}")
                        
                    yield event
                    # Handle tool use in content block start
                    if event["type"] == "block_start":
                        block_start = event["data"]
                        if "toolUse" in block_start.get("start", {}):
                            current_tool_use = block_start["start"]["toolUse"]
                            tool_calls.append(current_tool_use)
                            logger.info("Tool use detected: %s", current_tool_use)

                    if event["type"] == "block_delta":
                        delta = event["data"]
                        if "toolUse" in delta.get("delta", {}):
                            #Claude 是stream输出input，而Nova是一次性输出
                            #取出最近添加的tool,追加input参数
                            current_tool_use = tool_calls[-1]
                            if current_tool_use:
                                current_tooluse_input += delta["delta"]["toolUse"]["input"]
                                current_tool_use["input"] = current_tooluse_input 
                        if "text" in delta.get("delta", {}):
                            text += delta["delta"]["text"]
                        if "reasoningContent" in delta.get("delta", {}):
                            if 'signature' in delta["delta"]['reasoningContent']:
                                thinking_signature = delta["delta"]['reasoningContent']['signature']
                            if 'text' in delta["delta"]['reasoningContent']:
                                thinking_text += delta["delta"]['reasoningContent']["text"]
                            
                    # Handle tool use input in content block stop
                    if event["type"] == "block_stop":
                        if current_tooluse_input:
                            #取出最近添加的tool,把input str转成json
                            current_tool_use = tool_calls[-1]
                            if current_tool_use:
                                current_tool_use["input"] = json.loads(current_tooluse_input)
                                current_tooluse_input = ''

                    # Handle message stop and tool use
                    if event["type"] == "message_stop":     
                        stop_reason = event["data"]["stopReason"]
                        # Handle tool use if needed
                        if stop_reason == "tool_use" and tool_calls:
                            # 并行执行所有工具调用
                            async def execute_tool_call(tool):
                                logger.info("Call tool: %s" % tool)
                                try:
                                    tool_name, tool_args = tool['name'], tool['input']
                                    if tool_args == "":
                                        tool_args = {}
                                    #parse the tool_name
                                    server_id, llm_tool_name = MCPClient.get_tool_name4mcp(tool_name)
                                    mcp_client = mcp_clients.get(server_id)
                                    if mcp_client is None:
                                        raise Exception(f"mcp_client is None, server_id:{server_id}")
                                    
                                    result = await mcp_client.call_tool(llm_tool_name, tool_args)
                                    # logger.info(f"call_tool result:{result}")
                                    result_content = [{"text": "\n".join([x.text for x in result.content if x.type == 'text'])}]
                                    image_content =  [{"image":{"format":x.mimeType.replace('image/',''), "source":{"bytes":base64.b64decode(x.data)} } } for x in result.content if x.type == 'image']
                                    
                                    #content block for json serializable.
                                    image_content_base64 =  [{"image":{"format":x.mimeType.replace('image/',''), "source":{"base64":x.data} } } for x in result.content if x.type == 'image']

                                    return [{ 
                                                "toolUseId": tool['toolUseId'],
                                                "content": result_content+image_content
                                            },
                                            { 
                                                "toolUseId": tool['toolUseId'],
                                                "content": result_content
                                            },
                                            { 
                                                "toolUseId": tool['toolUseId'],
                                                "content": result_content+image_content_base64
                                            },
                                            ]
                                    
                                except Exception as err:
                                    err_msg = f"{tool['name']} tool call is failed. error:{err}"
                                    return [{
                                                "toolUseId": tool['toolUseId'],
                                                "content": [{"text": err_msg}],
                                                "status": 'error'
                                            }]*3
                            # 使用 asyncio.gather 并行执行所有工具调用
                            call_results = await asyncio.gather(*[execute_tool_call(tool) for tool in tool_calls])
                            # Correctly unpack the results - each call_result is a list of [tool_result, tool_text_result]
                            tool_results = []
                            tool_results_serializable = []
                            tool_text_results = []
                            for result in call_results:
                                tool_results.append(result[0])
                                tool_text_results.append(result[1])
                                tool_results_serializable.append(result[2])
                            logger.info(f'tool_text_results {tool_text_results[:100]}...')
                            # 处理所有工具调用的结果
                            tool_results_content = []
                            for tool_result in tool_results:
                                logger.info("Call tool result: Id: %s" % (tool_result['toolUseId']) )
                                tool_results_content.append({"toolResult": tool_result})
                            # save tool call result
                            tool_result_message = {
                                "role": "user",
                                "content": tool_results_content
                            }
                            if prompt_cache and tokens_need_cache >= cache_window:
                                if self.cache_checkpoint < 4:
                                    tool_result_message["content"] += [{"cachePoint": {"type": "default"}}]
                                    self.cache_checkpoint += 1
                                    logger.info(f"Write message cache: {tokens_need_cache}, checkpoint number :{self.cache_checkpoint}")
                                    tokens_need_cache = 0
                                else: # reset checkpoint
                                    messages = remove_cache_checkpoint(messages)
                                    tool_result_message["content"] += [{"cachePoint": {"type": "default"}}]
                                    self.cache_checkpoint = self.reset_checkpoint + 1
                                    logger.info(f"Reset prompt cache checkpoint to {self.reset_checkpoint}, Write message cache: {tokens_need_cache}, checkpoint number :{self.cache_checkpoint}")
                                    tokens_need_cache = 0
                                    
                            # output tool results
                            event["data"]["tool_results"] = [item for pair in zip(tool_calls, tool_results_serializable) for item in pair]
                            logger.info('yield event*****')
                            yield event
                            #append assistant message   
                            thinking_block = [{
                                "reasoningContent": 
                                    {
                                        "reasoningText":  {
                                            "text":thinking_text,
                                            "signature":thinking_signature
                                            }
                                    }
                            }]
                            
                            # tool_use_block = [{"toolUse":tool} for tool in tool_calls]
                            tool_use_block = []
                            for tool in tool_calls:
                                # if not json object, converse api will raise error
                                if tool['input'] == "":
                                    tool_use_block.append({"toolUse":{"name":tool['name'],"toolUseId":tool['toolUseId'],"input":{}}})
                                else:
                                    tool_use_block.append({"toolUse":tool})
             
                            
                            text_block = [{"text": text}] if text.strip() else []
                            assistant_message = {
                                "role": "assistant",
                                "content":   thinking_block+ tool_use_block + text_block if thinking_signature else text_block + tool_use_block
                            }     
                            # thinking_signature = ''
                            # thinking_text = ''
                            messages.append(assistant_message)

                                

                            #append tooluse result
                            messages.append(tool_result_message)
                            
                            if only_n_most_recent_images:
                                maybe_filter_to_n_most_recent_images(
                                    messages,
                                    only_n_most_recent_images,
                                    min_removal_threshold=image_truncation_threshold,
                            )

                            logger.info(f"Call new turn : message length:{len(messages)}")
                            
                            # Reset tool state
                            current_tool_use = None
                            
                            continue

                        # normal chat finished
                        elif stop_reason in ['end_turn','max_tokens','stop_sequence']:
                            # yield event
                            assistant_message = {
                                "role": "assistant",
                                "content":   [{"text": text}] if text.strip() else []
                            }    
                            messages.append(assistant_message)
                            turn_i = max_turns
                            continue

            except Exception as e:
                logger.error(f"Stream processing error: {e}")
                yield {"type": "error", "data": {"error": str(e)}}
                turn_i = max_turns
                break
        
        # Save the max history to session
        self.messages = messages
        self.system = system
        # Clean up the stop flag after streaming completes
        self.unregister_stream(stream_id)

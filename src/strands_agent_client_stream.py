"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
"""
Strands Agents SDK based streaming chat client
"""
import os
import sys
import asyncio
import logging
import json
import time
from typing import Dict, AsyncGenerator, Optional, List, AsyncIterator, Any
from dotenv import load_dotenv
from strands_agent_client import StrandsAgentClient
from mcp_client_strands import StrandsMCPClient
from utils import maybe_filter_to_n_most_recent_images, remove_cache_checkpoint
from constant import *
load_dotenv()  # load environment variables from .env

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
logger = logging.getLogger(__name__)

class StrandsAgentClientStream(StrandsAgentClient):
    """Extended Strands Agent Client with streaming support"""
    
    def __init__(self, credential_file='', user_id='',model_provider='bedrock', api_key='', api_base=None, 
                 access_key_id='', secret_access_key='', region=''):
        super().__init__(credential_file, user_id,access_key_id, secret_access_key, region, 
                        model_provider, api_key, api_base)
        # Stream-specific properties
        self.stop_flags = {}  # Dict to track stop flags for streams
        
    def register_stream(self, stream_id):
        """Register a new stream with a stop flag"""
        self.stop_flags[stream_id] = False
        logger.info(f"Registered stream: {stream_id}")
    
    def stop_stream(self, stream_id):
        """Set the stop flag for a stream to terminate it"""
        if stream_id in self.stop_flags:
            self.stop_flags[stream_id] = True
            logger.info(f"Stopping stream: {stream_id}")
            return True
        logger.warning(f"Attempted to stop unknown stream: {stream_id}")
        return False

    def unregister_stream(self, stream_id):
        """Clean up the stop flag after a stream completes"""
        if stream_id in self.stop_flags:
            del self.stop_flags[stream_id]
            logger.info(f"Unregistered stream: {stream_id}")
    
    async def _process_stream_response(self, stream_id:str,response) -> AsyncIterator[Dict]:
        """Process the raw response from converse_stream"""
        last_yield_time = time.time()
        async for chunk in response:
            # logger.info(chunk)
            if 'message' in chunk:
                message = chunk['message']
                if message.get('role') == 'user' and message.get('content'):
                    content = message['content']
                    for content_block in content:
                        if 'toolResult' in content_block:
                            toolUseId = content_block['toolResult']['toolUseId']
                            yield {"type": "toolResult", "toolUseId":toolUseId,"data": content_block['toolResult']}
                    
            elif 'event' in chunk:
                event = chunk['event']
                # logger.info(event)
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
            
    async def process_query_stream(self, 
            model_id="", max_tokens=1024, max_turns=30, temperature=0.1,
            messages=[], system=[], mcp_clients=None, mcp_server_ids=[], extra_params={}, keep_session=None,
            stream_id=None) -> AsyncGenerator[Dict, None]:
        """Submit user query or history messages, and get streaming response using Strands Agents SDK."""
        
        logger.info(f'client input message list length:{len(messages)}')
        if not messages:
            raise ValueError('empty message')
        # must be kept with Strands
        keep_session = True
        if keep_session:
            history = await self.load_history()
            if history:
                messages = history + messages 
            system = self.system if self.system else system #system 消息每次都会传入
        else:
            await self.clear_history()
            
        logger.info(f'llm input message list length:{len(messages)}')
        
        # Register this stream if an ID is provided
        if stream_id:
            self.register_stream(stream_id)
        
        # Convert system messages to system prompt
        system_prompt = ""
        if system:
            for item in system:
                if isinstance(item, dict) and "text" in item:
                    system_prompt += item["text"]
        
        # 添加用户id标志，用于mem0
        user_identity = f"\nHere is the request from User with user id:{self.user_id}\n"
        system_prompt += user_identity
        # Convert messages to Strands format
        # strands_messages = self._convert_messages_to_strands_format(messages)
        history_messages = messages[:-1]
        prompt = messages[-1]['content'][0]['text']
        thinking = extra_params.get('enable_thinking', False) and model_id in [CLAUDE_37_SONNET_MODEL_ID,CLAUDE_4_SONNET_MODEL_ID,CLAUDE_4_OPUS_MODEL_ID]
        thinking_budget = extra_params.get("budget_tokens",4096)
        max_tokens = max(thinking_budget + 1, max_tokens) if thinking else max_tokens
        # Create agent with MCP tools
        self.agent = await self._create_agent_with_tools(
            messages=history_messages,
            model_id=model_id,
            mcp_clients=mcp_clients,
            mcp_server_ids=mcp_server_ids,
            system_prompt=system_prompt,
            thinking=thinking,
            thinking_budget=thinking_budget,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        current_content = ""
        turn_i = 1
        stop_reason = ''
        tool_calls = []
        current_tool_use = None
        current_tooluse_input = ''
        thinking_text = ''
        text = ''
        only_n_most_recent_images = extra_params.get('only_n_most_recent_images', 3)
        image_truncation_threshold = only_n_most_recent_images or 0
        
        tool_calls = []
        tool_results_dict = {}
        # 记录已经发送过的tool result
        sent_results_history = {}
        response = self.agent.stream_async(prompt)
        async for event in self._process_stream_response(stream_id,response):
            # logger.info(event)
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
                    
            # Handle tool use input in content block stop
            if event["type"] == "block_stop":
                if current_tooluse_input:
                    #取出最近添加的tool,把input str转成json
                    current_tool_use = tool_calls[-1]
                    if current_tool_use:
                        current_tool_use["input"] = json.loads(current_tooluse_input)
                        current_tooluse_input = ''
                        
                        
            # Handle message stop and tool use
            if event["type"] == "toolResult":
                new_event = {}
                toolUseId = event['toolUseId']
                if toolUseId not in tool_results_dict:
                    tool_results_dict[toolUseId] = event['data']
                    # output tool results for UI
                    tool_results_serializable = [[tool,{"tool_name":tool['name'],"tool_result":tool_results_dict.get(tool['toolUseId'])}] for tool in tool_calls 
                                                    if tool_results_dict.get(tool['toolUseId']) and tool['toolUseId'] not in sent_results_history ]
                    # tool_results = [item for pair in zip(tool_calls, tool_results_serializable) for item in pair]
                    tool_results = [item for pair in tool_results_serializable for item in pair]
                    new_event = {'type':'result_pairs','data':{'stopReason':'tool_use','tool_results':tool_results}}
                    yield new_event
                    sent_results_history[toolUseId] = toolUseId
                    # logger.info(new_event)
                
            if event["type"] == "message_stop":     
                # Save the system to session
                self.system = system
                yield event

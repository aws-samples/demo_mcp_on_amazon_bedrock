"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
import os
import sys
import asyncio
import logging
import json
import time
import random
import base64
from typing import Dict, AsyncGenerator, Optional, List, AsyncIterator, Any, override
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import requests
from openai import OpenAI
from chat_client_stream import ChatClientStream
from chat_client import ChatClient

from mcp_client import MCPClient
from utils import maybe_filter_to_n_most_recent_images, remove_cache_checkpoint

load_dotenv()  # load environment variables from .env

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
logger = logging.getLogger(__name__)

class CompatibleChatClientStream(ChatClient):
    """Extended ChatClient with OpenAI v1/chat/completions API compatibility"""
    
    def __init__(self, credential_file='', api_key='', api_base=None):
        super().__init__(credential_file)
        self.api_key = api_key or os.environ.get('COMPATIBLE_API_KEY')
        self.api_base = api_base or os.environ.get('COMPATIBLE_API_BASE')
        self.max_retries = 10  # Maximum number of retry attempts
        self.base_delay = 10  # Initial backoff delay in seconds
        self.max_delay = 60  # Maximum backoff delay in seconds
        self.client_index = 0
        self.stop_flags = {}  # Dict to track stop flags for streams
        # Initialize the OpenAI client
        
        self.openai_client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        ) if self.api_base else OpenAI(
            api_key=self.api_key
        )
        
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

            
    async def _process_openai_stream_response(self,stream_id:str, stream_response) -> AsyncIterator[Dict]:
        """Process streaming response from OpenAI SDK format"""
        try:
            # For SDK streamed responses, we iterate through the chunks
            tool_index=0
            last_yield_time = time.time()
            for chunk in stream_response:
                current_time = time.time()
                if current_time - last_yield_time > 0.1:  # 每100ms让出一次控制权，避免阻塞
                    await asyncio.sleep(0.001)
                    last_yield_time = current_time
                
                if stream_id and stream_id in self.stop_flags and self.stop_flags[stream_id]:
                    logger.info(f"Stream {stream_id} was requested to stop")
                    yield {"type": "stopped", "data": {"message": "Stream stopped by user request"}}
                    break
                    
                # Process each chunk from the stream
                if hasattr(chunk, 'choices') and chunk.choices:
                    choice = chunk.choices[0]
                    # logger.info(choice)
                    
                    # Initial role message
                    if hasattr(choice, 'delta') and hasattr(choice.delta, 'role'):
                        yield {"type": "message_start", "data": {"role": choice.delta.role}}
                    
                    # Content delta
                    if hasattr(choice, 'delta') and hasattr(choice.delta, 'content') and choice.delta.content is not None:
                        content = choice.delta.content
                        if content:
                            yield {
                                "type": "block_delta",
                                "data": {"delta": {"text": content}}
                            }
                            
                    # Thinking delta
                    if hasattr(choice, 'delta') and hasattr(choice.delta, 'reasoning_content') and choice.delta.reasoning_content is not None:
                        content = choice.delta.reasoning_content
                        if content:
                            yield {
                                "type": "block_delta",
                                "data": {"delta": {"reasoningContent": {"text": content}}}
                            }
                            
                    # Tool calls
                    if hasattr(choice, 'delta') and hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                        for tool_call in choice.delta.tool_calls:
                            if hasattr(tool_call,'index'):
                                # 如果index变化，说明是新的tool call，需要发送一个block stop标志
                                if not tool_index == tool_call.index:
                                    tool_index = tool_call.index
                                    yield {
                                        "type": "block_stop",
                                        "data":{}
                                    }
                                    
                            if hasattr(tool_call, 'function'):
                                function = tool_call.function
                                
                                if hasattr(function, 'name') and function.name:
                                    # Tool use start
                                    yield {
                                        "type": "block_start",
                                        "data": {
                                            "start": {
                                                "toolUse": {
                                                    "name": function.name,
                                                    "toolUseId": tool_call.id,
                                                    "input": ""
                                                }
                                            }
                                        }
                                    }
                                
                                if hasattr(function, 'arguments') and function.arguments:
                                    # Tool input delta
                                    yield {
                                        "type": "block_delta",
                                        "data": {
                                            "delta": {
                                                "toolUse": {
                                                    "input": function.arguments
                                                }
                                            }
                                        }
                                    }
                    
                    # Finish reason
                    if hasattr(choice, 'finish_reason') and choice.finish_reason:
                        yield {
                                "type": "block_stop",
                                "data":{}
                            }
                        if choice.finish_reason == 'tool_calls':
                            yield {"type": "message_stop", "data": {"stopReason": "tool_use"}}
                        else:
                            yield {"type": "message_stop", "data": {"stopReason": choice.finish_reason}}
                
                # Usage and metadata - this might come in the final chunk
                if hasattr(chunk, 'usage'):
                    yield {
                        "type": "metadata",
                        "data": {
                            "usage": {
                                "inputTokens": chunk.usage.prompt_tokens if hasattr(chunk.usage, 'prompt_tokens') else 0,
                                "outputTokens": chunk.usage.completion_tokens if hasattr(chunk.usage, 'completion_tokens') else 0
                            }
                        }
                    }
            
            # End of stream
            yield {"type": "message_stop", "data": {"stopReason": "end_turn"}}
            
        except Exception as e:
            logger.error(f"Error processing OpenAI stream response: {e}")
            yield {"type": "error", "data": {"error": str(e)}}
    
    def _convert_messages_to_openai_format(self, messages, system=None):
        """Convert Bedrock message format to OpenAI format"""
        openai_messages = []
        
        # Add system message if provided
        if system:
            system_text = ""
            for item in system:
                if isinstance(item, dict) and "text" in item:
                    system_text += item["text"]
            if system_text:
                openai_messages.append({"role": "system", "content": system_text})
        
        # Process other messages
        for message in messages:
            role = message.get("role", "user")
            content = []
            tool_calls = []
            
            if isinstance(message.get("content"), list):
                for item in message["content"]:
                    if isinstance(item, dict):
                        # Handle text content
                        if "text" in item:
                            content.append({"type": "text", "text": item["text"]})
                        
                        # Handle image content
                        elif "image" in item and "source" in item["image"]:
                            img_source = item["image"]["source"]
                            if "bytes" in img_source:
                                img_base64 = base64.b64encode(img_source["bytes"]).decode('utf-8')
                                img_format = item["image"].get("format", "png")
                                content.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/{img_format};base64,{img_base64}"
                                    }
                                })
                        
                        # Handle tool results
                        elif "toolResult" in item:
                            # OpenAI uses tool_calls and tool_call_id
                            tool_result = item["toolResult"]
                            tool_id = tool_result.get("toolUseId", "")
                            tool_content = []
                            
                            for content_item in tool_result.get("content", []):
                                if "text" in content_item:
                                    tool_content.append(content_item["text"])
                            
                            openai_messages.append({
                                "role": "tool",
                                "content": "\n".join(tool_content),
                                "tool_call_id": tool_id
                            })
                            continue  # Skip adding this as part of regular message
                        
                        # Handle toolUse from assistant
                        elif "toolUse" in item and role == "assistant":
                            tool_use = item["toolUse"]
                            tool_id = tool_use.get("toolUseId", "")
                            tool_name = tool_use.get("name", "")
                            tool_input = tool_use.get("input", {})
                            
                            # Convert to OpenAI tool_calls format
                            tool_calls.append({
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(tool_input) if isinstance(tool_input, dict) else tool_input
                                }
                            })
            
            # If we have content as a list of objects, convert to OpenAI format
            if content:
                if role == "assistant" and tool_calls:
                    # If assistant has both content and tool calls
                    openai_messages.append({
                        "role": role, 
                        "content": content,
                        "tool_calls": tool_calls
                    })
                else:
                    openai_messages.append({"role": role, "content": content})
            # If assistant with only tool calls (no text content)
            elif role == "assistant" and tool_calls:
                openai_messages.append({
                    "role": role,
                    "content": "",
                    "tool_calls": tool_calls
                })
            # Otherwise if content is a single string
            elif isinstance(message.get("content"), str):
                openai_messages.append({"role": role, "content": message["content"]})
            # If we have an empty content list (indicating this is a toolResult message we already processed)
            elif not content and not any(item.get("toolResult") for item in message.get("content", [])) and not any(item.get("toolUse") for item in message.get("content", [])):
                openai_messages.append({"role": role, "content": ""})
        
        return openai_messages
    
    def _convert_tools_config(self, tools_config):
        """Convert Bedrock tool config to OpenAI format"""
        openai_tools = []
        
        if not tools_config or "tools" not in tools_config:
            return openai_tools
        
        for tool in tools_config["tools"]:
            if "toolSpec" in tool:
                spec = tool["toolSpec"]
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": spec["name"],
                        "description": spec.get("description", ""),
                        "parameters": json.loads(spec["inputSchema"]["json"]) if isinstance(spec["inputSchema"]["json"], str) else spec["inputSchema"]["json"]
                    }
                })
        
        return openai_tools
    
    async def process_query_stream(self, 
            model_id="", max_tokens=1024, max_turns=30, temperature=0.1,
            messages=[], system=[], mcp_clients=None, mcp_server_ids=[], extra_params={},keep_session=None,
            stream_id=None) -> AsyncGenerator[Dict, None]:
        """Submit user query or history messages, and get streaming response using OpenAI API.
        
        Similar to process_query but uses OpenAI v1/chat/completions API for streaming responses.
        """
        logger.info(f'client input message list length:{len(messages)}')

        if keep_session:
            messages = self.messages + messages
            system = self.system if self.system else system
        else:
            self.clear_history()
            
        logger.info(f'llm input message list length:{len(messages)}')

        # get tools from mcp server
        tool_config = {"tools": []}
        if mcp_clients is not None:
            for mcp_server_id in mcp_server_ids:
                tool_config_response = await mcp_clients[mcp_server_id].get_tool_config(server_id=mcp_server_id)
                tool_config['tools'].extend(tool_config_response["tools"])
        logger.info(f"Tool config: {tool_config}")
        
        # Register this stream if an ID is provided
        if stream_id:
            self.register_stream(stream_id)
        
        # Convert Bedrock format to OpenAI format
        openai_messages = self._convert_messages_to_openai_format(messages, system)
        openai_tools = self._convert_tools_config(tool_config)
        
        # Convert Bedrock request parameters to OpenAI parameters
        request_payload = {
            "model": model_id,
            "messages": openai_messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        
        # Add tools if we have any
        if openai_tools:
            request_payload["tools"] = openai_tools
            request_payload["tool_choice"] = "auto"
        
        # Handle other parameters like top_p, etc.
        if extra_params:
            if "top_p" in extra_params:
                request_payload["top_p"] = extra_params["top_p"]
            if "top_k" in extra_params:
                request_payload["top_logprobs"] = extra_params["top_k"]  # Not exact equivalent, but similar concept
        
        current_content = ""
        thinking_text = ""
        thinking_signature = ""
        tooluse_start = False
        turn_i = 1
        stop_reason = ''
        tool_calls = []
        current_tool_use = None
        current_tooluse_input = ''
        
        only_n_most_recent_images = extra_params.get('only_n_most_recent_images', 3)
        image_truncation_threshold = only_n_most_recent_images or 0
        
        while turn_i <= max_turns and stop_reason != 'end_turn':
            # Check if we need to stop
            if stream_id and stream_id in self.stop_flags and self.stop_flags[stream_id]:
                logger.info(f"Stream {stream_id} was requested to stop")
                yield {"type": "stopped", "data": {"message": "Stream stopped by user request"}}
                break
                
            try:
                # Make the API request using the OpenAI SDK directly
                response = self.openai_client.chat.completions.create(**request_payload)
                
                # Process the streaming response
                async for event in self._process_openai_stream_response(stream_id,response):
                    # logger.info(event)
                    # Forward the event to the caller
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
                            # Streaming tool input from OpenAI
                            current_tool_use = tool_calls[-1]
                            if current_tool_use:
                                current_tooluse_input += delta["delta"]["toolUse"]["input"]
                                current_tool_use["input"] = current_tooluse_input 
                        if "text" in delta.get("delta", {}):
                            current_content += delta["delta"]["text"]
                            
                        if "reasoningContent" in delta.get("delta", {}):
                            if 'text' in delta["delta"]['reasoningContent']:
                                thinking_text += delta["delta"]['reasoningContent']["text"]
                                
                    # Handle tool use input in content block stop
                    if event["type"] == "block_stop":
                        if current_tooluse_input:
                            #取出最近添加的tool,把input str转成json
                            # logger.info(current_tooluse_input)
                            current_tool_use = tool_calls[-1]
                            if current_tool_use:
                                current_tool_use["input"] = json.loads(current_tooluse_input)
                                current_tooluse_input = ''
                            
                    # Handle message stop and tool use
                    if event["type"] == "message_stop":     
                        stop_reason = event["data"]["stopReason"]
                        
                        # Handle tool use if needed
                        if stop_reason == "tool_use" and tool_calls:
                            # Parse any remaining tool input as JSON
                            for tool in tool_calls:
                                if isinstance(tool.get("input"), str) and tool["input"].strip():
                                    try:
                                        tool["input"] = json.loads(tool["input"])
                                    except json.JSONDecodeError:
                                        logger.error(f"Failed to parse tool input as JSON: {tool['input']}")
                            
                            # Execute all tool calls in parallel
                            async def execute_tool_call(tool):
                                logger.info("Call tool: %s" % tool)
                                try:
                                    tool_name, tool_args = tool['name'], tool['input']
                                    if tool_args == "":
                                        tool_args = {}
                                    # Parse the tool name
                                    server_id, llm_tool_name = MCPClient.get_tool_name4mcp(tool_name)
                                    mcp_client = mcp_clients.get(server_id)
                                    if mcp_client is None:
                                        raise Exception(f"mcp_client is None, server_id:{server_id}")
                                    
                                    result = await mcp_client.call_tool(llm_tool_name, tool_args)
                                    result_content = [{"text": "\n".join([x.text for x in result.content if x.type == 'text'])}]
                                    image_content = [{"image":{"format":x.mimeType.replace('image/',''), "source":{"bytes":base64.b64decode(x.data)} } } for x in result.content if x.type == 'image']
                                    
                                    # Content block for json serializable
                                    image_content_base64 = [{"image":{"format":x.mimeType.replace('image/',''), "source":{"base64":x.data} } } for x in result.content if x.type == 'image']

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
                                            }]
                                except Exception as err:
                                    err_msg = f"{tool['name']} tool call is failed. error:{err}"
                                    return [{
                                                "toolUseId": tool['toolUseId'],
                                                "content": [{"text": err_msg}],
                                                "status": 'error'
                                            }]*3
                            
                            # Execute all tool calls in parallel
                            call_results = await asyncio.gather(*[execute_tool_call(tool) for tool in tool_calls])
                            
                            tool_results = []
                            tool_results_serializable = []
                            tool_text_results = []
                            for result in call_results:
                                tool_results.append(result[0])
                                tool_text_results.append(result[1])
                                tool_results_serializable.append(result[2])
                            
                            # Process all tool call results
                            tool_results_content = []
                            for tool_result in tool_results:
                                logger.info("Call tool result: Id: %s" % (tool_result['toolUseId']))
                                tool_results_content.append({"toolResult": tool_result})
                            
                            # Create tool result message
                            tool_result_message = {
                                "role": "user",
                                "content": tool_results_content
                            }
                            
                            # Output tool results
                            event["data"]["tool_results"] = [item for pair in zip(tool_calls, tool_results_serializable) for item in pair]
                            yield event
                            
                            # Create assistant message
                            tool_use_block = []
                            for tool in tool_calls:
                                # If not JSON object, API will raise error
                                if tool['input'] == "":
                                    tool_use_block.append({"toolUse":{"name":tool['name'],"toolUseId":tool['toolUseId'],"input":{}}})
                                else:
                                    tool_use_block.append({"toolUse":tool})
                            
                            text_block = [{"text": current_content}] if current_content.strip() else []
                            assistant_message = {
                                "role": "assistant",
                                "content": text_block + tool_use_block
                            }
                            
                            # Update messages with assistant and tool result messages
                            messages.append(assistant_message)
                            messages.append(tool_result_message)
                            
                            # Filter images if needed
                            if only_n_most_recent_images:
                                maybe_filter_to_n_most_recent_images(
                                    messages,
                                    only_n_most_recent_images,
                                    min_removal_threshold=image_truncation_threshold,
                                )
                            
                            # logger.info(f"before convert:{messages}")
                            # Update OpenAI messages format for the next request
                            openai_messages = self._convert_messages_to_openai_format(messages, system)
                            request_payload["messages"] = openai_messages
                            # logger.info(openai_messages)
                            
                            # Reset state
                            current_content = ""
                            current_tool_use = None
                            current_tooluse_input = ""
                            tool_calls = []
                            thinking_text = ""
                            thinking_signature = ""
                            
                            # Continue to next turn (retry the outer loop)
                            turn_i += 1
                            break
                            
                        # Normal chat finished
                        elif stop_reason in ['end_turn', 'stop', 'length']:
                            # Map OpenAI finish reasons to Bedrock stop reasons
                            if stop_reason == 'stop':
                                stop_reason = 'end_turn'
                            elif stop_reason == 'length':
                                stop_reason = 'max_tokens'
                                
                            # End streaming
                            turn_i = max_turns + 1  # Exit the loop
                            continue
                
            except Exception as e:
                logger.error(f"Stream processing error: {e}")
                yield {"type": "error", "data": {"error": str(e)}}
                turn_i = max_turns + 1
                break
                
        # Save the max history to session
        self.messages = messages
        self.system = system
        # Clean up the stop flag after streaming completes
        self.unregister_stream(stream_id)
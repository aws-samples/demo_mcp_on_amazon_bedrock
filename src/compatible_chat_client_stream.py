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
from compatible_chat_client import CompatibleChatClient
from deepseek_r1_client import *
import re

from mcp_client import MCPClient
from utils import maybe_filter_to_n_most_recent_images, remove_cache_checkpoint

load_dotenv()  # load environment variables from .env

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
logger = logging.getLogger(__name__)

#Now deepseek-r1-0528 has supported tool use, skip the PE function call
TOOL_USE_SUPPORT = False

class CompatibleChatClientStream(CompatibleChatClient):
    """Extended ChatClient with OpenAI v1/chat/completions API compatibility for streaming"""
    
    def __init__(self, credential_file='', api_key='', api_base=None, access_key_id='', secret_access_key='', region=''):
        super().__init__(credential_file, access_key_id, secret_access_key, region, api_key, api_base)
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
            
    async def _process_openai_stream_response(self, stream_id:str, stream_response, model_id) -> AsyncIterator[Dict]:
        """Process streaming response from OpenAI SDK format"""
        # transform chunk data and extract infomation from it
        r1_status = "running"
        r1_text_response = ""
        r1_content = ""
        txt_tmp = ""
        outputing_text = True
        
        while True:
            try:
                # For SDK streamed responses, we iterate through the chunks
                tool_index=0
                last_yield_time = time.time()
                for chunk in stream_response:
                    current_time = time.time()
                    if current_time - last_yield_time > 0.1:  # 每100ms让出一次控制权，避免阻塞
                        await asyncio.sleep(0.001)
                        last_yield_time = current_time
                
                    # Process stream termination
                    if stream_id and stream_id in self.stop_flags and self.stop_flags[stream_id]:
                        logger.info(f"Stream {stream_id} was requested to stop")
                        yield {"type": "stopped", "data": {"message": "Stream stopped by user request"}}
                        break
                
                    # Process deepseek-r1 chunk
                    if "deepseek-r1" in model_id.lower() and not TOOL_USE_SUPPORT:
                        if hasattr(chunk, 'choices') and chunk.choices:
                            choice = chunk.choices[0]

                            # Initial role message
                            # Generate this msg for every chunk
                            if hasattr(choice, 'delta') and hasattr(choice.delta, 'role'):
                                yield {"type": "message_start", "data": {"role": choice.delta.role}}
                        
                            # Thinking delta
                            if hasattr(choice, 'delta') and hasattr(choice.delta, 'reasoning_content') and choice.delta.reasoning_content is not None:
                                think_content = choice.delta.reasoning_content
                                if think_content:
                                    yield {
                                    "type": "block_delta",
                                    "data": {"delta": {"reasoningContent": {"text": think_content}}}
                                }
                        
                            # Content delta
                            if hasattr(choice, 'delta') and hasattr(choice.delta, 'content') and choice.delta.content is not None:
                                answer = choice.delta.content
                                # logger.info(f"Chunk content: {answer}")
        
                                # Collect all "content" values for extracting tool-use command
                                # pay attention to the sequence of code execution, it counts
                                if choice.delta.content:
                                    r1_content += answer

                                # Check if text response ends
                                if answer and "<" in answer and outputing_text and not txt_tmp:
                                    # Handle senario that <t> is outputed separately in two chunks: first <, then t>
                                    # 1. Handle senario like </html> as the final output
                                    # 2. txt_tmp is empty, but < output appears as part of <t> or <tr>
                                    # 3. txt_tmp is not empty which means < in it. Concat two chunks and check whether <t> is in
                                    if txt_tmp == "" and choice.finish_reason == "stop":
                                        # logger.info(f"Answer text: {answer}")
                                        outputing_text = False
                                        yield {"type": "block_delta", "data": {"delta": {"text": answer}}}
                                    elif txt_tmp == "":
                                        txt_tmp += answer
                                elif txt_tmp and outputing_text:
                                    txt_tmp += answer
                                    if "<t>" in txt_tmp:
                                        match = re.search(r"(.*)<t>", txt_tmp, re.DOTALL)
                                        match_chunk_text = match.group(1)
                                        r1_text_response += match_chunk_text
                                        outputing_text = False
                                        logger.info(f"Last answer before tool: {match_chunk_text}")
                                        if match_chunk_text: yield {"type": "block_delta", "data": {"delta": {"text": match_chunk_text}}}
                                    elif "<t>" not in txt_tmp:
                                        # logger.info(f"Answer text: {txt_tmp}")
                                        yield {"type": "block_delta", "data": {"delta": {"text": txt_tmp}}}
                                    txt_tmp = ""
                                elif answer and outputing_text:
                                    # logger.info(f"Answer text: {answer}")
                                    yield {"type": "block_delta", "data": {"delta": {"text": answer}}}
                                
                                # check whether there is a tool_call
                                # if tool call exists, extract and return
                                if choice.finish_reason == "stop":
                                    if "<t>" in r1_content:
                                        extracted_toolcall = re.search("<t>(.*?)</t>", r1_content.strip(), re.DOTALL).group(1)
                                        dict_r1_content = json.loads(extracted_toolcall)
                                        if dict_r1_content["tool_calls"]: 
                                            r1_status = "tool_calls"
                                        else:
                                            r1_status = "regular_stop"
                                    else:
                                        r1_status = "regular_stop"
                                
                                    if r1_status == "tool_calls":
                                        func_name = dict_r1_content["tool_calls"][0]["tool_name"]
                                        func_id = uuid.uuid4().hex
                                        func_input = dict_r1_content["tool_calls"][0]["parameters"]  # dict
                                        # Return tool name
                                        yield {
                                    "type": "block_start",
                                        "data": {
                                            "start": {
                                                "toolUse": {
                                                    "name": func_name,
                                                    "toolUseId": func_id,
                                                    "input": ""
                                                }
                                            }
                                        }
                                    }
                                        # Return tool input
                                        yield {
                                    "type": "block_delta",
                                        "data": {
                                            "delta": {
                                                "toolUse": {
                                                    "input": json.dumps(func_input)   # convert dict to json string for subsequent processing
                                                }
                                            }
                                        }
                                    }
                                        # Block stop
                                        yield {"type": "block_stop", "data":{}}
                                        yield {"type": "message_stop", "data": {"stopReason": "tool_use"}}
                                    elif r1_status == "regular_stop":
                                        # Block stop
                                        yield {"type": "block_stop", "data":{}}
                                        yield {"type": "message_stop", "data": {"stopReason": "stop"}}

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
                    else:
                        # Process each chunk from the stream (for tool-use supporting models)
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
                logger.info("LLM Response finished")
                break
            
            except Exception as e:
                logger.error(f"Error processing OpenAI stream response: {e}")
                yield {"type": "error", "data": {"error": str(e)}}
    
    async def process_query_stream(self, 
            model_id="", max_tokens=1024, max_turns=30, temperature=0.1,
            messages=[], system=[], mcp_clients=None, mcp_server_ids=[], extra_params={}, keep_session=None,
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
        tool_config = {'tools': []}
        if mcp_clients is not None:
            for mcp_server_id in mcp_server_ids:
                tool_config_response = await mcp_clients[mcp_server_id].get_tool_config(server_id=mcp_server_id)
                tool_config['tools'].extend(tool_config_response["tools"])
        #logger.info(f"Tool config: {tool_config}")
        
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
                response = deepseek_r1_chat_stream(**request_payload) if "deepseek-r1" in model_id.lower() and not TOOL_USE_SUPPORT else self.openai_client.chat.completions.create(**request_payload)
                
                # Process the streaming response
                # yield twice (event+tool_result)
                async for event in self._process_openai_stream_response(stream_id, response, model_id):
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
                            # Parse the tool input JSON if it's a string
                            current_tool_use = tool_calls[-1]
                            if current_tool_use and current_tooluse_input.strip():
                                try:
                                    current_tool_use["input"] = json.loads(current_tooluse_input)
                                except json.JSONDecodeError:
                                    logger.error(f"Failed to parse tool input as JSON: {current_tooluse_input}")
                                current_tooluse_input = ''
                            
                    # Handle message stop and tool use
                    if event["type"] == "message_stop":     
                        stop_reason = event["data"]["stopReason"]
                        
                        # Handle tool use if needed
                        if stop_reason == "tool_use" and tool_calls:
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
                            
                            # Update OpenAI messages format for the next request
                            openai_messages = self._convert_messages_to_openai_format(messages, system)
                            # logger.info(openai_messages)
                            request_payload["messages"] = openai_messages
                            
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

"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
import os
import asyncio
import logging
import json
import base64
from typing import Dict, AsyncGenerator, List, Any
from dotenv import load_dotenv
from openai import OpenAI
from chat_client import ChatClient
from mcp_client import MCPClient
from utils import maybe_filter_to_n_most_recent_images

load_dotenv()  # load environment variables from .env

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
logger = logging.getLogger(__name__)

class CompatibleChatClient(ChatClient):
    """Bedrock chat wrapper compatible with OpenAI v1/chat/completions API"""

    def __init__(self, credential_file='', access_key_id='', secret_access_key='', region='', api_key='', api_base=None):
        # Initialize the parent ChatClient
        super().__init__(credential_file, access_key_id, secret_access_key, region)
        
        # Initialize OpenAI client
        self.api_key = api_key or os.environ.get('COMPATIBLE_API_KEY')
        self.api_base = api_base or os.environ.get('COMPATIBLE_API_BASE')
        
        # Additional properties for retries and error handling
        self.max_retries = 10  # Maximum number of retry attempts
        self.base_delay = 10  # Initial backoff delay in seconds
        self.max_delay = 60  # Maximum backoff delay in seconds
        
        # Create OpenAI client with custom base URL if provided
        if self.api_base:
            self.openai_client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
        else:
            self.openai_client = OpenAI(
                api_key=self.api_key
            )
    
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
    
    def _convert_openai_response_to_bedrock_format(self, response, model_id):
        """Convert OpenAI response to Bedrock format"""
        message = response.choices[0].message
        
        # Extract content
        content = []
        
        # Handle text content
        if message.content:
            content.append({"text": message.content})
        
        # Handle tool calls
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.type == "function":
                    # Parse arguments from JSON string to dict if needed
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        tool_args = tool_call.function.arguments
                        
                    content.append({
                        "toolUse": {
                            "name": tool_call.function.name,
                            "toolUseId": tool_call.id,
                            "input": tool_args
                        }
                    })
        
        # Convert stop reason
        stop_reason = "end_turn"
        if response.choices[0].finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif response.choices[0].finish_reason in ["length", "content_filter"]:
            stop_reason = "max_tokens"
        
        # Create Bedrock-style response structure
        bedrock_response = {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": content
                }
            },
            "stopReason": stop_reason,
            "modelId": model_id,
        }
        
        # Add usage info if available
        if hasattr(response, "usage"):
            bedrock_response["usage"] = {
                "inputTokens": getattr(response.usage, "prompt_tokens", 0),
                "outputTokens": getattr(response.usage, "completion_tokens", 0),
                "totalTokens": getattr(response.usage, "total_tokens", 0)
            }
            
        return bedrock_response
    
    async def process_query(self, 
            model_id="gpt-4o", max_tokens=1024, temperature=0.1, max_turns=30,
            messages=[], system=[], mcp_clients=None, mcp_server_ids=[], extra_params={}, keep_session=None) -> AsyncGenerator[Dict, None]:
        """Submit user query or history messages, and then get the response answer.
        
        This implementation uses OpenAI's API instead of Bedrock.
        """
        if keep_session:
            messages = self.messages + messages
            system = self.system if self.system else system
        else:
            self.clear_history()
            
        logger.info(f'llm input message list length: {len(messages)}')
        
        # Get tools from MCP server
        tool_config = {"tools": []}
        if mcp_clients is not None:        
            for mcp_server_id in mcp_server_ids:
                tool_config_response = await mcp_clients[mcp_server_id].get_tool_config(server_id=mcp_server_id)
                if tool_config_response:
                    tool_config['tools'].extend(tool_config_response["tools"])

        logger.info(f"tool_config: {tool_config}")
        
        # Convert Bedrock format to OpenAI format
        openai_messages = self._convert_messages_to_openai_format(messages, system)
        openai_tools = self._convert_tools_config(tool_config)
        
        # Process image filtering if needed
        only_n_most_recent_images = extra_params.get('only_n_most_recent_images', 3)
        image_truncation_threshold = only_n_most_recent_images or 0
        if only_n_most_recent_images:
            maybe_filter_to_n_most_recent_images(
                messages,
                only_n_most_recent_images,
                min_removal_threshold=image_truncation_threshold,
            )
        
        # Convert Bedrock request parameters to OpenAI parameters
        request_payload = {
            "model": model_id,
            "messages": openai_messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        if model_id.startswith('o3') or model_id.startswith('o4') :
            request_payload['reasoning_effort'] = 'high'
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
                
        turn_i = 1
        while turn_i <= max_turns:
            try:
                # Make the API request using the OpenAI SDK
                response = self.openai_client.chat.completions.create(**request_payload)
                
                # Convert OpenAI response to Bedrock format
                bedrock_response = self._convert_openai_response_to_bedrock_format(response, model_id)
                
                # Extract message and add to history
                output_message = bedrock_response['output']['message']
                messages.append(output_message)
                stop_reason = bedrock_response['stopReason']
                
                if stop_reason == 'end_turn':
                    # Normal chat finished
                    yield output_message
                    break
                elif stop_reason == 'tool_use' and mcp_clients is not None:
                    # Return tool request use
                    yield output_message
                    
                    # Handle tool use
                    tool_requests = output_message['content']
                    
                    # Collect all tool requests
                    tool_calls = []
                    for tool_request in tool_requests:
                        if 'toolUse' in tool_request:
                            tool = tool_request['toolUse']
                            tool_calls.append(tool)
                    
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
                            
                            # Include serializable version for logging/debugging
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
                    
                    # Use asyncio.gather to execute all tool calls in parallel
                    call_results = await asyncio.gather(*[execute_tool_call(tool) for tool in tool_calls])
                    
                    tool_results = []
                    tool_text_results = []
                    tool_results_serializable = []
                    for result in call_results:
                        tool_results.append(result[0])
                        tool_text_results.append(result[1])
                        tool_results_serializable.append(result[2])
                                            
                    # Process all tool call results
                    tool_results_content = []
                    for tool_result in tool_results:
                        logger.info("Call tool result: Id: %s" % (tool_result['toolUseId']))
                        tool_results_content.append({"toolResult": tool_result})
                    
                    # Save tool call result
                    tool_result_message = {
                        "role": "user",
                        "content": tool_results_content
                    }
                    messages.append(tool_result_message)
                    
                    # Return tool use results
                    yield tool_result_message
                    
                    # Update OpenAI messages for the next request
                    openai_messages = self._convert_messages_to_openai_format(messages, system)

                    request_payload["messages"] = openai_messages
                    
                    # Filter images if needed after tool calls
                    if only_n_most_recent_images:
                        maybe_filter_to_n_most_recent_images(
                            messages,
                            only_n_most_recent_images,
                            min_removal_threshold=image_truncation_threshold,
                        )
                    
                    turn_i += 1
                    
                else:
                    # Unexpected stop reason
                    yield output_message
                    break
                    
            except Exception as e:
                logger.error(f"Error processing request: {str(e)}")
                error_message = {
                    "role": "assistant", 
                    "content": [{"text": f"Error: {str(e)}"}]
                }
                yield error_message
                break
        
        # Save session history
        if keep_session:
            self.messages = messages
            self.system = system

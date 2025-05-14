"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
"""
Amazon Nova Sonic speech-to-speech streaming manager for real-time audio processing
"""
import os
import asyncio
import base64
import json
import uuid
import warnings
import pyaudio
import queue
import datetime
import time
import inspect
import io
import numpy as np
from mcp_client import MCPClient
from rx.subject import Subject
from rx import operators as ops
from rx.scheduler.eventloop import AsyncIOScheduler
from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
from aws_sdk_bedrock_runtime.config import Config, HTTPAuthSchemeResolver, SigV4AuthScheme
from smithy_aws_core.credentials_resolvers.environment import EnvironmentCredentialsResolver
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
# Initialize logger
logger = logging.getLogger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore")

# Audio configuration
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_SIZE = 512  # Number of frames per buffer

# Debug mode flag
DEBUG = False

def debug_print(message):
    """Print only if debug mode is enabled"""
    if DEBUG:
        functionName = inspect.stack()[1].function
        if  functionName == 'time_it' or functionName == 'time_it_async':
            functionName = inspect.stack()[2].function
        print('{:%Y-%m-%d %H:%M:%S.%f}'.format(datetime.datetime.now())[:-3] + ' ' + functionName + ' ' + message)

def time_it(label, methodToRun):
    start_time = time.perf_counter()
    result = methodToRun()
    end_time = time.perf_counter()
    debug_print(f"Execution time for {label}: {end_time - start_time:.4f} seconds")
    return result

async def time_it_async(label, methodToRun):
    start_time = time.perf_counter()
    result = await methodToRun()
    end_time = time.perf_counter()
    debug_print(f"Execution time for {label}: {end_time - start_time:.4f} seconds")
    return result

# Audio processing functions to improve quality
def smooth_pcm_data(pcm_data, window_size=3):
    """Apply a simple moving average filter to smooth PCM data"""
    if len(pcm_data) <= window_size:
        return pcm_data
        
    # Convert to int16 array for processing
    int16_data = np.frombuffer(pcm_data, dtype=np.int16)
    smoothed = np.zeros_like(int16_data)
    
    # Apply moving average filter
    for i in range(len(int16_data)):
        start = max(0, i - window_size // 2)
        end = min(len(int16_data), i + window_size // 2 + 1)
        smoothed[i] = int(np.mean(int16_data[start:end]))
    
    return smoothed.tobytes()

def normalize_pcm_data(pcm_data, target_level=0.9):
    """Normalize PCM data to target level to prevent clipping"""
    int16_data = np.frombuffer(pcm_data, dtype=np.int16)
    
    # Find max amplitude
    max_amp = np.max(np.abs(int16_data))
    if max_amp == 0:
        return pcm_data
        
    # Calculate target amplitude (90% of max int16)
    target_amp = 32767 * target_level
    
    # If already below target, return original
    if max_amp <= target_amp:
        return pcm_data
        
    # Apply gain
    gain = target_amp / max_amp
    normalized = (int16_data * gain).astype(np.int16)
    
    return normalized.tobytes()

class BedrockStreamManager:
    """Manages bidirectional streaming with AWS Bedrock using RxPy for event processing"""
    
    # Event templates
    START_SESSION_EVENT = '''{
        "event": {
            "sessionStart": {
            "inferenceConfiguration": {
                "maxTokens": 4096,
                "topP": 0.9,
                "temperature": 0.7
                }
            }
        }
    }'''
    
    START_PROMPT_EVENT = '''{
        "event": {
            "promptStart": {
            "promptName": "%s",
            "textOutputConfiguration": {
                "mediaType": "text/plain"
                },
            "audioOutputConfiguration": {
                "mediaType": "audio/lpcm",
                "sampleRateHertz": 24000,
                "sampleSizeBits": 16,
                "channelCount": 1,
                "voiceId": "matthew",
                "encoding": "base64",
                "audioType": "SPEECH"
                },
            "toolUseOutputConfiguration": {
                "mediaType": "application/json"
                },
            "toolConfiguration": {
                "tools": []
                }
            }
        }
    }'''

    CONTENT_START_EVENT = '''{
        "event": {
            "contentStart": {
            "promptName": "%s",
            "contentName": "%s",
            "type": "AUDIO",
            "interactive": true,
            "role": "USER",
            "audioInputConfiguration": {
                "mediaType": "audio/lpcm",
                "sampleRateHertz": 16000,
                "sampleSizeBits": 16,
                "channelCount": 1,
                "audioType": "SPEECH",
                "encoding": "base64"
                }
            }
        }
    }'''

    AUDIO_EVENT_TEMPLATE = '''{
        "event": {
            "audioInput": {
            "promptName": "%s",
            "contentName": "%s",
            "content": "%s"
            }
        }
    }'''

    TEXT_CONTENT_START_EVENT = '''{
        "event": {
            "contentStart": {
            "promptName": "%s",
            "contentName": "%s",
            "role": "%s",
            "type": "TEXT",
            "interactive": true,
                "textInputConfiguration": {
                    "mediaType": "text/plain"
                }
            }
        }
    }'''

    TEXT_INPUT_EVENT = '''{
        "event": {
            "textInput": {
            "promptName": "%s",
            "contentName": "%s",
            "content": "%s"
            }
        }
    }'''

    TOOL_CONTENT_START_EVENT = '''{
        "event": {
            "contentStart": {
                "promptName": "%s",
                "contentName": "%s",
                "interactive": false,
                "type": "TOOL",
                "role": "TOOL",
                "toolResultInputConfiguration": {
                    "toolUseId": "%s",
                    "type": "TEXT",
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        }
    }'''
    
    CONTENT_END_EVENT = '''{
        "event": {
            "contentEnd": {
            "promptName": "%s",
            "contentName": "%s"
            }
        }
    }'''

    PROMPT_END_EVENT = '''{
        "event": {
            "promptEnd": {
            "promptName": "%s"
            }
        }
    }'''

    SESSION_END_EVENT = '''{
        "event": {
            "sessionEnd": {}
        }
    }'''
    
    
    
    
    
    def start_prompt(self,tools = []):
        """Create a promptStart event"""    
        prompt_start_event = {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 24000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": f"{self.voice_id}",
                        "encoding": "base64",
                        "audioType": "SPEECH"
                    },
                    "toolUseOutputConfiguration": {
                        "mediaType": "application/json"
                    }
                }
            }
        }
        if tools:
            # 必须把json先dumps，否则不会有响应
            tools_formated = [{ "toolSpec":{ 
                                    "name":tool["toolSpec"]["name"],
                                    "description":tool["toolSpec"]["description"],
                                    "inputSchema":
                                    {
                                        "json":  json.dumps(tool["toolSpec"]["inputSchema"]["json"],ensure_ascii=False)
                                    }
                                }
                             } for tool in tools]
            
            prompt_start_event["event"]["promptStart"]["toolConfiguration"] = {"tools":tools_formated}
        
        return json.dumps(prompt_start_event)
    
    def tool_result_event(self, content_name, content, role):
        """Create a tool result event"""

        if isinstance(content, dict):
            content_json_string = json.dumps(content)
        else:
            content_json_string = content
            
        tool_result_event = {
            "event": {
                "toolResult": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": content_json_string
                }
            }
        }
        return json.dumps(tool_result_event)
    
    def __init__(self, on_text_callback,processToolUse,voice_id,tools_config=[],model_id='amazon.nova-sonic-v1:0', region='us-east-1'):
        """Initialize the stream manager."""
        self.model_id = model_id
        self.region = region
        self.input_subject = Subject()
        self.output_subject = Subject()
        self.audio_subject = Subject()
        self.on_text_callback = on_text_callback
        self.processToolUse = processToolUse
        self.response_task = None
        self.stream_response = None
        self.is_active = False
        self.barge_in = False
        self.bedrock_client = None
        self.scheduler = None
        self.voice_id = voice_id
        self.tools_config = tools_config
        
        # Audio playback components
        self.audio_output_queue = asyncio.Queue()

        # Text response components
        self.display_assistant_text = False
        self.role = None
        
        # Session information
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())

    def _initialize_client(self):
        """Initialize the Bedrock client."""
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            http_auth_scheme_resolver=HTTPAuthSchemeResolver(),
            http_auth_schemes={"aws.auth#sigv4": SigV4AuthScheme()}
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)
    
    async def initialize_stream(self):
        """Initialize the bidirectional stream with Bedrock."""
        if not self.bedrock_client:
            self._initialize_client()
        
        self.scheduler = AsyncIOScheduler(asyncio.get_event_loop())      
        try:
            self.stream_response = await time_it_async("invoke_model_with_bidirectional_stream", lambda : self.bedrock_client.invoke_model_with_bidirectional_stream( InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)))


            self.is_active = True
            default_system_prompt = "You are a friendly assistant. The user and you will engage in a spoken dialog " \
            "exchanging the transcripts of a natural real-time conversation. Keep your responses short, " \
            "generally two or three sentences for chatty scenarios."
            
            # Send initialization events
            prompt_event = self.start_prompt(tools=self.tools_config)
            text_content_start = self.TEXT_CONTENT_START_EVENT % (self.prompt_name, self.content_name, "SYSTEM")
            text_content = self.TEXT_INPUT_EVENT % (self.prompt_name, self.content_name, default_system_prompt)
            text_content_end = self.CONTENT_END_EVENT % (self.prompt_name, self.content_name)
            
            init_events = [self.START_SESSION_EVENT, prompt_event, text_content_start, text_content, text_content_end]
            
            for event in init_events:
                await self.send_raw_event(event)
            
            # Start listening for responses
            self.response_task = asyncio.create_task(self._process_responses())
            
            # Set up subscription for input events
            self.input_subject.pipe(
                ops.subscribe_on(self.scheduler)
            ).subscribe(
                on_next=lambda event: asyncio.create_task(self.send_raw_event(event)),
                on_error=lambda e: debug_print(f"Input stream error: {e}")
            )
            
            # Set up subscription for audio chunks
            self.audio_subject.pipe(
                ops.subscribe_on(self.scheduler)
            ).subscribe(
                on_next=lambda audio_data: asyncio.create_task(self._handle_audio_input(audio_data)),
                on_error=lambda e: debug_print(f"Audio stream error: {e}")
            )
            
            
            debug_print("Stream initialized successfully")
            return self
        except Exception as e:
            self.is_active = False
            logger.error(f"Failed to initialize stream: {str(e)}")
            # import traceback
            # traceback.print_exc()
            raise
    
    async def send_raw_event(self, event_json):
        """Send a raw event JSON to the Bedrock stream."""
        if not self.stream_response or not self.is_active:
            debug_print("Stream not initialized or closed")
            return
        
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
        )
        
        try:
            await self.stream_response.input_stream.send(event)
            # For debugging large events, you might want to log just the type
            if DEBUG:
                if len(event_json) > 200:
                    event_type = json.loads(event_json).get("event", {}).keys()
                    # debug_print(f"Sent event type: {list(event_type)}")
                else:
                    # debug_print(f"Sent event: {event_json}")
                    pass

        except Exception as e:
            debug_print(f"Error sending event: {str(e)}")
            if DEBUG:
                import traceback
                traceback.print_exc()
            self.input_subject.on_error(e)
    
    async def send_audio_content_start_event(self):
        """Send a content start event to the Bedrock stream."""
        content_start_event = self.CONTENT_START_EVENT % (self.prompt_name, self.audio_content_name)
        await self.send_raw_event(content_start_event)
        
    async def send_tool_start_event(self, content_name):
        """Send a tool content start event to the Bedrock stream."""
        content_start_event = self.TOOL_CONTENT_START_EVENT % (self.prompt_name, content_name, self.toolUseId)
        debug_print(f"Sending tool start event: {content_start_event}")  
        await self.send_raw_event(content_start_event)

    async def send_tool_result_event(self, content_name, tool_result):
        """Send a tool content event to the Bedrock stream."""
        # Use the actual tool result from processToolUse
        tool_result_event = self.tool_result_event(content_name=content_name, content=tool_result, role="TOOL")
        debug_print(f"Sending tool result event: {tool_result_event}")
        await self.send_raw_event(tool_result_event)
    
    async def send_tool_content_end_event(self, content_name):
        """Send a tool content end event to the Bedrock stream."""
        tool_content_end_event = self.CONTENT_END_EVENT % (self.prompt_name, content_name)
        debug_print(f"Sending tool content event: {tool_content_end_event}")
        await self.send_raw_event(tool_content_end_event)
        
    
    async def _handle_audio_input(self, data):
        """Process audio input before sending it to the stream."""
        audio_bytes = data.get('audio_bytes')
        if not audio_bytes:
            debug_print("No audio bytes received")
            return
        
        try:
       
            # Base64 encode the audio data
            blob = base64.b64encode(audio_bytes)
            audio_event = self.AUDIO_EVENT_TEMPLATE % (self.prompt_name, self.audio_content_name, blob.decode('utf-8'))
            
            # Send the event directly
            await self.send_raw_event(audio_event)
        except Exception as e:
            debug_print(f"Error processing audio: {e}")
            if DEBUG:
                import traceback
                traceback.print_exc()
    
    def add_audio_chunk(self, audio_bytes):
        """Add an audio chunk to the stream."""
        self.audio_subject.on_next({
            'audio_bytes': audio_bytes,
            'prompt_name': self.prompt_name,
            'content_name': self.audio_content_name
        })
    
    async def send_audio_content_end_event(self):
        """Send a content end event to the Bedrock stream."""
        if not self.is_active:
            debug_print("Stream is not active")
            return
        
        content_end_event = self.CONTENT_END_EVENT % (self.prompt_name, self.audio_content_name)
        await self.send_raw_event(content_end_event)
        debug_print("Audio ended")
    
    async def send_prompt_end_event(self):
        """Close the stream and clean up resources."""
        if not self.is_active:
            debug_print("Stream is not active")
            return
        
        prompt_end_event = self.PROMPT_END_EVENT % (self.prompt_name)
        await self.send_raw_event(prompt_end_event)
        debug_print("Prompt ended")
        
    async def send_session_end_event(self):
        """Send a session end event to the Bedrock stream."""
        if not self.is_active:
            debug_print("Stream is not active")
            return

        await self.send_raw_event(self.SESSION_END_EVENT)
        self.is_active = False
        debug_print("Session ended")
    
    async def _process_responses(self):
        """Process incoming responses from Bedrock."""
        try:
            while self.is_active:
                try:
                    output = await self.stream_response.await_output()
                    result = await output[1].receive()
                    if result.value and result.value.bytes_:
                        try:
                            response_data = result.value.bytes_.decode('utf-8')
                            json_data = json.loads(response_data)
                            # logger.info(json_data)
                            # Handle different response types
                            if 'event' in json_data:
                                if 'contentStart' in json_data['event']:
                                    debug_print("Content start detected")
                                    content_start = json_data['event']['contentStart']
                                    # set role
                                    self.role = content_start['role']
                                    # Check for speculative content
                                    if 'additionalModelFields' in content_start:
                                        try:
                                            additional_fields = json.loads(content_start['additionalModelFields'])
                                            if additional_fields.get('generationStage') == 'SPECULATIVE':
                                                debug_print("Speculative content detected")
                                                self.display_assistant_text = True
                                            else:
                                                self.display_assistant_text = False
                                        except json.JSONDecodeError:
                                            logger.error("Error parsing additionalModelFields")
                                elif 'textOutput' in json_data['event']:
                                    text_content = json_data['event']['textOutput']['content']
                                    # Check if there is a barge-in
                                    if '{ "interrupted" : true }' in text_content:
                                        if DEBUG:
                                            logger.info("Barge-in detected. Stopping audio output.")
                                        self.barge_in = True

                                    if (self.role == "ASSISTANT" and self.display_assistant_text):
                                        debug_print(f"Assistant: {text_content}")
                                        # Send text response via callback
                                        text_data = {
                                            "type": "text",
                                            "text": {
                                                "assistant": text_content
                                            }
                                        }
                                        await self.on_text_callback(text_data)
                                        
                                    elif (self.role == "USER"):
                                        debug_print(f"User: {text_content}")
                                        # Send user transcription via callback
                                        text_data = {
                                            "type": "text",
                                            "text": {
                                                "user": text_content
                                            }
                                        }
                                        await self.on_text_callback(text_data)                                
                                elif 'audioOutput' in json_data['event']:
                                    audio_content = json_data['event']['audioOutput']['content']
                                    audio_bytes = base64.b64decode(audio_content)
                                    # Add to audio queue for processing and playback
                                    await self.audio_output_queue.put(audio_bytes)
                                elif 'toolUse' in json_data['event']:
                                    self.toolUseContent = json_data['event']['toolUse']['content']
                                    self.toolName = json_data['event']['toolUse']['toolName']
                                    self.toolUseId = json_data['event']['toolUse']['toolUseId']
                                    logger.info(f"Tool use detected: {self.toolName}, ID: {self.toolUseId}")
                                    text_data = {
                                            "type": "toolUse",
                                            "data": {"toolUseId":self.toolUseId,
                                                     "name":self.toolName,
                                                     "input":self.toolUseContent }
                                        }
                                    await self.on_text_callback(text_data)   
                                elif 'contentEnd' in json_data['event'] and json_data['event']['contentEnd'].get('type') == 'TOOL':
                                    # logger.info("Processing tool use and sending result")
                                    toolResult = await self.processToolUse(self.toolName, self.toolUseContent)
                                    toolContent = str(uuid.uuid4())
                                    await self.send_tool_start_event(toolContent)
                                    await self.send_tool_result_event(toolContent, toolResult)
                                    await self.send_tool_content_end_event(toolContent)
                                    logger.info(f'Sent the tool result for {self.toolName} - {self.toolUseContent}')
                                    text_data = {
                                            "type": "toolResult",
                                            "data": {"toolUseId":self.toolUseId,
                                                     "content":[{"text": toolResult}]}
                                        }
                                    await self.on_text_callback(text_data) 
                                elif 'completionEnd' in json_data['event']:
                                    # Handle end of conversation, no more response will be generated
                                    logger.info("End of response sequence")
                                    
                            self.output_subject.on_next(json_data)
                        except json.JSONDecodeError:
                            self.output_subject.on_next({"raw_data": response_data})
                except StopAsyncIteration:
                    # Stream has ended
                    break
                except Exception as e:
                    debug_print(f"Error receiving response: {e}")
                    self.output_subject.on_error(e)
                    break
        except Exception as e:
            debug_print(f"Response processing error: {e}")
            self.output_subject.on_error(e)
        finally:
            if self.is_active:  
                self.output_subject.on_completed()
    
    async def close(self):
        """Close the stream properly."""
        if not self.is_active:
            return
            
        # Complete the subjects
        self.input_subject.on_completed()
        self.audio_subject.on_completed()

        # 先发送结束事件
        await self.send_audio_content_end_event()
        await self.send_prompt_end_event()
        await self.send_session_end_event()
        
        # 等待一小段时间让最后的响应处理完成
        await asyncio.sleep(0.5)
        
        self.is_active = False
        
        # 然后再取消任务
        if self.response_task and not self.response_task.done():
            self.response_task.cancel()
            try:
                await asyncio.wait_for(self.response_task, 1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # 最后关闭流
        if self.stream_response:
            await self.stream_response.input_stream.close()

    

class WebSocketAudioProcessor:
    """Handle real-time bidirectional audio processing for WebSocket connections using Nova Sonic"""
    
    def __init__(self, user_id,mcp_clients,mcp_server_ids,voice_id, model_id='amazon.nova-sonic-v1:0', region='us-east-1', websocket=None):
        self.user_id = user_id
        self.model_id = model_id
        self.region = region
        self.mcp_clients = mcp_clients
        self.mcp_server_ids = mcp_server_ids
        self.stream_manager = None
        self.is_streaming = False
        self.last_text = {"USER": "", "ASSISTANT": ""}
        self.voice_id = voice_id
        
        # WebSocket reference for direct communication
        self.websocket = websocket
        
        # Tasks for full duplex operation
        self.output_audio_task = None
        
        # Audio buffering for smoother playback
        self.audio_buffer = bytearray()
        self.buffer_size = 2048 #32000  # Buffer approximately 2 seconds of audio at 16kHz
        self.buffer_lock = asyncio.Lock()
        self.last_send_time = 0  # Track when we last sent audio
        
    async def initialize(self):
        """Initialize the stream manager and prepare for audio processing"""
        
        # get tools from mcp server
        tools_config = []
        if self.mcp_clients is not None:
            for mcp_server_id in self.mcp_server_ids:
                tool_config_response = await self.mcp_clients[mcp_server_id].get_tool_config(server_id=mcp_server_id)
                if tool_config_response:
                    tools_config.extend(tool_config_response["tools"])
                # else:
                #     yield {"type": "stopped", "data": {"message": f"Get tool config from {mcp_server_id} failed, please restart the MCP server"}}
        logger.info(f"Tool config: {tools_config}")
        
        self.stream_manager = BedrockStreamManager(
            model_id=self.model_id, 
            region=self.region,
            on_text_callback = self.on_text_received,
            processToolUse = self.processToolUse,
            tools_config=tools_config,
            voice_id=self.voice_id
            # on_audio_callback=None  # We'll handle audio via the output task
        )
        
        # Initialize the stream
        await self.stream_manager.initialize_stream()
        logger.info(f"Nova Sonic processor initialized for user {self.user_id} with full duplex mode")

        await self.start_streaming()
        return self
    
    async def processToolUse(self, toolName, toolUseContent):
        server_id, llm_tool_name = MCPClient.get_tool_name4mcp(toolName)
        try:
            tool_name, tool_args = toolName, json.loads(toolUseContent)
            if tool_args == "":
                tool_args = {}
            #parse the tool_name
            server_id, llm_tool_name = MCPClient.get_tool_name4mcp(tool_name)
            mcp_client = self.mcp_clients.get(server_id)
            if mcp_client is None:
                raise Exception(f"mcp_client is None, server_id:{server_id}")
            
            result = await mcp_client.call_tool(llm_tool_name, tool_args)
            result_content =  "\n".join([x.text for x in result.content if x.type == 'text'])
            # result_content = [{"text": "\n".join([x.text for x in result.content if x.type == 'text'])}]
            # logger.info(f"call_tool result_content:{result_content}")

            return {'result':result_content}
        except Exception as err:
            err_msg = f"{toolName} tool call is failed. error:{err}"
            return {
                        "content": err_msg,
                        "status": 'error'
                    }
            
    async def start_streaming(self):
        """Start streaming audio."""
    
        logger.info("Starting audio streaming.")

        # Send audio content start event
        await time_it_async("send_audio_content_start_event", lambda : self.stream_manager.send_audio_content_start_event())
        
        self.is_streaming = True
        
        # Start processing tasks
        self.output_audio_task = asyncio.create_task(self.process_output_audio())
    
    async def stop_streaming(self):
        """Stop streaming audio."""
        if not self.is_streaming:
            return
        self.is_streaming = False
        # Cancel the tasks
        tasks = []
        if self.output_audio_task and not self.output_audio_task.done():
            tasks.append(self.output_audio_task)
        
        for task in tasks:
            task.cancel()
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        await self.stream_manager.close() 
        
    async def process_output_audio(self):
        """Continuously process and send output audio (runs as a separate task)"""
        logger.info(f"Starting output audio processor for user {self.user_id}")
        
        try:
            while self.is_streaming:
                try:
                    # Check for barge-in flag
                    if self.stream_manager and self.stream_manager.barge_in:
                        # Clear the audio queue and buffer
                        logger.info("Barge-in detected - clearing audio queue and buffer")
                        while not self.stream_manager.audio_output_queue.empty():
                            try:
                                self.stream_manager.audio_output_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        
                        # Clear the buffer
                        async with self.buffer_lock:
                            self.audio_buffer.clear()
                            
                        self.stream_manager.barge_in = False
                        await asyncio.sleep(0.05)
                        continue
                    
                    # Get audio data with timeout to prevent blocking indefinitely
                    audio_data = None
                    try:
                        audio_data = await asyncio.wait_for(
                            self.stream_manager.audio_output_queue.get(),
                            timeout=0.1  # Short timeout
                        )
                    except asyncio.TimeoutError:
                        # If we have buffered data but no new data for a while, send what we have
                        async with self.buffer_lock:
                            if len(self.audio_buffer) > 0:
                                try:
                                    # Send the raw PCM audio data directly to the client
                                    if self.websocket and self.is_streaming:
                                        # Apply audio processing to improve quality
                                        processed_audio = bytes(self.audio_buffer)
                                        
                                        # Apply smoothing to reduce high-frequency noise
                                        processed_audio = smooth_pcm_data(processed_audio)
                                        
                                        # Normalize audio to prevent clipping
                                        processed_audio = normalize_pcm_data(processed_audio)
                                        
                                        # Create a JSON object with audio metadata and base64-encoded PCM data
                                        audio_metadata = {
                                            "type": "audio_data",
                                            "format": "pcm",
                                            "sampleRate": OUTPUT_SAMPLE_RATE,
                                            "bitsPerSample": 16,
                                            "channels": 1,
                                            "data": base64.b64encode(processed_audio).decode('utf-8')
                                        }
                                        
                                        # Send as JSON to include metadata
                                        await self.websocket.send_json(audio_metadata)
                                        logger.debug(f"Sent {len(processed_audio)} bytes of processed PCM audio to client")
                                        self.last_send_time = time.time() * 1000
                                    
                                    # Clear the buffer after sending
                                    self.audio_buffer.clear()
                                except Exception as e:
                                    logger.warning(f"Failed to send buffered audio: {e}")
                        
                        # No audio available yet, continue loop
                        await asyncio.sleep(0.01)  # Brief sleep to yield control
                        continue
                    except asyncio.CancelledError:
                        logger.info(f"Output audio task cancelled for user {self.user_id}")
                        break
                        
                    # If we have audio data, add it to the buffer
                    if audio_data and self.is_streaming:
                        async with self.buffer_lock:
                            # Add to buffer
                            self.audio_buffer.extend(audio_data)
                            
                            # If buffer is large enough, send it
                            if len(self.audio_buffer) >= self.buffer_size:
                                try:
                                    # Check if enough time has passed since last send (at least 100ms)
                                    current_time = time.time() * 1000  # Convert to milliseconds
                                    if current_time - self.last_send_time < 50:
                                        # Not enough time has passed, continue buffering
                                        continue
                                    
                                    # Send the raw PCM audio data directly to the client
                                    if self.websocket:
                                        # Apply audio processing to improve quality
                                        processed_audio = bytes(self.audio_buffer)
                                        
                                        # Apply smoothing to reduce high-frequency noise
                                        processed_audio = smooth_pcm_data(processed_audio)
                                        
                                        # Normalize audio to prevent clipping
                                        processed_audio = normalize_pcm_data(processed_audio)
                                        
                                        # Create a JSON object with audio metadata and base64-encoded PCM data
                                        audio_metadata = {
                                            "type": "audio_data",
                                            "format": "pcm",
                                            "sampleRate": OUTPUT_SAMPLE_RATE,
                                            "bitsPerSample": 16,
                                            "channels": 1,
                                            "data": base64.b64encode(processed_audio).decode('utf-8')
                                        }
                                        
                                        # Send as JSON to include metadata
                                        await self.websocket.send_json(audio_metadata)
                                        logger.debug(f"Sent {len(processed_audio)} bytes of processed PCM audio to client")
                                        self.last_send_time = current_time
                                    
                                    # Clear the buffer after sending
                                    self.audio_buffer.clear()
                                except Exception as e:
                                    logger.warning(f"Failed to send audio via WebSocket: {e}")
                                    # Clear buffer on error to avoid memory buildup
                                    self.audio_buffer.clear()
                            
                except Exception as e:
                    if self.is_streaming:  # Only log if still active
                        logger.error(f"Error in output audio processing: {e}")
                    await asyncio.sleep(0.1)  # Brief delay on error
        except asyncio.CancelledError:
            logger.info(f"Output audio processing task cancelled for user {self.user_id}")
        except Exception as e:
            logger.error(f"Unexpected error in output audio processor: {e}")
        finally:
            logger.info(f"Output audio processor stopped for user {self.user_id}")
    
    def set_websocket(self, websocket):
        """Update the WebSocket reference"""
        self.websocket = websocket
        
    async def on_text_received(self,data):
        # 告知客户端准备好接收音频
        # print(data)
        await self.websocket.send_json(data)
        
    async def process_input_audio(self, audio_bytes):
        """Process incoming audio from the user - input handling only in full duplex mode"""
        # Check if the processor is active
        if not self.is_streaming:
            logger.warning(f"Audio processor for user {self.user_id} is not active")
            return {
                "status": "inactive",
                "message": "Audio processor is not active",
                "text": self.last_text
            }
            
        if not self.stream_manager:
            logger.error(f"Stream manager for user {self.user_id} is not initialized")
            return {
                "status": "error",
                "message": "Audio processor not properly initialized",
                "text": self.last_text
            }
        
        try:
            # Add the audio chunk to the stream - use shield to protect against cancellation
            try:
                self.stream_manager.add_audio_chunk(audio_bytes)
            except Exception as e:
                logger.warning(f"Error adding audio chunk: {e}")
            
            # Just return current state - output is handled separately by continuous task
            current_text = {
                "user": self.last_text.get("USER", ""),
                "assistant": self.last_text.get("ASSISTANT", "")
            }
            
            return {
                "status": "success",
                "text": current_text
            }
        except Exception as e:
            logger.error(f"Error processing input audio for user {self.user_id}: {e}")
            if DEBUG:
                import traceback
                debug_print(f"Audio processing error details: {traceback.format_exc()}")
            
            # Still return the last known state
            return {
                "status": "error",
                "message": str(e),
                "text": {
                    "user": self.last_text.get("USER", ""),
                    "assistant": self.last_text.get("ASSISTANT", "")
                }
            }
    
    async def close(self):  
        await self.stop_streaming()      
    

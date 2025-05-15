"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
import os
import sys
import asyncio
import logging
from typing import Dict,AsyncGenerator
import boto3
from botocore.config import Config
from dotenv import load_dotenv
from mcp_client import MCPClient
from utils import maybe_filter_to_n_most_recent_images,filter_tool_use_result
import pandas as pd
load_dotenv()  # load environment variables from .env


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
logger = logging.getLogger(__name__)

CLAUDE_37_SONNET_MODEL_ID = 'us.anthropic.claude-3-7-sonnet-20250219-v1:0'

class ChatClient:
    """Bedrock simple chat wrapper"""

    bedrock_client_pool = []

    def __init__(self, credential_file='', access_key_id='', secret_access_key='', region=''):
        self.env = {
            'AWS_ACCESS_KEY_ID': access_key_id or os.environ.get('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': secret_access_key or os.environ.get('AWS_SECRET_ACCESS_KEY'),
            'AWS_REGION': region or os.environ.get('AWS_REGION'),
        }
        
        # self.max_history = int(os.environ.get('MAX_HISTORY_TURN',5))*2
        self.messages = [] # History messages without system message
        self.system = None
        self.cache_checkpoint = 0
        self.reset_checkpoint = 0
        
        if credential_file:
            credentials = pd.read_csv(credential_file)
            for index, row in credentials.iterrows():
                self.bedrock_client_pool.append(self._get_bedrock_client(ak=row['ak'],sk=row['sk']))
            logger.info(f"Loaded {len(self.bedrock_client_pool)} bedrock clients from {credential_file}")

    def _get_bedrock_client(self, ak='', sk='', region='', runtime=True):
        if ak and sk:
            bedrock_client = boto3.client(
                service_name='bedrock-runtime' if runtime else 'bedrock',
                aws_access_key_id=ak,
                aws_secret_access_key=sk,
                region_name=region or os.environ.get('AWS_REGION'),
                config=Config(
                    retries={
                        "max_attempts": 3,
                        "mode": "standard",
                    },
                    read_timeout=600,
                )
            )
        if self.env['AWS_ACCESS_KEY_ID'] and self.env['AWS_SECRET_ACCESS_KEY']:
            bedrock_client = boto3.client(
                service_name='bedrock-runtime' if runtime else 'bedrock',
                aws_access_key_id=self.env['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=self.env['AWS_SECRET_ACCESS_KEY'],
                region_name=self.env['AWS_REGION'],
                config=Config(
                    retries={
                        "max_attempts": 3,
                        "mode": "standard",
                    },
                    read_timeout=600,
                )
            )
        else:
            bedrock_client = boto3.client(
                service_name='bedrock-runtime' if runtime else 'bedrock',
                region_name=self.env['AWS_REGION'],
                config=Config(
                    retries={
                        "max_attempts": 3,
                        "mode": "standard",
                    },
                    read_timeout=600,
                ))

        return bedrock_client
    
    def clear_history(self):
        """clear session message of this client"""
        self.messages = []
        self.system = None
        self.cache_checkpoint = 0
        self.reset_checkpoint = 0
        
    async def process_query(self, 
            model_id="amazon.nova-lite-v1:0", max_tokens=1024, temperature=0.1,max_turns=30,
            messages=[], system=[], mcp_clients=None, mcp_server_ids=[],extra_params={},keep_session=None) -> AsyncGenerator[Dict, None]:
        """Submit user query or history messages, and then get the response answer.

        Note the specified mcp servers' tool maybe used.
        """
        if keep_session:
            messages = self.messages + messages
            system = self.system if self.system else system
        else:
            self.clear_history()
            
        # get tools from mcp server
        tool_config = {"tools": []}
        if mcp_clients is not None:        
            for mcp_server_id in mcp_server_ids:
                tool_config_response = await mcp_clients[mcp_server_id].get_tool_config(server_id=mcp_server_id)
                tool_config['tools'].extend(tool_config_response["tools"])

        logger.info(f"tool_config: {tool_config}")
        bedrock_client = self._get_bedrock_client()
        
        enable_thinking = extra_params.get('enable_thinking', False) and model_id in CLAUDE_37_SONNET_MODEL_ID
        only_n_most_recent_images = extra_params.get('only_n_most_recent_images', 3)
        image_truncation_threshold = only_n_most_recent_images or 0
        
        if enable_thinking:
            additionalModelRequestFields = {"reasoning_config": { "type": "enabled","budget_tokens": extra_params.get("budget_tokens",1024)}}
            inferenceConfig={"maxTokens":max(extra_params.get("budget_tokens",1024) + 1, max_tokens),"temperature":1,}

        else:
            additionalModelRequestFields = {}
            inferenceConfig={"maxTokens":max_tokens,"temperature":temperature,}
        
        # 如新一轮对话里没有启用mcp server，则需要清除之前的tool use content，否则会报错
        if len(messages) > 0 and not tool_config['tools']:
            messages = filter_tool_use_result(messages)
            
        requestParams = dict(
                    modelId=model_id,
                    messages=messages,
                    system=system,
                    inferenceConfig=inferenceConfig,
                    additionalModelRequestFields = additionalModelRequestFields
        )
        requestParams = {**requestParams, 'toolConfig': tool_config} if  tool_config['tools'] else requestParams
        
        # logger.info(f"requestParams: {requestParams}")

        # invoke bedrock llm with user query
        response = bedrock_client.converse(
                    **requestParams
        )
        logger.info(f"response: {response}")

        # the response may or not request tool use
        output_message = response['output']['message']
        messages.append(output_message)
        stop_reason = response['stopReason']

        if stop_reason == 'end_turn':
            # normal chat finished
            #save history message
            yield output_message
        elif stop_reason == 'tool_use' and mcp_clients is not None:
            # return tool request use
            yield output_message
            # multi-loop tool calling
            turn_i = 1
            while stop_reason == 'tool_use' and turn_i <= max_turns:
                logger.info(f"Use tool turn-{turn_i}")
                # tool call has been requested. 
                tool_requests = response['output']['message']['content']

                # 收集所有需要调用的工具请求
                tool_calls = []
                for tool_request in tool_requests:
                    if 'toolUse' in tool_request:
                        tool = tool_request['toolUse']
                        tool_calls.append(tool)
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
                        result_content = [{"text": "\n".join([x.text for x in result.content if x.type == 'text'])}]
                        image_content =  [{"image":{"format":x.mimeType.replace('image/',''), "source":{"bytes":base64.b64decode(x.data)} } } for x in result.content if x.type == 'image']
                        return  [{ 
                                                "toolUseId": tool['toolUseId'],
                                                "content": result_content+image_content
                                            },
                                            { 
                                                "toolUseId": tool['toolUseId'],
                                                "content": result_content
                                }]
                    except Exception as err:
                        err_msg = f"{tool['name']} tool call is failed. error:{err}"
                        return [{
                                                "toolUseId": tool['toolUseId'],
                                                "content": [{"text": err_msg}],
                                                "status": 'error'
                                  }]*2
                # 使用 asyncio.gather 并行执行所有工具调用
                call_results = await asyncio.gather(*[execute_tool_call(tool) for tool in tool_calls])
                tool_results = []
                tool_text_results = []
                for result in call_results:
                    tool_results.append(result[0])
                    tool_text_results.append(result[1])
                logger.info(f'tool_text_results {tool_text_results}')
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
                messages.append(tool_result_message)
                
                if only_n_most_recent_images:
                    maybe_filter_to_n_most_recent_images(
                        messages,
                        only_n_most_recent_images,
                        min_removal_threshold=image_truncation_threshold,
                )
                # return tool use results
                yield tool_result_message

                # send the tool results to the model.
                response = bedrock_client.converse(
                   **requestParams
                )
                stop_reason = response['stopReason']
                output_message = response['output']['message']
                messages.append(output_message)
                # return user query's answer
                yield output_message
                turn_i += 1
    
    async def chat_loop_cli(self, model_id="amazon.nova-lite-v1:0", mcp_client=None):
        """Run an interactive chat loop"""

        print("\nChat with Bedrock+MCP now!")
        print("Type your queries or 'quit' to exit.")
    
        history = []
        while True:
            try:
                query = input("\nQuery: ").strip()
    
                if query.lower() == 'quit':
                    break
    
                async for response in self.process_query(query, model_id=model_id, 
                                                         history=history, mcp_client=mcp_client):
                    print("\n")
                    print(response)
                    print("\n")
            except Exception as e:
                print(f"\nError: {str(e)}")
    

async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")

    if len(sys.argv) < 3:
        print("Usage: python client.py <mcp_server_id> <path_to_server_script> <server_script_args> -- <mcp_server_id> <path_to_server_script> <server_script_args>")
        sys.exit(1)

    model_id = sys.argv[1]
    server_args = [[]]
    for arg in sys.argv[2:]:
        if arg == '--':
            server_args.append([])
        else:
            server_args[-1].append(arg)

    try:
        mcp_client = MCPClient()
        for args in server_args:
            if len(args) < 2:
                continue
            server_id, server_script, server_script_args = args[0], args[1], args[2:]
            await mcp_client.connect_to_server(server_id, server_script, server_script_args)

        chat_client = ChatClient()
        await chat_client.chat_loop_cli(model_id=model_id, mcp_client=mcp_client)
    finally:
        await mcp_client.cleanup()


if __name__ == "__main__":
    from mcp_client import MCPClient
    asyncio.run(main())

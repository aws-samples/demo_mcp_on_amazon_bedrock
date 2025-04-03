"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
"""
MCP Client maintains Multi-MCP-Servers
"""
import os
import logging
import asyncio
from typing import Optional, Dict
from pydantic import ValidationError
from dotenv import load_dotenv
from InlineAgent.tools.mcp import MCPStdio
from mcp.client.stdio import stdio_client, get_default_environment
from mcp import StdioServerParameters


load_dotenv()  # load environment variables from .env
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

logger = logging.getLogger(__name__)
delimiter = "___"
tool_name_mapping = {}
tool_name_mapping_r = {}
class InlineAgentMCPClient:
    """Manage Inline Agent MCP sessions.

    Support features:
    - MCP multi-server
    - get tool config from server
    - call tool and get result from server
    """

    def __init__(self, name, access_key_id='', secret_access_key='', region='us-east-1'):
        self.env = {
            'AWS_ACCESS_KEY_ID': access_key_id or os.environ.get('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': secret_access_key or os.environ.get('AWS_SECRET_ACCESS_KEY'),
            'AWS_REGION': region or os.environ.get('AWS_REGION'),
        }
        self.name = name
        self.client = None

    @staticmethod
    def normalize_tool_name( tool_name):
        return tool_name.replace('-', '_').replace('/', '_').replace(':', '_')
    
    @staticmethod
    def get_tool_name4llm( server_id, tool_name, norm=True, ns_delimiter=delimiter):
        """Convert MCP server tool name to llm tool call"""
        global tool_name_mapping, tool_name_mapping_r
        # prepend server prefix namespace to support multi-mcp-server
        tool_key = server_id + ns_delimiter + tool_name
        tool_name4llm = tool_key if not norm else InlineAgentMCPClient.normalize_tool_name(tool_key)
        tool_name_mapping[tool_key] = tool_name4llm
        tool_name_mapping_r[tool_name4llm] = tool_key
        return tool_name4llm
    
    @staticmethod
    def get_tool_name4mcp( tool_name4llm, ns_delimiter=delimiter):
        """Convert llm tool call name to MCP server original name"""
        global  tool_name_mapping_r
        server_id, tool_name = "", ""
        tool_name4mcp = tool_name_mapping_r.get(tool_name4llm, "")
        if len(tool_name4mcp.split(ns_delimiter)) == 2:
            server_id, tool_name = tool_name4mcp.split(ns_delimiter)
        return server_id, tool_name

    async def disconnect_to_server(self):
        await self.client.cleanup()
    
    
    async def connect_to_server(self, server_script_path: str = "", server_script_args: list = [], 
            server_script_envs: Dict = {}, command: str = ""):
        """Connect to an MCP server"""
        if not ((command and server_script_args) or server_script_path):
            raise ValueError("Run server via script or command.")

        if server_script_path:
            # run via script
            is_python = server_script_path.endswith('.py')
            is_js = server_script_path.endswith('.js')
            is_uvx = server_script_path.startswith('uvx:')
            is_np = server_script_path.startswith('npx:')
            is_docker = server_script_path.startswith('docker:')
            is_uv = server_script_path.startswith('uv:')

            if not (is_python or is_js or is_uv or is_np or is_docker or is_uvx):
                raise ValueError("Server script must be a .py or .js file or package")
            if is_uv or is_np or is_uvx:
                server_script_path = server_script_path[server_script_path.index(':')+1:]

            server_script_args = [server_script_path] + server_script_args
    
            if is_python:
                command = "python"
            elif is_uv:
                command = "uv"
            elif is_uvx:
                command = "uvx"
            elif is_np:
                command = "npx"
                server_script_args = ["-y"] + server_script_args
            elif is_js:
                command = "node"
            elif is_docker:
                command = "docker"
        else:
            # run via command
            if command not in ["npx", "uvx", "node", "python","docker","uv",]:
                raise ValueError("Server command must be in the npx/uvx/node/python/docker/uv")

        env = get_default_environment()
        if self.env['AWS_ACCESS_KEY_ID'] and self.env['AWS_ACCESS_KEY_ID']:
            env['AWS_ACCESS_KEY_ID'] =  self.env['AWS_ACCESS_KEY_ID']
            env['AWS_SECRET_ACCESS_KEY'] = self.env['AWS_SECRET_ACCESS_KEY']
            env['AWS_REGION'] = self.env['AWS_REGION']
        env.update(server_script_envs)
        try: 
            server_params = StdioServerParameters(
                command=command, args=server_script_args, env=env
            )
        except Exception as e:
            logger.error(f"\n{e}")
            raise ValueError(f"Invalid server script or command. {e}")

        mcp_client = await MCPStdio.create(server_params)
        logger.info(f"\nCreate server %s %s" % (command, server_script_args))
        return mcp_client


    async def get_tool_config(self, model_provider='bedrock', server_id : str = ''):
        """Get llm's tool usage config via MCP server"""
        # list tools via mcp server
        response = await self.session.list_tools()
        if not response:
            return None

        # for bedrock tool config
        tool_config = {"tools": []}
        tool_config["tools"].extend([{
            "toolSpec":{
                # mcp tool's original name to llm tool name (with server id namespace)
                "name": InlineAgentMCPClient.get_tool_name4llm(server_id, tool.name, norm=True),
                "description": tool.description, 
                "inputSchema": {"json": tool.inputSchema}
            }
        } for tool in response.tools])

        return tool_config

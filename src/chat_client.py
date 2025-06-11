"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
import os
from dotenv import load_dotenv
from utils import get_user_message,save_user_message,delete_user_message,DDB_TABLE
import pandas as pd
from constant import *
load_dotenv()  # load environment variables from .env

class ChatClient:
    """chat wrapper"""
    def __init__(self, credential_file='',user_id='', access_key_id='', secret_access_key='', region=''):
        self.env = {
            'AWS_ACCESS_KEY_ID': access_key_id or os.environ.get('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': secret_access_key or os.environ.get('AWS_SECRET_ACCESS_KEY'),
            'AWS_REGION': region or os.environ.get('AWS_REGION'),
        }
        
        # self.max_history = int(os.environ.get('MAX_HISTORY_TURN',5))*2
        self.messages = [] # History messages without system message
        self.system = None
        self.agent = None
        self.user_id = user_id
    
    async def clear_history(self):
        """clear session message of this client"""
        self.messages = []
        self.system = None
        if DDB_TABLE:
            await delete_user_message(self.user_id)
    
    async def save_history(self):
        self.messages = self.agent.messages
        if DDB_TABLE:
            await save_user_message(self.user_id,self.messages)
            
    async def load_history(self):
        if DDB_TABLE:
            return await get_user_message(self.user_id)
        else:
            return self.messages 

            
    

"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
"""
import os
from dotenv import load_dotenv

import pandas as pd
from constant import *
load_dotenv()  # load environment variables from .env



class ChatClient:
    """chat wrapper"""
    def __init__(self, credential_file='', access_key_id='', secret_access_key='', region=''):
        self.env = {
            'AWS_ACCESS_KEY_ID': access_key_id or os.environ.get('AWS_ACCESS_KEY_ID'),
            'AWS_SECRET_ACCESS_KEY': secret_access_key or os.environ.get('AWS_SECRET_ACCESS_KEY'),
            'AWS_REGION': region or os.environ.get('AWS_REGION'),
        }
        
        # self.max_history = int(os.environ.get('MAX_HISTORY_TURN',5))*2
        self.messages = [] # History messages without system message
        self.system = None
    
    def clear_history(self):
        """clear session message of this client"""
        self.messages = []
        self.system = None
        self.cache_checkpoint = 0
        self.reset_checkpoint = 0
from openai import OpenAI
from deepseek_system_prompt import *
from deepseek_system_prompt_stream import *
from dotenv import load_dotenv
import json, uuid, os
import logging


load_dotenv(dotenv_path="../.env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
)
logger = logging.getLogger(__name__)



# Designed for DeepSeek series, especially for "Pro/deepseek-ai/DeepSeek-R1"
# non-streaming mode
def deepseek_r1_chat(model: str, messages: list, max_completion_tokens: int, temperature: float, api_key: str = None, base_url: str = "https://api.siliconflow.cn/v1",
                     tools: list = None, tool_choice: str = None, top_p: float = None, top_logprobs: float = None):
    
    # get api_key from env
    if not api_key:
        try:
            api_key = os.environ.get("COMPATIBLE_API_KEY")
        except Exception as e:
            raise(ValueError("API KEY not found."))
    
    # get tool configs & system prompt
    if tools:
        tool_config = "<h4>TOOL SET</h4>{}".format(json.dumps(tools))
    else:
        tool_config = "<h4>TOOL SET</h4>[]"
    system_prompt = messages[0]["content"] + " " + get_tool_use_intro() + " " + get_tool_use_formatting() + " " + tool_config
    #logger.info(f"System: {system_prompt}")
    r1_msgs = [{"role": "system", "content": system_prompt}]

    # Get rid of system message
    # convert openai format to r1 foramt
    for message in messages[1:]:
        r1_msgs.append(convert_to_r1_format(message))

    #logger.info("r1 format messages: {}".format(r1_msgs))
    
    # Invoke LLM
    client = OpenAI(api_key = api_key, base_url = base_url) 
    openai_response = client.chat.completions.create(model = model, messages = r1_msgs, temperature = temperature, 
                                                 max_completion_tokens = max_completion_tokens, stream = False, 
                                                 top_p = top_p, top_logprobs = top_logprobs)
    r1_content = json.loads(openai_response.choices[0].message.content)    # {"text": "", "tool_calls": "", "task_complete": ""}
    content = []
   
   
    #logger.info("r1 response contents: {}".format(r1_content))
  
    # Convert r1 stipulated format to bedrock content
    content.append({"text": r1_content["text"]})

    if r1_content["tool_calls"]:
        content.append({"toolUse": {
                            "name": r1_content["tool_calls"][0]['tool_name'],
                            "toolUseId": uuid.uuid4().hex,
                            "input": r1_content["tool_calls"][0]["parameters"]
                        }})

    # Convert stop reason
    stop_reason = "end_turn"
    if r1_content["tool_calls"]:
        stop_reason = "tool_use"
    elif openai_response.choices[0].finish_reason in ["length", "content_filter"]:
        stop_reason = "max_tokens"
    
    # Construct bedrock response
    bedrock_response = {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": content
                }
            },
            "stopReason": stop_reason,
            "modelId": model,
            "usage": {
                "inputTokens": openai_response.usage.prompt_tokens,
                "outputTokens": openai_response.usage.completion_tokens,
                "totalTokens": openai_response.usage.total_tokens
            },
        }
    return bedrock_response



# Designed for DeepSeek series, especially for "Pro/deepseek-ai/DeepSeek-R1"
# streaming mode
def deepseek_r1_chat_stream(model: str, messages: list, max_completion_tokens: int, temperature: float, stream, api_key: str = None, base_url: str = "https://api.siliconflow.cn/v1",
                     tools: list = None, tool_choice: str = None, top_p: float = None, top_logprobs: float = None):
    # get api_key from env
    if not api_key:
        try:
            api_key = os.environ.get("COMPATIBLE_API_KEY")
        except Exception as e:
            raise(ValueError("API KEY not found."))
    
    # get tool configs & system prompt
    if tools:
        tool_config = "<h4>TOOL SET</h4>{}".format(json.dumps(tools))
    else:
        tool_config = "<h4>TOOL SET</h4>[]"
    system_prompt = messages[0]["content"] + " " + get_tool_use_intro_stream() + " " + get_tool_use_formatting_stream() + " " + tool_config
    #logger.info(f"System: {system_prompt}")
    r1_msgs = [{"role": "system", "content": system_prompt}]

    # Get rid of system message
    # convert openai format to r1 foramt
    for message in messages[1:]:
        r1_msgs.append(convert_to_r1_format(message))

    #logger.info("r1 format messages: {}".format(r1_msgs))
    
    # Invoke LLM
    client = OpenAI(api_key = api_key, base_url = base_url) 
    stream_response = client.chat.completions.create(model = model, messages = r1_msgs, temperature = temperature, 
                                                 max_completion_tokens = max_completion_tokens, stream = True, 
                                                 top_p = top_p, top_logprobs = top_logprobs)
    return stream_response



def convert_to_r1_format(message: dict) -> dict:
    # keep user
    # convert assistant  
    # {"role": "assistant", "content": "...", "tool_calls": tool_calls} 
    # => {"role": "assistant", "content": "..."+"...tool_calls..."}}
    # convert tool to user
    # {"role": "tool", "content": content, "tool_call_id": tool_id}
    # => {"role": "user", "content": "{"tool_result": content, "tool_call_id": tool_id}"}
    if message:
        if message["role"] == "user":
            return message
        elif message["role"] == "tool":
            return {"role": "user", "content": str({"tool_result": message["content"], "tool_call_id": message["tool_call_id"]})}
        elif message["role"] == "assistant":
            if message["tool_calls"]:
                return {"role": "assistant", "content": str(message["content"])+str(message["tool_calls"])}   
            else:
                return {"role": "assistant", "content": str(message["content"]) + str({"tool_calls": []})}
        else:
            raise ValueError("role {} not supported for R1. Should be system, user, or assistant".format(message["role"]))
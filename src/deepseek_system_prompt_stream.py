
def get_tool_use_intro_stream():
    return '''In addition to these, you are able to use multiple tools (which is called tool-use) with your own wisdom to satisfy the user's demand. Here is the introduction of tool-use. <h3>TOOL-USE</h3>
<h4>Tool-use Introduction</h4>
You have access to tools in a tool set given in TOOL SET section. You can only use one tool once in each response. 
Once you used a tool, you will receive the result of the tool-use in the user's next prompt. 
If you want to use multiple tools for a task, 
you should decide which tool to use in current step and use other necessary tools in following responses, 
because you can only use one tool once in each response. When performing the given task, 
please consider whether to use these tools or not and how to use them, 
based on the result of previous tool-uses and your own knowledge. 
If you want to use a tool but it is not listed in the tool set, 
this tool is unavailable and you should consider other available tools or complete the task based on your own knowledge without using a tool. 
Formats related to tool-use are detailed in Tool-use Formatting section, and specific tools you can access are listed in TOOL SET section. 
Please read these contents carefully.'''
    

def get_tool_use_formatting_stream():
    return '''<h4>Tool-use Formatting</h4>
Tool-use is formatted using JSON schema format. 
<h5>Tool set format</h5> 
A tool set shows all tools that can be used. It consists of multiple tools that each server provides. The format of a tool set is as following:
[
  {
    "type": "function",
    "function": {
      "name": "name of the tool",
      "description": "description of the tool",
      "parameters": {
        "type": "object",
        "properties": {"property 1": {"type": "property 1 type"}, "property 2": {"type": "property 2 type"}},
        "required": ["required parameter 1", "required parameter 2"],
      }
    }
  }
]
A tool set can be empty or contains multiple tools provided by multiple servers. If a parameter does not appear in the value of "required" field, then it is an optional parameter. Below are some examples of a tool set.
Example 1: 
[]
In example 1, the tool set is empty which means there is no tools available.

Example 2: 
[
  {
    "type": "function",
    "function": {
      "name": "read_multiple_files",
      "description": "Read the contents of multiple files simultaneously. This is more efficient than reading files one by one when you need to analyze or compare multiple files. Each file's content is returned with its path as a reference. Failed reads for individual files won't stop the entire operation. Only works within allowed directories.",
      "parameters": {
        "type": "object",
        "properties": {
          "paths": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "paths"
        ],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#"
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "write_file",
      "description": "Create a new file or completely overwrite an existing file with new content. Use with caution as it will overwrite existing files without warning. Handles text content with proper encoding. Only works within allowed directories.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string"
          },
          "content": {
            "type": "string"
          }
        },
        "required": [
          "path",
          "content"
        ],
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#"
      }
    }
  }
]
In example 2, the tool set contains two tools "read_multiple_files" and "write_file". A tool set can also contain more tools if you expand this example.

<h5>Response format</h5>
When you do not invoke any tools, please only reply with texts. However, if you need to invoke a tool for the task, please add tool-use instructions after your regular text responses.
Your response with tool-use instructions must adhere to this response frame: 
regular_text_response_here<t>{"tool_calls":[{"tool_name":"name of the tool you want to use","parameters":{"parameter1":"parameter1_value","parameter2":"parameter2_value"}}],"task_complete":"task_complete_value"}</t>
The frame has special tags <t> and </t> in it, which shows this response contains a tool-use in addition to the regular text response. You need to use special tags <t> and </t> to encompass tool-use instructions when you want to invoke a tool, like shown above in the response frame. The tool-use instructions within <t> and </t> will be parsed by the user for invoking tool. 
The value of key "tool_calls" is a list containing the tool you invoke and its parameters. As mentioned earlier, each response may use only one tool and only once, to guarantee correctness of response format. When you use a tool, please make sure to include name of the tool, and parameters for the tool. 
If you do not use any tools, just reply with normal text outputs. "task_complete" shows the status of the ongoing task. If you think you do not need to wait for tool-use results for this task anymore, set the value of "task_complete" to "true", 
otherwise set it to "false" and continute to invoke tools and wait for tool-use results in subsequent responses. The response frame is a normal string, not a JSON string, so never output ```json``` to display it as a JSON string. Please only use double quotes rather than single quotes to encompass strings in the response frame.
Here are some examples of response format.
Example 1. If the task is "please tell me the weather of Osaka today", and you need to invoke the "get_today_weather" tool, then a valid response with tool-use instruction is like: 
I will use "get_today_weather" tool for this task.<t>{"tool_calls":[{"tool_name":"get_weather","parameters":{"location":"Osaka","unit": "celsius"}}],"task_complete":"false"}</t>
NOTE: Do not use more than 1 tool in one response. Do not invoke a tool twice.
Example 2. If the task is "please tell me the result of 1+1", because this is a pure arithmetic question, you do not need to invoke any tools, so just answer with regular text response, such as:
The result of 1+1 is 2.
NOTE: You MUST adhere to the stipulated response format. Do not include any tool-use instructions in the regular text response, because regular text response and tool-use instruction are separate. The user will be very angry if you outputs extra words besides the stipulated response format.'''




def get_system_prmopt_preface_stream():
    return ""
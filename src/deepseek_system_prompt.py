
def get_tool_use_intro():
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
    

def get_tool_use_formatting():
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
Your response must adhere to this frame: {"text":"This is regular text response.","tool_calls":[{"tool_name":"name of the tool you want to use","parameters":{"parameter1":"parameter1_value","parameter2":"parameter2_value"}}],"task_complete":"task_complete_value"}
where the value of "text" is regular text response other than tool calling, and the value of "tool_calls" is a list containing tools you want to use and their parameters. When you use a tool, please make sure to include name of the tool, and parameters for the tool. 
If you do not use any tool, leave the value of "tool_calls" blank. "task_complete" shows the status of the ongoing task. If you think you do not need to invoke tools and wait for tool-use results for this task anymore, set the value of "task_complete" to "true", 
otherwise set it to "false" and continute to invoke tools. The response frame is a normal string, not a JSON string, so never output ```json``` to show it as a JSON string. Please only use double quotes rather than single quotes to encompass strings in the response frame.
For example, if the task is "please tell me the weather of Osaka today", a valid response with tool-use is like: 
{"text": "I will use the tool get_weather to perform this task.","tool_calls": [{"tool_name": "get_weather","parameters": {"location": "Osaka","unit": "celsius"}}],"task_complete": "false"}
ATTENTION: You MUST NOT respond anything besides this stipulated frame. The user will be very angry if you output something besides the stipulated frame'''




def get_system_prmopt_preface():
    return ""
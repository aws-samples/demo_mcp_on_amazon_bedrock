# MCP on Amazon Bedrock
### Update Log
- [20250516] Added streamable HTTP (simple token authentication)
  - Currently only supports basic Bearer token authentication. Configuration example: add server with JSON configuration
  ```json
  {
    "mcpServers": {
      "MCPServerApi": {
        "url": "https://xxx.execute-api.us-east-1.amazonaws.com/Prod/mcp",
        "token":"123456",
      }
    }
  }
  ```  
  You can develop and deploy a serverless HTTP stream server using AWS Lambda. Reference example: https://github.com/mikegc-aws/Lambda-MCP-Server

- [20250507] New Nova Premier and Nova Sonic Voice Agent mode, see Section 6 for details
 - ⚠️ If deploying on EC2, you need to use [HTTPS deployment method](HTTPS_SETUP.md). If deploying locally, continue using the previous deployment method.

- [20250419] Keep Server Session feature, which can save all session historical messages on the server side, including Tool use history
  - UI activation method: Control through the `Keep Session on Server` switch on the UI. When clicking `Clear Conversion`, it will send a `v1/remove/history` request to clear the server session messages.
  - If using the server interface directly, add keep_session=True in the ChatCompletionRequest to indicate server-side saving. Only system and the latest user message need to be passed in the messages, no need to include historical messages.
  - To clear server-side history, send a `POST v1/remove/history` request
- [20250418] Added support for China region silicon-based mobile deepseek v3 model and SSE server support
  - Note: if upgrading, you need to run `uv sync` to update dependencies
  - Add use_bedrock=0 in .env file
- Demo Videos
![alt text](assets/demo_videos.png)
> ChatBot is the most common application form in the large model era, but it is limited by the large model's inability to obtain timely information and operate external systems, making ChatBot application scenarios relatively limited. Later, with the introduction of Function Calling/Tool Use functionality, large models were able to interact with external systems, but the drawback is that large model business logic and Tool development are tightly coupled, unable to leverage the efficiency of scale on the Tool side. Anthropic launched [MCP](https://www.anthropic.com/news/model-context-protocol) at the end of November 2024, breaking this situation and introducing the strength of the entire community to scale up on the Tool side. Currently, the open source community and various vendors have developed rich [MCP servers](https://github.com/modelcontextprotocol/servers), making the Tool side flourish. End users can plug and play to integrate them into their ChatBots, greatly extending the capabilities of ChatBot UI, with a trend of ChatBot unifying various system UIs.
- How MCP works
![alt text](assets/mcp_how.png)
- AWS-based MCP enterprise architecture design concept
![alt text](assets/image-aws-arch.png)
- This project provides ChatBot interaction services based on Nova, Claude, and other large models in **Bedrock**, while introducing **MCP** to greatly enhance and extend the application scenarios of ChatBot-form products, supporting seamless integration with local file systems, databases, development tools, internet searches, etc. If a ChatBot containing a large model is equivalent to a brain, then introducing MCP is like equipping it with arms and legs, truly making the large model move and connect with various existing systems and data.
- **This Demo Solution Architecture**
![arch](assets/arch.png)  

- **Deepwiki** 

https://deepwiki.com/aws-samples/demo_mcp_on_amazon_bedrock/1.1-system-architecture

- **Core Components**

![alt text](assets/core_comp.png)  
   1. MCP Client (mcp_client.py)
      - Responsible for managing connections to multiple MCP servers
      - Handles tool calls and resource access
      - Provides tool name mapping and normalization functionality
   2. Chat Client (chat_client.py, chat_client_stream.py)
      - Interacts with Amazon Bedrock API
      - Processes user queries and model responses
      - Supports streaming responses and tool calls
   3. Main Service (main.py)
      - Provides FastAPI service, exposing chat and MCP management APIs
      - Manages user sessions and MCP server configurations
      - Handles concurrent requests and resource cleanup
   4. Web Interface (chatbot.py)
      - Streamlit-based user interface
      - Allows users to interact with models and manage MCP servers
      - Displays tool call results and thinking processes
- **Technical Architecture**
   1. Front-end and back-end separation
      - Backend: FastAPI service providing REST API
      - Frontend: Streamlit Web interface
   2. Multi-user support
      - User session isolation
      - Support for concurrent access
   3. MCP server management
      - Support for dynamically adding and removing MCP servers
      - Global and user-specific MCP server configurations
- **Workflow**
![alt text](assets/image_process1.png)  
   1. User sends a query through the Web interface
   2. Backend service receives the query and forwards it to the Bedrock model
   3. If the model needs to use tools, the MCP client calls the corresponding MCP server
   4. Tool call results are returned to the model, and the model generates the final response
   5. Response is returned to the user, including the tool call process and results
- This project is still continuously exploring and improving. MCP is flourishing throughout the community, and we welcome everyone to follow along!
## 1. Project Features:
   - Supports both Amazon Nova Pro and Claude Sonnet models
   - Fully compatible with Anthropic's official MCP standard, allowing direct use of various [MCP servers](https://github.com/modelcontextprotocol/servers/tree/main) from the community in the same way
   - Decouples MCP capabilities from the client, encapsulates MCP capabilities on the server side, provides API services externally, and the chat interface is compatible with OpenAI, facilitating integration with other chat clients
   - Front-end and back-end separation, MCP Client and MCP Server can both be deployed on the server side, allowing users to interact directly through the backend web service via a web browser, thereby accessing LLM and MCP Server capabilities and resources
   - Supports multiple users, user session isolation, and concurrent access
   - Streaming responses
   - Thinking process visualization
   - Tool call result display and Computer Use screenshot display
## 2. Installation Steps
### 2.1. Dependencies Installation
Currently, mainstream MCP Servers are developed based on NodeJS or Python and run on users' PCs, so users' PCs need to install these dependencies.
### 2.1 NodeJS
NodeJS [download and install](https://nodejs.org/en), this project has been thoroughly tested with `v22.12.0`.
### 2.2 Python
Some MCP Servers are developed based on Python, so users must install [Python](https://www.python.org/downloads/). Additionally, this project's code is also developed based on Python and requires environment and dependency installation.
First, install the Python package management tool uv, please refer to the [uv](https://docs.astral.sh/uv/getting-started/installation/) official guide, this project has been thoroughly tested with `v0.5.11`.
### 2.3 Environment Configuration
After downloading and cloning the project, enter the project directory to create a Python virtual environment and install dependencies:
```bash
sudo apt update
sudo apt-get install portaudio19-dev
uv sync
```

If using a Mac environment:  
```bash
brew install portaudio
uv sync
```
At this point, the virtual environment is created in the `.venv` directory of the project, activate it:
```
source .venv/bin/activate
```
- (Optional) Use AWS CLI tool to create a DynamoDB table to save user config information. If not creating DynamoDB, it will directly generate user_mcp_config.json saved in the conf/ directory
```bash
aws dynamodb create-table \
    --table-name mcp_user_config_table \
    --attribute-definitions AttributeName=userId,AttributeType=S \
    --key-schema AttributeName=userId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST 
```
### 2.4 Configuration Editing (Using Bedrock in Regions Outside China)
> Tips: If you need to configure multiple account ak/sk using a rotation mechanism, you can add a `credential.csv` in the conf/ directory with column names **ak** and **sk**, and fill in multiple ak/sk pairs, for example:
ak,sk  
ak1,sk1  
ak2,sk2  

Run the following command to create an .env file, **please modify AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION and other information before running**
```bash
cat << EOF > .env
AWS_ACCESS_KEY_ID=(optional, not needed if credential.csv exists)
AWS_SECRET_ACCESS_KEY=(optional)<your-secret-key>
AWS_REGION=<your-region>
LOG_DIR=./logs
CHATBOT_SERVICE_PORT=8502
MCP_SERVICE_HOST=127.0.0.1
MCP_SERVICE_PORT=7002
API_KEY=123456
MAX_TURNS=200
INACTIVE_TIME=10
#If not using dynamodb, delete the line below
ddb_table=mcp_user_config_table
USE_HTTPS=0
EOF
```
Note: This project uses **AWS Bedrock Nova/Claude** series models, so you need to register and obtain access keys for the above services.
### 2.5 Configuration Editing (Using Silicon Flow API in China Region)
> Tips: For China region, you need to obtain Silicon Flow API Key in advance
Run the following command to create an .env file, **Note: please modify COMPATIBLE_API_KEY, COMPATIBLE_API_BASE and other information before running**
```bash
cat << EOF > .env
COMPATIBLE_API_KEY=<Silicon Flow apikey>
COMPATIBLE_API_BASE=https://api.siliconflow.cn
LOG_DIR=./logs
CHATBOT_SERVICE_PORT=8502
MCP_SERVICE_HOST=127.0.0.1
MCP_SERVICE_PORT=7002
API_KEY=123456
MAX_TURNS=200
INACTIVE_TIME=60
#Flag for not using bedrock
use_bedrock=0
#If not using dynamodb, delete the line below
ddb_table=mcp_user_config_table
USE_HTTPS=0
EOF
```
Default configuration supports `DeepSeek-V3` and `Qwen3`. If you need to support other models (must be models that support tool use), please modify the [conf/config.json](conf/config.json) configuration to add models, for example:
```json
  {
    "model_id": "Qwen/Qwen3-235B-A22B",
    "model_name": "Qwen3-235B-A22B"
  },
  {
    "model_id": "Qwen/Qwen3-30B-A3B",
    "model_name": "Qwen3-30B-A3B"
  },
  {
    "model_id": "Pro/deepseek-ai/DeepSeek-V3",
    "model_name": "DeepSeek-V3-Pro"
  },
  {
    "model_id": "deepseek-ai/DeepSeek-V3",
    "model_name": "DeepSeek-V3-free"
  }
```
## 3. Running
### 3.1 This project includes 1 backend service and a streamlit frontend, with front and back ends connected via REST API:
- **Chat interface service (Bedrock+MCP)**, which can provide Chat interfaces externally, host multiple MCP servers simultaneously, support multi-turn dialogue input history, and append tool call intermediate results to response content. Streaming responses are not supported yet.
- **ChatBot UI**, communicates with the above Chat interface service, providing multi-turn dialogue and MCP management Web UI demo service

### 3.2. (Optional) HTTPS Setup
Refer to [HTTPS_SETUP](./HTTPS_SETUP.md)

### 3.3. Chat Interface Service (Bedrock+MCP)
- The interface service can provide independent APIs externally to connect with other chat clients, achieving decoupling of server-side MCP capabilities and clients
- You can view the API documentation through http://{ip}:7002/docs#/
![alt text](./assets/image_api.png)
- Edit the configuration file `conf/config.json`, which predetermines which MCP servers to start. You can edit it to add or modify MCP server parameters.
- For the parameter specifications of each MCP server, refer to the following example: 
```
"db_sqlite": {
    "command": "uvx",
    "args": ["mcp-server-sqlite", "--db-path", "./tmp/test.db"],
    "env": {},
    "description": "DB Sqlite CRUD - MCP Server",
    "status": 1
}
```
- Start the service:
```bash
bash start_all.sh
```
- Stop the service:
```bash
bash stop_all.sh
```
- After starting, check the log `logs/start_mcp.log` to confirm there are no errors, then you can run a test script to check the Chat interface:
```bash
# The script uses Amazon Nova-lite model from Bedrock, which can be changed to others
# 123456 is used as the API key by default, please change according to your actual settings
curl http://127.0.0.1:7002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 123456" \
  -H "X-User-ID: user123" \
  -d '{
    "model": "us.amazon.nova-pro-v1:0",
    "mcp_server_ids":["local_fs"],
    "stream":true,
    "keep_session":false,
    "messages": [
      {
        "role": "user",
        "content": "list files in current dir"
      }
    ]
  }'
```
- If keep_session:true means keeping the session on the server side, the server will preserve historical messages and tool calls, and the client only needs to send the latest user message
### 3.4. ChatBot UI 
* The previous streamlit UI has been deprecated
Now using the new React UI
- 🚀 Modern frontend built on Next.js 15 and React 18, supporting Dark/Light mode
- 🎨 Beautiful user interface implemented with Tailwind CSS and Shadcn UI component library
- 🔄 Real-time streaming responses, providing a smooth conversation experience
- 🧠 Support for "thinking" mode, showing the model's reasoning process
- 🛠️ MCP server management functionality, supporting adding and configuring servers
- 👤 User session management, maintaining conversation context
- 📊 Visualization of tool use results, including image display
- 📱 Support for multimodal input, including uploading images, PDFs, documents, and other attachments
- [Installation Steps](react_ui/README.md)
![alt text](react_ui/image.png)
![alt text](react_ui/image-1.png)
#### ChatBot UI 
After starting, check the log `logs/start_chatbot.log` to confirm there are no errors, then open [service address](http://localhost:3000/chat) in your browser to experience the enhanced Bedrock large model ChatBot capabilities with MCP.
Since file system operations, SQLite database, and other MCP Servers are already built-in, you can try asking the following questions consecutively for a hands-on experience:
```
show all of tables in the db
how many rows in that table
show all of rows in that table
save those rows record into a file, filename is rows.txt
list all of files in the allowed directory
read the content of rows.txt file
```
### 3.5. Adding MCP Server
Currently, there are two ways to add an MCP Server:
1. Preset in `conf/config.json`, which will load the configured MCP Servers every time the Chat interface service restarts
2. Add MCP Servers through the ChatBot UI by submitting a form with MCP Server parameters. This is only effective for the current session and will be lost after service restart
Below is a demonstration of how to add an MCP Server through the ChatBot UI, using the Web Search provider [Exa](https://exa.ai/) as an example. The open source community already has a [MCP Server](https://github.com/exa-labs/exa-mcp-server) available for it.
First, go to the [Exa](https://exa.ai/) official website to register an account and obtain an API Key.
Then click [Add MCP Server], fill in the following parameters in the popup menu and submit:
- Method 1, directly add MCP json configuration file (same format as Anthropic official) 
```json
{
  "mcpServers": {
    "exa": {
      "command": "npx",
      "args": ["-y","exa-mcp-server"],
      "env": {
        "EXA_API_KEY": "your-api-key-here"
      }
    }
  }
}
```
- Method 2, add by field 
At this point, you can see the newly added item in the existing MCP Server list. Check it to launch that MCP Server.
## 4. CDK Installation (New)
[README](cdk/README.me)
## 5 Demo cases
### 5.1. Using MCP to operate Browser 
- Add this json file on the chatbot interface. Note: this [browser use](https://github.com/vinayak-mehta/mcp-browser-use) server starts the browser in headed mode by default, so it's suitable for demos deployed on local computers. If deploying on a server, please add the phrase `use headless is true to initialize the browser` in your prompt
**Note** For the first run, you need to install the corresponding dependency package on the server `sudo apt-get install libgbm1`
```json
{ "mcpServers": 
	{ "mcp-browser": 
		{ "command": "uvx", 
        "args": ["mcp-browser-use"],
        "env": {},
        "description": "mcp-browser"
		} 
	} 
}
```
- **New added 20250331** Using MS official [playwright](https://mcp.so/server/playwright-mcp/microsoft): 
**Note** If headless mode is needed, add the "--headless" parameter. For the first run, you need to install the corresponding dependency package on the server `npx playwright install chrome`
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--headless"
      ]
    }
  }
}
```
- test 1, In the chatbot interface, check both mcp-browser and local file system servers
Input task: `Help me prepare an introduction about Xiaomi SU7 ultra, including performance, price, special features, with rich text and images, and create a beautiful HTML saved to the local directory. If images from other websites are referenced, ensure they actually exist and are accessible.`
[Video demo](https://mp.weixin.qq.com/s/csg7N8SHoIR2WBgFOjpm6A)
[Final output file example](docs/xiaomi_su7_ultra_intro.html)
  - If running for the first time, you may need to install additional software. Please follow the prompts returned by the tool call
- test 2, In the chatbot interface, check exa, mcp-browser and local file system (3 servers), which will combine search engines and browsers to jointly obtain information and images, forming a richer report
Input task: `I want a comprehensive analysis of Tesla stock, including: Overview: company profile, key metrics, performance data, and investment recommendations Financial data: revenue trends, profit margins, balance sheet, and cash flow analysis Market sentiment: analyst ratings, sentiment indicators, and news impact Technical analysis: price trends, technical indicators, and support/resistance levels Asset comparison: market share and financial metrics comparison with major competitors Value investor: intrinsic value, growth potential, and risk factors Investment thesis: SWOT analysis and recommendations for different types of investors. And create a beautiful HTML saved to the local directory. If images from other websites are referenced, ensure they actually exist and are accessible. You can use mcp-browser and exa search to obtain as much real-time data and images as possible.` 
[Final output file example](docs/tesla_stock_analysis.html)
- **Sequence Diagram 1: Using Headless Browser MCP Server**
![alt text](assets/image-seq2.png)
### 5.2 Using MCP Computer Use to operate EC2 remote desktop
- Install and download remote-computer-use in another directory
```bash
git clone https://github.com/aws-samples/aws-mcp-servers-samples.git
```
- You need to set up an EC2 instance in advance and configure VNC remote desktop. For installation steps, please refer to the [instructions](https://github.com/aws-samples/aws-mcp-servers-samples/blob/main/remote_computer_use/README.md)
- After the environment is set up, configure the MCP demo client as follows:
```json
{
    "mcpServers": {
        "computer_use": {
            "command": "uv",
            "env": {
                "VNC_HOST":"",
                "VNC_PORT":"5901",
                "VNC_USERNAME":"ubuntu",
                "VNC_PASSWORD":"",
                "PEM_FILE":"",
                "SSH_PORT":"22",
                "DISPLAY_NUM":"1"
            },
            "args": [
                "--directory",
                "/absolute_path_to/remote_computer_use",
                "run",
                "server_claude.py"
            ]
        }
    }
}
```
- Using Computer Use is recommended with the Claude 3.7 model, and adding the following system prompt
```plaintext
You are an expert research assistant with deep analytical skills.
you have capability:
<SYSTEM_CAPABILITY>
* You are utilising an Ubuntu virtual machine using Linux architecture with internet access.
* You can feel free to install Ubuntu applications with your bash tool. Use curl instead of wget.
* When viewing a page it can be helpful to zoom out so that you can see everything on the page.  Either that, or make sure you scroll down to see everything before deciding something isn't available.
* When using your computer function calls, they take a while to run and send back to you.  Where possible/feasible, try to chain multiple of these calls all into one function calls request.
* You can double click to open firefox
</SYSTEM_CAPABILITY>
<IMPORTANT>
  * Don't assume an application's coordinates are on the screen unless you saw the screenshot. To open an application, please take screenshot first and then find out the coordinates of the application icon. 
  * When using Firefox, if a startup wizard or Firefox Privacy Notice appears, IGNORE IT.  Do not even click "skip this step".  Instead, click on the address bar where it says "Search or enter address", and enter the appropriate search term or URL there. Maximize the Firefox browser window to get wider vision.
  * If the item you are looking at is a pdf, if after taking a single screenshot of the pdf it seems that you want to read the entire document instead of trying to continue to read the pdf from your screenshots + navigation, determine the URL, use curl to download the pdf, install and use pdftotext to convert it to a text file, and then read that text file directly with your StrReplaceEditTool.
  * After each step, take a screenshot and carefully evaluate if you have achieved the right outcome. Explicitly show your thinking: "I have evaluated step X..." If not correct, try again. Only when you confirm a step was executed correctly should you move on to the next one.
</IMPORTANT>
``` 
- **Sequence Diagram: Using Computer Use to operate EC2 Remote Desktop**
![alt text](assets/image-seq3.png)
### 5.3. Using Sequential Thinking + Search for Deep Research (mainly for Nova/Claude 3.5 models, Claude 3.7 doesn't need it)
- Enable both websearch (refer to EXA configuration above) and [Sequential Thinking MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking). Currently, Sequential Thinking MCP Server is already preset in the configuration file. After starting, you can see the server name is cot.
![alt text](assets/image-serverlist.png)
- Sequential Thinking provides a structured output reasoning chain through dynamic structured thinking processes and reflection, prompting the model to produce a structured output reasoning chain through tool calls.
- EXA Search simultaneously provides keyword and vector retrieval search for network knowledge, returning detailed content from pages.
- Test questions
```
1. use search tool and sequential thinking to make comparison report between different agents frameworks such as autogen, langgraph, aws multi agents orchestrator
2. use sequential thinking and search tool to make me a travel plan to visit shanghai between 3/1/2025 to 3/5/2025. I will departure from Beijing
3. use sequential thinking to research what the key breakthroughs and future impact of deepseek r1
4. search and compare the API performance of deepseek r1 full version APIs provided by Volcano Engine, Alibaba Bailian, and Silicon Flow, including inference speed, TTFT, maximum context length, etc. Use the sequential thinking tool
```
- Results overview
![alt text](assets/image_deepresearch_1.png)
![alt text](assets/image_deepresearch_2.png)
- **Sequence Diagram: Using Search API MCP Server**
![alt text](assets/image-seq1.png)

###  5.4. Using Amazon Knowledge Base
First create or use an existing Bedrock Knowledge Base in the Bedrock console, and note down the Knowledge Base Id
Clone [AWS Knowledge Base Retrieval MCP Server](https://github.com/modelcontextprotocol/servers) locally, and replace the file in `src/aws-kb-retrieval-server/index.ts` with the file from [assets/aws-kb-retrieval-server/index.ts)](assets/aws-kb-retrieval-server/index.ts).
> The new file specifies the knowledgeBaseId through an environment variable, so it no longer needs to be passed through dialogue.
Package it with the following command in the newly cloned servers directory
```sh
docker build -t mcp/aws-kb-retrieval:latest -f src/aws-kb-retrieval-server/Dockerfile . 
```
Then add this json file on the chatbot interface, note that the fields in env need to be replaced with your own account information and Knowledge Base Id 
```json
{
  "mcpServers": {
    "aws-kb-retrieval": {
      "command": "docker",
      "args": [ "run", "-i", "--rm", "-e", "AWS_ACCESS_KEY_ID", "-e", "AWS_SECRET_ACCESS_KEY", "-e", "AWS_REGION", "-e", "knowledgeBaseId", "mcp/aws-kb-retrieval:latest" ],
      "env": {
        "AWS_ACCESS_KEY_ID": "YOUR_ACCESS_KEY_HERE",
        "AWS_SECRET_ACCESS_KEY": "YOUR_SECRET_ACCESS_KEY_HERE",
        "AWS_REGION": "YOUR_AWS_REGION_HERE",
        "knowledgeBaseId":"The knowledage base id"
      }
    }
  }
}
```

## 6. Voice Agent + MCP
- ⚠️ If deploying on EC2, you need to use [HTTPS deployment method](HTTPS_SETUP.md). If deploying locally, continue using the previous deployment method.
- Click on the microphone icon to experience end-to-end voice Agent mode. In this mode, the [Nova Sonic Speech 2 Speech model](https://docs.aws.amazon.com/nova/latest/userguide/speech.html) is used, which currently only supports English conversations and three voice output tones.
Nova Sonic model supports Function call, so it can also add MCP servers. For example, after enabling tavily search and time mcp server, ask in voice "what is the weather of beijing". You can see that the Nova Sonic model will listen to the microphone and directly respond with voice output, while simultaneously converting the voice input and output into text displayed in the chat box.
![alt text](assets/sonic_1.png)
- Voice Integration flow  
![alt text](assets/voice_flow.png)

## 7. Awesome MCPs
- AWS MCP Servers Samples https://github.com/aws-samples/aws-mcp-servers-samples
- AWS Labs MCP Servers https://awslabs.github.io/mcp
- https://github.com/punkpeye/awesome-mcp-servers
- https://github.com/modelcontextprotocol/servers
- https://www.aimcp.info/en
- https://github.com/cline/mcp-marketplace
- https://github.com/xiehust/sample-mcp-servers
- https://mcp.composio.dev/
- https://smithery.ai/
- https://mcp.so/

## 9. [LICENSE](./LICENSE)

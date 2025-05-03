#!/bin/bash
export $(grep -v '^#' .env | xargs)

echo "Stopping services..."

echo "Stopping MCP service on port ${MCP_SERVICE_PORT}"
pid=$(lsof -t -i:${MCP_SERVICE_PORT})

if [ -n "$pid" ]; then
    echo "Found main process: $pid"
    
    # 先尝试通过进程组终止所有相关进程
    pgid=$(ps -o pgid= $pid | grep -o '[0-9]*')
    if [ -n "$pgid" ]; then
        echo "Sending SIGTERM to process group $pgid"
        kill -- -$pgid 2>/dev/null
        sleep 2
        # 如果仍有进程存活，使用SIGKILL
        if kill -0 -- -$pgid 2>/dev/null; then
            echo "Some processes still running, sending SIGKILL"
            kill -9 -- -$pgid 2>/dev/null
        fi
    else
        # 如果进程组方法失败，使用递归方法终止进程树
        echo "Using recursive process termination"
        
        # 递归终止进程及其子进程
        kill_process_tree() {
            local parent=$1
            local child_pids=$(pgrep -P $parent)
            
            # 先递归终止所有子进程
            for child in $child_pids; do
                kill_process_tree $child
            done
            
            # 然后终止当前进程
            echo "Terminating process $parent"
            kill $parent 2>/dev/null
            sleep 0.1
            # 如果仍然存在则强制终止
            if kill -0 $parent 2>/dev/null; then
                kill -9 $parent 2>/dev/null
            fi
        }
        
        # 执行递归终止
        kill_process_tree $pid
    fi
    
    echo "All processes should be terminated"
else
    echo "MCP service not found running on port ${MCP_SERVICE_PORT}"
fi

# Stop Chatbot service
echo "Stopping Chatbot service on port ${CHATBOT_SERVICE_PORT}"
pid=$(lsof -t -i:${CHATBOT_SERVICE_PORT} -c streamlit)
kill -9 $pid
echo "All services stopped"
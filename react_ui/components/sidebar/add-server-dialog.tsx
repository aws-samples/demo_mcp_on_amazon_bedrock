'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useStore } from '@/lib/store';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { addMcpServer as apiAddMcpServer } from '@/lib/api/chat';

interface AddServerDialogProps {
  onClose: () => void;
}

export default function AddServerDialog({ onClose }: AddServerDialogProps) {
  const [serverName, setServerName] = useState('');
  const [serverId, setServerId] = useState('');
  const [serverCommand, setServerCommand] = useState('');
  const [serverArgs, setServerArgs] = useState('');
  const [serverEnv, setServerEnv] = useState('');
  const [jsonConfig, setJsonConfig] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('json');
  
  const { addMcpServer, userId } = useStore(); // 添加 userId
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (activeTab === 'form' && (!serverName || !serverId || !serverCommand)) {
      setError('Please fill in all required fields');
      return;
    }
    
    if (activeTab === 'json' && (!jsonConfig || !serverName)) {
      setError('Please provide a server name and JSON configuration');
      return;
    }
    
    setIsSubmitting(true);
    setError('');
    
    try {
      let finalServerId = serverId;
      let finalServerCommand = serverCommand;
      let args = serverArgs.split(' ').filter(Boolean);
      let env = {};
      
      if (activeTab === 'form') {
        // Parse form input
        if (serverEnv) {
          try {
            env = JSON.parse(serverEnv);
          } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            setError(`Invalid JSON format for environment variables: ${errorMessage}`);
            setIsSubmitting(false);
            return;
          }
        }
      } else {
        // Parse JSON config
        try {
          let config = JSON.parse(jsonConfig);
          
          // Handle nested mcpServers structure
          if (config.mcpServers) {
            config = config.mcpServers;
          }
          
          // Extract server ID (first key in object)
          const configServerId = Object.keys(config)[0];
          if (!configServerId) {
            throw new Error('Invalid JSON configuration format');
          }
          
          finalServerId = configServerId;
          const serverConfig = config[configServerId];
          
          // Extract command, args, env
          // if (!serverConfig.command) {
          //   throw new Error('Missing "command" in server configuration');
          // }
          
          finalServerCommand = serverConfig.command;
          args = serverConfig.args || [];
          env = serverConfig.env || {};
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : 'Unknown error';
          setError(`Invalid JSON configuration: ${errorMessage}`);
          setIsSubmitting(false);
          return;
        }
      }
      
      // Call API to add server
      let configJson = {};
      
      if (activeTab === 'json') {
        try {
          configJson = JSON.parse(jsonConfig);
        } catch (error) {
          // We already validated JSON earlier, so this shouldn't happen
          console.error("Error parsing JSON config:", error);
        }
      }
      
      const result = await apiAddMcpServer(
        userId || 'anonymous', // 使用从store获取的userId
        finalServerId,
        serverName,
        finalServerCommand,
        args,
        activeTab === 'form' ? env : null,
        activeTab === 'json' ? configJson : {}
      );
      
      if (result.success) {
        // Add to local store if API call was successful
        addMcpServer({
          serverId: finalServerId,
          serverName,
          enabled: true
        });
        
        // Close the dialog
        onClose();
      } else {
        setError(`Server error: ${result.message}`);
        setIsSubmitting(false);
        return;
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(`An error occurred while adding the server: ${errorMessage}`);
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };
  
  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center">
      <div className="bg-card border border-border rounded-lg shadow-lg w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Add MCP Server</h2>
          <button 
            onClick={onClose}
            className="p-2 rounded-md hover:bg-secondary transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        {error && (
          <div className="mb-4 p-3 bg-destructive/10 border border-destructive text-destructive text-sm rounded-md">
            {error}
          </div>
        )}
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="server-name" className="text-sm font-medium">
              Server Name *
            </label>
            <input
              id="server-name"
              value={serverName}
              onChange={(e) => setServerName(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-md border border-input bg-background"
              placeholder="e.g., GitHub MCP"
              required
            />
          </div>
          
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2 mb-4">
              <TabsTrigger value="json">JSON Config</TabsTrigger>
              <TabsTrigger value="form">Form</TabsTrigger>
            </TabsList>
            
            <TabsContent value="form" className="space-y-4">
          
              <div className="space-y-2">
                <label htmlFor="server-id" className="text-sm font-medium">
                  Server ID *
                </label>
                <input
                  id="server-id"
                  value={serverId}
                  onChange={(e) => setServerId(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-md border border-input bg-background"
                  placeholder="e.g., github_mcp"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Unique identifier for the server (alphanumeric and underscores only)
                </p>
              </div>
              
              <div className="space-y-2">
                <label htmlFor="server-command" className="text-sm font-medium">
                  Command *
                </label>
                <select
                  id="server-command"
                  value={serverCommand}
                  onChange={(e) => setServerCommand(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-md border border-input bg-background"
                  required
                >
                  <option value="">Select command</option>
                  <option value="node">node</option>
                  <option value="python">python</option>
                  <option value="npx">npx</option>
                  <option value="uvx">uvx</option>
                  <option value="docker">docker</option>
                  <option value="uv">uv</option>
                </select>
              </div>
              
              <div className="space-y-2">
                <label htmlFor="server-args" className="text-sm font-medium">
                  Arguments
                </label>
                <input
                  id="server-args"
                  value={serverArgs}
                  onChange={(e) => setServerArgs(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-md border border-input bg-background"
                  placeholder="e.g., -y mcp-server-git --repository path/to/repo"
                />
              </div>
              
              <div className="space-y-2">
                <label htmlFor="server-env" className="text-sm font-medium">
                  Environment Variables (JSON)
                </label>
                <textarea
                  id="server-env"
                  value={serverEnv}
                  onChange={(e) => setServerEnv(e.target.value)}
                  className="w-full h-24 px-3 py-2 text-sm rounded-md border border-input bg-background"
                  placeholder='{"API_KEY": "your_key_here"}'
                />
              </div>
            </TabsContent>
            
            <TabsContent value="json" className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="json-config" className="text-sm font-medium">
                  JSON Configuration *
                </label>
                <textarea
                  id="json-config"
                  value={jsonConfig}
                  onChange={(e) => setJsonConfig(e.target.value)}
                  className="w-full h-64 px-3 py-2 text-sm rounded-md border border-input bg-background font-mono"
                  placeholder={`{\n  "mcpServers": {\n    "server_id": {\n      "command": "node",\n      "args": ["path/to/script.js"],\n      "env": {\n        "API_KEY": "your_key_here"\n      }\n    }\n  }\n}`}
                  required={activeTab === 'json'}
                />
                <p className="text-xs text-muted-foreground">
                  Paste a complete MCP server configuration in JSON format
                </p>
              </div>
            </TabsContent>
          </Tabs>
          
          <div className="flex justify-end space-x-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Adding...' : 'Add Server'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

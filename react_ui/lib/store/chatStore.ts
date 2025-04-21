import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type MessageRole = 'system' | 'user' | 'assistant';

export interface ContentItem {
  type: string;
  text?: string;
  image_url?: {
    url: string;
    detail?: string;
  };
  file?: {
    file_id?: string;
    file_data?: string;
    filename?: string;
  };
}

export interface Message {
  role: MessageRole;
  content: string | ContentItem[];
  toolUse?: any[];
  thinking?: string;
}

export interface ToolUse {
  name: string;
  input: Record<string, any>;
  output?: Record<string, any>;
}

export interface MCPServer {
  server_id: string;
  server_name: string;
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

interface ChatState {
  // Messages
  messages: Message[];
  thinking: string;
  
  // Settings
  systemPrompt: string;
  enableStream: boolean;
  enableThinking: boolean;
  maxTokens: number;
  budgetTokens: number;
  temperature: number;
  onlyNMostRecentImages: number;
  keepSession: boolean;
  
  // Models and servers
  modelNames: Record<string, string>; // name -> id
  selectedModel: string;
  mcpServers: Record<string, string>; // name -> id
  selectedServers: string[];
  
  // User info
  userId: string;
  
  // Actions
  setUserId: (id: string) => void;
  generateRandomUserId: () => void;
  setSystemPrompt: (prompt: string) => void;
  addMessage: (message: Message) => void;
  setThinking: (thinking: string) => void;
  clearMessages: () => void;
  setModelNames: (models: Record<string, string>) => void;
  setMcpServers: (servers: Record<string, string>) => void;
  toggleServer: (serverName: string) => void;
  setSelectedModel: (modelName: string) => void;
  updateSettings: (settings: Partial<ChatState>) => void;
  setKeepSession: (keep: boolean) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      // Messages
      messages: [{ role: 'system', content: 'You are a deep researcher' }],
      thinking: '',
      
      // Settings
      systemPrompt: 'You are a deep researcher',
      enableStream: true,
      enableThinking: false,
      maxTokens: 8000,
      budgetTokens: 8192,
      temperature: 0.6,
      onlyNMostRecentImages: 1,
      keepSession: true,
      
      // Models and servers
      modelNames: {},
      selectedModel: '',
      mcpServers: {},
      selectedServers: [],
      
      // User info
      userId: '',
      
      // Actions
      setUserId: (id) => set({ userId: id }),
      
      generateRandomUserId: () => {
        const newId = Math.random().toString(36).substring(2, 10);
        set({ userId: newId });
        // Ensure we always store a plain string, not a JSON object
        localStorage.setItem('mcp_chat_user_id', newId);
      },
      
      setSystemPrompt: (prompt) => {
        set((state) => {
          // Update system prompt in state
          const newMessages = [...state.messages];
          if (newMessages[0]?.role === 'system') {
            newMessages[0].content = prompt;
          } else {
            newMessages.unshift({ role: 'system', content: prompt });
          }
          
          return { 
            systemPrompt: prompt,
            messages: newMessages
          };
        });
      },
      
      addMessage: (message) => set((state) => {
        // Check if this is an assistant message and we already have an assistant message as the last one
        if (message.role === 'assistant' && 
            state.messages.length > 0 && 
            state.messages[state.messages.length - 1].role === 'assistant') {
          // Update the last message instead of adding a new one
          const newMessages = [...state.messages];
          newMessages[newMessages.length - 1] = {
            ...newMessages[newMessages.length - 1],
            content: message.content
          };
          return { messages: newMessages };
        } else {
          // Add as a new message
          return { messages: [...state.messages, message] };
        }
      }),
      
      setThinking: (thinking) => set({ thinking }),
      
      clearMessages: () => set((state) => ({ 
        messages: [{ role: 'system', content: state.systemPrompt }] 
      })),
      
      setModelNames: (models) => set({ 
        modelNames: models,
        selectedModel: Object.keys(models)[0] || ''
      }),
      
      setMcpServers: (servers) => set({ mcpServers: servers }),
      
      toggleServer: (serverName) => set((state) => {
        const serverId = state.mcpServers[serverName];
        if (!serverId) return state;
        
        const newSelectedServers = [...state.selectedServers];
        const index = newSelectedServers.indexOf(serverId);
        
        if (index >= 0) {
          newSelectedServers.splice(index, 1);
        } else {
          newSelectedServers.push(serverId);
        }
        
        return { selectedServers: newSelectedServers };
      }),
      
      setSelectedModel: (modelName) => set({ selectedModel: modelName }),
      
      updateSettings: (settings) => set(settings),
      
      setKeepSession: (keep) => set({ keepSession: keep }),
    }),
    {
      name: 'mcp-chat-storage',
      partialize: (state) => ({
        userId: state.userId,
        systemPrompt: state.systemPrompt,
        enableStream: state.enableStream,
        enableThinking: state.enableThinking,
        maxTokens: state.maxTokens,
        budgetTokens: state.budgetTokens,
        temperature: state.temperature,
        onlyNMostRecentImages: state.onlyNMostRecentImages,
        keepSession: state.keepSession,
      }),
    }
  )
);

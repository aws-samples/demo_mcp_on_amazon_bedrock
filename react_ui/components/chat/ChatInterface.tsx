'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useStore, McpServer } from '@/lib/store';
import { v4 as uuidv4 } from 'uuid';
// import { ToolInputPanel } from './ToolInputPanel';
import { ToolUsagePanel } from './ToolUsagePanel';
import { fetchMcpServers } from '@/lib/api';

export default function ChatInterface() {
  const [showSettings, setShowSettings] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(30); // Default width 30%
  const [isResizing, setIsResizing] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isLoadingMcpServers, setIsLoadingMcpServers] = useState(true);
  const resizeRef = useRef<HTMLDivElement>(null);
  const loadedRef = useRef<boolean>(false);
  const { userId, setUserId, mcpServers, setMcpServers } = useStore();
  
  // Store sidebar width in localStorage
  useEffect(() => {
    const storedWidth = localStorage.getItem('mcp_sidebar_width');
    if (storedWidth) {
      setSidebarWidth(parseInt(storedWidth));
    }
    
    const sidebarCollapsed = localStorage.getItem('mcp_sidebar_collapsed');
    if (sidebarCollapsed) {
      setIsSidebarCollapsed(sidebarCollapsed === 'true');
    }
  }, []);
  
  // Save sidebar width to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('mcp_sidebar_width', sidebarWidth.toString());
  }, [sidebarWidth]);
  
  // Save sidebar collapsed state to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('mcp_sidebar_collapsed', isSidebarCollapsed.toString());
  }, [isSidebarCollapsed]);
  
  // Handle mouse down on resize handle
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    
    // Add a class to the body to change cursor during resize
    document.body.classList.add('resizing');
  }, []);
  
  // Handle mouse move for resizing
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      
      const containerWidth = window.innerWidth;
      // Calculate the width from the right edge of the screen instead of the left
      // This makes dragging left increase the sidebar width and dragging right decrease it
      const newWidth = 100 - ((e.clientX / containerWidth) * 100);
      
      // Limit width between 15% and 50%
      const limitedWidth = Math.max(15, Math.min(50, newWidth));
      setSidebarWidth(limitedWidth);
    };
    
    const handleMouseUp = () => {
      setIsResizing(false);
      
      // Remove the resizing class from body
      document.body.classList.remove('resizing');
    };
    
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }
    
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);
  
  // Toggle sidebar collapsed state
  const toggleSidebar = useCallback(() => {
    setIsSidebarCollapsed(prev => !prev);
  }, []);
  
  // Initialize userId if not set
  useEffect(() => {
    if (!userId) {
      // Check if user ID exists in localStorage
      const storedUserId = localStorage.getItem('mcp_chat_user_id');
      if (storedUserId) {
        setUserId(storedUserId);
      } else {
        // Generate new random user ID
        const newUserId = uuidv4().substring(0, 8);
        setUserId(newUserId);
        localStorage.setItem('mcp_chat_user_id', newUserId);
      }
    }
  }, [userId, setUserId]);
  
  // Fetch MCP servers when component mounts - only run once
  useEffect(() => {
    // Only load servers once
    if (loadedRef.current) return;
    
    const loadMcpServers = async () => {
      setIsLoadingMcpServers(true);
      try {
        const servers = await fetchMcpServers();
        
        // Process servers
        let updatedServers;
        if (mcpServers.length > 0) {
          // Preserve enabled state from existing servers
          updatedServers = servers.map(newServer => {
            const existingServer = mcpServers.find(
              existing => existing.serverId === newServer.serverId
            );
            
            if (existingServer) {
              return {
                ...newServer,
                enabled: existingServer.enabled
              };
            }
            
            return newServer;
          });
        } else {
          updatedServers = servers;
        }
        
        // Update the store
        setMcpServers(updatedServers);
        
        // Mark as loaded
        loadedRef.current = true;
      } catch (error) {
        console.error('Failed to load MCP servers:', error);
      } finally {
        setIsLoadingMcpServers(false);
      }
    };
    
    loadMcpServers();
  }, []); // Empty dependency array to run only once
  
  return (
    <div className="flex flex-col h-full">
      {/* Header with sidebar toggle button */}
      <div className="h-12 border-b border-gray-200 dark:border-gray-700 flex items-center px-4">
        <button
          onClick={toggleSidebar}
          className="flex items-center gap-2 text-sm bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 px-3 py-1 rounded-md transition-colors"
        >
          {isSidebarCollapsed ? (
            <>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="9" y1="3" x2="9" y2="21"></line>
              </svg>
              <span>Show Tools</span>
            </>
          ) : (
            <>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="9" y1="3" x2="9" y2="21"></line>
                <polyline points="14 9 19 9"></polyline>
                <polyline points="14 15 19 15"></polyline>
              </svg>
              <span>Hide Tools</span>
            </>
          )}
        </button>
      </div>
      
      {/* Main chat area with tool sidebar - using dynamic widths */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Chat messages and input - dynamic width based on sidebar */}
        <div
          className="flex flex-col min-w-0 transition-all duration-300 ease-in-out"
          style={{ width: `${isSidebarCollapsed ? 100 : (100 - sidebarWidth)}%` }}
        >
          {/* Message list */}
          <MessageList isLoading={isLoadingMcpServers} />
          
          {/* Chat input */}
          <ChatInput disabled={isLoadingMcpServers} />
          
        </div>
        
        {/* Resize handle - positioned at the left edge of the sidebar */}
        {!isSidebarCollapsed && (
          <div
            ref={resizeRef}
            className={`w-1 hover:w-2 ${isResizing ? 'bg-blue-500 w-2' : 'bg-transparent hover:bg-blue-500'} cursor-col-resize transition-all z-10 resize-handle`}
            onMouseDown={handleMouseDown}
            style={{
              position: 'absolute',
              height: '100%',
              right: `${sidebarWidth}%`,
              transform: 'translateX(50%)'
            }}
          >
            {/* Visual indicator for resize handle */}
            <div className="absolute inset-y-0 left-0 w-1 flex items-center justify-center pointer-events-none">
              <div className="h-16 w-1 rounded-full bg-gray-300 dark:bg-gray-600 opacity-50"></div>
              {/* Add visual indicators for drag direction */}
              <div className="absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-500 dark:text-gray-400 opacity-50">
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                  {/* <polyline points="12 5 19 12 12 19"></polyline> */}
                </svg>
              </div>
            </div>
          </div>
        )}
        
        {/* Tool Input and Tool Usage sidebar - dynamic width */}
        <div
          className={`border-l border-gray-200 dark:border-gray-700 transition-all duration-300 ease-in-out ${isSidebarCollapsed ? 'w-0 opacity-0 overflow-hidden' : ''}`}
          style={{
            width: isSidebarCollapsed ? '0%' : `${sidebarWidth}%`,
            minWidth: isSidebarCollapsed ? 0 : '200px',
            maxWidth: isSidebarCollapsed ? 0 : '50%'
          }}
        >
          {!isSidebarCollapsed && (
            <div className="flex items-center justify-end bg-gray-50 dark:bg-gray-800 p-1 border-b border-gray-200 dark:border-gray-700">
              {/* <span className="text-xs text-gray-500 dark:text-gray-400 pl-2">
                {Math.round(sidebarWidth)}%
              </span> */}
              <button
                onClick={toggleSidebar}
                className="p-1 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
                aria-label="Collapse sidebar"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="15 18 9 12 15 6"></polyline>
                </svg>
              </button>
            </div>
          )}
          {!isSidebarCollapsed && (
            <Tabs defaultValue="toolUsage" className="h-full">
            <TabsList className="grid grid-cols-1 w-full sticky top-0 z-10 bg-white dark:bg-gray-900">
              {/* <TabsTrigger value="toolInput">Tool Input</TabsTrigger> */}
              <TabsTrigger value="toolUsage" className='text-lg'>Tool Usage</TabsTrigger>
            </TabsList>
            <div className="overflow-hidden h-[calc(100vh-130px)]">
              {/* <TabsContent value="toolInput" className="h-full overflow-auto m-0 p-0">
                <ToolInputPanel />
              </TabsContent> */}
              <TabsContent value="toolUsage" className="h-full overflow-auto m-0 p-0">
                <ToolUsagePanel />
              </TabsContent>
            </div>
            </Tabs>
          )}
        </div>
      </div>
    </div>
  );
}

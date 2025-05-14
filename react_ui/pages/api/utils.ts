import { NextApiRequest, NextApiResponse } from 'next';
import fetch from 'node-fetch';

// Base URL for the MCP server backend (internal only)
// Using localhost works with both direct deployment and Docker with host network mode
const MCP_BASE_URL = process.env.SERVER_MCP_BASE_URL || 'http://localhost:7002';

// Configure fetch to ignore SSL errors for self-signed certificates
// This is safe because we're making the request from the server side
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

// Get standardized headers for backend requests
export const getBackendHeaders = (req: NextApiRequest) => {
  // Copy relevant headers from the client request
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // Forward authorization header if present
  if (req.headers.authorization) {
    headers['Authorization'] = req.headers.authorization as string;
  }

  // Forward user ID header if present
  if (req.headers['x-user-id']) {
    headers['X-User-ID'] = req.headers['x-user-id'] as string;
  }

  return headers;
};

// Proxy a GET request to the backend
export async function proxyGetRequest(
  req: NextApiRequest,
  res: NextApiResponse,
  endpoint: string
) {
  try {
    // Construct backend URL - use the protocol specified in MCP_BASE_URL
    const url = MCP_BASE_URL + endpoint;
    
    // Make the request to the backend
    const response = await fetch(url, {
      headers: getBackendHeaders(req)
    });

    // Get response data
    const data = await response.json();

    // Forward the response to the client
    res.status(response.status).json(data);
  } catch (error) {
    console.error(`Error in proxy GET request to ${endpoint}:`, error);
    res.status(500).json({ 
      error: 'Failed to proxy request to backend service',
      message: error instanceof Error ? error.message : 'Unknown error'
    });
  }
}

// Proxy a POST request to the backend
export async function proxyPostRequest(
  req: NextApiRequest,
  res: NextApiResponse,
  endpoint: string
) {
  try {
    // Construct backend URL - use the protocol specified in MCP_BASE_URL
    const url = MCP_BASE_URL + endpoint;
    
    // Make the request to the backend
    const response = await fetch(url, {
      method: 'POST',
      headers: getBackendHeaders(req),
      body: JSON.stringify(req.body)
    });

    // Get content type to determine how to handle response
    const contentType = response.headers.get('content-type');

    // For event streams, forward the response directly
    if (contentType && contentType.includes('text/event-stream')) {
      // Set headers for SSE and forward X-Stream-ID if present
      const headers: any = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no' // Prevent Nginx from buffering the response
      };
      
      // Forward X-Stream-ID if present in the backend response
      const streamId = response.headers.get('X-Stream-ID');
      if (streamId) {
        headers['X-Stream-ID'] = streamId;
      }
      
      res.writeHead(200, headers);

      // Get the response as a readable stream
      const stream = response.body;
      if (!stream) {
        throw new Error('Response body is null');
      }

      // Use streams properly with node-fetch
      const reader = stream as any;
      let decoder = new TextDecoder();
      
      // Handle client disconnect
      req.on('close', () => {
        // When client disconnects, clean up resources
        if (reader && typeof reader.destroy === 'function') {
          reader.destroy();
        }
      });
      
      // Process the stream
      async function processStream() {
        try {
          // For node-fetch, we need to handle the stream differently
          reader.on('data', (chunk: Buffer) => {
            // Decode the chunk and write it directly to the response
            // This ensures we preserve the exact SSE format
            const decodedChunk = decoder.decode(chunk, { stream: true });
            res.write(decodedChunk);
          });
          
          reader.on('end', () => {
            // End the response when the stream is done
            res.end();
          });
          
          reader.on('error', (error: Error) => {
            console.error('Stream error:', error);
            res.end();
          });
        } catch (error) {
          console.error('Error processing stream:', error);
          res.end();
        }
      }
      
      // Start processing the stream
      processStream();
      
      return; // Return early since we're handling the response as a stream
    }

    // For JSON responses
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (error) {
    console.error(`Error in proxy POST request to ${endpoint}:`, error);
    res.status(500).json({ 
      error: 'Failed to proxy request to backend service', 
      message: error instanceof Error ? error.message : 'Unknown error'
    });
  }
}

// Proxy a DELETE request to the backend
export async function proxyDeleteRequest(
  req: NextApiRequest,
  res: NextApiResponse,
  endpoint: string
) {
  try {
    // Construct backend URL - use the protocol specified in MCP_BASE_URL
    const url = MCP_BASE_URL + endpoint;
    
    // Make the request to the backend
    const response = await fetch(url, {
      method: 'DELETE',
      headers: getBackendHeaders(req)
    });

    // Get response data
    const data = await response.json();

    // Forward the response to the client
    res.status(response.status).json(data);
  } catch (error) {
    console.error(`Error in proxy DELETE request to ${endpoint}:`, error);
    res.status(500).json({ 
      error: 'Failed to proxy request to backend service',
      message: error instanceof Error ? error.message : 'Unknown error'
    });
  }
}

import type { NextApiRequest, NextApiResponse } from 'next';
import { Readable, Transform } from 'stream';

// Base URL for the MCP service (internal server-side only)
// Use the protocol specified in SERVER_MCP_BASE_URL
const MCP_BASE_URL = process.env.SERVER_MCP_BASE_URL || 'http://localhost:7002';

// Configure fetch to ignore SSL errors for self-signed certificates
// This is safe because we're making the request from the server side
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

// Configure Next.js API route to allow streaming responses with large payloads
export const config = {
  api: {
    responseLimit: false,
    // Set a much larger limit for request body size to accommodate large prompts with images
    bodyParser: {
      sizeLimit: '50mb',
    },
  },
};

/**
 * Stream processor to ensure complete JSON objects in SSE data lines
 * This handles the case where JSON gets split across chunks
 */
class SseJsonTransform extends Transform {
  private buffer = '';
  private dataPrefix = 'data: ';
  
  constructor(options = {}) {
    super({ ...options });
  }
  
  _transform(chunk: Buffer, encoding: string, callback: Function) {
    // Convert chunk to string and add to buffer
    const chunkStr = chunk.toString();
    this.buffer += chunkStr;
    
    // Process complete lines in buffer
    let processedBuffer = '';
    const lines = this.buffer.split('\n');
    
    // Keep the last line in buffer (it might be incomplete)
    const lastLine = lines.pop() || '';
    
    // Process complete lines
    for (const line of lines) {
      // If it's a data line that contains JSON, make sure the JSON is complete
      if (line.startsWith(this.dataPrefix)) {
        try {
          const jsonStr = line.substring(this.dataPrefix.length);
          // Try to parse to verify it's valid JSON
          JSON.parse(jsonStr);
          // If we get here, it's valid JSON, so include the line
          processedBuffer += line + '\n';
        } catch (e) {
          // If we can't parse it, it might be an incomplete JSON
          // Keep it in the buffer by adding it back to the last line
          this.buffer = line + '\n' + lastLine;
          break;
        }
      } else {
        // Non-data lines go through as is
        processedBuffer += line + '\n';
      }
    }
    
    // Update buffer with the last (potentially incomplete) line
    this.buffer = lastLine;
    
    // Push processed data if we have any
    if (processedBuffer) {
      this.push(processedBuffer);
    }
    
    callback();
  }
  
  _flush(callback: Function) {
    // If there's anything left in the buffer on stream end, push it out
    if (this.buffer) {
      this.push(this.buffer);
    }
    callback();
  }
}

// Stream the conversation completion response from backend to client
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method Not Allowed' });
  }
  
  // Create an abort controller to handle connection termination
  const controller = new AbortController();
  const { signal } = controller;
  
  // Set up cleanup on client disconnect
  req.on('close', () => {
    controller.abort();
    console.log('Client disconnected, aborting backend request');
  });
  
  try {
    // Forward appropriate headers to the backend service
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    };
    
    if (req.headers.authorization) {
      headers['Authorization'] = req.headers.authorization as string;
    }
    
    if (req.headers['x-user-id']) {
      headers['X-User-ID'] = req.headers['x-user-id'] as string;
    }
    
    // Make the request to the backend service
    const fetchResponse = await fetch(`${MCP_BASE_URL}/v1/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify(req.body),
      signal,
    });
    
    if (!fetchResponse.ok) {
      console.error(`Backend error: ${fetchResponse.status} ${fetchResponse.statusText}`);
      return res.status(fetchResponse.status).json({
        error: 'Backend service error',
        status: fetchResponse.status,
        message: fetchResponse.statusText,
      });
    }
    
    // Get the response body as a stream
    const backendStream = fetchResponse.body;
    if (!backendStream) {
      return res.status(500).json({ error: 'No response stream from backend' });
    }
    
    // Set up our response as a proper server-sent events stream
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no'); // Prevent Nginx buffering
    
    // Forward X-Stream-ID if present in the backend response
    const streamId = fetchResponse.headers.get('X-Stream-ID');
    if (streamId) {
      console.log('Forwarding stream ID from backend:', streamId);
      res.setHeader('X-Stream-ID', streamId);
    }
    
    res.status(200);
    
    // Use Node.js native streams for reliable forwarding
    const readable = Readable.fromWeb(backendStream as any);
    
    // Create a transform stream to ensure complete JSON objects
    const jsonTransform = new SseJsonTransform();
    
    // Set up the pipeline: readable -> jsonTransform -> response
    readable
      .pipe(jsonTransform)
      .pipe(res);
    
    // Handle the end of the stream
    readable.on('end', () => {
      console.log('Stream ended properly');
      // The response will be automatically ended by the pipe
    });
    
    // Handle potential errors in any part of the stream
    readable.on('error', (err) => {
      console.error('Stream read error:', err);
      if (!res.writableEnded) {
        res.end(`data: ${JSON.stringify({ error: 'Stream read error' })}\n\n`);
      }
    });
    
    jsonTransform.on('error', (err) => {
      console.error('JSON transform error:', err);
      if (!res.writableEnded) {
        res.end(`data: ${JSON.stringify({ error: 'JSON processing error' })}\n\n`);
      }
    });
  } catch (error) {
    console.error('Error handling streaming request:', error);
    // Only send response if headers haven't been sent yet
    if (!res.headersSent) {
      res.status(500).json({ 
        error: 'Internal server error',
        message: error instanceof Error ? error.message : 'Unknown error'
      });
    } else if (!res.writableEnded) {
      // If headers sent but response not ended, try to gracefully close the stream
      res.end(`data: ${JSON.stringify({ error: 'Internal server error' })}\n\n`);
    }
  }
}

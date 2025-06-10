import { NextApiRequest, NextApiResponse } from 'next';
import { getApiKey } from '../../../../lib/server/secrets';

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // Get API key from environment variable or AWS Secrets Manager
    const apiKey = await getApiKey();
    
    if (!apiKey) {
      return res.status(500).json({ error: 'API key not configured' });
    }

    // Return the API key (in production, you might want to be more careful about this)
    res.status(200).json({ api_key: apiKey });
  } catch (error) {
    console.error('Error fetching API key:', error);
    res.status(500).json({ error: 'Failed to fetch API key' });
  }
}

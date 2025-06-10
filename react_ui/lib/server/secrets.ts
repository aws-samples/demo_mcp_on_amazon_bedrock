import { SecretsManagerClient, GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";

let secretsClient: SecretsManagerClient | null = null;

// Initialize the secrets manager client
function getSecretsClient(): SecretsManagerClient {
  if (!secretsClient) {
    secretsClient = new SecretsManagerClient({
      region: process.env.AWS_REGION || 'us-east-1'
    });
  }
  return secretsClient;
}

/**
 * Get secret value from AWS Secrets Manager
 * @param secretName - The name or ARN of the secret
 * @returns The secret value or null if failed
 */
export async function getSecret(secretName: string): Promise<string | null> {
  try {
    const client = getSecretsClient();
    const command = new GetSecretValueCommand({
      SecretId: secretName,
      VersionStage: "AWSCURRENT", // Default to current version
    });
    
    const response = await client.send(command);
    return response.SecretString || null;
  } catch (error) {
    console.warn(`No secret found for ${secretName}: ${error}`);
    return null;
  }
}

/**
 * Initialize API key - check if it's an ARN and fetch from Secrets Manager if so
 * @param apiKeyValue - The API key value or ARN from environment
 * @returns The actual API key value
 */
export async function initApiKey(apiKeyValue?: string): Promise<string> {
  const envApiKey = apiKeyValue || process.env.NEXT_PUBLIC_API_KEY;
  
  if (!envApiKey) {
    console.warn('No API key found in environment');
    return '';
  }
  
  // Check if the API key is an ARN (starts with arn:aws)
  if (envApiKey.startsWith("arn:aws")) {
    console.log('API key appears to be an ARN, fetching from Secrets Manager...');
    const secret = await getSecret(envApiKey);
    
    if (secret) {
      try {
        // Try to parse as JSON in case the secret contains a JSON object
        const secretObj = JSON.parse(secret);
        if (secretObj && typeof secretObj === 'object' && secretObj.api_key) {
          // Ensure the extracted API key is a string
          const extractedKey = secretObj.api_key;
          if (typeof extractedKey === 'string') {
            return extractedKey;
          } else {
            console.error('API key from secret object is not a string:', typeof extractedKey, extractedKey);
            return String(extractedKey); // Convert to string as fallback
          }
        }
        // If parsing succeeds but no api_key field, return the raw secret
        return secret;
      } catch (e) {
        // If not JSON, return the raw secret string
        return secret;
      }
    } else {
      console.error('Failed to retrieve secret from AWS Secrets Manager');
      return envApiKey; // Fallback to original value
    }
  }
  
  // Return the original value if not an ARN
  return envApiKey;
}

/**
 * Cache for the resolved API key to avoid repeated AWS calls
 */
let cachedApiKey: string | null = null;
let apiKeyInitialized = false;

/**
 * Get the API key, initializing from Secrets Manager if needed
 * This function caches the result to avoid repeated AWS API calls
 */
export async function getApiKey(): Promise<string> {
  if (apiKeyInitialized && cachedApiKey !== null) {
    return cachedApiKey;
  }
  
  try {
    cachedApiKey = await initApiKey();
    apiKeyInitialized = true;
    return cachedApiKey;
  } catch (error) {
    console.error('Error initializing API key:', error);
    // Fallback to environment variable
    return process.env.NEXT_PUBLIC_API_KEY || '';
  }
}

/**
 * Reset the cached API key (useful for testing or if you need to refresh)
 */
export function resetApiKeyCache(): void {
  cachedApiKey = null;
  apiKeyInitialized = false;
}

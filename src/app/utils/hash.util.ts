/**
 * Utility functions for consistent hashing across the application
 */

/**
 * Compute SHA-256 hash of a string
 * @param data The string to hash
 * @returns Hex string representation of the hash
 */
export async function computeSHA256Hash(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const dataBuffer = encoder.encode(data);
  const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Compute SHA-256 hash for an object by stringifying it
 * @param obj The object to hash
 * @returns Hex string representation of the hash
 */
export async function computeObjectHash(obj: any): Promise<string> {
  const jsonString = JSON.stringify(obj);
  return computeSHA256Hash(jsonString);
}

/**
 * Compute a simple numeric hash (32-bit) from a string
 * Used for backward compatibility where numeric hashes are expected
 * @param data The string to hash
 * @returns 32-bit numeric hash
 */
export function computeNumericHash(data: string): number {
  let hash = 0;
  if (data.length === 0) return hash;
  
  for (let i = 0; i < data.length; i++) {
    const char = data.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  
  return Math.abs(hash);
}
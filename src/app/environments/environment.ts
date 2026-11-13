// src/environments/environment.ts (development environment)
// Runtime configuration is loaded from assets/env.js (see index.html)
// For Docker deployments, env.js is generated at container startup from env.template.js

const API_URL_KEY = 'api_url';

/**
 * The backend's address: from assets/env.js, else the one this browser used last, else the
 * development backend. env.js is always fetched from the server (the address can change with a
 * deployment), so the installed app, started offline, has to remember the address itself.
 */
function apiUrl(): string {
  const configured: string | undefined = (window as any)['env']?.['apiUrl'];
  try {
    if (configured) {
      localStorage.setItem(API_URL_KEY, configured);
      return configured;
    }
    return localStorage.getItem(API_URL_KEY) || 'https://localhost:8443';
  } catch {
    // No storage (private mode, blocked site data)
    return configured || 'https://localhost:8443';
  }
}

export const environment = {
  production: false,
  apiUrl: apiUrl(),
  auth: {
    // Switch providers via environment
    provider: 'mock', // 'mock' | 'auth0' | 'okta' | 'azure' | etc.
    // TODO: Future IDP config goes here
    clientId: '',
    domain: '',
    redirectUri: '',
    audience: ''
  }
};

/*
// src/environments/environment.prod.ts (production environment)
export const environment = {
    production: true,
    apiUrl: 'https://your-production-domain.com'  // Change this to your actual production URL
};
*/

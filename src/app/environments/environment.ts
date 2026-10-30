// src/environments/environment.ts (development environment)
// Runtime configuration is loaded from assets/env.js (see index.html)
// For Docker deployments, env.js is generated at container startup from env.template.js
export const environment = {
  production: false,
  apiUrl: (window as any)['env']?.['apiUrl'] || 'https://localhost:8443',
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

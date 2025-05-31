// src/environments/environment.ts (development environment)
export const environment = {
  production: false,
  apiUrl: 'https://localhost:8443',  // Change to 'http://localhost:8443' if you don't want to use https for development
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

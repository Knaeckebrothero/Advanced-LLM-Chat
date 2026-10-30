// Runtime environment configuration
// This file is processed by envsubst at container startup
// See docker/Dockerfile CMD for details
(function(window) {
  window.env = window.env || {};
  window.env.apiUrl = '${API_URL}';
})(window);

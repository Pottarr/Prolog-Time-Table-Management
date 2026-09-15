// Base URL for the gateway API. Empty string means "same origin" — relative
// `/api/...` calls, which is what both the Vite dev proxy and the production
// Nginx proxy expect. Override with VITE_API_BASE_URL for a gateway hosted
// on a different origin.
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

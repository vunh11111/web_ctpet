import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(() => {
  if (process.env.VERCEL === '1' && process.env.VITE_PUBLIC_PREVIEW !== 'true') {
    const value = process.env.VITE_API_URL;
    if (!value) throw new Error('Set VITE_API_URL to the public HTTPS backend URL (including /api) before deploying on Vercel.');
    const api = new URL(value);
    if (api.protocol !== 'https:') throw new Error('Vercel frontend requires a public HTTPS backend URL.');
  }
  const proxy = {'/api': {target: `http://127.0.0.1:${process.env.VITE_API_PORT || '8108'}`, changeOrigin: true}};
  const allowedHosts=process.env.PUBLIC_WEB_HOST?[process.env.PUBLIC_WEB_HOST]:[];
  // Let /api preflight reach FastAPI's explicit CORS policy instead of being
  // consumed by Vite's localhost-only default CORS middleware.
  return {plugins:[react()], server:{proxy,allowedHosts,cors:false}, preview:{proxy,allowedHosts,cors:false}};
});

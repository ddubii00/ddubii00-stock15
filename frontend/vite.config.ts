import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/stock15-7/',
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/stock15-7/api/insights/telemoa': { target: 'http://127.0.0.1:8015', rewrite: path => path.replace('/stock15-7', '') },
      '/stock15-7/api': { target: 'https://127.0.0.1:8000', secure: false },
    },
  },
});

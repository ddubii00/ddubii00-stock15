import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/telegram-7/',
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/telegram-7/api/insights/telemoa': { target: 'http://127.0.0.1:8015', rewrite: path => path.replace('/telegram-7', '') },
      '/telegram-7/api': { target: 'https://127.0.0.1:8000', secure: false },
    },
  },
});

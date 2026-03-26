import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
        configure: (proxy) => {
          // Prevent redirect responses from exposing internal Docker hostnames
          proxy.on('proxyRes', (proxyRes) => {
            const location = proxyRes.headers['location'];
            if (location && location.includes('api:8000')) {
              proxyRes.headers['location'] = location.replace(
                'http://api:8000',
                '',
              );
            }
          });
        },
      },
    },
  },
});

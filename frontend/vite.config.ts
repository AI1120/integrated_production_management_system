import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Bind dual-stack by default.
//
// Vite's default host is "localhost", which Node on Windows resolves to ::1 and
// then binds IPv6-ONLY. A browser that asks for 127.0.0.1 gets connection
// refused and shows a blank page. Listening on "::" creates a dual-stack socket
// (both 0.0.0.0 and [::]), so http://localhost:5173 works regardless of which
// address the browser picks - and shop-floor tablets on the LAN can reach the
// operator terminal, which is the point of this app.
//
// That also means the dev server is reachable from the local network. To keep it
// on this machine only, run with IPMS_HOST=127.0.0.1.
const HOST = process.env.IPMS_HOST ?? '::'

export default defineConfig({
  plugins: [react()],
  server: {
    host: HOST,
    port: 5173,
    strictPort: true, // fail loudly instead of silently moving to 5174
    // Talk to the API on the same origin in dev, so no CORS or base-URL juggling.
    proxy: {
      '/api': {
        target: process.env.IPMS_API ?? 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})

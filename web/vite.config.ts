import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { VitePWA } from 'vite-plugin-pwa'

// SharedArrayBuffer (multi-threaded WASM) requires cross-origin isolation.
// public/_headers sets the same headers on Cloudflare Pages.
const isolationHeaders = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
}

export default defineConfig({
  // Served next to the landing page at adamschepis.com/sightline/app/.
  base: '/sightline/app/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.png'],
      manifest: {
        name: 'Sightline',
        short_name: 'Sightline',
        description: 'Privacy-first face blurring, redaction, and transcription. Everything runs on your device.',
        theme_color: '#020513',
        background_color: '#020513',
        display: 'standalone',
        icons: [{ src: 'icon.png', sizes: '512x512', type: 'image/png' }],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,png,svg}'],
        // The 27 MB ORT runtime and the detector model are cached on first use
        // rather than precached, so installing the PWA stays quick.
        globIgnores: ['**/ort-wasm-simd-threaded*', 'models/**'],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.includes('ort-wasm-simd-threaded') || url.pathname.includes('/models/'),
            handler: 'CacheFirst',
            options: { cacheName: 'sightline-runtime-v1', expiration: { maxEntries: 20 } },
          },
        ],
      },
    }),
  ],
  server: { headers: isolationHeaders },
  preview: { headers: isolationHeaders },
  worker: { format: 'es' },
  // Pre-bundle worker deps up front: discovering them lazily makes Vite reload
  // the page mid-job in dev.
  optimizeDeps: { include: ['mp4box', 'mp4-muxer'], exclude: ['onnxruntime-web', '@huggingface/transformers'] },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 4000,
  },
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
  },
})

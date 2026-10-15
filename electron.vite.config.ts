import { resolve } from 'node:path'
import { defineConfig } from 'electron-vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  main: { build: { rollupOptions: { input: resolve('desktop/src/main/index.ts') } } },
  preload: {
    build: {
      rollupOptions: {
        input: resolve('desktop/src/preload/index.ts'),
        output: { format: 'cjs', entryFileNames: 'index.cjs' },
      },
    },
  },
  renderer: {
    root: 'frontend',
    plugins: [vue()],
    build: { rollupOptions: { input: resolve('frontend/index.html') } },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    fs: { allow: ['..', '/mnt/t7'] },
  },
  assetsInclude: ['**/*.f32', '**/*.glb'],
})

import { defineConfig } from 'vite';

export default defineConfig({
  root: 'src/spa',
  base: './',
  build: { outDir: '../../dist', emptyOutDir: true, assetsInlineLimit: 0 },
  test: { root: '.', include: ['test/**/*.test.ts'] },
});

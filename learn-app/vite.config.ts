import { defineConfig } from 'vite';

export default defineConfig({
  root: 'src/spa',
  base: './',
  build: { outDir: '../../dist', emptyOutDir: true },
  test: { root: '.', include: ['test/**/*.test.ts'] },
});

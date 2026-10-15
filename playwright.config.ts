import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60000,
  workers: 1,
  outputDir: process.env.LITEXTRACT_TEST_EXECUTABLE ? 'test-results-packaged' : 'test-results',
  reporter: 'list',
})

/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import path from 'path'

export default defineConfig({
  test: {
    globals: true,
    environment: 'node', // Use node environment for API tests by default
    setupFiles: ['./test/setup.ts'],
    env: {
      ...process.env,
    },
    // Increase timeout for integration tests
    testTimeout: 30000,
    hookTimeout: 10000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'node_modules/',
        'test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/coverage/**',
        '**/__tests__/**',
        '**/types/**',
      ],
      reportsDirectory: './coverage',
    },
    reporters: ['default', 'junit'],
    outputFile: {
      junit: './test-results.xml',
    },
    // Pool options for better CI performance
    pool: 'forks',
    poolOptions: {
      forks: {
        singleFork: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
}) 
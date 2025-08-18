import '@testing-library/jest-dom'
import { config } from 'dotenv'
import { resolve } from 'path'

// Load test environment variables
config({ path: resolve(process.cwd(), '.env.test') }) 
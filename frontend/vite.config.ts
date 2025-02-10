import { fileURLToPath } from "url"
import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src")
    }
  },
  server: {
    port: 5173,
    host: true, // Needed for proper WebSocket connection
    watch: {
      usePolling: true // Helps with some file system issues
    }
  }
})

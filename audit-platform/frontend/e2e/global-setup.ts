/**
 * Playwright globalSetup — 确保 FIX-F / FIX-I6 E2E 底稿与夹具数据存在
 */
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const backendRoot = path.resolve(__dirname, '../../../backend')

export default async function globalSetup() {
  if (process.env.SKIP_E2E_SEED === '1') {
    console.log('[e2e setup] SKIP_E2E_SEED=1，跳过 seed')
    return
  }
  try {
    console.log('[e2e setup] 运行 seed_fix_projects.py --fix（含 FIX-F / FIX-I6 底稿）…')
    execSync('python scripts/e2e/seed_fix_projects.py --fix', {
      cwd: backendRoot,
      stdio: 'inherit',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })
    const manifestPath = path.join(backendRoot, 'data/e2e_fix_projects.json')
    if (fs.existsSync(manifestPath)) {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'))
      const env = manifest?.env ?? {}
      if (env.TEST_PROJECT_ID_FIX_I6 && !process.env.TEST_PROJECT_ID_FIX_I6) {
        process.env.TEST_PROJECT_ID_FIX_I6 = env.TEST_PROJECT_ID_FIX_I6
      }
      if (env.I6_E2E_WP_ID && !process.env.I6_E2E_WP_ID) {
        process.env.I6_E2E_WP_ID = env.I6_E2E_WP_ID
      }
    }
  } catch (e) {
    console.warn('[e2e setup] seed 失败，部分 E2E 可能 skip:', e)
  }
}

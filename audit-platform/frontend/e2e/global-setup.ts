/**
 * Playwright globalSetup — 确保 FIX-F F2 E2E 底稿存在（复制真实 xlsx 模板）
 */
import { execSync } from 'node:child_process'
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
    console.log('[e2e setup] 运行 seed_fix_projects.py --fix（含 FIX-F F2 底稿）…')
    execSync('python scripts/e2e/seed_fix_projects.py --fix', {
      cwd: backendRoot,
      stdio: 'inherit',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })
  } catch (e) {
    console.warn('[e2e setup] seed 失败，部分 E2E 可能 skip:', e)
  }
}

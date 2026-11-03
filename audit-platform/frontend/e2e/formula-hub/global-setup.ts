/**
 * formula-hub 专用 globalSetup — ADR-FEC-02
 *
 * 与主 e2e/global-setup.ts 的区别：种子失败直接抛错终止，不告警继续。
 */
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const backendRoot = path.resolve(__dirname, '../../../../backend')
const manifestPath = path.join(backendRoot, 'data/e2e_formula_manifest.json')

export default async function globalSetup() {
  if (process.env.SKIP_FORMULA_SEED === '1') {
    console.log('[formula-hub setup] SKIP_FORMULA_SEED=1，跳过种子（已手动播种）')
  } else {
    console.log('[formula-hub setup] 运行 seed_formula_e2e.py …')
    // CI 环境用 DATABASE_URL 环境变量指向一次性库；
    // 本地开发：先手动 seed --allow-shared 再设 SKIP_FORMULA_SEED=1
    const args = process.env.FH_E2E_ALLOW_SHARED === '1' ? ' --allow-shared' : ''
    execSync(`python scripts/e2e/seed_formula_e2e.py${args}`, {
      cwd: backendRoot,
      stdio: 'inherit',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })
  }

  // 种子完成后清单必须存在（否则规格无法读取项目 id）
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`种子清单不存在：${manifestPath}`)
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'))

  // 把清单里的关键 id 写入环境变量供规格读取
  const env: Record<string, string> = {
    FH_E2E_STANDALONE_ID: manifest.standalone?.project_id ?? '',
    FH_E2E_CONSOL_ID: manifest.consolidated?.project_id ?? '',
    FH_E2E_YEAR: String(manifest.year ?? 2025),
  }

  for (const [k, v] of Object.entries(env)) {
    if (v) process.env[k] = v
  }

  console.log('[formula-hub setup] 项目 id 已注入环境变量')
}

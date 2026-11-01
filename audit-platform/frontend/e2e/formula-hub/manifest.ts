/**
 * 读取种子清单 e2e_formula_manifest.json — 规格的唯一数据来源（ADR-FEC-03）。
 *
 * 规格内不得写死任何 UUID / 端口 / 密码，全部从清单读。
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const manifestPath = path.resolve(
  __dirname,
  '../../../../backend/data/e2e_formula_manifest.json',
)

export interface FormulaManifest {
  accounts: Record<string, string>
  standalone: {
    project_id: string
    project_name: string
    wp_ids: Record<string, string>
  }
  consolidated: {
    project_id: string
    project_name: string
    wp_ids: Record<string, string>
  }
  year: number
}

let _cached: FormulaManifest | null = null

export function loadManifest(): FormulaManifest {
  if (_cached) return _cached
  if (!fs.existsSync(manifestPath)) {
    throw new Error(
      `公式 E2E 清单不存在: ${manifestPath}\n` +
        '请先运行 python backend/scripts/e2e/seed_formula_e2e.py',
    )
  }
  _cached = JSON.parse(fs.readFileSync(manifestPath, 'utf-8')) as FormulaManifest
  return _cached
}

/** 返回第一个账号的用户名和密码（默认 partner）。 */
export function defaultCredentials(): { username: string; password: string } {
  const m = loadManifest()
  const entries = Object.entries(m.accounts)
  if (entries.length === 0) throw new Error('清单 accounts 为空')
  return { username: entries[0][0], password: entries[0][1] }
}

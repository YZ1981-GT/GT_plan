/**
 * 附注同步 URL 契约守卫（disclosure-note-linkage-completion Req2.5 / Task 3.3）
 *
 * 断言：`src/components/workpaper/**` 下所有披露 tab 对
 * disclosure-notes 的结构化同步 HTTP 调用一律走 canonical 端点
 *   POST /api/projects/{project_id}/disclosure-notes/sync-from-workpaper
 * 不再出现历史 5 套非 canonical 形态：
 *   - /api/disclosure-notes/{pid}/sync-from-workpaper                       (H3 旧)
 *   - /api/disclosure-notes/{pid}/{year}/{section}/sync-from-workpaper      (H5/J1 旧)
 *   - /api/projects/{pid}/disclosure-notes/{year}/sync-from-workpaper       (H4 旧，带 year 段)
 *
 * 判定：某行同时含 `sync-from-workpaper` + `/api/` + `disclosure-notes`（=对附注模块的
 * HTTP 同步调用），但不含 canonical 子串 `disclosure-notes/sync-from-workpaper` → 违规。
 *
 * 不受约束（allowlist）：
 *  - `eventBus.emit('sync-from-workpaper'` 事件信号（D6 useD6Disclosure，非 HTTP URL）——
 *    无 `/api/` 与 `disclosure-notes` 故天然不命中；
 *  - 集中调整同步 `/api/projects/{pid}/adjustments/sync-from-workpaper`（不含 disclosure-notes）；
 *  - 注释行（含 `sync-from-workpaper` 但非实际调用）——无 `/api/`+`disclosure-notes` 组合时不命中；
 *    含 URL 的注释以 CANONICAL 子串判定放行。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const WP_ROOT = resolve(process.cwd(), 'src/components/workpaper')

/** canonical 子串：disclosure-notes/ 后紧跟 sync-from-workpaper（无 year/section 段） */
const CANONICAL = 'disclosure-notes/sync-from-workpaper'

function walk(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) {
      if (name === 'node_modules' || name === 'dist' || name === '__tests__') continue
      out.push(...walk(p))
    } else if (/\.(ts|vue)$/.test(name) && !/\.spec\.ts$/.test(name) && !/\.d\.ts$/.test(name)) {
      out.push(p)
    }
  }
  return out
}

describe('附注同步 URL 契约守卫（Req2.5）', () => {
  const files = walk(WP_ROOT)

  it('披露 tab 对 disclosure-notes 的同步一律走 canonical /api/projects/{pid}/disclosure-notes/sync-from-workpaper', () => {
    const offenders: string[] = []
    for (const f of files) {
      const content = readFileSync(f, 'utf-8')
      const lines = content.split(/\r?\n/)
      lines.forEach((line, idx) => {
        if (!line.includes('sync-from-workpaper')) return
        // 仅约束对附注模块的 HTTP 同步调用（含 /api/ + disclosure-notes）
        if (!line.includes('/api/') || !line.includes('disclosure-notes')) return
        // 命中 canonical 子串 → 合规
        if (line.includes(CANONICAL)) return
        offenders.push(`${f.replace(WP_ROOT, 'workpaper')}:${idx + 1}  ${line.trim()}`)
      })
    }
    expect(
      offenders,
      `以下披露同步调用未走 canonical /api/projects/{pid}/disclosure-notes/sync-from-workpaper：\n${offenders.join('\n')}`,
    ).toEqual([])
  })
})

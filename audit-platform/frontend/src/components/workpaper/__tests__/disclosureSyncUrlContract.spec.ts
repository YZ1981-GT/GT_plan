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
 * 🔴 判据修正（i-cycle-extraction-formula-and-disclosure-closure）：
 * 旧判据要求命中行**必须含 `disclosure-notes`** 才检查：
 *     if (!line.includes('/api/') || !line.includes('disclosure-notes')) return
 * 这是循环论证 —— 用「已经写对了一半」来筛选「需要检查的对象」。走错端点的调用
 * （实测存量 15 个 M/J 循环文件写成 `/api/workpapers/${props.wpId}/sync-from-workpaper`，
 * 后端无此路由必 404）**恰恰不含 `disclosure-notes`**，于是被整条放过，守卫恒绿。
 *
 * 新判据：某行含 `sync-from-workpaper` + `/api/`（=一个 HTTP 同步 URL），
 * 除 ALLOWED_NON_NOTE（非附注模块的合法端点）外，一律必须命中 CANONICAL 之一 → 否则违规。
 * 即「先按 URL 形态圈定全部同步调用，再逐一要求走对端点」，不再依赖被检对象自证。
 *
 * 后端实测仅存三个 `sync-from-workpaper` 路由（`backend/app/routers/`）：
 *  - wp_disclosure_sync.py  `/{project_id}/disclosure-notes/sync-from-workpaper`   ← canonical
 *  - adjustments.py         `/sync-from-workpaper`（prefix `…/{pid}/adjustments`）  ← allowlist
 *  - tb_sync.py             `/{project_id}/{year}/sync-from-workpaper`（试算表）    ← allowlist
 *
 * 不受约束：
 *  - `eventBus.emit('sync-from-workpaper'` 事件信号（D6 useD6Disclosure，非 HTTP URL）——
 *    无 `/api/` 故天然不命中；
 *  - 纯注释行 —— 注释不执行，不构成运行时缺陷；且历史形态常被写在注释里作「已废弃」说明，
 *    若一并计入会把文档变成违规。以行首 `//` `*` `/*` 判定。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const WP_ROOT = resolve(process.cwd(), 'src/components/workpaper')

/**
 * canonical 子串：disclosure-notes/ 后紧跟 sync-from-workpaper（无 year/section 段）。
 * 批量形态 sync-batch-from-workpaper 同为合法 canonical（多 section 一次推送）。
 */
const CANONICAL = [
  'disclosure-notes/sync-from-workpaper',
  'disclosure-notes/sync-batch-from-workpaper',
]

/**
 * 非附注模块的合法 sync-from-workpaper 端点（后端确有路由，不受附注 canonical 约束）。
 * 不是「豁免检查」而是「归属别的契约」：它们同步的目标不是 disclosure_notes 表。
 */
const ALLOWED_NON_NOTE = [
  'adjustments/sync-from-workpaper', // backend/app/routers/adjustments.py（集中调整登记）
  'trial-balance/', // backend/app/routers/tb_sync.py（试算表 /{pid}/{year}/sync-from-workpaper）
]

/** 纯注释行：注释不执行，历史形态常写在注释里作废弃说明 */
function isCommentLine(line: string): boolean {
  const t = line.trim()
  return t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')
}

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
        // 只看 HTTP URL 形态（排除 eventBus 事件名等非 URL 用法）
        if (!line.includes('/api/')) return
        // 纯注释行不计（不执行）
        if (isCommentLine(line)) return
        // 归属别的契约的合法端点（集中调整 / 试算表）
        if (ALLOWED_NON_NOTE.some((a) => line.includes(a))) return
        // 命中 canonical 子串 → 合规
        if (CANONICAL.some((c) => line.includes(c))) return
        offenders.push(`${f.replace(WP_ROOT, 'workpaper')}:${idx + 1}  ${line.trim()}`)
      })
    }
    expect(
      offenders,
      `以下披露同步调用未走 canonical /api/projects/{pid}/disclosure-notes/sync-from-workpaper：\n${offenders.join('\n')}`,
    ).toEqual([])
  })
})

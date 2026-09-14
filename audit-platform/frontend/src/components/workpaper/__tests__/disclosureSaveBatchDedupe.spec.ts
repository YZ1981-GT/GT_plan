/**
 * 防抖累积批次去重守卫
 *
 * 🔴 同一批次不得重复提交相同 `item_id` —— 后端会**整批拒绝**，该批全部数据丢失。
 *
 * 平台已有 `fix_save_batch_dedup.py --check` 覆盖 `saveBatch(items)` 那种形状；
 * 本守卫覆盖另一种形状：**防抖累积器**（`pendingSaveItems` 之类先 push 再一次性提交）。
 * 披露表把每张动态表整表存成一个 JSON item，防抖窗口内改同一张表两个格子
 * 必然产生两条同 id 记录 —— 2026-07-30 浏览器实测中招（连改 4 个格子 →
 * `D1-disc-soe-class-end-rows` 4 条同批 → 整批被拒，界面有值但库里没这个键）。
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const WORKPAPER_ROOT = path.resolve(__dirname, '..')

/** 递归收集 .vue / .ts（跳过测试与快照目录） */
function collectSources(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === '__snapshots__') continue
      collectSources(full, out)
    } else if (/\.(vue|ts)$/.test(entry.name)) {
      out.push(full)
    }
  }
  return out
}

/** 防抖累积器变量名（先 push 累积、稍后整批 PUT 的形状） */
const ACCUMULATOR_RE = /const\s+(pending\w*(?:SaveItems|Items|Payload)\w*)\s*=\s*ref\s*(?:<[^>]*>)?\s*\(/g

const DEDUPE_HINTS = [
  'dedupeByItemId',
  'new Map',
  'byId.set',
  'Set(',
]

describe('披露表防抖累积批次必须按 item_id 去重', () => {
  const sources = collectSources(WORKPAPER_ROOT)

  it('扫描到了源码（防守卫空转）', () => {
    expect(sources.length).toBeGreaterThan(100)
  })

  it('每个防抖累积器在提交前都做了去重', () => {
    const offenders: string[] = []
    for (const file of sources) {
      const text = fs.readFileSync(file, 'utf-8')
      ACCUMULATOR_RE.lastIndex = 0
      let m: RegExpExecArray | null
      const names: string[] = []
      while ((m = ACCUMULATOR_RE.exec(text)) !== null) names.push(m[1])
      if (names.length === 0) continue
      // 累积器存在 → 该文件里必须出现去重痕迹
      const hasDedupe = DEDUPE_HINTS.some(h => text.includes(h))
      if (!hasDedupe) {
        offenders.push(`${path.relative(WORKPAPER_ROOT, file)}: ${names.join(', ')}`)
      }
    }
    expect(
      offenders,
      '防抖窗口内对同一张表改两个格子会产生两条同 item_id 记录 → 后端整批拒绝、'
        + '该批全部数据静默丢失。提交前请按 item_id 去重（后写覆盖先写）',
    ).toEqual([])
  })

  it('D1 披露表确实带了去重实现（自检，防正则失效导致守卫空转）', () => {
    const file = path.join(WORKPAPER_ROOT, 'd1', 'D1TabDisclosure.vue')
    const text = fs.readFileSync(file, 'utf-8')
    expect(text).toMatch(/const\s+pendingSaveItems\s*=\s*ref\s*(?:<[^>]*>)?\s*\(/)
    expect(text).toContain('dedupeByItemId')
    // 提交路径必须走去重后的数组
    expect(text).toMatch(/dedupeByItemId\(pendingSaveItems\.value\)/)
  })

  it('保存失败不得完全静默（数据丢了要让用户知道）', () => {
    const file = path.join(WORKPAPER_ROOT, 'd1', 'D1TabDisclosure.vue')
    const text = fs.readFileSync(file, 'utf-8')
    const block = text.slice(text.indexOf('const debouncedSave'), text.indexOf('async function saveWithDebounce'))
    expect(block).toMatch(/ElMessage\.(warning|error)/)
  })
})

describe('dedupeByItemId 语义（就地复刻，锁死后写覆盖先写）', () => {
  function dedupeByItemId(items: Array<{ item_id: string; remark: string }>) {
    const byId = new Map<string, { item_id: string; remark: string }>()
    for (const it of items) {
      const key = String(it?.item_id ?? '')
      if (!key) continue
      byId.set(key, it)
    }
    return [...byId.values()]
  }

  it('同 id 只保留最后一条', () => {
    const out = dedupeByItemId([
      { item_id: 'a', remark: '1' },
      { item_id: 'b', remark: 'x' },
      { item_id: 'a', remark: '2' },
      { item_id: 'a', remark: '3' },
    ])
    expect(out).toHaveLength(2)
    expect(out.find(i => i.item_id === 'a')!.remark).toBe('3')
  })

  it('丢弃空 item_id（后端会拒绝）', () => {
    expect(dedupeByItemId([{ item_id: '', remark: 'x' }])).toEqual([])
  })

  it('保持首次出现的键序（便于排查）', () => {
    const out = dedupeByItemId([
      { item_id: 'b', remark: '1' },
      { item_id: 'a', remark: '1' },
      { item_id: 'b', remark: '2' },
    ])
    expect(out.map(i => i.item_id)).toEqual(['b', 'a'])
  })
})

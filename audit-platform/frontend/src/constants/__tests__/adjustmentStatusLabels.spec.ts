/**
 * 调整分录状态中文名：前后端同一套（spec consol-autotree-residual-closure R4）
 *
 * 单一来源 = 后端系统字典「调整分录状态」（system_dicts.py）。本文件直读后端源码交叉锁死
 * （同 h0DictConsumption.spec.ts 的做法）：
 *  - 前端常量 ADJUSTMENT_STATUS_LABELS 与字典逐值相等；
 *  - 底稿侧集中登记标签 CENTRAL_STATUS_LABELS 取自该常量（原先单写一份，「已批准」写成「已通过」）；
 *  - 可解释状态机面板的文字来自 adjustment_sm.py，与字典同一套；
 *  - 合并抵销分录保留「待审批 / 已审批」，「已驳回」与调整分录一致（前端 statusLabel 与后端抵销服务相等）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { ADJUSTMENT_STATUS_LABELS } from '../statusEnum'
import { CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { statusLabel as elimStatusLabel } from '@/components/consolidation/composables/elimNodePanel'

function findRepoRoot(from: string): string {
  let dir = from
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(dir, 'backend', 'app', 'routers', 'system_dicts.py'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能定位仓库根（从 ${from} 向上找 backend/app/routers/system_dicts.py）`)
}

const BACKEND = path.join(findRepoRoot(__dirname), 'backend', 'app')
const read = (rel: string) => fs.readFileSync(path.join(BACKEND, rel), 'utf-8')

/** 从 `anchor` 之后第一个开括号起做括号配对取整块（取值里没有括号，但不能靠 indexOf(闭括号)） */
function block(src: string, anchor: string, open: '[' | '{'): string {
  const at = src.indexOf(anchor)
  expect(at, `未找到 ${anchor}`).toBeGreaterThan(-1)
  const close = open === '[' ? ']' : '}'
  const start = src.indexOf(open, at)
  let depth = 0
  for (let i = start; i < src.length; i++) {
    if (src[i] === open) depth++
    else if (src[i] === close && --depth === 0) return src.slice(start, i + 1)
  }
  throw new Error(`${anchor} 括号未配对`)
}

/** 字典条目 `{"value": "x", "label": "y", ...}` → { x: y } */
function dictLabels(): Record<string, string> {
  const body = block(read('routers/system_dicts.py'), '"adjustment_status": [', '[')
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/"value":\s*"([^"]+)",\s*"label":\s*"([^"]+)"/g)) out[m[1]] = m[2]
  return out
}

/** Python 字面量 dict `{"k": "v", ...}` → { k: v } */
function pyStringDict(rel: string, anchor: string): Record<string, string> {
  const body = block(read(rel), anchor, '{')
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/"(\w+)":\s*"([^"]+)"/g)) out[m[1]] = m[2]
  return out
}

const STATUSES = ['draft', 'pending_review', 'approved', 'rejected']
const frontLabels = () => Object.fromEntries(STATUSES.map((s) => [s, ADJUSTMENT_STATUS_LABELS[s].label]))

describe('调整分录状态中文名', () => {
  it('后端字典解析得到四个状态（解析失效自检）', () => {
    expect(Object.keys(dictLabels()).sort()).toEqual([...STATUSES].sort())
  })

  it('前端常量与后端系统字典逐值相等', () => {
    expect(frontLabels()).toEqual(dictLabels())
  })

  it('底稿侧集中登记标签取自同一常量（不再是「已通过」）', () => {
    expect(CENTRAL_STATUS_LABELS).toEqual(frontLabels())
    expect(Object.values(CENTRAL_STATUS_LABELS)).not.toContain('已通过')
  })

  it('可解释状态机面板的状态名与字典同一套', () => {
    const sm = pyStringDict('services/state_machines/adjustment_sm.py', 'status_labels_zh=')
    expect(Object.fromEntries(STATUSES.map((s) => [s, sm[s]]))).toEqual(dictLabels())
    const actions = pyStringDict('services/state_machines/adjustment_sm.py', 'action_labels_zh=')
    expect([actions.submit, actions.reject]).toEqual(['提交复核', '驳回'])
  })

  it('合并抵销分录保留审批措辞，「已驳回」与调整分录一致，前后端相等', () => {
    const backendElim = pyStringDict('services/consol_elimination_sheet_service.py', 'STATUS_LABELS =')
    expect(Object.fromEntries(STATUSES.map((s) => [s, elimStatusLabel(s)]))).toEqual(
      Object.fromEntries(STATUSES.map((s) => [s, backendElim[s]])),
    )
    expect([elimStatusLabel('pending_review'), elimStatusLabel('approved')]).toEqual(['待审批', '已审批'])
    expect(elimStatusLabel('rejected')).toBe(ADJUSTMENT_STATUS_LABELS.rejected.label)
  })
})

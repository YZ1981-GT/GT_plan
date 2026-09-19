/**
 * confirmationGridPersistence.spec.ts — 函证汇总表「编辑必须能落库」守卫
 *
 * 🔴 修复的 P0（2026-08-03 F0 浏览器实测抓到，波及 D0/E0/F0/G0/H0/K0/L0 七个循环）：
 * 「完整表格视图」的 `@update="handleGridUpdate"` 原先只调 `data.updateField`（改内存），
 * 既不 `emit('save')`、`useConfirmationData` 也没有 autosave；
 * 只有列表视图的 `ConfirmationMaster @save="handleSave"` 有保存入口
 * → 在完整表格视图录完一行刷新页面，`checklist_responses` 0 条、`parsed_data.html_data`
 * 仍为空，**数据全丢且无任何提示**。
 *
 * 用户裁决（2026-08-03）：**补显式保存按钮**，不做自动保存。
 *
 * 本守卫是源码级的（不挂载组件），钉住四件事：
 *  1. 每个改内存的入口都要 markDirty()（漏一个就会出现「改了但保存按钮仍禁用」）
 *  2. 工具栏必须有一个受 hasUnsavedChanges 驱动的保存按钮，且 disabled 绑在该状态上
 *  3. handleSave 必须清 dirty（否则按钮永远高亮，用户无法判断是否已保存）
 *  4. 保存必须走 emit('save', data.buildPayload())，不得另造持久化路径
 * 外加反向自检：确认解析到了真实源码而非空串。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname_ = dirname(fileURLToPath(import.meta.url))
// __tests__ → confirmation → workpaper → components → src → frontend → audit-platform → repo
const REPO_ROOT = resolve(__dirname_, '../../../../../../..')

const SUMMARY_VUE =
  'audit-platform/frontend/src/components/workpaper/confirmation/GtConfirmationSummary.vue'

function readSource(rel: string): string {
  return readFileSync(resolve(REPO_ROOT, rel), 'utf-8')
}

/** 去注释（防「修复背景」说明文字被数成真实代码） */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 花括号配对截取函数体（避免固定字符窗口溢出到下一个函数） */
function fnBody(src: string, name: string): string {
  // 🔴 必须带 `(` 锚定函数名 —— 否则 `handleSave` 会先命中 `handleSaveClick`
  //   （前缀相同且它在文件里出现更早），断言就跑在错误的函数体上。
  let i = src.indexOf(`function ${name}(`)
  if (i < 0) i = src.indexOf(`async function ${name}(`)
  if (i < 0) return ''
  const j = src.indexOf('{', i)
  if (j < 0) return ''
  let depth = 0
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') depth++
    else if (src[k] === '}') {
      depth--
      if (depth === 0) return src.slice(i, k + 1)
    }
  }
  return ''
}

const RAW = readSource(SUMMARY_VUE)
const SRC = stripComments(RAW)

// ─── 反向自检 ────────────────────────────────────────────────────────────────

describe('反向自检：解析器读到真实源码', () => {
  it('源码非空且含关键符号', () => {
    expect(RAW.length).toBeGreaterThan(5000)
    expect(SRC).toContain('handleGridUpdate')
    expect(SRC).toContain('handleSave')
  })

  it('stripComments 真的去掉了注释（否则后续断言可能数到说明文字）', () => {
    // 修复背景注释里必然提到这些词，去注释后不应残留在注释形态里
    expect(RAW).toContain('用户裁决')
    expect(SRC).not.toContain('用户裁决')
  })

  it('fnBody 能按花括号配对截出函数体且不溢出', () => {
    const body = fnBody(SRC, 'handleGridUpdate')
    expect(body).toContain('updateField')
    // 不应吞进下一个函数
    expect(body).not.toContain('function handleFieldUpdate')
  })

  it('fnBody 按 `(` 锚定名字，不被同前缀函数抢走', () => {
    // handleSave 与 handleSaveClick 前缀相同 → 必须各自命中
    const save = fnBody(SRC, 'handleSave')
    const click = fnBody(SRC, 'handleSaveClick')
    expect(save.startsWith('function handleSave(')).toBe(true)
    expect(click.startsWith('function handleSaveClick(')).toBe(true)
    expect(save).not.toBe(click)
  })
})

// ─── Property 1: 每个改内存的入口都要 markDirty ──────────────────────────────

describe('Property 1: 改内存的入口必须标记未保存', () => {
  const MUTATING_HANDLERS = [
    'handleGridUpdate',   // 完整表格视图（P0 的根因位置）
    'handleFieldUpdate',  // 列表视图明细面板
    'handleAdd',          // 新增行
    'handleDelete',       // 删除行
  ] as const

  it.each(MUTATING_HANDLERS)('%s 必须调用 markDirty()', (name) => {
    const body = fnBody(SRC, name)
    expect(body, `未能定位 ${name}`).not.toBe('')
    expect(body).toContain('markDirty()')
  })

  it('markDirty 只做置位，不夹带持久化副作用', () => {
    const body = fnBody(SRC, 'markDirty')
    expect(body).toContain('hasUnsavedChanges.value = true')
    expect(body).not.toContain('emit(')
  })
})

// ─── Property 2: 工具栏保存按钮存在且受 dirty 驱动 ───────────────────────────

describe('Property 2: 显式保存按钮（用户裁决的修法）', () => {
  it('模板里有受 hasUnsavedChanges 驱动的保存按钮', () => {
    // 原始模板（含注释外的属性绑定）
    expect(RAW).toMatch(/:disabled="!hasUnsavedChanges"/)
    expect(RAW).toMatch(/@click="handleSaveClick"/)
  })

  it('保存按钮不在某个视图内部 —— 两个视图共用同一入口', () => {
    // 必须落在工具栏区块内（toolbar-right），而不是 v-if 的列表/表格分支里
    const toolbar = RAW.match(
      /<div class="gt-confirmation-summary__toolbar-right">[\s\S]*?\n {10}<\/div>/,
    )
    expect(toolbar, '未能定位 toolbar-right 区块').not.toBeNull()
    expect(toolbar![0]).toContain('handleSaveClick')
  })

  it('有「未保存」可见标记（数据丢失前给用户信号）', () => {
    expect(RAW).toMatch(/v-if="hasUnsavedChanges"[\s\S]{0,120}未保存/)
  })

  it('只读模式下不渲染保存按钮', () => {
    const btn = RAW.match(/<el-button[^>]*handleSaveClick[\s\S]{0,60}/)
    // 按钮块内需带 v-if="!readonly"
    const block = RAW.match(/<el-button\s+v-if="!readonly"[\s\S]{0,400}?handleSaveClick/)
    expect(btn).not.toBeNull()
    expect(block, '保存按钮必须带 v-if="!readonly"').not.toBeNull()
  })
})

// ─── Property 3: handleSave 清 dirty 且走既有 emit 路径 ─────────────────────

describe('Property 3: 保存语义', () => {
  const body = fnBody(SRC, 'handleSave')

  it('走 emit(save, data.buildPayload())，不另造持久化路径', () => {
    expect(body).toContain('data.buildPayload()')
    expect(body).toMatch(/emit\(\s*'save'\s*,/)
  })

  it('保存后清 dirty（否则按钮永远高亮，用户无法判断是否已保存）', () => {
    expect(body).toContain('hasUnsavedChanges.value = false')
  })

  it('handleSaveClick 委托 handleSave（与列表视图保存同源幂等）', () => {
    const clickBody = fnBody(SRC, 'handleSaveClick')
    expect(clickBody).not.toBe('')
    expect(clickBody).toContain('handleSave()')
    // dirty 为 false 时短路，避免空保存刷新 last_modified
    expect(clickBody).toMatch(/if\s*\(\s*!hasUnsavedChanges\.value\s*\)\s*return/)
  })

  it('给出明确保存回执（静默保存会让用户不确定是否已落库）', () => {
    const clickBody = fnBody(SRC, 'handleSaveClick')
    expect(clickBody).toMatch(/ElMessage\.success/)
  })
})

// ─── Property 4: 未引入自动保存（用户明确不要） ──────────────────────────────

describe('Property 4: 用户裁决 = 显式按钮，不做自动保存', () => {
  it('本组件未对明细行接入防抖自动保存', () => {
    const body = fnBody(SRC, 'handleGridUpdate')
    expect(body).not.toContain('scheduleAutoSync')
    expect(body).not.toContain('debounce')
    expect(body).not.toMatch(/setTimeout\s*\(/)
  })

  it('matrix 手工覆盖仍走自己的 checklist 落库路径（与本次改动无关，不得被并进 buildPayload）', () => {
    const body = fnBody(SRC, 'handleF0MatrixOverride')
    if (body) {
      // 矩阵覆盖持久化到 checklist item，不是明细行 payload
      expect(body).toMatch(/emit\(\s*'save'\s*,\s*\{\s*itemId/)
      expect(body).not.toContain('buildPayload')
    }
  })
})

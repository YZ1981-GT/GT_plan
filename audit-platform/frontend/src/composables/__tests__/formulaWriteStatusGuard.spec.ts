/**
 * formulaWriteStatusGuard.spec.ts — 需求 15.3
 *
 * 公式管理写请求按状态码判成功：
 * ① 源码扫描：新增报表行 POST 与保存全部的写请求不得使用 `validateStatus`
 * ② 错误处理函数对 409/422/428/500 返回中文提示、不返回成功文案
 * ③ showFormulaError 对各状态码用正确的消息级别（warning / error）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// Mock element-plus 必须在 import useFormulaSettings 之前
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
  ElMessageBox: { confirm: vi.fn() },
}))

import { formulaErrorText, showFormulaError } from '@/composables/formula/useFormulaSettings'
import { ElMessage } from 'element-plus'

function mockAxiosError(status: number, detail?: string) {
  return {
    response: {
      status,
      data: { detail: detail || undefined, message: detail || undefined },
    },
  }
}

// ── ① 源码扫描：写请求不得使用 validateStatus ──────────────

describe('FormulaManagerDialog 写请求不使用 validateStatus（需求 15.3）', () => {
  // 支持从环境变量指定被扫描文件路径（worktree 场景）
  const srcPath = process.env.FORMULA_DIALOG_PATH
    || path.resolve(__dirname, '../../components/formula/FormulaManagerDialog.vue')
  const src = fs.readFileSync(srcPath, 'utf-8')

  it('新增报表行 POST 不含 validateStatus', () => {
    // 在 onFormulaEditSave 函数内定位新增报表行的 api.post → _isNew = false → 新公式 区域
    // 用 [\s\S] 匹配跨行内容
    const addRowRegion = src.match(
      /api\.post\(P_rc\.list,[\s\S]{0,500}?_silent[\s\S]{0,300}?_isNew\s*=\s*false[\s\S]{0,200}?新公式/,
    )
    // 如果上面匹配到了 _silent，说明 validateStatus 已被替换，直接通过
    // 否则尝试匹配旧写法（不该存在）
    if (addRowRegion) {
      expect(addRowRegion[0]).not.toContain('validateStatus')
    } else {
      // 退路：更宽泛地匹配新增报表行区域
      const fallbackRegion = src.match(
        /api\.post\(P_rc\.list,[\s\S]{0,600}?新公式/,
      )
      expect(fallbackRegion, '定位新增报表行 POST 区域').toBeTruthy()
      expect(fallbackRegion![0]).not.toContain('validateStatus')
    }
  })

  it('保存全部内新增行 POST 不含 validateStatus', () => {
    const fnStart = src.indexOf('async function onSaveAllFormulas')
    expect(fnStart).toBeGreaterThan(0)
    const fnBody = src.slice(fnStart)
    const newRowBranch = fnBody.match(
      /row\._isNew && row\.formula[\s\S]{0,800}?_isNew\s*=\s*false/,
    )
    expect(newRowBranch, '定位 onSaveAllFormulas 新增行分支').toBeTruthy()
    expect(newRowBranch![0]).not.toContain('validateStatus')
  })

  it('保存全部内底稿行 PUT 不含 validateStatus', () => {
    const fnStart = src.indexOf('async function onSaveAllFormulas')
    expect(fnStart).toBeGreaterThan(0)
    const fnBody = src.slice(fnStart)
    const wpBranch = fnBody.match(
      /api\.put\(wpFormula\.upsert[\s\S]{0,600}?savedDefinitionVersion/,
    )
    expect(wpBranch, '定位 onSaveAllFormulas 底稿行 PUT 区域').toBeTruthy()
    expect(wpBranch![0]).not.toContain('validateStatus')
  })
})

// ── ② 错误处理函数对 4xx/5xx 返回中文、不返回成功文案 ─────────

describe('formulaErrorText 对 409/422/428/500 返回中文提示（需求 15.3）', () => {
  const fallback = '保存失败'

  it('409 → 含中文且不含成功文案', () => {
    const text = formulaErrorText(mockAxiosError(409), fallback)
    expect(text).toBeTruthy()
    expect(text).not.toContain('成功')
    expect(text).not.toContain('已保存')
  })

  it('409 带后端 detail 透传', () => {
    const text = formulaErrorText(mockAxiosError(409, '版本冲突'), fallback)
    expect(text).toContain('版本冲突')
  })

  it('422 → 不含成功文案', () => {
    const text = formulaErrorText(mockAxiosError(422), fallback)
    expect(text).toBeTruthy()
    expect(text).not.toContain('成功')
  })

  it('428 → 含版本提示', () => {
    const text = formulaErrorText(mockAxiosError(428), fallback)
    expect(text).toContain('版本')
  })

  it('500 → 不含成功', () => {
    const text = formulaErrorText(mockAxiosError(500), fallback)
    expect(text).toBeTruthy()
    expect(text).not.toContain('成功')
  })
})

// ── ③ showFormulaError 对各状态码用正确级别 ─────────────────

describe('showFormulaError 注入 409/422/428/500 不弹成功（需求 15.3）', () => {
  beforeEach(() => {
    vi.mocked(ElMessage.success).mockReset()
    vi.mocked(ElMessage.warning).mockReset()
    vi.mocked(ElMessage.error).mockReset()
  })

  it('409 → warning、不弹 success', () => {
    showFormulaError(mockAxiosError(409), '保存失败')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.warning).toHaveBeenCalled()
  })

  it('422 → error、不弹 success', () => {
    showFormulaError(mockAxiosError(422), '保存失败')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalled()
  })

  it('428 → warning、不弹 success', () => {
    showFormulaError(mockAxiosError(428), '保存失败')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.warning).toHaveBeenCalled()
  })

  it('500 → error、不弹 success', () => {
    showFormulaError(mockAxiosError(500), '保存失败')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalled()
  })
})

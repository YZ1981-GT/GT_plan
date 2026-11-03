/**
 * 函证类型单一来源（spec attachment-confirmation-evidence-loop 需求 5.1，ADR-ACE-05）
 *
 * 前端六类 = 后端 `ConfirmationType` 枚举；「从底稿导入」四类 = 后端有科目前缀的类型；
 * 函证中心的创建 / 导入下拉都从这里取（不再各写一份硬编码选项）。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { FRONTEND_SRC, stripHtmlComments } from '@/__tests__/_helpers/frontendSourceScan'
import {
  CONFIRM_TYPE_FILTERS,
  CONFIRM_TYPE_OPTIONS,
  IMPORTABLE_CONFIRM_TYPES,
  confirmTypeLabel,
  confirmationStatusLabel,
} from '../confirmationTypeLabels'

const REPO = resolve(FRONTEND_SRC, '../../..')
/** 统一成 LF 再解析（后端文件是 CRLF） */
const read = (rel: string) => readFileSync(resolve(REPO, rel), 'utf-8').replace(/\r\n/g, '\n')

function backendEnumValues(): string[] {
  const src = read('backend/app/models/confirmation_models.py')
  const body = /class ConfirmationType\(str, enum\.Enum\):([\s\S]*?)\n\n/.exec(src)?.[1] ?? ''
  return [...body.matchAll(/^\s+(\w+) = "(\w+)"/gm)].map((m) => m[2])
}

function backendPrefixedTypes(): string[] {
  const src = read('backend/app/services/confirmation_service.py')
  const body = /_CONFIRM_TYPE_ACCOUNT_PREFIXES[^{]*\{([\s\S]*?)\n\}/.exec(src)?.[1] ?? ''
  return [...body.matchAll(/^\s+"(\w+)":/gm)].map((m) => m[1])
}

describe('函证类型', () => {
  it('六类与后端枚举逐项一致（含律师 / 其他）', () => {
    const values = backendEnumValues()
    expect(values.length).toBeGreaterThanOrEqual(6) // 解析没塌缩
    expect(CONFIRM_TYPE_OPTIONS.map((o) => o.value)).toEqual(values)
    expect(confirmTypeLabel('legal')).toBe('律师')
    expect(confirmTypeLabel('other')).toBe('其他')
    expect(CONFIRM_TYPE_FILTERS.map((f) => f.text)).toEqual(CONFIRM_TYPE_OPTIONS.map((o) => o.label))
  })

  it('「从底稿导入」只列后端能按科目取候选的四类', () => {
    const prefixed = backendPrefixedTypes()
    expect(prefixed.sort()).toEqual(['bank', 'loan', 'payable', 'receivable'])
    expect(IMPORTABLE_CONFIRM_TYPES.map((o) => o.value).sort()).toEqual(prefixed)
  })

  it('未知值原样显示、状态中文', () => {
    expect(confirmTypeLabel('xyz')).toBe('xyz')
    expect(confirmationStatusLabel('returned')).toBe('已回函')
  })

  it('函证中心的创建 / 导入下拉取自单一来源，类型列可筛选', () => {
    const hub = stripHtmlComments(read('audit-platform/frontend/src/views/ConfirmationHub.vue'))
    expect(hub).toMatch(/v-for="opt in CONFIRM_TYPE_OPTIONS"/)
    expect(hub).toMatch(/v-for="opt in IMPORTABLE_CONFIRM_TYPES"/)
    expect(hub).toMatch(/:filters="CONFIRM_TYPE_FILTERS"/)
    expect(hub).not.toMatch(/<el-option label="应收" value="receivable"/)
  })
})

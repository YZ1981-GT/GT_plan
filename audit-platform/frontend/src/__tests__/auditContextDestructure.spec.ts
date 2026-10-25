/**
 * `useAuditContext()` 解构键守卫
 *
 * 缺陷（2026-09-30 Playwright 实测）：J2 两个披露 Tab 写 `const { projectId, auditYear } = useAuditContext()`，
 * 而返回值字段是 `year` 不是 `auditYear` ⇒ 解构出 undefined，`auditYear.value` 在构造请求体时抛 TypeError、
 * 被 `catch {}` 静默吞掉 ⇒ 「同步到附注」按钮与自动同步**连网络请求都没发出过**，控制台也没有报错。
 *
 * 这类错误本该由类型检查抓到（AuditContextState 上不存在该属性），但本仓库全量 vue-tsc 内存溢出跑不动，
 * `.vue` 文件里的类型错误长期无人看见 ⇒ 用这条纯文本守卫兜底：解构的每个键都必须是 AuditContextState 的字段。
 */
import { describe, expect, it } from 'vitest'
import { resolve } from 'node:path'
import {
  FRONTEND_SRC,
  isTestFile,
  readSource,
  stripHtmlComments,
  stripJsComments,
  toSrcRelative,
  walkSourceFiles,
} from './_helpers/frontendSourceScan'

const CONTEXT_FILE = resolve(FRONTEND_SRC, 'composables/useAuditContext.ts')

/** 从接口声明解析字段名（`name:` / `name?:`） */
export function interfaceFields(source: string, name: string): string[] {
  const m = new RegExp(`export interface ${name}\\s*\\{([\\s\\S]*?)\\n\\}`).exec(stripJsComments(source))
  if (!m) return []
  return [...m[1].matchAll(/^\s*(\w+)\??\s*:/gm)].map((x) => x[1])
}

const DESTRUCTURE_RE = /(?:const|let|var)\s*\{([^}]*)\}\s*=\s*useAuditContext\s*\(/g

/** 解构模式里的**源键**（`a: b` 取 a；`a = 1` 取 a；剩余参数 `...rest` 不计） */
export function destructuredKeys(code: string): string[][] {
  const out: string[][] = []
  DESTRUCTURE_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = DESTRUCTURE_RE.exec(code)) !== null) {
    out.push(m[1].split(',').map((p) => p.trim()).filter((p) => p && !p.startsWith('...'))
      .map((p) => p.split(':')[0].split('=')[0].trim()))
  }
  return out
}

const FIELDS = new Set(interfaceFields(readSource(CONTEXT_FILE), 'AuditContextState'))
const FILES = walkSourceFiles(FRONTEND_SRC).filter((f) => !isTestFile(f))

describe('useAuditContext 解构键守卫 · 判据自身不空洞', () => {
  it('接口字段解析到位（projectId / year 等）', () => {
    expect(FIELDS.has('projectId')).toBe(true)
    expect(FIELDS.has('year')).toBe(true)
    expect(FIELDS.size).toBeGreaterThanOrEqual(5)
  })

  it('反向自检：重命名 / 默认值 / 剩余参数的源键识别正确', () => {
    expect(destructuredKeys('const { projectId: pid, year: auditYear, canEdit = true, ...rest } = useAuditContext()'))
      .toEqual([['projectId', 'year', 'canEdit']])
    expect(destructuredKeys('const { projectId, auditYear } = useAuditContext()')).toEqual([['projectId', 'auditYear']])
  })

  it('反向自检：J2 缺陷原形（解构 auditYear）被判为缺失字段；修复写法（year: auditYear）不被判', () => {
    const missing = (code: string) => destructuredKeys(code).flat().filter((k) => !FIELDS.has(k))
    expect(missing('const { projectId: ctxProjectId, auditYear } = useAuditContext()')).toEqual(['auditYear'])
    expect(missing('const { projectId: ctxProjectId, year: auditYear } = useAuditContext()')).toEqual([])
  })

  it('扫描面非空（全仓解构站点足够多）', () => {
    const sites = FILES.reduce((n, f) => n + destructuredKeys(stripJsComments(readSource(f))).length, 0)
    expect(sites).toBeGreaterThan(50)
  })
})

describe('useAuditContext 解构的键必须真实存在', () => {
  it('全仓无解构不存在字段的站点', () => {
    const offenders: string[] = []
    for (const f of FILES) {
      const src = readSource(f)
      const code = stripJsComments(f.endsWith('.vue') ? stripHtmlComments(src) : src)
      for (const keys of destructuredKeys(code)) {
        const missing = keys.filter((k) => !FIELDS.has(k))
        if (missing.length) offenders.push(`${toSrcRelative(f)} → ${missing.join(', ')}`)
      }
    }
    expect(offenders, `可用字段：${[...FIELDS].join(' / ')}`).toEqual([])
  })
})

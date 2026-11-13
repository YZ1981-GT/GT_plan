/**
 * 报表页深链带 ?year= 时仍取项目信息（准则 / 口径），附注编号映射随口径重取（2026-11-10）。
 *
 * 原状：`_ensureProjectYearWrapper` 路由给了年度就直接 return，不调 `ensureProjectYear` ⇒ 模板停在默认「国企版」，
 * 上市项目的报表 / 公式管理按国企口径取数、附注列显示「八、x」；附注编号映射只在映射为空时取一次，先到的国企口径
 * 映射一直留着。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = readFileSync(resolve(__dirname, '..', 'ReportView.vue'), 'utf8')

function functionBody(name: string): string {
  const m = new RegExp(`^(?:async )?function ${name}\\([^)]*\\)[^{]*\\{`, 'm').exec(SRC)
  expect(m, `没有 ${name}`).toBeTruthy()
  let depth = 1
  let i = m!.index + m![0].length
  while (depth > 0 && i < SRC.length) {
    if (SRC[i] === '{') depth += 1
    else if (SRC[i] === '}') depth -= 1
    i += 1
  }
  return SRC.slice(m!.index, i)
}

describe('报表页深链口径', () => {
  it('先取项目信息并同步模板，再处理路由年度', () => {
    const body = functionBody('_ensureProjectYearWrapper')
    const fetchAt = body.indexOf('await ensureProjectYear()')
    const syncAt = body.indexOf('selectedTemplateType.value = templateType.value')
    const routeAt = body.indexOf('if (routeYear.value !== null)')
    expect(fetchAt).toBeGreaterThan(-1)
    expect(syncAt).toBeGreaterThan(fetchAt)
    expect(routeAt).toBeGreaterThan(syncAt)
  })

  it('口径变化时重取附注编号映射，旧响应作废', () => {
    expect(SRC).toMatch(/watch\(\(\) => `\$\{selectedTemplateType\.value\}_\$\{reportScope\.value\}`, \(\) => \{\s*\n\s*if \(rows\.value\.length > 0\) loadRowNoteMapping\(\)/)
    const body = functionBody('loadRowNoteMapping')
    expect(body).toMatch(/const seq = \+\+rowNoteMappingSeq/)
    expect(body).toMatch(/if \(seq !== rowNoteMappingSeq\) return/)
  })
})

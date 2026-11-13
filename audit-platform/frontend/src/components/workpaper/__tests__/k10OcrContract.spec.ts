/**
 * K10 两张检查表的行级识别：按底稿调 D4 识别接口、读后端真有的字段（spec platform-performance-residual-findings-closure）。
 *
 * 原先 `api.post('/d4/contract-ocr')`：少 /api 前缀又没有底稿 id（后端没有这条路由，恒失败），读的 `text` 字段后端
 * 也不返回（识别全文在 `ocr_text`）。跨语言契约：从后端 `D4ContractOcrResponse` 取字段集合，前端读到的 `res?.x`
 * 必须都在里面。识别附件挂本行（`rowEv.append`）+ 小眼睛由 AttachmentEyeCoverageGuard 守。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { stripJsComments } from '../../../__tests__/_helpers/frontendSourceScan'

const SRC = resolve(__dirname, '../../..')
const BACKEND_OCR = resolve(SRC, '../../../backend/app/routers/wp_render_strategies/_d4_contract_ocr.py')
const HOSTS = ['components/workpaper/k10/inspection/K10TabOtherIncomeCheck.vue', 'components/workpaper/k10/inspection/K10TabReceivableGrant.vue']

function responseFields(py: string): Set<string> {
  const m = /class D4ContractOcrResponse\(BaseModel\):\n((?:[ \t]+.*\n)+)/.exec(py)
  if (!m) throw new Error('后端 D4ContractOcrResponse 没找到（解析失效即打红）')
  return new Set([...m[1].matchAll(/^[ \t]+(\w+)\s*:/gm)].map((x) => x[1]))
}

function functionBody(src: string, name: string): string {
  const start = src.search(new RegExp(`async function ${name}\\(`))
  if (start < 0) throw new Error(`没找到 ${name}`)
  const open = src.indexOf('{', src.indexOf(')', start))
  let depth = 0
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}' && (depth -= 1) === 0) return src.slice(start, i + 1)
  }
  throw new Error(`${name} 括号不配平`)
}

const fields = responseFields(readFileSync(BACKEND_OCR, 'utf8').replace(/\r\n/g, '\n'))

describe('K10 行级识别契约', () => {
  it('后端响应字段集合可解析（含 ocr_text / extracted_fields）', () => {
    expect([...fields]).toEqual(expect.arrayContaining(['attachment_id', 'ocr_text', 'extracted_fields']))
    expect(fields.has('text')).toBe(false)
  })

  it.each(HOSTS)('%s：按底稿调识别、附件挂本行、只读后端真有的字段', (rel) => {
    const sfc = readFileSync(resolve(SRC, rel), 'utf8')
    const script = [...sfc.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join('\n')
    const body = functionBody(stripJsComments(script), 'handleOCR')
    expect(body).toContain('`/api/workpapers/${props.wpId}/d4/contract-ocr`')
    expect(body).toMatch(/rowEv\.append\(formData, EVIDENCE_SHEET, rowEvidenceCell\(row\.rowKey\)\)/)
    const reads = [...body.matchAll(/\bres\?\.(\w+)/g)].map((m) => m[1])
    expect(reads).toContain('ocr_text')
    expect(reads.filter((f) => !fields.has(f))).toEqual([])
  })
})

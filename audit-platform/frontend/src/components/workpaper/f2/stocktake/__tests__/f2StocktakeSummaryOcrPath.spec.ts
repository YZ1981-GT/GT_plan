import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('F2TabStocktakeSummary OCR endpoint', () => {
  it('uses f2-st/contract-ocr and not d4/contract-ocr', () => {
    const src = readFileSync(
      resolve(__dirname, '../F2TabStocktakeSummary.vue'),
      'utf-8',
    )
    expect(src).toContain('f2-st/contract-ocr')
    expect(src).not.toContain('d4/contract-ocr')
  })
})

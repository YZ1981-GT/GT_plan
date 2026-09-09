import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '..')

describe('archive module 零网络/落盘结构守卫', () => {
  it('archive 目录源码不含 fetch/XHR/http/fs 写出', () => {
    const files = [
      'archive/archiveContainer.ts',
      'archive/archiveLimits.ts',
      'archive/archiveFixtures.ts',
      'archive/archive.worker.ts',
    ]
    for (const f of files) {
      const src = readFileSync(resolve(ROOT, f), 'utf8')
      expect(src).not.toMatch(/\bfetch\s*\(/)
      expect(src).not.toMatch(/XMLHttpRequest/)
      expect(src).not.toMatch(/from ['"]@\/utils\/http['"]/)
      expect(src).not.toMatch(/from ['"]@\/services\//)
      expect(src).not.toMatch(/showSaveFilePicker|createObjectURL.*download/)
    }
  })
})

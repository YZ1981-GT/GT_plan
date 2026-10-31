import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const bundleFiles = [
  's32-fraud-bundle/GtS32Bundle.vue',
  's33-ann14-bundle/GtS33Bundle.vue',
  's34-ipo-bundle/GtS34Bundle.vue',
  's35-refinance-bundle/GtS35Bundle.vue',
]

describe('S32~S35 bundle 负责人展示接线', () => {
  it.each(bundleFiles)('%s consumes the read-only assignee map', (relativePath) => {
    const source = readFileSync(
      resolve(__dirname, '../../', relativePath),
      'utf-8',
    )
    expect(source).toContain('BundleAssigneeDisplay')
    expect(source).toContain('assignedToMap')
  })
})

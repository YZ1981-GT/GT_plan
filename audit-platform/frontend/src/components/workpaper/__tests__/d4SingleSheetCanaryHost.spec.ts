import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(__dirname, '..', 'GtD4OperatingRevenue.vue')
const source = readFileSync(HOST, 'utf8')
const template = source.slice(source.indexOf('<template>'), source.indexOf('</template>'))

describe('D4-2 普通 single-sheet canary 宿主接线', () => {
  it('用 d42-managed 映射到父 D4 published entry', () => {
    expect(source).toContain("'D4-2': 'd42-managed'")
    expect(source).toContain("const D4_SYNC_ENTRY_ID = 'xlsx/gt-d4-operating-revenue'")
  })

  it('在线编辑分支消费 WorkpaperSyncEditorHost，不渲染 GtOnlyOfficeSheet', () => {
    const roomStart = template.indexOf(
      "v-if=\"renderMode === 'onlyoffice' && isD4DetailSheet\"",
    )
    const legacyStart = template.indexOf('<GtOnlyOfficeSheet')
    expect(roomStart).toBeGreaterThanOrEqual(0)
    expect(legacyStart).toBeGreaterThan(roomStart)
    const roomBlock = template.slice(roomStart, legacyStart)
    expect(roomBlock).toContain('<WorkpaperSyncEditorHost')
    expect(roomBlock).toContain(':descriptor="syncOoDescriptor"')
    expect(roomBlock).toContain(':bridge="syncBridge"')
  })
})

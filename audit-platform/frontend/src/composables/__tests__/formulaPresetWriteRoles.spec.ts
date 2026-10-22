/**
 * 公式预设写入角色 —— 前后端逐值对齐守卫（spec formula-governance-coverage-closure R4.2 / R1.8）
 *
 * 后端「导入入库」（import-data persist）与「新增自定义预设」（/presets/custom）共用
 * `_CUSTOM_PRESET_WRITE_ROLES`；前端「导入数据」可用性与「新建 / 编辑自定义预设」入口共用 `PRESET_WRITE_ROLES`。
 * 两份清单不一致 ⇒ 有权的人看不到入口，或无权的人点了必 403。任一侧改动都会让本守卫判红。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { PRESET_WRITE_ROLES, canWritePresets } from '../useFormulaImportExport'

const SRC = resolve(__dirname, '..', '..')
const BACK = resolve(SRC, '../../../backend/app/routers/formula_import_export.py')
const read = (p: string) => readFileSync(p, 'utf-8')
const noPyComments = (s: string) => s.replace(/"""[\s\S]*?"""/g, '').replace(/^\s*#.*$/gm, '')
const noTsComments = (s: string) =>
  s.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')

describe('公式预设写入角色', () => {
  const back = noPyComments(read(BACK))

  it('🔴 前端 PRESET_WRITE_ROLES 与后端 _CUSTOM_PRESET_WRITE_ROLES 逐值一致', () => {
    const m = back.match(/^_CUSTOM_PRESET_WRITE_ROLES\s*=\s*\[([^\]]+)\]/m)
    expect(m, '后端未找到 _CUSTOM_PRESET_WRITE_ROLES').toBeTruthy()
    const be = m![1].split(',').map((s) => s.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean)
    expect([...PRESET_WRITE_ROLES].sort()).toEqual([...be].sort())
  })

  it('后端两处入口都用这份清单（导入入库判角色 / 新增自定义预设 require_role）', () => {
    const importFn = back.split('async def import_data')[1]?.split('\n@router')[0] ?? ''
    expect(importFn).toMatch(/if persist and role not in _CUSTOM_PRESET_WRITE_ROLES/)
    const customSig = (back.split('async def create_custom_preset')[1] ?? '').split(/\n\)\s*->/)[0]
    expect(customSig).toContain('require_role(_CUSTOM_PRESET_WRITE_ROLES)')
  })

  it('前端入口都经 canWritePresets 判，不再各写一份角色字面量', () => {
    for (const rel of ['components/formula/GtFormulaPresetDialog.vue', 'components/template-library/FormulaTab.vue']) {
      const code = noTsComments(read(resolve(SRC, rel)))
      expect(code, rel).toContain('canWritePresets(')
      expect(code, rel).not.toMatch(/role\s*===\s*['"](admin|partner)['"]/)
    }
    expect(canWritePresets('admin')).toBe(true)
    expect(canWritePresets('partner')).toBe(true)
    expect(canWritePresets('manager')).toBe(false)
    expect(canWritePresets(undefined)).toBe(false)
  })
})

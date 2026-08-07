/**
 * Task 13 守卫：母公司章取数溯源的前端消费方。
 *
 * 覆盖 Property 22（缺失留空不填零）与 Property 23（溯源三项）的**前端侧**，
 * 并与后端 `parent_company_note_sections.py` 的键名常量交叉锁死。
 *
 * 🔴 键名不能只在前端断言 —— 它是跨前后端契约，改后端一侧前端会静默读到
 * `undefined`（横幅永不渲染 = 又一个 dead output）。故本文件直读那份 py 源码。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  PARENT_SOURCE_META_KEY,
  PARENT_PROJECT_MISSING_KEY,
  PARENT_SOURCE_META_FIELDS,
  PARENT_PROJECT_MISSING_TEXT,
  readParentCompanySource,
  parentCompanySourceSummary,
  parentScopeLabel,
} from '../parentCompanyNoteSource'

// ── 仓库根定位：双哨兵具体文件向上查找（禁写死回退级数，memory 铁律） ──
function repoRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i += 1) {
    const a = resolve(dir, 'backend/app/services/parent_company_note_sections.py')
    const b = resolve(dir, 'backend/app/services/disclosure_engine.py')
    if (existsSync(a) && existsSync(b)) return dir
    dir = resolve(dir, '..')
  }
  throw new Error('未找到仓库根（双哨兵 parent_company_note_sections.py + disclosure_engine.py 均不可见）')
}

const ROOT = repoRoot()
const PY_SECTIONS = readFileSync(
  resolve(ROOT, 'backend/app/services/parent_company_note_sections.py'),
  'utf-8',
)
const PY_ENGINE = readFileSync(
  resolve(ROOT, 'backend/app/services/disclosure_engine.py'),
  'utf-8',
)
const VUE = readFileSync(
  resolve(ROOT, 'audit-platform/frontend/src/views/DisclosureEditor.vue'),
  'utf-8',
)

function pyConst(name: string): string {
  const m = new RegExp(`^${name}\\s*=\\s*["']([^"']+)["']`, 'm').exec(PY_SECTIONS)
  if (!m) throw new Error(`后端常量 ${name} 未找到（正则失效或已改名）`)
  return m[1]
}

function pyTuple(name: string): string[] {
  const i = PY_SECTIONS.indexOf(`${name}: tuple[str, ...] = (`)
  if (i === -1) throw new Error(`后端常量 ${name} 未找到`)
  const j = PY_SECTIONS.indexOf(')', i)
  return [...PY_SECTIONS.slice(i, j).matchAll(/"([^"]+)"/g)].map((m) => m[1])
}

describe('跨前后端键名交叉锁死', () => {
  it('PARENT_SOURCE_META_KEY 与后端逐字相等', () => {
    expect(PARENT_SOURCE_META_KEY).toBe(pyConst('PARENT_SOURCE_META_KEY'))
  })

  it('PARENT_PROJECT_MISSING_KEY 与后端逐字相等', () => {
    expect(PARENT_PROJECT_MISSING_KEY).toBe(pyConst('PARENT_PROJECT_MISSING_KEY'))
  })

  it('溯源三项字段名与后端 PARENT_SOURCE_META_KEYS 逐字相等且顺序一致', () => {
    expect([...PARENT_SOURCE_META_FIELDS]).toEqual(pyTuple('PARENT_SOURCE_META_KEYS'))
  })

  it('反向自检：常量抽取器对不存在的名字必须抛错（防正则失效变空转）', () => {
    expect(() => pyConst('PARENT_SOURCE_META_KEY_DOES_NOT_EXIST')).toThrow()
    expect(() => pyTuple('NOPE_KEYS')).toThrow()
  })

  it('后端确实把这两个键落在表级 table_data 上（否则前端永远读不到）', () => {
    const i = PY_ENGINE.indexOf('_attach_parent_source_meta')
    expect(i).toBeGreaterThan(-1)
    const body = PY_ENGINE.slice(i, i + 2000)
    expect(body).toMatch(/table_data\[PARENT_SOURCE_META_KEY\]\s*=/)
    expect(body).toMatch(/table_data\[PARENT_PROJECT_MISSING_KEY\]\s*=\s*True/)
  })
})

describe('三态判定', () => {
  it('非母公司章 → none（横幅不渲染）', () => {
    for (const t of [null, undefined, {}, { headers: [], rows: [] }, 'x', 42]) {
      expect(readParentCompanySource(t as unknown).state).toBe('none')
    }
  })

  it('溯源三项齐备 → resolved', () => {
    const view = readParentCompanySource({
      [PARENT_SOURCE_META_KEY]: {
        source_project_name: '甲公司（母公司）',
        source_company_code: '91330000X',
        source_scope: 'standalone',
      },
    })
    expect(view.state).toBe('resolved')
    expect(view.projectName).toBe('甲公司（母公司）')
    expect(view.companyCode).toBe('91330000X')
    expect(view.scopeLabel).toBe('单体（母公司）')
  })

  it('表级 parent_project_missing → missing（缺失优先于 meta）', () => {
    const view = readParentCompanySource({
      [PARENT_PROJECT_MISSING_KEY]: true,
      [PARENT_SOURCE_META_KEY]: {
        source_project_name: null,
        source_company_code: null,
        source_scope: null,
      },
    })
    expect(view.state).toBe('missing')
    expect(view.scopeLabel).toBeNull()
  })

  it('meta 内嵌 parent_project_missing 也算 missing（后端 payload 形态）', () => {
    const view = readParentCompanySource({
      [PARENT_SOURCE_META_KEY]: {
        source_project_name: null,
        source_company_code: null,
        source_scope: null,
        [PARENT_PROJECT_MISSING_KEY]: true,
      },
    })
    expect(view.state).toBe('missing')
  })

  it('missing 与 none 不得合并 —— 两者必须可区分', () => {
    const missing = readParentCompanySource({ [PARENT_PROJECT_MISSING_KEY]: true })
    const none = readParentCompanySource({ headers: [] })
    expect(missing.state).not.toBe(none.state)
  })

  it('meta 全空且无缺失标记 → none（不渲染空横幅）', () => {
    const view = readParentCompanySource({
      [PARENT_SOURCE_META_KEY]: {
        source_project_name: null,
        source_company_code: null,
        source_scope: null,
      },
    })
    expect(view.state).toBe('none')
  })
})

describe('口径标签中文化', () => {
  it('已知口径译成中文', () => {
    expect(parentScopeLabel('standalone')).toBe('单体（母公司）')
    expect(parentScopeLabel('consolidated')).toBe('合并')
  })

  it('未知口径原样透出便于排查；空值返 null', () => {
    expect(parentScopeLabel('parent_only')).toBe('parent_only')
    expect(parentScopeLabel(null)).toBeNull()
    expect(parentScopeLabel('')).toBeNull()
    expect(parentScopeLabel(undefined)).toBeNull()
  })

  it('展示标签不得出现裸英文口径值（UI 全中文化）', () => {
    expect(parentScopeLabel('standalone')).not.toBe('standalone')
  })
})

describe('文案', () => {
  it('resolved 摘要含来源项目名/企业代码/口径三项', () => {
    const text = parentCompanySourceSummary({
      state: 'resolved',
      projectName: '甲公司（母公司）',
      companyCode: '91330000X',
      scopeLabel: '单体（母公司）',
    })
    expect(text).toContain('甲公司（母公司）')
    expect(text).toContain('91330000X')
    expect(text).toContain('单体（母公司）')
  })

  it('非 resolved 态摘要为空串（由缺失文案接手）', () => {
    expect(
      parentCompanySourceSummary({
        state: 'missing',
        projectName: null,
        companyCode: null,
        scopeLabel: null,
      }),
    ).toBe('')
  })

  it('缺项按「—」占位而不隐藏整条', () => {
    const text = parentCompanySourceSummary({
      state: 'resolved',
      projectName: null,
      companyCode: null,
      scopeLabel: '单体（母公司）',
    })
    expect(text).toContain('—')
  })

  it('缺失文案必须说明「留空不是零余额」（区分无数据与余额为 0）', () => {
    expect(PARENT_PROJECT_MISSING_TEXT).toContain('未建母公司单体')
    expect(PARENT_PROJECT_MISSING_TEXT).toMatch(/留空/)
    expect(PARENT_PROJECT_MISSING_TEXT).toMatch(/非零余额|不是 ?0|非 ?0/)
  })
})

describe('DisclosureEditor 已挂载横幅（防孤儿模块）', () => {
  it('导入了纯函数与文案常量', () => {
    expect(VUE).toMatch(/from '@\/views\/composables\/parentCompanyNoteSource'/)
    expect(VUE).toContain('readParentCompanySource')
    expect(VUE).toContain('parentCompanySourceSummary')
    expect(VUE).toContain('PARENT_PROJECT_MISSING_TEXT')
  })

  it('模板里真的渲染了横幅（含标签名边界，防被改名骗过）', () => {
    expect(VUE).toMatch(/class="gt-de-parent-source"/)
    expect(VUE).toMatch(/parentSourceView\.state !== 'none'/)
    expect(new RegExp('<el-alert(?=[\\s/>])').test(VUE)).toBe(true)
  })

  it('computed 从表级 activeTableData 取（键落在表级，取章节级会恒空）', () => {
    expect(VUE).toMatch(/readParentCompanySource\(activeTableData\.value\)/)
  })

  it('missing 态用 warning、resolved 用 info（缺失必须视觉可见）', () => {
    const i = VUE.indexOf('gt-de-parent-source')
    const block = VUE.slice(i, i + 1200)
    expect(block).toMatch(/'missing' \? 'warning' : 'info'/)
  })

  it('CSS 类已定义（否则横幅无样式塌成一行）', () => {
    const css = readFileSync(
      resolve(ROOT, 'audit-platform/frontend/src/views/DisclosureEditor.css'),
      'utf-8',
    )
    expect(css).toContain('.gt-de-parent-source')
    expect(css).toContain('.gt-de-parent-source__body')
  })
})

/**
 * 交付件溯源展示守卫 — deliverable-lineage-wiring-and-writeback-closure Task 22 / 23
 *
 * Property 22：版本链 `created_via` 中文化（禁裸英文）+ 展示 `tb_hash` 短标识与 stale 状态。
 * 需求 10.3：报表差异在交付中心以告警呈现具体报表行与差额。
 *
 * 手法：**纯函数行为断言 + 源码级结构断言**。不挂载组件的理由与
 * `deliverableCapabilityGating.spec.ts` 一致（Element Plus 表格/告警的挂载在
 * jsdom 下需要整套 iframe/尺寸桩，既有 OnlyOfficeEditor.spec.ts 已有 2 例预存在失败）；
 * 而本波次要钉住的恰是「有没有裸英文」「stale 是不是三态」这类结构性问题。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

import {
  CREATED_VIA_LABEL,
  createdViaLabel,
  driftAttributionLabel,
  driftAttributionTag,
  driftDiffs,
  driftPeriodLabel,
  shortHash,
  shouldShowDriftAlert,
} from '../deliverableLineageLabels'

// ── 仓库根定位：哨兵**文件**向上查找（禁写死回退级数）
function repoRoot(): string {
  let dir = resolve(__dirname)
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(join(dir, 'backend', 'app', 'services', 'deliverable_service.py'))) {
      return dir
    }
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未能定位仓库根（哨兵 backend/app/services/deliverable_service.py 未找到）')
}

const ROOT = repoRoot()

function readSrc(rel: string): string {
  const text = readFileSync(join(ROOT, rel), 'utf-8')
  expect(text.length, `${rel} 读取为空`).toBeGreaterThan(0)
  return text
}

const FE = 'audit-platform/frontend/src'
const VERSION_LIST = readSrc(`${FE}/components/deliverable/DeliverableVersionList.vue`)
const DRIFT_ALERT = readSrc(`${FE}/components/deliverable/DeliverableDriftAlert.vue`)
const CENTER = readSrc(`${FE}/views/DeliverableCenter.vue`)
const LABELS = readSrc(`${FE}/components/deliverable/deliverableLineageLabels.ts`)

/** 剥掉 JS/HTML 注释，避免"说明注释里写出的反例"被数成真实代码。 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

it('剥注释函数自检（否则源码级断言全是空转）', () => {
  const sample = 'const a = 1 // v.created_via\n<!-- v.created_via -->\n/* v.created_via */\nconst b = 2'
  const out = stripComments(sample)
  expect(sample.split('v.created_via').length - 1).toBe(3)
  expect(out).not.toContain('v.created_via')
  expect(out).toContain('const a = 1')
  expect(out).toContain('const b = 2')
})

// ─── Property 22: created_via 中文化且标签是单一真源 ─────────────────────────

describe('Property 22 — created_via 中文化', () => {
  it('后端产出的每个 created_via 取值都有中文标签', () => {
    // 交叉锁死：扫后端全部 `created_via="xxx"` 实参，逐个要求前端有标签。
    // 后端新增一种来源（如未来的 "import"）而前端漏加标签 ⇒ 立即打红。
    const files = [
      'backend/app/services/deliverable_service.py',
      'backend/app/services/onlyoffice_callback_service.py',
      'backend/app/services/deliverable_refresh_service.py',
      'backend/app/services/full_deliverables_executor.py',
      'backend/app/routers/deliverable.py',
    ]
    const found = new Set<string>()
    for (const rel of files) {
      const src = readSrc(rel)
      for (const m of src.matchAll(/created_via\s*=\s*["']([a-z_]+)["']/g)) {
        found.add(m[1])
      }
    }
    expect(found.size, '未扫到任何 created_via 实参 ⇒ 正则失效（空转）').toBeGreaterThan(0)
    for (const value of found) {
      expect(
        Object.prototype.hasOwnProperty.call(CREATED_VIA_LABEL, value),
        `后端会产出 created_via='${value}' 但前端无中文标签 ⇒ 版本链会显示裸英文`,
      ).toBe(true)
    }
  })

  it('版本链模板必须经标签函数渲染，不得直接输出裸值', () => {
    const src = stripComments(VERSION_LIST)
    expect(src).toContain('createdViaLabel(v.created_via)')
    expect(src, '模板仍在直接插值 created_via ⇒ 裸英文').not.toMatch(/\{\{\s*v\.created_via\s*\}\}/)
  })

  it('标签缺失时回退为「未记录」而非空白', () => {
    expect(createdViaLabel(null)).toBe('未记录')
    expect(createdViaLabel(undefined)).toBe('未记录')
    expect(createdViaLabel('')).toBe('未记录')
    // 未登记取值原样透出（比显示空白可诊断），但上一条守卫会先打红
    expect(createdViaLabel('brand_new')).toBe('brand_new')
    expect(createdViaLabel('onlyoffice_edit')).toBe('在线编辑')
  })
})

// ─── Property 22: tb_hash 短标识 + stale 三态 ────────────────────────────────

describe('Property 22 — 快照与 stale 展示', () => {
  it('shortHash 取前 8 位，空值返 null 交调用方决定', () => {
    expect(shortHash('a'.repeat(64))).toBe('aaaaaaaa')
    expect(shortHash(null)).toBeNull()
    expect(shortHash(undefined)).toBeNull()
    expect(shortHash('')).toBeNull()
  })

  it('版本链展示 tb_hash 短标识，且未记录时明示', () => {
    const src = stripComments(VERSION_LIST)
    expect(src).toContain('shortHash(v.bound_tb_hash)')
    expect(src).toContain('快照未记录')
    // 完整 hash 应作为 tooltip 而不是直接铺在行里
    expect(src).toContain('v.bound_tb_hash')
  })

  it('🔴 stale 必须三态：未知不得渲染成「与上游一致」', () => {
    const src = stripComments(VERSION_LIST)
    expect(src, 'stale 未按 === true 判定').toContain("v.is_stale === true")
    expect(src, 'stale 未按 === false 判定').toContain("v.is_stale === false")
    // 反向自检：出现 `v-else` 兜底就意味着 null 会落进某一态 ⇒ 骗人
    expect(
      /v-else\s*>[^<]*(上游已变更|与上游一致)/.test(src),
      'stale 用 v-else 兜底 ⇒ 未知态被渲染成确定结论',
    ).toBe(false)
    expect(src, 'stale 退化为真值判断').not.toMatch(/v-if="v\.is_stale"/)
  })

  it('编辑人只读 edited_by_name，未知时如实显示', () => {
    const src = stripComments(VERSION_LIST)
    expect(src).toContain('v.edited_by_name')
    expect(src).toContain('编辑人未知')
    // 🔴 OO 路径下 created_by 只是回调处理占位，拿它当编辑人会让所有在线编辑
    // 版本都显示成交付物创建人（需求 7.2/7.3）
    expect(src, '编辑人回退了 created_by').not.toContain('v.created_by')
  })

  it('后端下发的 edited_at 必须有渲染出口（不得是下发了没人看的死字段）', () => {
    const src = stripComments(VERSION_LIST)
    expect(src, 'edited_at 零消费 ⇒ 属 dead output').toContain('v.edited_at')
    expect(src).toContain('editorTooltip')
  })
})

// ─── 需求 10.3：差异告警 ────────────────────────────────────────────────────

describe('需求 10.3 — 报表差异告警', () => {
  const ONE_DIFF = {
    diffs: [
      {
        row_code: 'BS-006',
        row_name: '应收账款',
        sheet: 'balance_sheet',
        coord: 'C12',
        period: 'current',
        file_value: '500.00',
        expected_value: '400.00',
        diff: '100.00',
      },
    ],
  }

  it('🔴 可见性判据与后端 should_block_confirm 同口径（三态）', () => {
    expect(shouldShowDriftAlert(null)).toBe(false)
    expect(shouldShowDriftAlert(undefined)).toBe(false)
    // 已比对且一致 ⇒ 不告警
    expect(shouldShowDriftAlert({ diffs: [] })).toBe(false)
    expect(shouldShowDriftAlert(ONE_DIFF)).toBe(true)
    expect(shouldShowDriftAlert({ unavailable: '映射解析失败' })).toBe(true)
  })

  it('反向自检：朴素 `!!report` 会让配了映射的报表常亮空告警', () => {
    const clean = { diffs: [], checked: 292 }
    expect(Boolean(clean), '朴素判据在此为 true（复现旧行为）').toBe(true)
    expect(shouldShowDriftAlert(clean), '正确判据必须为 false').toBe(false)
  })

  it('driftDiffs 对非数组一律按空处理', () => {
    expect(driftDiffs(null)).toEqual([])
    expect(driftDiffs({ diffs: undefined })).toEqual([])
    expect(driftDiffs({ diffs: 'oops' as unknown })).toEqual([])
    expect(driftDiffs(ONE_DIFF)).toHaveLength(1)
  })

  it('告警呈现具体报表行、位置与两侧数值（需求 10.3）', () => {
    const src = stripComments(DRIFT_ALERT)
    expect(src).toContain('row_name')
    expect(src).toContain('row.coord')
    expect(src).toContain('row.file_value')
    expect(src).toContain('row.expected_value')
    expect(src).toContain('row.diff')
    expect(src, '未提示走调整分录').toContain('调整分录')
  })

  it('🔴 告警文案必须中性归因，不得断言有人改了数字', () => {
    const src = stripComments(DRIFT_ALERT)
    // 三种可能原因都要列出（与后端 should_block_confirm 文案对齐）
    expect(src).toContain('上游数据已变更')
    expect(src).toContain('单元格映射与模板布局不一致')
    // 允许「确有手工改动」作为可能原因之一，但不得作为结论式断言
    expect(src).toContain('确有手工改动')
    expect(src).not.toContain('有人手工改')
    expect(src).not.toContain('手工改动共')
  })

  it('「本次编辑引入」列必须区分三态（含无基线可比）', () => {
    const src = stripComments(DRIFT_ALERT)
    expect(src).toContain('row.pre_existing === true')
    expect(src).toContain('row.pre_existing === false')
    expect(src, '无基线时必须明示，不得当成"本次引入"').toContain('无基线可比')
  })

  it('归因标签/色值来自单一真源且四态齐全', () => {
    for (const key of ['upstream_changed', 'pre_existing', 'manual_edit', 'unknown']) {
      expect(driftAttributionLabel(key)).toBeTruthy()
      expect(['warning', 'info', 'danger']).toContain(driftAttributionTag(key))
    }
    // 未知/缺失一律落 unknown，不得抛也不得显示英文
    expect(driftAttributionLabel(null)).toBe('成因待确认')
    expect(driftAttributionLabel('weird_value')).toBe('成因待确认')
    expect(driftAttributionTag(null)).toBe('info')
    // pre_existing 不得用 danger（那是指向人的色）
    expect(driftAttributionTag('pre_existing')).not.toBe('danger')
  })

  it('期间列中文化', () => {
    expect(driftPeriodLabel('current')).toBe('本期')
    expect(driftPeriodLabel('prior')).toBe('上期')
    expect(driftPeriodLabel(null)).toBe('-')
  })

  it('🔴 列表行即可见差异徽标（不必先展开版本链）', () => {
    const group = readSrc(`${FE}/components/deliverable/DeliverableGroupList.vue`)
    const src = stripComments(group)
    expect(src, '列表行无差异徽标 ⇒ 需求 10.3 要用户先怀疑再去查').toContain(
      'row.drift_blocked',
    )
    expect(src).toContain('row.drift_reason')
    // 🔴 判定必须用后端下发的布尔，不得在前端复现三态判据
    expect(src, '前端自写 `if (row.drift_report)` ⇒ 空 diffs 会常亮空告警').not.toContain(
      'row.drift_report',
    )
  })

  it('交付中心已挂载告警组件且只对最新版告警', () => {
    const src = stripComments(CENTER)
    expect(src, '告警组件未渲染 ⇒ 需求 10.3 无出口').toContain('<DeliverableDriftAlert')
    expect(src).toContain("import DeliverableDriftAlert from '@/components/deliverable/DeliverableDriftAlert.vue'")
    // 版本链按时间倒序，取 [0] 即最新版
    expect(src).toContain('versionChain.value[0]?.drift_report')
  })

  it('金额格式走 displayPrefs.fmtAmount（平台单一真源）', () => {
    const src = stripComments(DRIFT_ALERT)
    expect(src).toContain('displayPrefs.fmtAmount')
    // 🔴 fmtAmount 是 store 成员，不是模块级导出；写成命名导入会让整页崩
    expect(src).not.toMatch(/import\s*\{[^}]*fmtAmount[^}]*\}\s*from\s*'@\/stores\/displayPrefs'/)
  })
})

// ─── Property 23 前端半边：三件套三列对照 + 重新生成入口（需求 11.3/11.4）────

describe('需求 11.3/11.4 — 三件套一致性三列对照', () => {
  const BANNER = readSrc(`${FE}/components/deliverable/CompletenessBanner.vue`)

  it('三列对照消费后端下发的滞后判定字段，不自己算多数', () => {
    const src = stripComments(BANNER)
    for (const field of [
      'trio_tb_hashes',
      'trio_lagging',
      'trio_majority_tb_hash',
      'trio_ambiguous',
    ]) {
      expect(src, `未消费 ${field}`).toContain(field)
    }
    // 反向自检：前端不得自己数多数（判据在后端 check_trio_consistency）
    expect(src).not.toMatch(/\bcounts\b/)
  })

  it('三件套中文名与后端 _TRIO_LABEL 逐字一致（禁裸 doc_type）', () => {
    const py = readSrc('backend/app/services/deliverable_snapshot_service.py')
    const block = py.slice(py.indexOf('_TRIO_LABEL'))
    const backendLabels = new Map<string, string>()
    for (const m of block.matchAll(/"([a-z_]+)":\s*"([^"]+)"/g)) {
      backendLabels.set(m[1], m[2])
      if (backendLabels.size >= 3) break
    }
    expect(backendLabels.size, '未抽到后端三件套中文名 ⇒ 正则失效').toBe(3)

    const src = stripComments(BANNER)
    for (const [docType, label] of backendLabels) {
      expect(src, `前端缺 ${docType} 的中文名`).toContain(`'${docType}'`)
      expect(src, `前端 ${docType} 中文名与后端不一致（应为「${label}」）`).toContain(label)
    }
  })

  it('只在不一致时展开三列（一致时保持紧凑单行 bar）', () => {
    const src = stripComments(BANNER)
    expect(src).toContain('trio_consistent === false')
    expect(src).toContain('showTrioTable')
  })

  it('提供「重新生成这一类」入口且复用既有生成通路', () => {
    const banner = stripComments(BANNER)
    expect(banner).toContain('重新生成这一类')
    expect(banner).toContain("emit('regenerate', row.docType)")

    const center = stripComments(CENTER)
    expect(center).toContain('@regenerate="onRegenerateTrio"')
    // 🔴 不得新造生成逻辑（会绕过 guardGenerate 权限校验）
    expect(center).toContain('function onRegenerateTrio')
    const i = center.indexOf('function onRegenerateTrio')
    const body = center.slice(i, i + 600)
    expect(body).toMatch(/openGenerateReport|goGenerateReports|goGenerateNotes/)
    expect(body, '重新生成入口自己发请求 ⇒ 绕过权限校验').not.toContain('api.post')
  })
})

// ─── 需求 11.5/11.6：列表行级溯源 ───────────────────────────────────────────

describe('需求 11.5/11.6 — 列表行级溯源', () => {
  const DRAWER = readSrc(`${FE}/components/deliverable/DeliverableTraceDrawer.vue`)
  const GROUP = readSrc(`${FE}/components/deliverable/DeliverableGroupList.vue`)

  it('列表每行有溯源入口并向上抛事件', () => {
    const src = stripComments(GROUP)
    expect(src).toContain('数据溯源')
    expect(src).toContain("command=\"trace\"")
    expect(src).toContain("emit('trace', row)")
    expect(src).toContain('trace: [item: DeliverableItem]')
  })

  it('交付中心接线抽屉', () => {
    const src = stripComments(CENTER)
    expect(src).toContain('@trace="openTrace"')
    expect(src).toContain('<DeliverableTraceDrawer')
    expect(src).toContain('function openTrace')
  })

  it('🔴 溯源请求复用 useDeliverableLineage，不重写一份', () => {
    const src = stripComments(DRAWER)
    expect(src).toContain('useDeliverableLineage')
    expect(src).toContain('traceSection')
    // 抽屉自己只允许调 section-states（trace 端点由 composable 负责，
    // 否则 504 超时的明确文案要写两份、改一处另一处不红）
    expect(src).not.toMatch(/api\.get<[^>]*>\([^)]*\/trace/)
  })

  it('链条阶段顺序固定为「附注章节 → 底稿 → 试算表 → 调整分录」', () => {
    const src = stripComments(DRAWER)
    const order = ['附注章节', '底稿', '试算表 / 序时账', '调整分录']
    let cursor = -1
    for (const label of order) {
      const at = src.indexOf(`label: '${label}'`)
      expect(at, `阶段「${label}」缺失`).toBeGreaterThan(-1)
      expect(at, `阶段顺序错乱：「${label}」出现得太早`).toBeGreaterThan(cursor)
      cursor = at
    }
  })

  it('空阶段与无锚点都要给明确原因（需求 11.6 禁空白）', () => {
    const src = stripComments(DRAWER)
    expect(src).toContain('emptyHint')
    expect(src).toContain('未匹配')
    expect(src).toContain('没有章节锚点')
    // 章节清单加载失败也要给原因
    expect(src).toContain('章节清单加载失败')
  })

  it('契约：LinkageStatus 四态全部有中文标签', () => {
    const src = stripComments(DRAWER)
    for (const [key, label] of [
      ['current', '最新'],
      ['stale', '已过期'],
      ['conflict', '冲突'],
      ['manual_override', '人工覆盖'],
    ]) {
      expect(src).toContain(`${key}: '${label}'`)
    }
  })
})

// ─── 标签真源不得被复制 ─────────────────────────────────────────────────────

it('标签 map 只有一份（禁止各组件再抄一份）', () => {
  for (const [name, src] of [
    ['DeliverableVersionList.vue', VERSION_LIST],
    ['DeliverableDriftAlert.vue', DRIFT_ALERT],
  ] as const) {
    const stripped = stripComments(src)
    expect(
      stripped.includes("onlyoffice_edit:") || stripped.includes("'在线编辑'"),
      `${name} 里出现了标签字面量 ⇒ 与 deliverableLineageLabels 分叉`,
    ).toBe(false)
  }
  // 反向自检：真源里确实有这些字面量
  expect(LABELS).toContain('onlyoffice_edit:')
  expect(LABELS).toContain('在线编辑')
})

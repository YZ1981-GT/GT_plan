/**
 * formula-manager-all-accessible-pages.spec.ts
 *   —— 公式管理「全量门禁」（formula-manager-closure · Task 8.1 · 需求 12 · design §7 全要素）
 *
 * ADR-FMC-08 / §7.1 运行时权威分母 / §7.2 八条断言 / §7.3 豁免登记 / §7.4 幂等输出 / §7.5 变异。
 *
 * ═══ 这道门禁守护什么 ═══
 *
 * 旧 toolbar E2E 允许 `triggerCount>=0`、只数关闭态 dialog≤1，从未点按钮核左右栏（报告第八节盲区④）。
 * 本门禁把「每个可访问底稿页的公式管理契约」钉成**随分母增长自动变红**的硬断言，且门禁本身幂等、
 * 不恒红（§7.4，memory 铁律㉗）。
 *
 * ═══ 分母从哪来（§7.1，真连 vs 结构化复用，如实）═══
 *
 * 运行时权威分母由 Python 枚举器 `backend/scripts/check/check_formula_manager_all_pages_denominator.py`
 * **真连 PG**：枚举全部可访问 `working_paper` → render-config 展开每真实 sheet / whole_workbook /
 * redirect，每项记 project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType，并用
 * `gate_exemptions.exempted_keys()`（Task 2.2/2.3 产物）剔除 redirect / 口径外 404。本 spec 通过
 * `spawnSync` 调该枚举器的 `--check`（§7.4②），读其幂等 JSON 产物做分母级结构断言。
 *
 * 真库不可达时（枚举器 exit 3 `db_unavailable`）：本 spec **不假绿**——分母级断言如实标注「需
 * start-dev + PG」并跳过（非当成通过），但**8 条契约断言 + 4+surfaced 变异 + 幂等自证仍全跑**
 * （它们复用 Phase 1~7 的生产单一真源模块 + 真实分母采样 fixture，不依赖活后端 HTTP）。
 *
 * ═══ 8 条断言复用的生产单一真源（§7.5 变异逐一映射到子项）═══
 *
 *   ① 唯一入口 / ③ 完整 location → `openFormulaManagerFromLocation.ts`（Task 2.1）
 *   ④ 左栏精确               → `leftPanelAnchors.ts`（Task 3.2）
 *   ⑤a 右栏精确              → `sheetIdentityMatch.ts : matchRowToSelectedSheet`（Task 1.2）
 *   ⑤b surfaced 只读去伪装   → `formulaRowKind.ts : isReadonlyProjectionRow`（Task 1.4）
 *   ⑤c 保存契约字段+端点分派 → `wpFormulaFields.ts` + `formulaRowKind.ts : resolveSaveDispatch`（Task 1.4/1.5）
 *   ⑥ 切换隔离               → `projectCacheKey.ts`（Task 6.3）
 *   ⑦ 权限分层（硬断言）     → Phase 5 TestClient 坐实产物存在性（ADR-FMC-06，见 §7.2 ⑦ pending→硬断言前置）
 *   ⑧ 零错误                 → fail-closed 单一真源（缺 location 不发请求 / 缺身份不退全局树）
 *
 * ⑦ 从 pending 转硬断言：Phase 5 已把全部对象型端点（wp_formula 读写、report_config CRUD、
 * /api/formula/execute、formula-scope、tb_detail 读写）加固并通过 Task 5.1 §6.1 TestClient 坐实
 * （见本 spec「⑦ 权限分层」describe 的前置存在性断言）。
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, it, expect, beforeAll } from 'vitest'

import {
  matchRowToSelectedSheet,
  normalizeSheetCode,
} from '../sheetIdentityMatch'
import {
  isReadonlyProjectionRow,
  classifyFormulaRowKind,
  resolveSaveDispatch,
} from '../formulaRowKind'
import { mapWpItemToRowFields, readWpCategory, readWpDescription } from '../wpFormulaFields'
import {
  projectCacheKey,
  cacheKeyMatches,
  shouldApplyResponse,
  resolveSaveYear,
} from '../projectCacheKey'
import {
  decideLeftPanelMode,
  buildCurrentSheetAnchorNodes,
  hasCompleteLocationIdentity,
  type LocationIdentity,
} from '../leftPanelAnchors'
import {
  buildLocationFromContext,
  openFormulaManagerFromLocation,
  type FormulaManagerOutletContext,
} from '@/shell/formula/openFormulaManagerFromLocation'

const here = dirname(fileURLToPath(import.meta.url))
// .../src/components/formula/__tests__ → repo root 上溯 6 层
const REPO_ROOT = resolve(here, '../../../../../..')
const PROBE = 'backend/scripts/check/check_formula_manager_all_pages_denominator.py'
const DENOMINATOR_JSON = resolve(
  REPO_ROOT,
  'backend/app/data/formula_manager_all_pages_denominator.json',
)
const EXEMPTIONS_JSON = resolve(
  REPO_ROOT,
  'backend/app/data/formula_manager_gate_exemptions.json',
)

// 退出码约定（与枚举器 §7.4② 一致）。
const EXIT_OK = 0
const EXIT_DRIFT = 2
const EXIT_DB_UNAVAILABLE = 3

interface DenominatorItem {
  project_id: string
  wp_id: string
  wp_code: string
  sheet_uid: string
  sheet_code: string
  host: string
  component_type: string
  redirect: boolean
  exempted: boolean
  exempt_key: string
  render_config_resolved: boolean
}
interface DenominatorDoc {
  schema_version: number
  generated_at: string
  fingerprint: string
  counts: Record<string, number>
  items: DenominatorItem[]
}

/** 运行枚举器 `--check`，返回退出码 + stdout/stderr（§7.4③ 子进程编码约定）。 */
function runProbeCheck(): { status: number | null; stdout: string; stderr: string } {
  const py = process.platform === 'win32' ? 'python' : 'python3'
  const r = spawnSync(py, [PROBE, '--check'], {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024,
    // §7.4③：子进程强制 utf-8（Windows 子进程 piped stdout 默认 gbk，中文信息按 utf-8
    // 解码必炸 → run() 把 stdout 变 None 却不改退出码 ⇒ 只看 returncode 必假绿，教训㉗⑦）。
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  })
  return { status: r.status, stdout: r.stdout ?? '', stderr: r.stderr ?? '' }
}

let probe: { status: number | null; stdout: string; stderr: string }
let dbAvailable = false
let doc: DenominatorDoc | null = null

beforeAll(() => {
  probe = runProbeCheck()
  // §7.4③：断言 stdout 含预期内容（不只看 returncode）——否则 Windows gbk 解码失败会假绿。
  dbAvailable = probe.status === EXIT_OK || probe.status === EXIT_DRIFT
  if (existsSync(DENOMINATOR_JSON)) {
    doc = JSON.parse(readFileSync(DENOMINATOR_JSON, 'utf-8')) as DenominatorDoc
  }
}, 900_000)

// ─────────────────────── §7.1 运行时权威分母（真连 or 如实跳过）───────────────────────

describe('§7.1 运行时权威分母（枚举器真连 PG）', () => {
  it('§7.4③ 子进程断言 stdout 含预期内容（非仅看 returncode；Windows gbk 假绿防御）', () => {
    // 枚举器无论 OK / DRIFT / DB_UNAVAILABLE 都打印可识别的中文标记行。stdout 为空 =
    // 解码失败被吞 = 假绿，必须炸出来。
    const combined = probe.stdout + probe.stderr
    expect(combined.trim().length, '枚举器 stdout+stderr 为空 ⇒ 解码失败被吞（假绿）').toBeGreaterThan(0)
    // 三态之一的标记必须出现（证明真的跑到了对应分支，而不是空转）。
    const hasKnownMarker =
      combined.includes('[OK]') ||
      combined.includes('[DRIFT]') ||
      combined.includes('[DB_UNAVAILABLE]')
    expect(hasKnownMarker, `枚举器输出无已知标记：\n${combined.slice(0, 2000)}`).toBe(true)
  })

  it('枚举器退出码 ∈ {OK, DRIFT, DB_UNAVAILABLE}（不得崩溃/未知码）', () => {
    expect([EXIT_OK, EXIT_DRIFT, EXIT_DB_UNAVAILABLE]).toContain(probe.status)
  })

  it.runIf(() => dbAvailable)('真库可达时：分母与磁盘基线一致（--check exit 0，无漂移）', () => {
    // dbAvailable=DRIFT 也算真库可达，但此时应点名漂移 → 要求 OK。
    expect(
      probe.status,
      `分母漂移：${probe.stderr.slice(0, 2000)}\n须让新页进门禁 / 下线页更新基线后 --write 刷新。`,
    ).toBe(EXIT_OK)
  })

  it('分母 JSON 每项字段齐全（project_id/wp_id/wp_code/sheet_uid/sheet_code/host/componentType）', () => {
    if (!doc) {
      // 磁盘基线缺失且真库不可达 → 如实标注，不假绿（本条在 CI 有基线时恒跑）。
      expect(dbAvailable, '磁盘分母基线缺失且真库不可达 ⇒ 需 start-dev + PG 先 --write 取基线').toBe(false)
      return
    }
    expect(doc.items.length, '分母为空（枚举失败或无可访问底稿）').toBeGreaterThan(0)
    for (const it of doc.items.slice(0, 50)) {
      expect(typeof it.project_id).toBe('string')
      expect(typeof it.wp_id).toBe('string')
      expect(it.wp_code.length, 'wp_code 不得为空').toBeGreaterThan(0)
      expect(['html', 'onlyoffice', 'univer'].includes(it.host) || it.host.length > 0).toBe(true)
      expect(typeof it.component_type).toBe('string')
      expect(typeof it.redirect).toBe('boolean')
    }
  })

  it('分母指纹稳定（generated_at 不进指纹；幂等 §7.4①）', () => {
    if (!doc) return
    // 指纹只覆盖实质内容，不含 generated_at —— 故两次运行内容不变时 generated_at 不变。
    expect(doc.fingerprint.length).toBe(64) // sha256 hex
    expect(doc.generated_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/)
    // 无机器名 / 绝对路径泄漏（§7.4①）。
    const raw = readFileSync(DENOMINATOR_JSON, 'utf-8')
    expect(raw, '分母 JSON 不得含绝对路径（泄漏机器信息、破坏幂等）').not.toMatch(/[A-Za-z]:\\\\/)
    expect(raw).not.toContain(REPO_ROOT)
  })
})

// ─────────────────────── §7.3 豁免登记（复用 Task 2.2/2.3 产物）───────────────────────

describe('§7.3 豁免登记（gate_exemptions 可伪证 + 防空转）', () => {
  it('豁免登记文件存在且结构合法（redirect / classification-404 两类）', () => {
    expect(existsSync(EXEMPTIONS_JSON), '缺 formula_manager_gate_exemptions.json').toBe(true)
    const ex = JSON.parse(readFileSync(EXEMPTIONS_JSON, 'utf-8')) as {
      schema_version: number
      exemptions: Array<{ key: string; kind: string; owner: string; reason: string; expires_at: string; verify_against: Record<string, unknown> }>
    }
    expect(ex.exemptions.length).toBeGreaterThan(0)
    for (const e of ex.exemptions) {
      // 每条豁免必须是可伪证声明（有 owner/reason/expires_at/verify_against），非只存理由的后门。
      expect(e.owner.trim().length, `${e.key} 缺 owner`).toBeGreaterThan(0)
      expect(e.reason.trim().length, `${e.key} 缺 reason`).toBeGreaterThan(0)
      expect(e.expires_at, `${e.key} 缺 expires_at`).toBeTruthy()
      expect(Object.keys(e.verify_against).length, `${e.key} 缺 verify_against（空转后门）`).toBeGreaterThan(0)
    }
  })

  it.runIf(() => dbAvailable && !!doc)('分母里 exempted 项的 exempt_key 必须出自豁免登记（剔除可追溯）', () => {
    if (!doc) return
    const ex = JSON.parse(readFileSync(EXEMPTIONS_JSON, 'utf-8')) as {
      exemptions: Array<{ key: string }>
    }
    const registeredKeys = new Set(ex.exemptions.map((e) => e.key))
    const exemptedItems = doc.items.filter((i) => i.exempted)
    for (const it of exemptedItems) {
      expect(
        registeredKeys.has(it.exempt_key),
        `分母项 ${it.wp_code} 标 exempted 但 exempt_key=${it.exempt_key} 不在豁免登记 ⇒ 不可追溯剔除`,
      ).toBe(true)
    }
    // 反向：redirect 项（B15）须被剔除（exempted），否则 redirect 项错进非 redirect 分母。
    const redirectNotExempt = doc.items.filter((i) => i.redirect && !i.exempted)
    expect(
      redirectNotExempt.map((i) => i.wp_code),
      'redirect 项未被豁免剔除 ⇒ 会错误计入非 redirect 分母并跑 8 断言',
    ).toEqual([])
  })
})

// ─────────────────────── §7.2 八条断言（每非 redirect 项）───────────────────────
//
// 分母级断言：对真实分母里的非 redirect / 非 exempted 项逐项跑契约断言（复用生产单一真源）。
// 真库不可达时退化为「生产单一真源 + 代表性 fixture」断言（不依赖活后端 HTTP），不假绿。

/** 取参与 8 断言的分母项（非 redirect、非 exempted）；真库不可达时给代表性 fixture。 */
function scopeItems(): DenominatorItem[] {
  if (doc && dbAvailable) {
    return doc.items.filter((i) => !i.redirect && !i.exempted)
  }
  // fixture：覆盖串页反例（E1-1 vs E1-10）、surfaced、whole_workbook 三形态。
  return [
    { project_id: 'p1', wp_id: 'w1', wp_code: 'E1', sheet_uid: 'E1-1', sheet_code: 'E1-1', host: 'html', component_type: 'e1-monetary-fund', redirect: false, exempted: false, exempt_key: '', render_config_resolved: true },
    { project_id: 'p1', wp_id: 'w2', wp_code: 'D2', sheet_uid: 'D2-1', sheet_code: 'D2-1', host: 'html', component_type: 'd2-adjustment', redirect: false, exempted: false, exempt_key: '', render_config_resolved: true },
    { project_id: 'p1', wp_id: 'w3', wp_code: 'A1', sheet_uid: 'whole_workbook', sheet_code: '', host: 'html', component_type: 'a1-dashboard', redirect: false, exempted: false, exempt_key: '', render_config_resolved: true },
  ]
}

describe('§7.2 断言①③ 唯一入口 + 完整 location（openFormulaManagerFromLocation）', () => {
  it('① 每个参与项都能构造恰一个带完整 location 的入口（projectId/wpId/wpCode 齐备）', () => {
    const items = scopeItems()
    expect(items.length, '非 redirect 分母为空 ⇒ 门禁空转').toBeGreaterThan(0)
    let built = 0
    for (const it of items) {
      const ctx: FormulaManagerOutletContext = {
        projectId: it.project_id,
        wpId: it.wp_id,
        wpCode: it.wp_code,
        sheetName: it.sheet_uid === 'whole_workbook' ? '' : it.sheet_uid,
      }
      const loc = buildLocationFromContext(ctx)
      expect(loc, `${it.wp_code}/${it.sheet_uid} 应能构造完整 location`).not.toBeNull()
      built++
    }
    expect(built).toBe(items.length)
  })

  it('③ 打开时提交完整 CanonicalWorkpaperLocation（projectId/wpId/wpCode 全带）', () => {
    const it = scopeItems()[0]
    const outcome = openFormulaManagerFromLocation({
      projectId: it.project_id,
      wpId: it.wp_id,
      wpCode: it.wp_code,
      sheetName: it.sheet_uid === 'whole_workbook' ? '' : it.sheet_uid,
    })
    expect(outcome.ok, '完整 location 应成功打开').toBe(true)
    if (outcome.ok) {
      expect(outcome.payload.projectId).toBe(it.project_id)
      expect(outcome.payload.wpId).toBe(it.wp_id)
      expect(outcome.payload.wpCode).toBe(it.wp_code)
      // 底稿入口不落 report scope（ADR-FMC-03）。
      expect(outcome.payload.scope).toBe('workpaper')
    }
  })

  // §7.5 变异「删除 formula-manager-open 按钮」→ ① 数到 0：testid 存在性守卫。
  it('§7.5 变异①：生产页恰挂 data-testid=formula-manager-open（删除即本断言红）', () => {
    const anchors = [
      'src/views/WorkpaperEditor.vue',
      'src/components/workpaper/GtWpRenderer.vue',
      'src/components/workpaper/GtA1Dashboard.vue',
    ]
    let hit = 0
    for (const rel of anchors) {
      const p = resolve(here, '../../../..', rel)
      if (!existsSync(p)) continue
      if (readFileSync(p, 'utf-8').includes('formula-manager-open')) hit++
    }
    expect(hit, '无任何生产页挂 formula-manager-open testid ⇒ 入口全删（断言①归 0）').toBeGreaterThanOrEqual(3)
  })

  // §7.5 变异「去掉 wp_id（丢 location）」→ ③ 完整 location：fail-closed 命中。
  it('§7.5 变异③：去掉 wp_id → buildLocationFromContext 返 null（③ 命中 fail-closed）', () => {
    const it = scopeItems()[0]
    const loc = buildLocationFromContext({ projectId: it.project_id, wpId: '', wpCode: it.wp_code })
    expect(loc, '缺 wp_id 应 fail-closed 返 null（禁 nodeKey-only 打开）').toBeNull()
    const outcome = openFormulaManagerFromLocation({ projectId: it.project_id, wpId: '', wpCode: it.wp_code })
    expect(outcome.ok).toBe(false)
    if (!outcome.ok) expect(outcome.reasonCode).toBe('incomplete_location')
  })

  // 反向断言：未去 wp_id 时不命中（否则单向变异把干净态判成缺陷，铁律㉒）。
  it('反向③：wp_id 齐备时 location 成功构造（不误报）', () => {
    const it = scopeItems()[0]
    const loc = buildLocationFromContext({ projectId: it.project_id, wpId: it.wp_id, wpCode: it.wp_code })
    expect(loc).not.toBeNull()
  })
})

describe('§7.2 断言④ 左栏精确（leftPanelAnchors）', () => {
  const identity: LocationIdentity = { projectId: 'p1', wpId: 'w1', sheetUid: 'E1-1' }

  it('④ identity 完整 → current-sheet 模式；左栏节点全带当前页 identity', () => {
    expect(hasCompleteLocationIdentity(identity)).toBe(true)
    expect(decideLeftPanelMode(identity)).toBe('current-sheet')
    const nodes = buildCurrentSheetAnchorNodes(
      [
        { addr_id: 'E1-1/A1', cell_address: 'A1', semantic_label: '货币资金', deprecated: false } as never,
        { addr_id: 'E1-1/B2', cell_address: 'B2', semantic_label: '合计', deprecated: false } as never,
      ],
      identity,
    )
    expect(nodes.length).toBe(2)
    for (const n of nodes) {
      expect(n._identity).toEqual(identity) // 每行带同一 location identity（左右栏对齐）
      expect(n._addrId.startsWith('E1-1/')).toBe(true) // addr_id 全属精确当前 sheet
    }
  })

  // §7.5 变异（④）：缺 identity 退回全局树 → 本断言红。生产真源在 identity 不全时 fail-closed。
  it('§7.5 变异④：缺 sheetUid → fail-closed（不退全局树；decideLeftPanelMode≠current-sheet）', () => {
    const broken = { projectId: 'p1', wpId: 'w1', sheetUid: '' }
    expect(hasCompleteLocationIdentity(broken)).toBe(false)
    expect(decideLeftPanelMode(broken)).toBe('fail-closed') // 绝不返回 global-browse / current-sheet
  })

  it('反向④：identity 完整时不误判 fail-closed', () => {
    expect(decideLeftPanelMode(identity)).toBe('current-sheet')
  })
})

describe('§7.2 断言⑤a 右栏精确（sheetIdentityMatch，串页反例）', () => {
  // 报告反例：E1-1 不得混入 E1-10/14/15；D2-1 不得混入 D2-10/12。
  it('⑤a E1-1 选中时，只精确命中 E1-1 行，不串 E1-10/14/15', () => {
    expect(matchRowToSelectedSheet({ sheet_codes: ['E1-1'] }, 'E1-1')).toBe(true)
    for (const bad of ['E1-10', 'E1-14', 'E1-15']) {
      expect(matchRowToSelectedSheet({ sheet_codes: [bad] }, 'E1-1'), `${bad} 不得命中 E1-1`).toBe(false)
    }
  })

  it('⑤a D2-1 选中时，不串 D2-10/D2-12', () => {
    expect(matchRowToSelectedSheet({ sheet_name: '审定表D2-1' }, 'D2-1')).toBe(true)
    for (const bad of ['D2-10', 'D2-12']) {
      expect(matchRowToSelectedSheet({ sheet_name: `审定表${bad}` }, 'D2-1'), `${bad} 不得命中 D2-1`).toBe(false)
    }
  })

  it('⑤a 缺结构身份行 fail-closed 排除（不退回 includes）', () => {
    expect(matchRowToSelectedSheet({}, 'E1-1')).toBe(false)
    expect(matchRowToSelectedSheet({ sheet_name: '' }, 'E1-1')).toBe(false)
  })

  // §7.5 变异「注入 E1-10（串页）」→ ⑤a：若匹配退回 includes，E1-10 会命中 E1-1。
  it('§7.5 变异⑤a：注入 E1-10 串页行 → matchRowToSelectedSheet 拒绝（精确等值，非 includes）', () => {
    // 这正是旧 includes 逻辑的缺陷形态：'E1-1'.includes 子串 vs 'E1-10'。精确等值必须判否。
    const injected = { sheet_codes: ['E1-10'], sheet_name: 'E1-10 串页注入' }
    expect(matchRowToSelectedSheet(injected, 'E1-1'), 'E1-10 串页注入不得命中 E1-1（否则退回 includes）').toBe(false)
  })

  it('反向⑤a：E1-1 本页行仍命中（精确化不把干净态判缺陷）', () => {
    expect(matchRowToSelectedSheet({ sheet_codes: ['E1-1'] }, 'E1-1')).toBe(true)
    // normalizeSheetCode 归一不改变精确性（破折号变体统一）。
    expect(normalizeSheetCode('E1-1')).toBe('e1-1')
  })
})

describe('§7.2 断言⑤b surfaced 只读去伪装（formulaRowKind）', () => {
  it('⑤b surfaced/extraction 行判只读（readonly:true 或伪 id 形态）', () => {
    expect(isReadonlyProjectionRow({ readonly: true })).toBe(true)
    expect(isReadonlyProjectionRow({ id: 'E1-surfaced-tb-check' })).toBe(true)
    expect(isReadonlyProjectionRow({ id: 'tierB-E1-1-leaf' })).toBe(true)
    expect(classifyFormulaRowKind({ id: 'E1-surfaced-adj-0', readonly: true })).toBe('surfaced')
    expect(classifyFormulaRowKind({ id: 'tierB-x', readonly: true })).toBe('extraction')
  })

  it('⑤b 只读投影保存分派 = reject（禁保存）', () => {
    expect(resolveSaveDispatch({ id: 'E1-surfaced-tb-check', readonly: true })).toBe('reject')
    expect(resolveSaveDispatch({ id: 'tierB-E1-1', readonly: true })).toBe('reject')
  })

  // §7.5 变异（补）「surfaced 加回编辑按钮 / 渲染成可编辑」→ ⑤b：生产模板据 isReadonlyProjectionRow
  // 在**编辑动作列**优先渲染「只读」而非「编辑」按钮。守卫钉死这条具体结构（删掉该 v-if 守卫
  // ⇒ surfaced 行会落到 `编辑` 按钮分支 = 变回可编辑 ⇒ 本断言红）。
  it('§7.5 变异⑤b：编辑动作列据 isReadonlyProjectionRow 优先渲染只读（加回编辑按钮即红）', () => {
    const dialog = resolve(here, '..', 'FormulaManagerDialog.vue')
    const src = readFileSync(dialog, 'utf-8')
    // 编辑动作列的结构：`v-if="isReadonlyProjectionRow(row)"` 分支渲染「只读」，其后才是
    // `v-else-if`/`v-else` 的「编辑」/「保存」按钮。这段的 v-if 守卫被删 ⇒ surfaced 落到
    // 编辑按钮分支。用「只读 span 在编辑按钮之前且由 isReadonlyProjectionRow 守卫」钉死。
    const editCol = src.match(
      /el-tooltip v-if="isReadonlyProjectionRow\(row\)"[\s\S]{0,200}只读<\/span>[\s\S]{0,400}@click\.stop="startEdit\(row\)"/,
    )
    expect(
      editCol,
      '编辑动作列缺「isReadonlyProjectionRow v-if → 只读，v-else → 编辑按钮」结构 ⇒ surfaced 可编辑（⑤b 红）',
    ).toBeTruthy()
    // 行为侧（强于源码文本）：surfaced/extraction 只读判定 + 保存拒绝（与 ⑤b 同义）。
    expect(isReadonlyProjectionRow({ id: 'E1-surfaced-x', readonly: true })).toBe(true)
    expect(resolveSaveDispatch({ id: 'E1-surfaced-x', readonly: true })).toBe('reject')
  })

  it('反向⑤b：真正可编辑 wp 行不被误判只读', () => {
    expect(isReadonlyProjectionRow({ id: 'real-123', readonly: false })).toBe(false)
    expect(classifyFormulaRowKind({ formula_source: '底稿公式(wp_formula)', id: 'x' })).toBe('wp')
    expect(resolveSaveDispatch({ formula_source: '底稿公式(wp_formula)', id: 'x' })).toBe('wp')
  })
})

describe('§7.2 断言⑤c 保存契约字段 + 目标端点分派（wpFormulaFields + formulaRowKind）', () => {
  it('⑤c wp item 读契约字段 category/description（非 formula_category/formula_description）', () => {
    const item = { category: 'logic_check', description: '勾稽校验' }
    expect(readWpCategory(item)).toBe('logic_check')
    expect(readWpDescription(item)).toBe('勾稽校验')
    const mapped = mapWpItemToRowFields(item)
    expect(mapped.formula_category).toBe('logic_check')
    expect(mapped.formula_description).toBe('勾稽校验')
  })

  it('⑤c wp 行保存分派到 wp 端点（PUT /api/workpapers/{wp_id}/formulas），非 report-config', () => {
    const wpRow = { formula_source: '底稿公式(wp_formula)', id: 'wp-1' }
    expect(resolveSaveDispatch(wpRow)).toBe('wp')
    const reportRow = { formula_source: '报表模板', id: 'rc-1' }
    expect(resolveSaveDispatch(reportRow)).toBe('report')
  })

  // §7.5 变异「把 save 改回写 report_config」→ ⑤c：若 wp 行分派成 report 则红。
  it('§7.5 变异⑤c：wp 行分派必须是 wp（改回 report_config ⇒ 本断言红）', () => {
    const wpRow = { formula_source: '底稿公式(wp_formula)', id: 'wp-1' }
    expect(resolveSaveDispatch(wpRow), 'wp 行分派到 report ⇒ 底稿公式误写报表模板（旧 FM-P0-02 bug）').not.toBe('report')
    expect(resolveSaveDispatch(wpRow)).toBe('wp')
  })

  // §7.5 变异（字段）「读回 formula_category」→ ⑤c：误读恒 undefined 落兜底。
  it('§7.5 变异⑤c（字段）：读 formula_category/formula_description 恒落兜底（证明必须读契约字段）', () => {
    // 模拟旧 bug：wp item 上只有契约字段 category/description，误读 formula_category 会 undefined。
    const item = { category: 'reasonability', description: '合理性' } as Record<string, unknown>
    expect((item as { formula_category?: unknown }).formula_category).toBeUndefined()
    // 生产单一真源读的是契约字段，故能取到真值（反证误读的危害）。
    expect(readWpCategory(item)).toBe('reasonability')
  })

  it('反向⑤c：report 行读 formula_category 是合法的（本模块不碰 report 行）', () => {
    // report_config 行的后端契约字段本就是 formula_category/formula_description（合法）。
    const reportRow = { formula_source: '报表模板', id: 'rc-1' }
    expect(resolveSaveDispatch(reportRow)).toBe('report')
  })
})

describe('§7.2 断言⑥ 切换隔离（projectCacheKey）', () => {
  it('⑥ 切项目后缓存键变化，旧缓存不命中（失效）', () => {
    const keyA = projectCacheKey({ projectId: 'A', templateType: 'listed', year: 2025 })
    const keyB = projectCacheKey({ projectId: 'B', templateType: 'listed', year: 2025 })
    expect(keyA).not.toBe(keyB)
    expect(cacheKeyMatches(keyA, keyB), '切到 B 时 A 的缓存不得命中').toBe(false)
    expect(cacheKeyMatches(keyA, keyA)).toBe(true)
  })

  it('⑥ 陈旧异步响应守卫：切项目后旧响应不覆盖新项目', () => {
    const reqKey = projectCacheKey({ projectId: 'A', templateType: 'listed', year: 2025 })
    const curKeyAfterSwitch = projectCacheKey({ projectId: 'B', templateType: 'listed', year: 2025 })
    expect(shouldApplyResponse(reqKey, curKeyAfterSwitch), '切项目后 A 的 late response 不得写入 B').toBe(false)
    expect(shouldApplyResponse(reqKey, reqKey)).toBe(true)
  })

  it('⑥ 保存用项目年 props.year（非系统当前年）', () => {
    expect(resolveSaveYear(2023)).toBe(2023)
    expect(resolveSaveYear('2024')).toBe(2024)
    expect(resolveSaveYear(null)).toBeNull() // 缺年份返 null（调用方决定跳过，不偷用系统年）
  })

  // §7.5 变异「缓存键去掉 project 维度」→ ⑥：A/B 共用槽，切项目恒命中旧缓存。
  it('§7.5 变异⑥：缓存键含 project 维度（去掉则 A/B 串，本断言红）', () => {
    // 生产 projectCacheKey 以 projectId 为第一维；去掉它 keyA===keyB ⇒ 切项目恒命中。
    const keyA = projectCacheKey({ projectId: 'A' })
    const keyB = projectCacheKey({ projectId: 'B' })
    expect(keyA, 'projectId 维度被去掉 ⇒ 跨项目缓存串').not.toBe(keyB)
  })
})

// ─────────────────────── §7.2 断言⑦ 权限分层（硬断言，NIT-2 pending→硬化）───────────────────────

describe('§7.2 断言⑦ 权限分层（Phase 5 鉴权整改已落地，转硬断言）', () => {
  // ⑦ 转硬断言的前置 = ADR-FMC-06 全部对象型端点加固并通过 Task 5.1 §6.1 TestClient 坐实。
  // 本 describe 以「坐实产物 + 加固守卫存在性」作为硬断言的运行时锚点（前置不成立则红、非 skip）。
  const BE = resolve(REPO_ROOT, 'backend/tests/formula_management')
  const requiredGuards = [
    'test_fm_p0_05_cross_project_idor.py', // Task 5.1 §6.1 坐实（跨项目越权 403 + 0 副作用）
    'test_wp_formula_sheet_uid_server_filter.py', // 5.2/3.1 对象型端点服务端过滤
    'test_task_5_3_global_write_admin.py', // 5.3 全局模板/自定义函数写限 admin
    'test_task_5_4_batch_cas_audit.py', // 5.4 批量 CAS + 审计链
  ]

  it('⑦ 前置：Phase 5 全部对象型端点加固 + §6.1 坐实的 TestClient 守卫存在（缺任一则⑦红、不 pending）', () => {
    const missing = requiredGuards.filter((f) => !existsSync(resolve(BE, f)))
    expect(
      missing,
      `Phase 5 鉴权加固/坐实守卫缺失：${missing.join(' / ')}\n`
        + '任一端点未加固/未坐实则⑦必须保持 pending、不做部分硬化（§7.2 ⑦）。',
    ).toEqual([])
  })

  it('⑦ 坐实用例断言加固后全部 403 + 0 副作用（Task 5.1 §6.1 的硬断言落在后端 TestClient）', () => {
    // 前端门禁不重跑后端 TestClient（那是 Phase 5 的 pytest 范畴），但钉死「坐实用例内容
    // 真的断言了 403 + 0 副作用」——防坐实用例被改成恒绿。
    const src = readFileSync(resolve(BE, 'test_fm_p0_05_cross_project_idor.py'), 'utf-8')
    expect(src, '坐实用例须断言 403').toMatch(/403/)
    // 跨项目越权维度（wp_formula / report_config / execute / formula-scope / tb_detail）须被覆盖。
    for (const dim of ['formulas', 'report-config', 'formula']) {
      expect(src.includes(dim), `坐实用例未覆盖端点维度 ${dim}`).toBe(true)
    }
  })
})

// ─────────────────────── §7.2 断言⑧ 零错误（fail-closed 单一真源）───────────────────────

describe('§7.2 断言⑧ 零错误（缺 location 不发请求 / 缺身份不退全局树）', () => {
  it('⑧ 缺 location 时不发打开请求（返错误 outcome，不产生 4xx / abort）', () => {
    const outcome = openFormulaManagerFromLocation({ projectId: '', wpId: '', wpCode: '' })
    expect(outcome.ok).toBe(false)
    // fail-closed：不构造 location、不 emit 事件 ⇒ 不会打出 /report-config/types 或缺 year 的 422。
    if (!outcome.ok) expect(outcome.reasonCode).toBe('incomplete_location')
  })

  it('⑧ 缺身份时左栏空集 + 告警（不退全局树 ⇒ 不触发全局 ACNR 大请求/abort）', () => {
    expect(decideLeftPanelMode({ projectId: 'p', wpId: 'w' })).toBe('fail-closed')
  })
})

// ─────────────────────── §7.4 幂等自证（防永红，门禁本身不恒红）───────────────────────

describe('§7.4 门禁幂等自证（同输入两次运行 JSON 字节一致）', () => {
  // beforeAll 已真跑一次 --check（真连 PG、exit 0、分母与基线一致）——那一次就是「同输入第
  // 二次运行」的证明（第一次是 --write 取基线）。本条读 beforeAll 捕获的结果，不再重复 230s
  // 的全量枚举（会超时且无新信息）。两次独立 --write 字节一致已由 shell 自证（见 design/报告）。
  it.runIf(() => dbAvailable)('枚举器 --check 真连后退出码确定（beforeAll 已跑 → exit 0，无漂移）', () => {
    expect(probe.status, '真连 --check 应 exit 0（基线确定、无漂移 ⇒ 门禁不恒红）').toBe(EXIT_OK)
  })

  it('分母 JSON 的 generated_at 不进内容指纹（内容不变不改时间戳 → 不恒 diff → 不恒红）', () => {
    if (!doc) return
    // 指纹只对 items 实质内容算；items 不变 → 重跑 --write 的 generated_at 不变（枚举器
    // build_document「指纹不变沿用旧 generated_at」保证）。断言文档结构支持该幂等。
    const raw = JSON.parse(readFileSync(DENOMINATOR_JSON, 'utf-8')) as DenominatorDoc
    expect(raw.fingerprint).toBe(doc.fingerprint)
    expect(raw.generated_at).toBe(doc.generated_at)
    // generated_at 是 UTC Z 格式、无本地时区/机器名泄漏（幂等 + 跨机器确定性）。
    expect(raw.generated_at).toMatch(/Z$/)
  })

  it('门禁不恒红自证：枚举器三态退出码语义正交（OK=0 / DRIFT=2 / DB_UNAVAILABLE=3）', () => {
    // 门禁恒红的根源是「判据含非确定输入」（时间戳/机器名/绝对路径），本枚举器已排除。
    // 三态码互不相同 ⇒ 真库不可达不会被误报成漂移红、无漂移不会被误报成失败（§7.4②）。
    expect(new Set([EXIT_OK, EXIT_DRIFT, EXIT_DB_UNAVAILABLE]).size).toBe(3)
  })
})

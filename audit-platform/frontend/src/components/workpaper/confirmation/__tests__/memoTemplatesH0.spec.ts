/**
 * memoTemplatesH0.spec.ts — H0-3 跟函话术与核对点守卫
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 9.1~9.6；Property 24
 *
 * 源模板文字的逐字比对在
 * `backend/tests/test_h0_source_template_facts.py::test_h0_3_memo_mentions_escort_and_staff_no`
 * 与 `::test_h0_3_three_checkpoints_and_signature`；本文件负责模板/场景/占位符自洽性，
 * 以及 **E0 银行五段话术逐字节不变**（零回归支点）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  BANK_ALL_RESPONDED_TPL,
  BANK_COUNTER_TPL,
  BANK_DEPARTMENT_TPL,
  BANK_LATER_RECEIVED_TPL,
  BANK_LEAVE_TPL,
  IMMEDIATE_CONFIRM_TPL,
  LATER_FOLLOW_TPL,
  LATER_RECEIVED_TPL,
  THIRD_PARTY_CALLBACK_TPL,
  getTemplate,
  scenariosFor,
} from '../followup/memoTemplates'
import { FOLLOWUP_CONTROL_CHECKPOINTS } from '../followup/followupEnums'
import { useMemoCompose } from '../followup/composables/useMemoCompose'
import type { FollowupRow } from '../followup/followupTypes'

function findRepoRoot(from: string): string {
  let dir = from
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(dir, 'backend', 'app', 'routers', 'system_dicts.py'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能定位仓库根（从 ${from}）`)
}
const REPO_ROOT = findRepoRoot(__dirname)
const FU_DIR = path.join(
  REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper', 'confirmation', 'followup',
)

/** 抽模板里的占位符 */
function placeholders(tpl: string): string[] {
  return [...tpl.matchAll(/〔(\w+)〕/g)].map((m) => m[1])
}

// ─── Property 24: 通用话术补齐源模板要素 ────────────────────────────────────

describe('Property 24: 通用话术含陪同情况与工号', () => {
  it('即时确认话术含陪同情况占位（源模板 A10 的关键舞弊防范要素）', () => {
    expect(placeholders(IMMEDIATE_CONFIRM_TPL)).toContain('escort_desc')
  })

  it('即时确认话术含工号占位（源模板 A13「工号为[XX]（如有）」）', () => {
    expect(placeholders(IMMEDIATE_CONFIRM_TPL)).toContain('confirm_staff_no')
    expect(IMMEDIATE_CONFIRM_TPL).toContain('工号')
  })

  it('留函话术同样含陪同情况与工号（源模板 A15/A17）', () => {
    const ph = placeholders(LATER_FOLLOW_TPL)
    expect(ph).toContain('escort_desc')
    expect(ph).toContain('leave_staff_no')
    expect(LATER_FOLLOW_TPL).toContain('工号')
  })

  it('两段通用话术都含跟函人员占位（备忘录主语，源模板「审计项目组成员[XXX…]」）', () => {
    expect(placeholders(IMMEDIATE_CONFIRM_TPL)).toContain('followup_staff')
    expect(placeholders(LATER_FOLLOW_TPL)).toContain('followup_staff')
  })
})

describe('Property 24: 第三方回访段（源模板 A18/A19）', () => {
  it('是独立可取用的场景', () => {
    expect(scenariosFor()).toContain('third_party_callback')
    expect(getTemplate('third_party_callback', { cycle: null })).toBe(THIRD_PARTY_CALLBACK_TPL)
  })

  it('话术含「对外公开电话」与「接待」两个关键判据', () => {
    expect(THIRD_PARTY_CALLBACK_TPL).toContain('对外公开电话')
    expect(THIRD_PARTY_CALLBACK_TPL).toContain('接待')
    expect(THIRD_PARTY_CALLBACK_TPL).toContain('独立公开来源')
  })

  it('占位符齐备（回访人/日期/电话/结果）', () => {
    const ph = placeholders(THIRD_PARTY_CALLBACK_TPL)
    for (const f of ['callback_staff', 'callback_date', 'callback_phone', 'callback_result']) {
      expect(ph, `缺占位符 ${f}`).toContain(f)
    }
  })
})

// ─── 占位符必须在 FIELD_LABELS 与 FollowupRow 中登记 ────────────────────────

describe('占位符可追溯', () => {
  const composeSrc = fs.readFileSync(path.join(FU_DIR, 'composables', 'useMemoCompose.ts'), 'utf-8')
  const typesSrc = fs.readFileSync(path.join(FU_DIR, 'followupTypes.ts'), 'utf-8')

  const allPh = new Set([
    ...placeholders(IMMEDIATE_CONFIRM_TPL),
    ...placeholders(LATER_FOLLOW_TPL),
    ...placeholders(LATER_RECEIVED_TPL),
    ...placeholders(THIRD_PARTY_CALLBACK_TPL),
  ])

  it('每个占位符都在 FIELD_LABELS 有中文标签（缺失会在 UI 显示英文字段名）', () => {
    for (const f of allPh) {
      expect(new RegExp(`\\b${f}:\\s*'`).test(composeSrc), `FIELD_LABELS 缺 ${f}`).toBe(true)
    }
  })

  it('每个占位符都是 FollowupRow 的 optional 字段', () => {
    for (const f of allPh) {
      expect(new RegExp(`\\b${f}\\?:`).test(typesSrc), `FollowupRow 缺 optional 字段 ${f}`).toBe(true)
    }
  })

  it('compose 对缺失占位符回填中文标签而非留英文（missingFields 可提示）', () => {
    const { compose } = useMemoCompose()
    const row: FollowupRow = { scenario: 'immediate', entity_name: '甲公司' }
    const { text, missingFields } = compose(row)
    expect(text).toContain('甲公司')
    expect(text).not.toMatch(/〔[a-z_]+〕/) // 不得残留英文占位符
    expect(missingFields).toContain('陪同情况')
    expect(missingFields).toContain('处理人工号')
  })
})

// ─── Property 24: E0 银行五段话术零回归 ─────────────────────────────────────

describe('Property 24: E0 银行话术逐字节不变（零回归支点）', () => {
  const E0_SCENARIOS = [
    'bank_counter', 'bank_department', 'bank_leave',
    'bank_all_responded', 'bank_later_received',
  ] as const

  it('scenariosFor(E0) 仍是五段银行话术', () => {
    expect(scenariosFor('E0')).toEqual([...E0_SCENARIOS])
  })

  it('五段话术内容未被改动（含工号/公示等银行专属概念）', () => {
    expect(BANK_COUNTER_TPL).toContain('对公柜台')
    expect(BANK_COUNTER_TPL).toContain('工号为〔bank_staff_no〕')
    expect(BANK_DEPARTMENT_TPL).toContain('对公柜台不办理函证业务')
    expect(BANK_LEAVE_TPL).toContain('无法即时确认询证函所列各项内容')
    expect(BANK_ALL_RESPONDED_TPL).toContain('银行管理制度及公示内容一致')
    expect(BANK_LATER_RECEIVED_TPL).toContain('寄回致同会计师事务所')
  })

  it('getTemplate 对 E0 五场景逐一返回对应模板', () => {
    const map: Record<string, string> = {
      bank_counter: BANK_COUNTER_TPL,
      bank_department: BANK_DEPARTMENT_TPL,
      bank_leave: BANK_LEAVE_TPL,
      bank_all_responded: BANK_ALL_RESPONDED_TPL,
      bank_later_received: BANK_LATER_RECEIVED_TPL,
    }
    for (const s of E0_SCENARIOS) {
      expect(getTemplate(s, { cycle: 'E0' })).toBe(map[s])
    }
  })

  it('旧签名（第二参为布尔）行为不变：immediate + laterReceived 拼接补记段', () => {
    expect(getTemplate('immediate')).toBe(IMMEDIATE_CONFIRM_TPL)
    expect(getTemplate('immediate', true)).toBe(IMMEDIATE_CONFIRM_TPL + LATER_RECEIVED_TPL)
    expect(getTemplate('later_follow', false)).toBe(LATER_FOLLOW_TPL)
  })
})

// ─── Property 24: 三核对点标签逐字源模板 ────────────────────────────────────

describe('Property 24: 三项核对点（源模板 X0-3 A23:A25）', () => {
  it('标签逐字取源模板（含「和处理人员」「及权限」两层语义）', () => {
    expect(FOLLOWUP_CONTROL_CHECKPOINTS.map((c) => c.label)).toEqual([
      '是否了解处理函证的通常流程和处理人员',
      '是否确认询证函处理人员的身份及权限',
      '处理人员是否按正常流程处理',
    ])
  })

  it('锚点为 A23/A24/A25', () => {
    expect(FOLLOWUP_CONTROL_CHECKPOINTS.map((c) => c.anchor)).toEqual(['A23', 'A24', 'A25'])
  })

  it('字段名与 FollowupRow 既有字段一致（不新造字段，零数据迁移）', () => {
    expect(FOLLOWUP_CONTROL_CHECKPOINTS.map((c) => c.field)).toEqual([
      'control_process', 'control_identity', 'control_normal_flow',
    ])
  })

  it('每条都有判断提示（hint）', () => {
    for (const c of FOLLOWUP_CONTROL_CHECKPOINTS) {
      expect(c.hint.length).toBeGreaterThan(10)
    }
  })

  it('UI 引用常量而非内联意译标签（防漂移）', () => {
    const detail = fs.readFileSync(path.join(FU_DIR, 'FollowupDetail.vue'), 'utf-8')
    expect(detail).toContain('FOLLOWUP_CONTROL_CHECKPOINTS')
    // 改造前的意译短标签不得复活
    expect(detail).not.toContain('>了解处理流程<')
    expect(detail).not.toContain('>确认身份权限<')
    expect(detail).not.toContain('>按正常流程处理<')
  })

  it('三核对点仍为点选（是/否/不适用），不是自由文本', () => {
    const detail = fs.readFileSync(path.join(FU_DIR, 'FollowupDetail.vue'), 'utf-8')
    // 🔴 定位 v-for 渲染点，而不是 indexOf('CONTROL_CHECKPOINTS')
    //    —— 后者会命中注释里提到的常量名（首版即因此取到注释块）
    const idx = detail.indexOf('v-for="cp in CONTROL_CHECKPOINTS"')
    expect(idx, '未找到三核对点的 v-for 渲染点').toBeGreaterThan(-1)
    const block = detail.slice(idx, idx + 900)
    expect(block).toContain('el-select')
    expect(block).toContain('value="na"')
  })
})

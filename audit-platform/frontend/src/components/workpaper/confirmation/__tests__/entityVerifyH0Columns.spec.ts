/**
 * entityVerifyH0Columns.spec.ts — H0-2 补列守卫
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 8.1~8.6；Property 23
 *
 * 源模板列名/列位的逐字比对在
 * `backend/tests/test_h0_source_template_facts.py::test_h0_2_second_send_block`；
 * 本文件负责字段可选性、无 `undefined` 键、条件展开、枚举绑定与说明文字齐备。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import type { EntityVerifyRow } from '../entityVerify/entityVerifyTypes'
import { CONFIRMATION_DICTS, fallbackOptions } from '../coordination/confirmationDicts'

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
const EV_DIR = path.join(
  REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper', 'confirmation', 'entityVerify',
)

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

const TYPES_SRC = fs.readFileSync(path.join(EV_DIR, 'entityVerifyTypes.ts'), 'utf-8')
const DETAIL_RAW = fs.readFileSync(path.join(EV_DIR, 'EntityVerifyDetail.vue'), 'utf-8')
const DETAIL_SRC = stripComments(DETAIL_RAW)

/** 源模板 X0-2 AF6:AK6 六列 → 平台字段 */
const SECOND_SEND_FIELDS = [
  'second_entity_address',
  'second_entity_zipcode',
  'second_contact_person',
  'second_contact_phone',
  'second_fax',
  'second_info_verified',
] as const

/** 被审计单位提供侧缺列（源模板 E6 / H6） */
const PROVIDED_FIELDS = ['provided_zipcode', 'provided_email_fax'] as const

// ─── Property 23: 8 字段齐备且全为 optional ─────────────────────────────────

describe('Property 23: H0-2 补列齐备且 optional', () => {
  it.each([...SECOND_SEND_FIELDS, ...PROVIDED_FIELDS])('%s 已声明且为 optional', (field) => {
    const m = new RegExp(`\\b${field}\\?:`).test(TYPES_SRC)
    expect(m, `${field} 未声明或不是 optional（旧载荷读回必须为 undefined）`).toBe(true)
  })

  it('8 个字段各带源模板锚点注释（可追溯）', () => {
    for (const field of [...SECOND_SEND_FIELDS, ...PROVIDED_FIELDS]) {
      const idx = TYPES_SRC.indexOf(`${field}?:`)
      expect(idx).toBeGreaterThan(-1)
      const before = TYPES_SRC.slice(Math.max(0, idx - 260), idx)
      expect(before, `${field} 缺源模板锚点注释`).toMatch(/X0-2|源模板/)
    }
  })

  it('旧 entity-verify-v1 载荷读回时新字段为 undefined，写回不产生 undefined 键', () => {
    const legacy: EntityVerifyRow = {
      _row_id: 'r1',
      confirm_index: 'H0-001',
      entity_name: '甲公司',
      first_result: '退回',
      is_second_send: true,
    }
    for (const f of [...SECOND_SEND_FIELDS, ...PROVIDED_FIELDS]) {
      expect((legacy as Record<string, unknown>)[f]).toBeUndefined()
    }
    // 展开保存后 JSON 里不出现这些键（undefined 不被 JSON.stringify 序列化）
    const saved = JSON.parse(JSON.stringify({ ...legacy }))
    for (const f of [...SECOND_SEND_FIELDS, ...PROVIDED_FIELDS]) {
      expect(Object.prototype.hasOwnProperty.call(saved, f)).toBe(false)
    }
    // 既有字段一字不变
    expect(saved.entity_name).toBe('甲公司')
    expect(saved.is_second_send).toBe(true)
  })

  it('提供侧邮编/邮箱传真与企查查侧是两组独立字段（不复用）', () => {
    expect(TYPES_SRC).toMatch(/\bqcc_zipcode\?:/)
    expect(TYPES_SRC).toMatch(/\bqcc_email_fax\?:/)
    expect(TYPES_SRC).toMatch(/\bprovided_zipcode\?:/)
    expect(TYPES_SRC).toMatch(/\bprovided_email_fax\?:/)
  })
})

// ─── Property 23: 渲染与条件展开 ────────────────────────────────────────────

describe('Property 23: H0-2 详情面板渲染', () => {
  it('六列均有录入控件并绑定 emitUpdate', () => {
    for (const f of SECOND_SEND_FIELDS) {
      expect(DETAIL_SRC, `${f} 无录入控件`).toContain(`row.${f}`)
      expect(DETAIL_SRC, `${f} 未绑定 emitUpdate`).toContain(`emitUpdate('${f}'`)
    }
  })

  it('提供侧两列均有录入控件', () => {
    for (const f of PROVIDED_FIELDS) {
      expect(DETAIL_SRC).toContain(`row.${f}`)
      expect(DETAIL_SRC).toContain(`emitUpdate('${f}'`)
    }
  })

  it('第二次发函列组按 is_second_send 条件展开（在二次发函折叠块内）', () => {
    const start = DETAIL_SRC.indexOf('title="二次发函"')
    expect(start, '未找到二次发函折叠块').toBeGreaterThan(-1)
    const end = DETAIL_SRC.indexOf('</el-collapse-item>', start)
    const block = DETAIL_SRC.slice(start, end)
    for (const f of SECOND_SEND_FIELDS) {
      expect(block, `${f} 不在二次发函折叠块内（不会按条件折叠）`).toContain(`row.${f}`)
    }
    // 该折叠块本身受 is_second_send 控制
    const head = DETAIL_SRC.slice(Math.max(0, start - 200), start)
    expect(head).toContain('row.is_second_send')
  })

  it('第二次发函区块有中文小标题（与首次发函信息区分）', () => {
    expect(DETAIL_SRC).toContain('第二次发函的被函证单位信息')
  })

  it('信息核查一致列是点选（是/否），不是自由文本', () => {
    const idx = DETAIL_SRC.indexOf("emitUpdate('second_info_verified'")
    expect(idx).toBeGreaterThan(-1)
    const around = DETAIL_SRC.slice(Math.max(0, idx - 500), idx + 300)
    expect(around).toContain('el-select')
    expect(around).toContain('label="是"')
    expect(around).toContain('label="否"')
  })
})

// ─── R8.3: 地址核实方式绑定源模板枚举 ───────────────────────────────────────

describe('R8.3: 地址不一致的核实方式绑定枚举', () => {
  it('核实方式改为 el-select 且引用 ADDR_VERIFY 枚举真源', () => {
    expect(DETAIL_SRC).toContain('addrVerifyOptions')
    expect(DETAIL_SRC).toContain('CONFIRMATION_DICTS.ADDR_VERIFY')
    const idx = DETAIL_SRC.indexOf("emitUpdate('address_verify_result'")
    expect(idx).toBeGreaterThan(-1)
    const around = DETAIL_SRC.slice(Math.max(0, idx - 700), idx + 300)
    expect(around).toContain('el-select')
    expect(around).toContain('addrVerifyOptions')
  })

  it('枚举 6 项与源模板 X0-2!L7 一致', () => {
    expect(fallbackOptions(CONFIRMATION_DICTS.ADDR_VERIFY)).toEqual([
      '发票/合同地址核实', '电话核实', '官网/公告查询', '地图查询', '邮件确认', '其他方式',
    ])
  })

  it('保留 allow-create（历史自由文本值仍可显示，不丢数据）', () => {
    const idx = DETAIL_SRC.indexOf("emitUpdate('address_verify_result'")
    const around = DETAIL_SRC.slice(Math.max(0, idx - 700), idx + 300)
    expect(around).toContain('allow-create')
  })
})

// ─── R8.6: 源模板两条审计说明就地展示 ──────────────────────────────────────

describe('R8.6: 源模板审计说明（C25/C26）', () => {
  it('两条说明逐字展示且为只读方法论上下文', () => {
    expect(DETAIL_SRC).toContain('SOURCE_AUDIT_NOTES')
    expect(DETAIL_RAW).toContain(
      '1.采用电子函证方式的无需核对发函地址信息，无需核对回函发出地址、回函寄件人信息等；',
    )
    expect(DETAIL_RAW).toContain(
      '2.采用电子函证方式的应记录并检查回函能够证明电子地址或身份的信息，关注被审计单位、注册会计师和被询证者在电子询证函平台操作的具体时间、回函经办人（如适用）、意见反馈等信息（如适用）',
    )
  })

  it('说明区无录入控件（纯只读）', () => {
    const idx = DETAIL_SRC.indexOf('entity-verify-detail__src-hint')
    expect(idx).toBeGreaterThan(-1)
    const block = DETAIL_SRC.slice(idx, idx + 400)
    expect(block).not.toContain('el-input')
    expect(block).not.toContain('emitUpdate')
  })
})

// ─── 守卫自检 ────────────────────────────────────────────────────────────────

describe('守卫自检', () => {
  it('stripComments 不会把注释里的字段名计入真实代码', () => {
    const sample = "// row.second_fax\n/* emitUpdate('second_fax', v) */\nconst a = 1\n"
    const cleaned = stripComments(sample)
    expect(cleaned).not.toContain('second_fax')
    expect(sample).toContain('second_fax') // 原文确实含被禁字样
  })

  it('DETAIL_SRC 去注释后仍非空且含关键结构（strip 未过度）', () => {
    expect(DETAIL_SRC.length).toBeGreaterThan(3000)
    expect(DETAIL_SRC).toContain('el-collapse')
  })
})

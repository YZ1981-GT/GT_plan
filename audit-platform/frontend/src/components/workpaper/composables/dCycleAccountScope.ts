/**
 * D 循环（销售与收款）科目定位 —— **前端单一真源**，与后端
 * `app/services/d_cycle_extraction/d_account_resolver.py` 的 `D_ACCOUNT_SPECS`
 * 及 `d1_account_resolver.py` 的 D1 参数逐字对称。
 *
 * 改一侧必改另一侧；守卫 `__tests__/dCycleAccountScope.spec.ts` 读后端 py 源码
 * 交叉锁死槽键、报表行号与兜底码。
 *
 * 🔴 **落点有两套并存约定，本模块两层都读**（2026-08-05 实测，design.md 写错了）
 *
 * | 落点 | 循环 |
 * |---|---|
 * | `html_data` **顶层** | D1 / D2 / D3 / D5 / D6 / D7（6 个） |
 * | `html_data.project_context` | **D4 独一个** |
 *
 * design.md 的 Architecture 段按平台惯例写的是 `project_context.*`，与 6 个循环的
 * 实际落点不符。只读一层 ⇒ 恒 `undefined` ⇒ 面板永不渲染，而 `get_diagnostics` /
 * vitest / Vite 200 四层全绿（E1 已实证过同款）。故 :func:`pickDTbSourceCodes`
 * **顶层优先、`project_context` 兼容**，两处都读、不做假设。
 *
 * 🔴 **槽载荷字段名与共享工厂的期望不同，必须先归一**
 *
 * 后端 `SlotAmounts.as_dict()` 的实测键集（见 `d_tb_fetch.py`）::
 *
 *     key / found / state / query_codes / tb_rows_count / prefix_mismatch
 *     opening / closing / debit / credit / convention / parent_diff
 *     dropped / warnings / filter_applied
 *
 * 注意**没有** `codes` / `standard_codes` —— 而共享工厂 `cycleAccountScope` 的
 * `isAccountAbsent()` 在 `found !== false` 时会退到判 `standard_codes`/`codes` 是否
 * 双空，直接喂原始槽会把「有科目、有数据」的槽误判成「本项目无此科目」。
 * 故 :func:`normalizeDSlots` 把 `query_codes` 投影成 `codes` + `standard_codes`
 * 再交给工厂。
 *
 * 🔴 **三态语义**（Requirements 3.1~3.3、Property 10）
 *
 * | 判据 | 语义 | `isAccountAbsent` |
 * |---|---|---|
 * | 槽键不存在（render 未下发） | **未取数（未知）** | `false` —— 未知不等于无 |
 * | `found=false` / `state='no_account'` | 本项目无此科目 | `true` |
 * | `found=true` 且 `closing === null` | 科目表有、四表无数据行 | `false`（科目是有的） |
 * | `found=true` 且 `closing === 0` | **余额确实为 0** | `false` |
 *
 * 「本项目无此科目」（`amount=null`）与「余额为 0」（`amount=0`）必须可区分 ——
 * 禁写 `Number(null) === 0` 这类判定（它会把前者静默变成后者）。
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
 *       Requirements 3.1, 3.2, 3.3, 3.5 / Property 12, 15
 */
import {
  type CycleAccountScope,
  type CycleAccountScopeSpec,
  createCycleAccountScope,
} from './shared/cycleAccountScope'
import type { TbSemanticSlot, TbSourceCodes } from './shared/tbSourceCodes'

/** 后端 `SlotAmounts.state` 的取值域（`d_tb_fetch.SlotAmounts.state`） */
export type DSlotState = 'no_account' | 'no_data' | 'prefix_mismatch' | 'ok'

/** 后端 `SlotAmounts.as_dict()` 的槽载荷形态（字段逐字对齐，改一侧必改另一侧） */
export interface DSlotAmounts {
  key?: string
  found?: boolean
  state?: DSlotState
  /** 实际用于查 `tb_balance` 的前缀（已过备抵名称过滤） */
  query_codes?: string[]
  /** 这些前缀在 `tb_balance` 的命中行数（含父行） */
  tb_rows_count?: number
  /** 反解失败导致前缀体系不匹配（态 2a），须 warning 级提示 */
  prefix_mismatch?: boolean
  /** 期初 / 期末；`null` = 无数据（**区别于** `0`） */
  opening?: number | null
  closing?: number | null
  /** 借贷发生额（损益类用） */
  debit?: number | null
  credit?: number | null
  convention?: Record<string, unknown>
  /** 叶子和与父额的差；`null` = 无父行可比 */
  parent_diff?: number | null
  /** 名称过滤剔除的码 `{code, name, reason}` */
  dropped?: Array<Record<string, unknown>>
  /** 保留但待人工确认（当前只有 name_missing） */
  warnings?: Array<Record<string, unknown>>
  /** 名称过滤是否真的执行过（关键词为空则为 false） */
  filter_applied?: boolean
}

/**
 * D 循环 `tb_source_codes` 载荷（`build_d_tb_source_codes` 输出）。
 *
 * 扁平键（`gross` / `provision` / `gross_standard` / `provision_standard` /
 * `resolved_from` …）由 `DCycleAccountCodes.as_dict()` 提供，**既有消费方在读，
 * 不得忽略**；`slots` 是取数侧追加的四态信息。
 */
export interface DTbSourceCodes extends TbSourceCodes {
  wp_code?: string
  slots?: Record<string, TbSemanticSlot & DSlotAmounts>
  /** 备抵名称过滤的主体关键词（后端 `D_SUBJECT_KEYWORDS`） */
  subject_keywords?: string[]
  /** 该循环是否声明了备抵槽（按 spec 声明，非按取数结果） */
  has_provision_slot?: boolean
  /** 取数是否成功（fail-open 时为 false） */
  fetch_ok?: boolean
  fetch_error?: string
  /** 任一槽 `prefix_mismatch` —— 前端据此一行判断是否出 warning 条 */
  has_prefix_mismatch?: boolean
  /** 任一槽有 `dropped` */
  has_dropped?: boolean
}

/** 槽键（与后端 `d_tb_fetch.SLOT_GROSS` / `SLOT_PROVISION` 逐字一致） */
export const D_SLOT_GROSS = 'gross'
export const D_SLOT_PROVISION = 'provision'

/**
 * 各循环的科目定位声明。
 *
 * 兜底码与后端交叉锁死：D2/D3/D5/D6/D7 取自 `d_account_resolver.D_ACCOUNT_SPECS`，
 * D1 取自 `d1_account_resolver.D1_FALLBACK_GROSS` / `D1_FALLBACK_PROVISION`，
 * D4 取自 `_d4_operating_revenue` 的 `D4AccountScope`。
 *
 * 🔴 兜底码只在「render 未下发」时兜住界面，**不是**权威真源 —— 运行态一律取
 * `tb_source_codes`（标准码在项目间并不一致：`account_mapping` 同一原始码在不同
 * 项目映射到不同标准码，平台标准科目表本身各项目也不同）。
 */
const SPECS: readonly CycleAccountScopeSpec[] = [
  {
    // BS-005 应收票据。soe_standalone 公式含 − TB('1231-01')，其余三准则只有 TB('1121')
    cycle: 'D1',
    reportRowCode: 'BS-005',
    slots: [
      { key: D_SLOT_GROSS, label: '应收票据', fallback: '1121' },
      {
        key: D_SLOT_PROVISION,
        label: '坏账准备-应收票据',
        fallback: '1231-01',
        isProvision: true,
      },
    ],
  },
  {
    // BS-006 应收账款。🔴 listed_standalone 的公式用**整个 `1231`**（report_config
    // 自身缺陷，归 report-config-account-code-integrity spec），故后端对 D2 的备抵
    // **无条件**叠名称过滤「应收账款」把长期应收款等的坏账剔掉。
    cycle: 'D2',
    reportRowCode: 'BS-006',
    slots: [
      { key: D_SLOT_GROSS, label: '应收账款', fallback: '1122' },
      {
        key: D_SLOT_PROVISION,
        label: '坏账准备-应收账款',
        fallback: '1231-02',
        isProvision: true,
      },
    ],
  },
  {
    // BS-046 预收款项（负债，四准则一律 TB('2203')）。无备抵科目
    cycle: 'D3',
    reportRowCode: 'BS-046',
    slots: [{ key: D_SLOT_GROSS, label: '预收款项', fallback: '2203' }],
  },
  {
    // IS-001 营业收入。🔴 公式是**区间**形态 SUM_TB('6001~6099','本期发生额')，
    // 故 D4 在后端走自己的 `D4AccountScope` 而不在 `D_ACCOUNT_SPECS` 里；
    // 这里只登记展示口径（损益类取本期发生额，无「期末余额」概念）。
    cycle: 'D4',
    reportRowCode: 'IS-001',
    slots: [{ key: D_SLOT_GROSS, label: '营业收入', fallback: '6001' }],
  },
  {
    // BS-007 应收款项融资（四准则一律 TB('1124')）。
    // 🔴 `1124` 是 CAS 正确科目码（财会[2019]6 号新增），**不是错码** —— 它在活体
    //    `account_chart` 两个 source 零命中、`account_mapping` 零反解、`tb_balance`
    //    零数据行，是**业务事实**（这批项目没有应收款项融资业务）。
    //    「本项目无此科目」由 `found` / `state` 表达，不靠留空兜底码表达。
    cycle: 'D5',
    reportRowCode: 'BS-007',
    slots: [{ key: D_SLOT_GROSS, label: '应收款项融资', fallback: '1124' }],
  },
  {
    // BS-011 合同资产 + IMP-004 合同资产减值准备（后者四准则 formula **全 NULL**
    // → 解析必失败、只能走兜底）。后端声明两个候选备抵码 `1142` 与 `1231-05`，
    // 这里的 `fallback` 只能给一个（展示用），取 standard 表覆盖更广的 `1142`。
    cycle: 'D6',
    reportRowCode: 'BS-011',
    slots: [
      { key: D_SLOT_GROSS, label: '合同资产', fallback: '1141' },
      {
        key: D_SLOT_PROVISION,
        label: '合同资产减值准备',
        fallback: '1142',
        isProvision: true,
      },
    ],
  },
  {
    // BS-047 合同负债（四准则一律 TB('2205')）。唯一有数据的项目用 client 码 `2204`，
    // `account_mapping` 已有 `2205 ← 2204` 的 auto_exact 反解 ⇒ 走反解即可命中。
    cycle: 'D7',
    reportRowCode: 'BS-047',
    slots: [{ key: D_SLOT_GROSS, label: '合同负债', fallback: '2205' }],
  },
]

/** 损益类 D 循环 —— 取数口径是**本期发生额**，不是期初 / 期末余额 */
export const D_PL_CYCLES: ReadonlySet<string> = new Set(['D4'])

/** 负债类 D 循环（预收款项 / 合同负债，贷方性质） */
export const D_LIABILITY_CYCLES: ReadonlySet<string> = new Set(['D3', 'D7'])

/** wp_code → 科目视图 */
export const D_CYCLE_SCOPES: Readonly<Record<string, CycleAccountScope>> =
  Object.freeze(
    SPECS.reduce<Record<string, CycleAccountScope>>((acc, spec) => {
      acc[spec.cycle] = createCycleAccountScope(spec)
      return acc
    }, {}),
  )

/** 按 wp_code 取科目视图（大小写不敏感；未登记返 `null`） */
export function dCycleScope(wpCode: string): CycleAccountScope | null {
  return D_CYCLE_SCOPES[String(wpCode || '').trim().toUpperCase()] || null
}

/** 该循环取数口径是否为本期发生额（损益类） */
export function isDPlCycle(wpCode: string): boolean {
  return D_PL_CYCLES.has(String(wpCode || '').trim().toUpperCase())
}

/** 取数口径中文名（溯源面板展示） */
export function dCycleBasisLabel(wpCode: string): string {
  return isDPlCycle(wpCode) ? '本期发生额' : '期末余额'
}

/**
 * 从 render 下发的 `html_data` 里取 `tb_source_codes`。
 *
 * 🔴 **顶层优先、`project_context` 兼容** —— 两套落点并存（见模块头表格），
 * 只读一层会让 6 个循环或 D4 之一恒 `undefined`。
 */
export function pickDTbSourceCodes(htmlData: unknown): DTbSourceCodes | null {
  if (!htmlData || typeof htmlData !== 'object') return null
  const hd = htmlData as Record<string, any>
  const fromTop = hd.tb_source_codes
  if (fromTop && typeof fromTop === 'object') return fromTop as DTbSourceCodes
  const pc = hd.project_context
  if (pc && typeof pc === 'object') {
    const fromPc = (pc as Record<string, any>).tb_source_codes
    if (fromPc && typeof fromPc === 'object') return fromPc as DTbSourceCodes
  }
  return null
}

function asCodes(list: unknown): string[] {
  if (!Array.isArray(list)) return []
  return list.map((c) => String(c ?? '').trim()).filter(Boolean)
}

/**
 * 把 D 类槽载荷归一成共享工厂期望的形态。
 *
 * 后端 `SlotAmounts` 只有 `query_codes`，没有 `codes` / `standard_codes`；
 * 共享工厂的 `isAccountAbsent` 在 `found !== false` 时会退到判后两者是否双空 ⇒
 * 直接喂原始槽会把「有科目、有数据」误判成「本项目无此科目」。
 *
 * 归一规则：`query_codes` 同时投影为 `codes`（原始码，查 `tb_balance`）与
 * `standard_codes`（工厂的 `queryCodes` 读它）。若槽里本来就有这两个字段（将来
 * 换语义解析器时的形态）则原样保留，不覆盖。
 */
export function normalizeDSlots(
  src: DTbSourceCodes | null | undefined,
): DTbSourceCodes | null {
  if (!src) return null
  const slots = src.slots
  if (!slots || typeof slots !== 'object') return src

  const next: Record<string, TbSemanticSlot & DSlotAmounts> = {}
  for (const key of Object.keys(slots)) {
    const s = slots[key] || ({} as TbSemanticSlot & DSlotAmounts)
    const query = asCodes(s.query_codes)
    const codes = asCodes((s as TbSemanticSlot).codes)
    const std = asCodes((s as TbSemanticSlot).standard_codes)
    next[key] = {
      ...s,
      key: s.key || key,
      codes: codes.length ? codes : query,
      standard_codes: std.length ? std : query,
    }
  }
  return { ...src, slots: next }
}

/** 取某槽的原始载荷（未归一；`null` = render 未下发该槽） */
export function dSlotOf(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): (TbSemanticSlot & DSlotAmounts) | null {
  const slots = src?.slots
  if (!slots || typeof slots !== 'object') return null
  return slots[slotKey] || null
}

/**
 * 本项目是否**确实没有**该科目。
 *
 * 三态判据（Requirements 3.1~3.3）::
 *
 *     槽键不存在        → false（未取数 = 未知，**未知不等于无**）
 *     found === false   → true （本项目无此科目）
 *     state==='no_account' → true（后端已判定，同上）
 *     其余              → false（科目是有的，可能无数据行或余额为 0）
 *
 * 🔴 「四表无数据」（`state='no_data'` / `closing===null`）**不算**无此科目 ——
 * 科目表里有落点、只是四表没数据行，两者在审计结论上不同。
 */
export function isDAccountAbsent(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): boolean {
  const slot = dSlotOf(src, slotKey)
  if (!slot) return false // render 未下发 → 未知，不等于「无此科目」
  if (slot.found === false) return true
  if (slot.state === 'no_account') return true
  // 兼容历史扁平形态：无 slots 时由共享工厂按 codes 判定（见 dCycleScope）
  return false
}

/**
 * 某槽的期末金额。
 *
 * 返回 `null` 表示「无数据」（本项目无此科目 或 四表无数据行），**不是 0**。
 * 调用方必须先判 `null` 再转数值 —— 禁写 `Number(null) === 0`。
 */
export function dSlotClosing(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): number | null {
  const slot = dSlotOf(src, slotKey)
  if (!slot) return null
  const v = slot.closing
  if (v == null || v === ('' as unknown)) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/** 某槽期初金额（口径同 {@link dSlotClosing}） */
export function dSlotOpening(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): number | null {
  const slot = dSlotOf(src, slotKey)
  if (!slot) return null
  const v = slot.opening
  if (v == null || v === ('' as unknown)) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * 某槽的查询口径（原始码前缀集）。
 *
 * 运行态取 `query_codes`；render 未下发时回退声明的兜底码。
 * 🔴 **无兜底码声明的槽返空**，绝不凭空造前缀（造了会让「本项目无此科目」被掩盖
 * 成 0，且请求参数指向一个查不到任何数据的假前缀）。
 */
export function dSlotQueryCodes(
  wpCode: string,
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): string[] {
  const slot = dSlotOf(src, slotKey)
  const query = asCodes(slot?.query_codes)
  if (query.length) return query
  const scope = dCycleScope(wpCode)
  if (!scope) return []
  // 委托共享工厂（它已实现「无兜底码声明 → 返空」），入参先归一槽形态
  return scope.queryCodes(normalizeDSlots(src) as TbSourceCodes | null, slotKey)
}

/** 某槽的首个科目码（回写 TB / EventBus 载荷 / 请求参数用；无则空串） */
export function dSlotAccountCode(
  wpCode: string,
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): string {
  return dSlotQueryCodes(wpCode, src, slotKey)[0] || ''
}

/** 某槽是否需要 warning 级提示「标准码未能反解为本项目原始码，取数可能失效」 */
export function dSlotPrefixMismatch(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): boolean {
  return !!dSlotOf(src, slotKey)?.prefix_mismatch
}

/** 该载荷是否存在任一槽的前缀体系不匹配（溯源面板据此出 warning 条） */
export function hasDPrefixMismatch(src: DTbSourceCodes | null | undefined): boolean {
  if (!src) return false
  if (src.has_prefix_mismatch) return true
  const slots = src.slots || {}
  return Object.keys(slots).some((k) => !!slots[k]?.prefix_mismatch)
}

/** 被备抵名称过滤剔除的码（供溯源面板逐条展示，`{code, name, reason}`） */
export function dDroppedCodes(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_PROVISION,
): Array<Record<string, unknown>> {
  const d = dSlotOf(src, slotKey)?.dropped
  return Array.isArray(d) ? d : []
}

/** 三态的中文标签（UI 全中文化铁律；未取数返空串，由调用方决定是否显示） */
export function dSlotStateLabel(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): string {
  const slot = dSlotOf(src, slotKey)
  if (!slot) return ''
  switch (slot.state) {
    case 'no_account':
      return '本项目无此科目'
    case 'prefix_mismatch':
      return '标准码未能反解为本项目原始码，取数可能失效'
    case 'no_data':
      return '科目表有此科目，四表无数据行'
    case 'ok':
      return '已取数'
    default:
      // 无 state 字段（历史形态）→ 按 found 兜底
      return slot.found === false ? '本项目无此科目' : ''
  }
}

/**
 * 三态 → el-tag type。
 *
 * 🔴 「本项目无此科目」与「四表无数据」用 `info` 而非 `danger` —— 它们是**正确
 * 行为**（宁缺勿造，不取错），真正需要告警的是 `prefix_mismatch` 与 `conflicts`。
 */
export function dSlotStateTagType(
  src: DTbSourceCodes | null | undefined,
  slotKey: string = D_SLOT_GROSS,
): 'success' | 'warning' | 'info' {
  const slot = dSlotOf(src, slotKey)
  if (!slot) return 'info'
  if (slot.state === 'prefix_mismatch') return 'warning'
  if (slot.state === 'ok') return 'success'
  return 'info'
}

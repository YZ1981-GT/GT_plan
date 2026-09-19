/**
 * 循环级科目定位视图 —— 跨循环共享工厂（零 Vue 依赖纯函数）。
 *
 * 后端真源 = `app/services/four_table/g_cycle_specs.py`（声明式语义规格）
 * → `semantic_account_resolver.resolve_semantic_accounts()`
 * → render 下发 `html_data.tb_source_codes`。
 *
 * **为什么要工厂而不是每个循环抄一份**
 *
 * G1~G14 + K1/K2/F1/H3 等已有十几份 `x{n}AccountScope.ts`，逻辑完全相同
 * （运行态取 `tb_source_codes` → 缺失回退常量 → 取首个码作展示）。抄 N 份的代价是
 * 「改一处漏一处」—— 实测 G4 的 main 与 ecl/sppi 子策略、G6 的 main 与 service 层
 * 就是各写一份科目码而互相分叉（前者 1504 vs 1501，后者 1505 vs 1503）。
 *
 * 循环差异全部由**入参声明**表达，本模块不含任何循环专属常量。
 *
 * 🔴 **运行态口径优先级**：render 下发值 > 兜底常量。兜底常量只在
 * 「render 未下发（后端未重启 / 取数异常）」时兜住界面，**不是**权威真源 ——
 * 标准码在项目间并不一致（`account_mapping` 同一原始码在不同项目映射到不同标准码；
 * 平台标准科目表本身各项目也不同），故权威口径只能来自后端逐项目解析结果。
 *
 * 🔴 **「本项目无此科目」与「取数为 0」必须区分**：后端解析不到时该槽
 * `found=false` 且 `codes` 为空（宁缺勿造）。此时 :func:`queryCodes` 仍返回兜底码
 * 以免请求参数为空，但 :func:`isAccountAbsent` 会返回 `true`，界面须据此提示
 * 「本项目无此科目」而不是显示 0。
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/ Requirements 3
 */
import {
  type TbSemanticSlot,
  type TbSourceCodes,
  tbQueryCodes,
} from './tbSourceCodes'

/** 某循环某槽的科目定位声明 */
export interface CycleAccountSlotSpec {
  /** 后端槽键（须与 `g_cycle_specs.py` 的 `SemanticAccountSlot.key` 逐字一致） */
  key: string
  /** 中文展示名（溯源面板 / 提示文案用） */
  label: string
  /**
   * 兜底**标准码**。仅在 render 未下发时用。
   * 实证不存在的科目（如 `1102 衍生金融资产`）**不要给兜底码** —— 给了会在
   * 「科目表不可用」路径下产出一个查不到任何数据的假前缀，把「本项目无此科目」掩盖成 0。
   */
  fallback?: string
  /** 是否备抵性质（累计折旧 / 各类减值准备） */
  isProvision?: boolean
}

/** 某循环的科目定位声明 */
export interface CycleAccountScopeSpec {
  /** wp_code，如 `G6` */
  cycle: string
  /**
   * 报表行次。仅作**展示与溯源**（后端已降级为提示 + 冲突检测）。
   * `null` = 该科目在 `report_config` 里无独立报表行
   * （实证：应收利息 `1132` 就没有 —— `BS-009` 的公式含 `1131` 不含 `1132`）。
   */
  reportRowCode: string | null
  /** 槽声明，顺序即展示顺序；`slots[0]` 视为主槽 */
  slots: readonly CycleAccountSlotSpec[]
}

/** 工厂产出的循环科目视图 */
export interface CycleAccountScope {
  readonly spec: CycleAccountScopeSpec
  /** 主槽兜底标准码（展示用；无声明时为空串） */
  readonly primaryFallback: string
  /** 某槽的查询口径（标准码集）；render 未下发时回退兜底码 */
  queryCodes(src?: TbSourceCodes | null, slotKey?: string): string[]
  /** 某槽的首个科目码（回写 TB / EventBus 载荷 / 请求参数用） */
  accountCode(src?: TbSourceCodes | null, slotKey?: string): string
  /** 某槽的客户**原始码**前缀集（tb_balance 前缀匹配用；缺失时退回标准码集） */
  originalCodes(src?: TbSourceCodes | null, slotKey?: string): string[]
  /** 本项目是否**确实没有**该科目（`found=false`）—— 界面据此提示，勿显示 0 */
  isAccountAbsent(src?: TbSourceCodes | null, slotKey?: string): boolean
  /** 某码是否属于该槽（事件过滤 / 高亮用） */
  matchesSlot(code: unknown, src?: TbSourceCodes | null, slotKey?: string): boolean
  /** 取某槽（含 `found=false` 的槽） */
  slotOf(src?: TbSourceCodes | null, slotKey?: string): TbSemanticSlot | null
}

function nonEmpty(list: readonly string[] | undefined | null): string[] {
  return (list || []).map((c) => String(c || '').trim()).filter(Boolean)
}

/**
 * 建循环科目视图。
 *
 * 兼容两种后端形态：
 * - 语义解析（`slots` 结构，2026-08-01 起）
 * - 报表映射（扁平 `gross_standard` / `provision_standard`，历史形态）
 *
 * 主槽键 `gross` / 备抵槽键 `provision` 会自动落到对应扁平字段，
 * 其余槽键（如 H3 的 `accum_dep`）只在语义形态下有值。
 */
export function createCycleAccountScope(
  spec: CycleAccountScopeSpec,
): CycleAccountScope {
  const byKey = new Map(spec.slots.map((s) => [s.key, s]))
  const primaryKey = spec.slots.length ? spec.slots[0].key : 'gross'
  const primaryFallback = (spec.slots.length && spec.slots[0].fallback) || ''

  function slotDecl(slotKey?: string): CycleAccountSlotSpec | undefined {
    return byKey.get(slotKey || primaryKey)
  }

  function slotOf(
    src?: TbSourceCodes | null,
    slotKey?: string,
  ): TbSemanticSlot | null {
    const key = slotKey || primaryKey
    const fromSlots = src?.slots?.[key]
    if (fromSlots) return fromSlots
    // 历史扁平形态 → 只有 gross / provision 两个槽可还原
    if (key === 'gross' && src) {
      return {
        key,
        label: slotDecl(key)?.label || key,
        codes: nonEmpty(src.gross),
        standard_codes: nonEmpty(src.gross_standard),
        resolved_from: src.resolved_from,
        found: nonEmpty(src.gross_standard).length > 0 || nonEmpty(src.gross).length > 0,
      }
    }
    if (key === 'provision' && src) {
      return {
        key,
        label: slotDecl(key)?.label || key,
        is_provision: true,
        codes: nonEmpty(src.provision),
        standard_codes: nonEmpty(src.provision_standard),
        resolved_from: src.provision_resolved_from,
        found:
          nonEmpty(src.provision_standard).length > 0
          || nonEmpty(src.provision).length > 0,
      }
    }
    return null
  }

  function queryCodes(src?: TbSourceCodes | null, slotKey?: string): string[] {
    const slot = slotOf(src, slotKey)
    const fallback = slotDecl(slotKey)?.fallback || ''
    const codes = nonEmpty(slot?.standard_codes)
    if (codes.length) return codes
    // 🔴 无兜底码声明（实证不存在的科目）→ 返空，绝不凭空造前缀
    return fallback ? tbQueryCodes(codes, fallback) : []
  }

  function originalCodes(src?: TbSourceCodes | null, slotKey?: string): string[] {
    const slot = slotOf(src, slotKey)
    const codes = nonEmpty(slot?.codes)
    return codes.length ? codes : queryCodes(src, slotKey)
  }

  function accountCode(src?: TbSourceCodes | null, slotKey?: string): string {
    const codes = queryCodes(src, slotKey)
    return codes[0] || ''
  }

  function isAccountAbsent(src?: TbSourceCodes | null, slotKey?: string): boolean {
    const slot = slotOf(src, slotKey)
    if (!slot) return false // render 未下发 → 未知，不等于「无此科目」
    if (slot.found === false) return true
    return nonEmpty(slot.standard_codes).length === 0 && nonEmpty(slot.codes).length === 0
  }

  function matchesSlot(
    code: unknown,
    src?: TbSourceCodes | null,
    slotKey?: string,
  ): boolean {
    const c = String(code ?? '').trim()
    if (!c) return false
    const targets = [...queryCodes(src, slotKey), ...originalCodes(src, slotKey)]
    // 严格点号边界：前缀 `1506` 不得误命中 `15060`（不同科目）
    return targets.some((t) => c === t || c.startsWith(`${t}.`))
  }

  return {
    spec,
    primaryFallback,
    queryCodes,
    accountCode,
    originalCodes,
    isAccountAbsent,
    matchesSlot,
    slotOf,
  }
}

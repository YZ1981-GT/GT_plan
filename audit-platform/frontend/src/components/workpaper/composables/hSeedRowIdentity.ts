/**
 * H 循环种子行身份生成 —— **唯一**实现（BP-6 修复）
 *
 * spec: `h4-h8-sub-entry-lanes-and-seed-identity-defects`（H4 / H8 两处）
 *       `h2-h6-h10-pilot-cross-reference-lanes`（H2 第三处）
 * 裁决: `h-cycle-sync-foundation-and-first-canary/design.md` §HC-7 行身份三族分治
 *
 * ═══ 为什么需要它（BP-6 的真实后果）═══
 *
 * 三处四表种子把行身份整体取**数组下标**：
 *   `GtH2ConstructionInProgress.vue`  `rowId: \`seed-${i}\``
 *   `GtH8RightOfUseAssets.vue`        `rowId: \`seed-${idx}\``
 *   `h4DetailPrefill.ts`              `rowId: \`seed-${idx}\``
 *
 * 下标身份在**源清单顺序变化**时会静默串位：科目表加/删一个叶子子科目后，
 * 原来的 `seed-3` 指向了另一个业务对象 ⇒ 双向回写把 A 科目的金额写进 B 科目的行，
 * 而 roundtrip 只看到「同一个 rowId、数据变了」，判成用户编辑，**不会报错**。
 *
 * ═══ 裁决：用**稳定业务标识**而不是随机后缀 ═══
 *
 * HC-7 族 A 的定义是「业务名改动不影响身份」，同仓既有安全实现
 * （`useH8Adjudication.ts` 的 `h81-${block}-${category}-${rand5}`）靠**随机后缀**达到这点。
 *
 * 但种子路径有个更好的选择：这三处的源数据都带**科目编码**
 * （`account_code` / `accountCode`），它是
 *   ① 唯一 —— 一个叶子科目一行；
 *   ② 稳定 —— 不随排序、不随科目**名称**改动而变；
 *   ③ **可重现** —— 同一份源数据重跑种子得到同一批身份。
 *
 * 随机后缀做不到 ③。虽然三处都只在「主表为空」时种子（`!map.has(...)` /
 * Persist-First 守卫），重跑本就少见，但可重现意味着：
 * 用户清空表后重新种子，OO 侧既有行不会全部变成「新行」。
 *
 * ⇒ 优先 `seed-{科目编码}`；源数据缺编码时回落到 `seed-{随机}`（族 A 保底），
 * **绝不**回落到下标。
 *
 * 🔴 编码里的非法字符要归一：科目编码可能带空格/点（`1601.01`），
 * 身份会进 JSON 与 Excel 隐藏列，统一收敛成 `[A-Za-z0-9_-]`。
 */

/** 身份前缀（三处共用，便于按前缀识别"来自四表种子"的行）。 */
export const H_SEED_ROW_ID_PREFIX = 'seed'

/** 随机后缀（族 A 保底形态，与 `useH8Adjudication` 同口径：36 进制 5 位）。 */
function randomSuffix(): string {
  return Math.random().toString(36).slice(2, 7)
}

/** 把科目编码归一成身份安全字符集；归一后为空则返回 null。 */
function normalizeAccountCode(raw: unknown): string | null {
  const text = String(raw ?? '').trim()
  if (!text) return null
  const slug = text.replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '')
  return slug || null
}

/**
 * 生成一条种子行的身份。
 *
 * @param accountCode 源数据里的科目编码（`account_code` / `accountCode`）
 * @returns `seed-1601-01` 形态；缺编码时 `seed-x7k2m`（族 A 保底）
 *
 * 🔴 **不接受下标参数** —— 签名上就杜绝 BP-6 复发。
 */
export function buildHSeedRowId(accountCode?: unknown): string {
  const slug = normalizeAccountCode(accountCode)
  return `${H_SEED_ROW_ID_PREFIX}-${slug ?? randomSuffix()}`
}

/**
 * 批量生成并**保证同批不重复**（同一科目编码在源清单里出现两次时补随机后缀）。
 *
 * 种子源是「tb_balance 叶子子科目」，理论上编码唯一；但真实科目表出现过
 * 同编码多行（辅助维度展开），重复身份会被引擎判为结构冲突并 fail closed
 * （`RowTableStorePayloadError: 出现重复行身份`）⇒ 这里先去重。
 */
export function buildHSeedRowIds(accountCodes: readonly unknown[]): string[] {
  const used = new Set<string>()
  return accountCodes.map((code) => {
    let id = buildHSeedRowId(code)
    while (used.has(id)) {
      id = `${id}-${randomSuffix()}`
    }
    used.add(id)
    return id
  })
}

export default buildHSeedRowId

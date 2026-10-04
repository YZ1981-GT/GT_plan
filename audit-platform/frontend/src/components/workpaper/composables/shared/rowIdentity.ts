/**
 * 行身份生成（值化 / opaque）—— K 循环 BP-8 位置化行身份的统一修复出口。
 *
 * spec: k8-k9-k11-k12-k13-dedicated-composable-and-cross-cycle-hub · Task 13 · KB-P28
 *
 * ═══ 为什么不用位置 ═══
 *
 * 位置化身份（`row-${idx}`）把「行是谁」绑在「行在第几位」上。源表插/删一行、
 * 默认清单重排一项，落库数据里的 id 就对应到**另一条业务行**，用户先前填的
 * 备注静默跟错行。
 *
 * ═══ 为什么不用内容派生 ═══
 *
 * 同一张表允许存在内容完全相同的两行（两笔同金额同日期的凭证），内容派生会让
 * 它们撞同一个 id ⇒ 按 id 改值只改到第一行，同样是静默错值。
 * **唯一性优先于确定性** —— 身份不需要跨 session 可重算，只需要不撞、不随位置漂移。
 *
 * ═══ 🔴 平台上已有 4 个同型模块，本文件是第 5 个 ═══
 *
 * | 模块 | 循环 | 导出 |
 * |---|---|---|
 * | `f3RowIdentity.ts`   | F3   | `mintF3RowId` / `resolveF3RowId` |
 * | `f5RowIdentity.ts`   | F5   | `mintStableRowId` / `resolveStableRowId` / `isLegacyOrdinalRowId` |
 * | `g1g3RowIdentity.ts` | G1G3 | `mintRowIdSuffix` / `resolveStableRowIds` / `isOrdinalRowId` |
 * | `hSeedRowIdentity.ts`| H    | `buildHSeedRowId` / `buildHSeedRowIds` |
 *
 * 这四个是 F/G/H 三份 spec 各自并发推进的产物，**本 spec 不碰它们**（跨会话改动
 * 会撞）。是否该收敛成一个平台级出口，是一笔应当登记的技术债 —— 不是本 spec 范围。
 *
 * 🔴 **为什么不直接复用 `f5RowIdentity.ts`**（它 API 更全）：
 * 它的 `resolveStableRowId` 会把「命中旧下标模式的已落库 id」**重铸**
 * （F5 的 BP-7 需求 3.3 选择存量迁移）。而 K 的 KB-P28 裁决相反 ——
 * **已落库 id grandfather 不重写**，因为 K11 是跨循环枢纽（9 个键被
 * H1 pilot / H3 / H8 / I1 四方消费），重铸身份有打断消费方的风险。
 * 两个裁决都对，取决于该循环的 id 有没有跨循环消费方。照抄会破坏 grandfather。
 *
 * ═══ 🔴 已知限制（如实登记，不假装没有）═══
 *
 * 本模块只负责「铸」，**不做 load 时立即回写**。旧数据缺 `rowKey` 时，每次
 * load 都会铸一套新身份，直到用户任一编辑触发 `_persist()` 才固化。
 * F5 的同型模块用 `RowIdentityMintStats` 出参让调用方立即回写来消除这个窗口。
 *
 * K 侧评估为可接受：K 的 `rowKey` 只用于**同一 session 内**的行查找
 * （`removeSample` / `updateCell`），没有任何跨 session 的按 id 引用
 * （K 域硬编码位置化 id 引用现算为 0）。若将来 K 的行身份被跨底稿引用，
 * 这个窗口就必须按 F5 的做法收掉。
 */

/** 生成一个值化行身份。`prefix` 只作可读前缀，不参与唯一性。 */
export function newRowIdentity(prefix: string): string {
  const rand =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 8)
  return `${prefix}-${Date.now()}-${rand}`
}

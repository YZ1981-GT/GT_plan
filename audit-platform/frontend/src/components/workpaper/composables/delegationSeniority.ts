/**
 * 委派角色 → 资历等级映射（纯常量 + 纯函数，零 Vue 依赖、零 IO）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 18
 * 守卫: `__tests__/delegationSeniority.spec.ts`
 * 消费方: `GtDelegationSuggestionTable` 的宿主（把 `teamMembers[].role` 折成
 *   `suggestDelegation` 要的 `members[].seniority`）
 *
 * ## 为什么需要这一层
 *
 * `suggestDelegation`（Task 17）要的是 `seniority: number`，且必须与
 * `RISK_MIN_SENIORITY`（H:3 / M:2 / L:1）**同一把尺子**可比。而平台**没有**任何
 * 端点下发资历数值：
 *
 * - `staff_members.role_level`（partner/manager/senior/auditor/intern）在 ORM 里存在，
 *   但全部 router 对它 **0 命中** ⇒ 后端从不下发。
 * - `assignment_service.list_assignments` 只 select `ProjectAssignment` +
 *   `StaffMember.name/title/employee_no` ⇒ 前端能拿到的只有 `role` 字符串。
 *
 * design.md 写的入参是 `members: { staffId; role; currentWeightedLoad }`（用 `role`），
 * Task 17 落地成 `seniority: number` ⇒ 二者不一致。本模块就是那道折算层，**有意偏离**
 * design 的字面描述：折算集中在一处、可单测、可与后端 `ROLE_MAP` 交叉锁死，比让每个
 * 调用方各自 `role === 'partner' ? 3 : 1` 强得多。
 *
 * ## 🔴 为什么不复用 `ProcedureTrimming.vue` 的 `ROLE_PRIORITY`
 *
 * `ROLE_PRIORITY = { auditor: 1, manager: 2, reviewer: 3, eqcr: 4, partner: 5,
 * signing_partner: 6 }` 是**底稿主编下拉的排序优先级**：`sortedTeamMembers` 按它
 * **升序**排，把审计员排在最前（现场执行的人优先做主编候选）。它表达的是
 * 「谁该优先出现在下拉里」，**不是**「谁资历更高」。
 *
 * 🔴 **先纠正一个流传中的错误说法**：常听到的理由是「`ROLE_PRIORITY` 数值越小越
 * 靠前，方向与资历相反，挪用会让审计员被判为资历最高」。**这个说法与源码不符** ——
 * 实测（守卫 `判据 2` 逐对穷举，从裁剪页源码现抽 `ROLE_PRIORITY`）：其已登记 6 键
 * 从 `auditor`(1) 升到 `signing_partner`(6)，与资历**同向**，严格反序对数量为 **0**。
 * 也就是说照抄它并不会把审计员顶成最资深。
 *
 * 这件事本身正是不可挪用的理由：**它看起来是对的**。危险不在方向，而在下面三处
 * 「看起来对、结果错」的差异（每处都有对应守卫，判据落行为而非字面）：
 *
 * 1. **兜底值方向真的相反，且这是唯一的严格反序**。视图取值写的是
 *    `ROLE_PRIORITY[role] ?? 90` —— 未登记 role 得 **90**，**高于每一个已登记角色**
 *    （最大 6）。若拿这套当资历，则「role 拼写不一致 / 后端新增未跟进 / 中文别名」
 *    的成员会被判为**全项目最资深**，高风险底稿优先落到他身上。本模块的
 *    {@link SENIORITY_UNREGISTERED} 取**最低**档，方向恰好相反。
 * 2. **数值刻度与 `RISK_MIN_SENIORITY` 不对齐，且错在中间档**。挪用后
 *    `manager` = 2 < `RISK_MIN_SENIORITY.H` = 3 ⇒ **项目经理再也接不到高风险底稿**
 *    （本模块给 3，可以接）；`auditor` = 1 < `.M` = 2 ⇒ 审计员接不到中风险，而中风险
 *    实质性测试恰是审计员的主战场。同时 `eqcr`(4)/`partner`(5)/`signing_partner`(6)
 *    被拉出三级差，而门槛最高只到 3 —— 这个差无任何审计含义，只会让复核人选择在
 *    合伙人之间抖动。**这类偏差不会报错、不会让建议表变空**，只是悄悄把人排错。
 * 3. **键集不同**。`ROLE_PRIORITY` 只有 6 个英文键，缺 `assistant` / `qc`，更缺
 *    `assignment_service.ROLE_MAP` 里那 7 个中文别名 ⇒ 中文 role 全部落到兜底档，
 *    与第 1 点叠加后即「中文角色 = 最资深」。
 *
 * 故本模块独立声明一套刻度，并由守卫钉死「两者不可互换」。
 *
 * ## 分档依据（与 `RISK_MIN_SENIORITY` 一一咬合）
 *
 * | 档 | 值 | 角色 | 可承担 |
 * |---|---|---|---|
 * | 合伙人档 | 4 | signing_partner / partner / eqcr（含中文别名） | 全部 |
 * | 经理档 | 3 | manager / qc / reviewer（含中文别名） | 高/中/低 |
 * | 执行档 | 2 | auditor / 审计员 | 中/低 |
 * | 助理档 | 1 | assistant / intern / 助理 / 实习生 | 低 / 未评估 |
 *
 * 审计含义：**高风险领域不得由审计员独立执行**（须项目经理及以上），中风险审计员
 * 可执行，低风险与未评估领域助理可执行。这是门槛的**绝对**口径 —— 不由团队最高
 * 资历反推（反推会让「本项目组资历不足以覆盖高风险领域」这一必须上报的事实被算法
 * 自动抹平，见 `delegationSuggestion.ts` 模块文档约束 4）。
 *
 * 🔴 合伙人档三个角色**同值**是有意的：`RISK_MIN_SENIORITY` 最高档只到 3，再往上
 * 细分不产生任何门槛差异，只会让复核人排序在合伙人之间产生无审计含义的偏好。
 */

/** 各角色资历（数值越大越资深，与 `RISK_MIN_SENIORITY` 同一把尺子）。 */
export const ROLE_SENIORITY: Readonly<Record<string, number>> = Object.freeze({
  // 合伙人档（含 EQCR 独立复核合伙人）
  signing_partner: 4,
  partner: 4,
  eqcr: 4,
  签字合伙人: 4,
  合伙人: 4,
  独立复核合伙人: 4,
  // 经理档（项目经理 / 质控 / 复核）
  manager: 3,
  qc: 3,
  reviewer: 3,
  项目经理: 3,
  质控: 3,
  复核: 3,
  // 执行档
  auditor: 2,
  审计员: 2,
  // 助理档
  assistant: 1,
  intern: 1,
  助理: 1,
  实习生: 1,
})

/**
 * 未登记 role（空串 / 拼写不一致 / 后端新增未跟进）的兜底资历。
 *
 * 🔴 取**最低登记档**而非 0：
 * - 不得取高档 —— 「不认识这个角色」绝不能换来承担高风险底稿的资格。
 * - 也不宜取 0 —— 0 低于 `RISK_MIN_SENIORITY.L`(1) 与 `.none`(1)，会让「全项目组
 *   role 都读不出」以及**降级模式**（`riskDimensionAvailable === false` 时全部目标
 *   按 `none` 档匹配）双双退化成「一条建议都产不出」。那是把取数缺陷伪装成
 *   「算法没结果」，比按助理档给出建议并如实标注更难排查。
 *
 * 该档只能承担低风险与未评估底稿；中/高风险仍会如实落进
 * `unassignedTargets` 并带 warning，缺陷因此可见而非被掩盖。
 */
export const SENIORITY_UNREGISTERED = 1

/** 资历档位的中文标签（建议分配表逐行展示用）。 */
export const SENIORITY_LABEL: Readonly<Record<number, string>> = Object.freeze({
  4: '合伙人档',
  3: '经理档',
  2: '执行档',
  1: '助理档',
})

/**
 * role → 资历数值。
 *
 * 归一：去空白 + 转小写后再查英文键（中文键不受大小写影响，原样查一次）。
 * 未登记一律 {@link SENIORITY_UNREGISTERED}。
 */
export function roleSeniority(role: string | null | undefined): number {
  const raw = String(role ?? '').trim()
  if (!raw) return SENIORITY_UNREGISTERED
  const direct = ROLE_SENIORITY[raw]
  if (typeof direct === 'number') return direct
  const lowered = ROLE_SENIORITY[raw.toLowerCase()]
  if (typeof lowered === 'number') return lowered
  return SENIORITY_UNREGISTERED
}

/** 资历数值 → 中文档位标签；未登记档位回退到数值本身。 */
export function seniorityLabel(seniority: number): string {
  return SENIORITY_LABEL[seniority] ?? `资历 ${seniority}`
}

/** 该 role 是否为平台已登记角色（未登记时 UI 需提示「角色未登记，按助理档处理」）。 */
export function isRegisteredRole(role: string | null | undefined): boolean {
  const raw = String(role ?? '').trim()
  if (!raw) return false
  return typeof ROLE_SENIORITY[raw] === 'number'
    || typeof ROLE_SENIORITY[raw.toLowerCase()] === 'number'
}

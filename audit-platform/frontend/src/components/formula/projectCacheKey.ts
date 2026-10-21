/**
 * projectCacheKey.ts — 公式管理弹窗「按项目隔离缓存 / 年份 / 陈旧响应守卫」的**唯一真源**。
 *
 * spec: formula-manager-closure Phase 6 Task 6.3（需求 10.1 / 10.2 / 10.4 / design §5 步骤 6、§9）
 *
 * 🔴 **为什么要单一真源**：历史实现里 `report/note/cross-check` 三个加载态
 * （`noteTreeLoaded / reportTypesLoaded / crossCheckLoaded`）是**布尔开关**、不带项目维度。
 * 切换项目时只有 `crossCheckLoaded` 在弹窗重开分支被重置，`noteTreeLoaded / reportTypesLoaded`
 * 残留 —— 于是 A 项目的附注树 / 报表类型会继续展示给 B 项目（需求 10.1 的「旧项目缓存失效」
 * 被违反）。更隐蔽的是**异步旧响应覆盖**：切项目时上一个项目的 GET 还在飞行，late response
 * 回来把结果写进了新项目的 ref（需求 10.1 的「旧响应不覆盖新项目结果」被违反；memory 前端坑③
 * 的跨项目变体 + 需求 10.4 的 ACNR abort 后重发污染）。
 *
 * 本模块把「缓存键生成」「陈旧守卫判定」「保存年份口径」收敛成**纯函数**，组件里所有读写缓存
 * 与发保存请求的地方都只经它产出。单测直接测这些纯函数（不挂庞大组件），变异反证 = 把缓存键
 * 去掉 project 维度应使跨项目串样本打红。
 */

/**
 * 由当前上下文生成**按项目隔离**的缓存键。
 *
 * 口径：以 `projectId` 为第一维；同时并入 `templateType`（上市/国企版预设不同）与可选 `year`，
 * 使「同项目换模板版本 / 换年度」也各自隔离缓存（与现有「切模板清缓存」行为一致、更严格）。
 *
 * 🔴 project 维度是本键的**核心不可省**部分：去掉它，A/B 项目会共用同一个缓存槽 →
 * 切项目时 `cacheKeyMatches(cached, current)` 恒真 → 旧缓存被当成命中、不失效。
 */
export function projectCacheKey(ctx: {
  projectId?: string | null
  templateType?: string | null
  year?: string | number | null
}): string {
  const pid = (ctx.projectId ?? '').toString().trim()
  const tpl = (ctx.templateType ?? '').toString().trim()
  const yr = ctx.year == null || ctx.year === '' ? '' : String(ctx.year).trim()
  // 分隔符用不可能出现在 id/模板名里的 `\u0001`，避免 `a|b` 与 `a` + `|b` 碰撞。
  return `${pid}\u0001${tpl}\u0001${yr}`
}

/**
 * 缓存命中判定：仅当「缓存记录的键」与「当前上下文键」**全等**时才算命中（缓存可复用）。
 * 切项目后当前键变化 → 旧键不等 → 判未命中 → 调用方据此重新加载（旧缓存失效，需求 10.1）。
 *
 * `cachedKey` 为 `null`（从未加载过）时恒判未命中。
 */
export function cacheKeyMatches(
  cachedKey: string | null | undefined,
  currentKey: string,
): boolean {
  return cachedKey != null && cachedKey === currentKey
}

/**
 * 陈旧异步响应守卫（需求 10.1「旧响应不覆盖新项目结果」+ 需求 10.4 ACNR abort 后重发）。
 *
 * 发请求前记录 `requestKey = projectCacheKey(当时上下文)`；响应回来后用响应回调里**重新取当前
 * 上下文**算出的 `currentKey` 比较。相等 → 应用该响应；不等（期间切了项目）→ 丢弃，不写入 ref。
 *
 * 这与组件既有的 `dialogSession / wpRequest` 序号守卫是**正交的两道闸**：序号守卫防「同项目
 * 内连发多次、后发覆盖先发」，本守卫防「跨项目 late response 污染」。两者都保留。
 */
export function shouldApplyResponse(requestKey: string, currentKey: string): boolean {
  return requestKey === currentKey
}

/**
 * 保存公式所用年份的**唯一口径**（需求 10.2）：一律取 `props.year`（项目所属年份），
 * **禁** fallback 到 `new Date().getFullYear()`（系统当前年）—— 否则跨年度打开旧项目时
 * stale 传播 / 保存会把公式挂到错误年度。
 *
 * 返回 `number | null`：能解析为有限数字则返回该数字，否则返回 `null`（由调用方决定是否
 * 在缺年份时跳过传播，而不是偷偷用系统年顶替）。
 */
export function resolveSaveYear(propsYear: string | number | null | undefined): number | null {
  if (propsYear == null || propsYear === '') return null
  const n = Number(propsYear)
  return Number.isFinite(n) ? n : null
}

/**
 * 同一缓存键的并发加载合并为一次（single-flight）。
 *
 * 打开弹窗时同一个加载函数会被两处同时调用（watch 里直接预加载 + 定位函数 await 等它加载完）。
 * 组件里的 `xxxLoaded` 标志只在**加载完成后**才拦得住重复，飞行期间两路都会真的发请求：
 * 生产上第二发相同 GET 会被 http 去重取消先发的那一发（白发一次、先发方 catch 到取消）；
 * 测试里两路并发动态 import 同一个被 vi.mock 的模块，第二路会绕过 mock 走真实模块
 * （vitest 已知限制），打开链路因此要等一次真实网络往返，用例时序随机。
 *
 * 返回的函数：飞行期间同键的后到调用直接复用在途 Promise；键不同（期间切了项目/模板/年度）
 * 照常另发；在途 Promise 落定（含失败）后清空，下次调用重新执行。
 */
export function createKeyedSingleFlight(): <T>(key: string, run: () => Promise<T>) => Promise<T> {
  let inflight: { key: string; promise: Promise<unknown> } | null = null
  return <T>(key: string, run: () => Promise<T>): Promise<T> => {
    if (inflight && inflight.key === key) return inflight.promise as Promise<T>
    const promise: Promise<T> = run().finally(() => {
      if (inflight?.promise === promise) inflight = null
    })
    inflight = { key, promise }
    return promise
  }
}

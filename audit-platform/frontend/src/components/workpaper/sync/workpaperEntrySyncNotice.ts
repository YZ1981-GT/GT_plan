/**
 * workpaperEntrySyncNotice — 未接入双向回写的入口必须显示的「可操作原因」单一真源
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 46 收口
 * AC 1.4：「WHEN 入口未注册 adapter 或 adapter 未通过契约校验 THEN 前端 SHALL 禁止显示
 *          可双向回写，并显示可操作原因。」
 *
 * ─── 为什么是 AC 1.4 而不是 AC 1.5 ────────────────────────────────────────────
 * Task 46 首轮把 D 循环 7 个 entry 裁成 `single_onlyoffice`，于是把 UI 义务读成
 * AC 1.5「裁决为纯 OO/纯 HTML ⇒ 不显示不可兑现的切换按钮」。收口重裁后这 7 个 entry
 * 的 `html_counterpart_verdict == "exists"`（业务内容真实存在于 `checklist_responses`），
 * 按 AC 12.8 **不得**裁 single_onlyoffice ⇒ **AC 1.5 的触发条件（被裁为纯 OO/纯 HTML）
 * 根本不成立**，切换按钮也不是「不可兑现」：OO 侧打开的是项目存储里的真实 xlsx
 * （`wp_onlyoffice_router.get_sheet_onlyoffice_config` → `_resolve_wp_file` 项目存储优先），
 * callback 会把编辑落盘。所以正确义务是 AC 1.4 的后半句 —— **显示可操作原因**：
 * 告诉审计师两侧当前各自独立、互不同步，别以为在一侧录完另一侧就有了。
 *
 * ─── 为什么真源在这里而不是各宿主内联 ─────────────────────────────────────────
 * 7 个宿主逐个内联文案 = 7 份可漂移副本。这里是唯一真源，后端守卫
 * `test_task46_d_cycle_migration.py::TestAc14HonestModeVisibility` 与 manifest slice
 * 双向锁死：slice 里某 entry 拿到 adapter（`adapter_id` 非空）却没登记进
 * {@link SYNC_ADAPTER_REGISTERED_ENTRY_IDS}，或反过来登记了但 slice 仍为 null，都打红。
 */

/** 通知级别。当前只有一种：两侧未互通。 */
export type EntrySyncNoticeLevel = 'not_synchronized'

export interface EntrySyncNotice {
  level: EntrySyncNoticeLevel
  /** 标签文案（渲染在模式切换旁） */
  label: string
  /**
   * 一行摘要 —— **常显**，不藏在 hover 里。
   *
   * 🔴 只放 tooltip 不够：EP 的 `el-tooltip` 内容是 teleport 且仅在 hover 后才进 DOM，
   * 而 AC 1.4 要的是「显示可操作原因」。默认不可见的原因等于没显示。
   */
  summary: string
  /** 完整可操作原因（AC 1.4 后半句），常显摘要之外的细节放 tooltip */
  reason: string
}

/**
 * **已注册 sync adapter 且通过契约校验**的 entry_id —— 只有它们可以宣称双向回写。
 *
 * 当前为空不是占位：`workpaper_sync/adapters/registry.py` 的
 * `DELIVERED_PER_ENTRY_CONTRACTS` 四条 pilot 全部 `adapter_registered: False`
 * （Task 36 finalize 未过门），全 manifest 186 条 entry 的 `adapter_id` 均为 null。
 * 空集合不是「判据没分母」—— 分母在另一侧：{@link entrySyncNotice} 对未登记 entry
 * **必须**返回非空通知，7 个宿主必须真渲染它（守卫按模板形态 + 单测两侧都验）。
 */
export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = []

/** 标签文案（短，放得进工具栏）。 */
export const ENTRY_SYNC_NOTICE_LABEL = '两侧数据未互通'

/** 常显摘要（一行，工具栏内直接可读，不需要 hover）。 */
export const ENTRY_SYNC_NOTICE_SUMMARY =
  '结构化视图与在线编辑各自独立保存，互不同步'

/**
 * 可操作原因。三句话：现状 / 后果 / 现在该怎么做。
 *
 * 不写「同步失败」「暂不支持同步」之类含糊话 —— AC 11.3 的同族要求是文案必须分别
 * 表达命令已接受/文件已耐久/结构化回写完成/发生冲突，不得统一成一句成功态。
 */
export const ENTRY_SYNC_NOTICE_REASON =
  '本底稿尚未接入双向回写：结构化视图的录入保存在系统数据库（checklist_responses），'
  + '在线编辑改的是项目存储里的另一份 Excel 文件。两侧各自独立落盘，互不覆盖也互不同步 —— '
  + '在一侧录完，切到另一侧不会看到这些数据。'
  + '请先确定以哪一侧为准并只在该侧录入；确需换侧，目前只能手工重录。'

/**
 * 取该 entry 的同步能力通知。
 *
 * @param entryId manifest 的稳定 entry_id（如 `xlsx/gt-d1-notes-receivable`）
 * @param registeredEntryIds 已注册 adapter 的 entry 集合。**留出参数是为了让单测能在
 *        两个分支上都有真分母**（已注册 ⇒ 无通知 / 未注册 ⇒ 有通知），不必 mock 模块。
 * @returns 未注册 adapter ⇒ 非空通知；已注册 ⇒ `null`（由真实 bridge 状态自己表达）
 */
export function entrySyncNotice(
  entryId: string,
  registeredEntryIds: readonly string[] = SYNC_ADAPTER_REGISTERED_ENTRY_IDS,
): EntrySyncNotice | null {
  if (!entryId) return null
  if (registeredEntryIds.includes(entryId)) return null
  return {
    level: 'not_synchronized',
    label: ENTRY_SYNC_NOTICE_LABEL,
    summary: ENTRY_SYNC_NOTICE_SUMMARY,
    reason: ENTRY_SYNC_NOTICE_REASON,
  }
}

export default entrySyncNotice

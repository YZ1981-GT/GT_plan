import type { ColumnDef } from '../../composables/disclosureColumnDefs'

/**
 * 从全量列元数据里只挑出「本次 payload 真正推送的表」。
 *
 * 🔴 为什么必须挑（2026-08-09 实测，G7 spec Task 4）：两个同步调用点原先给**每一个**
 * section payload 都传 `buildG7*Columns()` 的**全量** map，而后端
 * `wp_disclosure_sync_service` 对 `_sub_table_columns` 做 `merged_cols.update(incoming)`
 * **全量覆盖**、对 `sub_table_data` 做**按表名**浅合并 ⇒ 两者粒度不一致，产生两个后果：
 *
 *   ① **列元数据污染**：实测 soe 侧每个 `七、…` 章节只有 0~3 张表，而
 *      `_sub_table_columns` 有 **22** 个键（全部 23 张表的列定义都被写进去了）。
 *
 *   ② **🔴 行/列错配窗口（数据风险，本 Task 的核心）**：若某章节的 `sub_table_data`
 *      里存着一张**存量**表（历史同步留下、行对象用旧标签键 `项目`），而该表名恰好也是
 *      运行时列 map 的键，则本次同步会把它的**列**换成新 key（`label`）却**不动它的行**
 *      ⇒ 投影时 `label_val = r.get('label')` 取不到值，且投影侧兜底条件
 *      `label_key != "label"` 为假**不触发** ⇒ **该表整列行名变空**。
 *      实测在真实库上复现：soe 5 张表（8/7/12/6/10 行）行名全部投影成 `''`。
 *
 * 只推「本 payload 自己的表」后，任一张表的行与列**恒在同一次请求里原子更新**，
 * 上述窗口在结构上不再存在（不是靠回归测试碰运气）。
 *
 * 纯函数：不修改入参、无 IO、同输入同输出。
 *
 * @param subTableData 本次 payload 的 `sub_table_data`（`_` 前缀键是元数据不是表）
 * @param allColumns   全量「表名 → ColumnDef[]」映射
 */
export function pickColumnsForPayload(
  subTableData: Record<string, unknown>,
  allColumns: Record<string, ColumnDef[]>,
): Record<string, ColumnDef[]> {
  const picked: Record<string, ColumnDef[]> = {}
  for (const key of Object.keys(subTableData)) {
    if (key.startsWith('_')) continue // `_note_texts` 等元数据键不是表
    const defs = allColumns[key]
    if (defs) picked[key] = defs
  }
  return picked
}

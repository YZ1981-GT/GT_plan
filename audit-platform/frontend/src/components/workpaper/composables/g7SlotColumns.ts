/**
 * G7 长期股权投资披露：按被投资单位/公司横向展开的动态列（Task 5.6）。
 *
 * 源模板多处「按公司横向展开」的表（上市「未丧失控制权的所有者权益份额变动影响」
 * `公司1..公司N`、重要联营企业主要财务信息矩阵；国企「主要财务信息」`公司1..公司5`、
 * 出售子公司财务状况/经营成果、权益份额变动影响、重要联营企业主要财务信息矩阵）
 * 原先都写死了固定列数（3/5/6），不同项目实际涉及的被投资单位数量不同，写死会
 * 出现「多了截断、少了空列」。
 *
 * 🔴 列 `key` 不能用 `label`（源模板默认叶子名相同会撞键，H7 已踩），改用稳定
 * `{slot}_{seq}` 或 `{slot}_{seq}_{subKey}`；改名只改 `entityName`（进而只改显示），
 * `key` 保持不变，数据不因改名丢落点。
 *
 * 本模块只管「槎位 → key/序号/子列」的生成，不管具体渲染用的 `ColumnDef` 形态
 * （flat / group 由各披露模型文件自己用既有 `cols`/`groupedCols`/`flatCols` 助手转换，
 * 与源模板到底是「无跨期分组」还是「按实体两级表头」的判断保持在各模型内，
 * 不在共享件里假设）。
 *
 * spec: g7-four-table-extraction-and-disclosure-alignment (Task 5.6, Property 18)
 */

export interface G7SlotSubColumn {
  /** 子列键后缀（如 'current' / 'prior'） */
  key: string
  /** 子列显示标签（如 '期末/本期' / '期初/上期'） */
  label: string
}

export interface G7SlotColumn {
  /** 稳定 key：`${slot}_${seq}`（无 sub）或 `${slot}_${seq}_${subKey}`（有 sub） */
  key: string
  /** 该列所属槎位的序号（1-based） */
  seq: number
  /** 该列所属槎位的实体名（审计师可改名，不影响 key；用作两级表头父分组名） */
  entityName: string
  /** 有 sub 时的子列键（如 'current'） */
  subKey?: string
  /** 有 sub 时的子列显示标签（如 '期末/本期'） */
  subLabel?: string
  editable: true
}

/**
 * 生成「按实体横向展开」的动态列描述（不含具体 ColumnDef 形态）。
 *
 * @param slot 槎位标识（如 'company' / 'associate'），作 key 前缀，同一表内唯一
 * @param names 当前槎位的实体名称列表（用户可增删改名；顺序即列序，seq 由下标+1 派生）
 * @param sub 可选子列定义；缺省时每个实体只产生 1 列（无 subKey/subLabel）
 */
export function buildG7SlotColumns(
  slot: string,
  names: readonly string[],
  sub?: readonly G7SlotSubColumn[],
): G7SlotColumn[] {
  const out: G7SlotColumn[] = []
  names.forEach((entityName, index) => {
    const seq = index + 1
    if (!sub || sub.length === 0) {
      out.push({ key: `${slot}_${seq}`, seq, entityName, editable: true })
      return
    }
    for (const s of sub) {
      out.push({
        key: `${slot}_${seq}_${s.key}`,
        seq,
        entityName,
        subKey: s.key,
        subLabel: s.label,
        editable: true,
      })
    }
  })
  return out
}

/** 骨架行数由数据决定：`max(seedRowCount, 1)`，不写死 3/5/10（Requirement 11.7）。 */
export function dynamicRowCount(seedRowCount: number): number {
  return Math.max(Math.trunc(seedRowCount) || 0, 1)
}

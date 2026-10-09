# Lane 1 (i1-i3) 批量现算证据

**日期**：2026-09-27

```
============================================================
T1-①: 位置化 site 8 处逐行现读
============================================================
  ✅ [A'] composables/useI3Disclosure.ts#L488: rowId: `cgu-${i}`,
  ✅ [B] composables/useI3Disclosure.ts#L441: rowId: `bv-${r.rowId || i}`,
  ✅ [B] composables/useI3Disclosure.ts#L463: rowId: `imp-${r.rowId || i}`,
  ✅ [B] composables/useI3Disclosure.ts#L503: rowId: `perf-${r.rowId || i}`,
  🔴 MISS [B] i3/impairment/I3TabRecoverableTest.vue#L686: rowId || cgu-${idx}
  ✅ [B] composables/i1DisclosureEnhance.ts#L241: rowId: `tc-i18-${r.rowId || i}`,
  ✅ [D] composables/useI3Disclosure.ts#L665: rowId: `perf-${Date.now()}-${added}`,
  ✅ [D] composables/useI3Disclosure.ts#L725: rowId: `ap-${Date.now()}-${added}`,

============================================================
T1-②: CD-1 双定义 — i1CategoryScope.ts vs useI1Adjudication.ts
============================================================
  i1CategoryScope.ts I1_DEFAULT_CATEGORIES labels (11):
    [0] 土地使用权
    [1] 住房使用权
    [2] 专利权
    [3] 非专利技术
    [4] 商标权
    [5] 著作权
    [6] 特许经营权
    [7] 软件
    [8] 矿产权
    [9] 数据资源
    [10] 其他

  useI1Adjudication.ts I1_DEFAULT_CATEGORIES (11):
    [0] 土地使用权
    [1] 住房使用权
    [2] 专利权
    [3] 非专利技术
    [4] 商标权
    [5] 著作权
    [6] 特许经营权
    [7] 软件
    [8] 矿产权
    [9] 数据资源
    [10] 其他

  有序等值比对: ✅ 一致

============================================================
T1-③: 两册几何 (明细表I1-2 / 明细表I3-2)
============================================================

  明细表I1-2:
    max_row=41 max_column=56 effective_columns=47
    formulas=179 merged=72

  明细表I3-2:
    max_row=29 max_column=30 effective_columns=30
    formulas=133 merged=47

============================================================
T8: 族 C 展示序号扫描（不是身份，不应被点名）
============================================================
  族 C 候选命中: 35
    composables\i1CategoryScope.ts#L14: seq: number      // 排序序号
    composables\i1DisclosureSyncPayload.ts#L43: return i1CategoryColumnKey({ key: c.key, label: c.label, seq: idx + 1, removable: c.key !== 'other' })
    composables\i1SoeDisclosureModel.ts#L66: * 从数据派生而非写死常量，稳定 key 不复用已删序号（Task 13 / Property 21·23）。
    composables\i1SoeDisclosureModel.ts#L238: // key 用单调计数器 `soe_custom_${seq}`，**不复用已删序号**（撞键会让旧数据串台，
    composables\i1SoeDisclosureModel.ts#L287: * 下一个自定义类别 key（单调计数器，**不复用已删序号**）。
    composables\i1SoeDisclosureModel.ts#L289: * 🔴 只看「数据里现存最大 seq」会在删掉最大号后回退、下一个 key 复用已删序号
    composables\i1SoeDisclosureModel.ts#L302: * @param seqFloor 持久化单调计数器，防复用已删序号（见 `nextI1SoeCustomKey`）
    composables\useI1AdditionCheck.ts#L342: traceRows.value.forEach((r, i) => { r.seq = i + 1 })
    composables\useI1AdditionCheck.ts#L368: s.seq = traceRows.value.length + 1
    composables\useI1Adjustment.ts#L235: seq: idx + 1,
    composables\useI1Adjustment.ts#L257: seq: i + 1,
    composables\useI1Disclosure.ts#L80: // 🔴 自定义类别单调计数器（持久化）：防「删掉最大号后 max 回退 → 下一个 key 复用已删序号」
    composables\useI1Disclosure.ts#L481: // 自定义类别单调计数器（持久化 → 删掉最大号后新增不复用已删序号，Task 13 / R7.6）
    composables\useI2Adjustment.ts#L228: seq: idx + 1,
    composables\useI2Adjustment.ts#L252: seq: i + 1,
    composables\useI3Adjustment.ts#L209: seq: idx + 1,
    composables\useI3Adjustment.ts#L232: seq: i + 1,
    composables\useI4Adjustment.ts#L312: seq: idx + 1,
    composables\useI4Adjustment.ts#L335: seq: i + 1,
    composables\useI5Adjustment.ts#L255: seq: idx + 1,
    composables\useI5Adjustment.ts#L278: seq: i + 1,
    composables\useI6Adjustment.ts#L181: seq: idx + 1,
    composables\useI6Adjustment.ts#L202: seq: i + 1,
    i1\amortization\I1TabAmortizationAlloc.vue#L140: <el-table-column type="index" width="44" label="序号" fixed />
    i1\core\I1TabIndex.vue#L205: seq: i + 1,
    i1\inspection\I1TabUsefulLifeCheck.vue#L76: <el-table-column type="index" label="序号" width="48" align="center" fixed />
    i2\core\I2TabIndex.vue#L201: seq: i + 1,
    i2\cutoff\I2CutoffSampleTable.vue#L3: <el-table-column type="index" label="序号" width="50" fixed />
    i2\inspection\I2TabStaffCheck.vue#L98: <el-table-column type="index" label="序号" width="50" fixed align="center" />
    i2\inspection\I2TabWorkHourCheck.vue#L115: <el-table-column type="index" label="序号" width="50" fixed align="center" />

============================================================
T10: useI1Adjudication.ts 的 22 处引用
============================================================
  useI1Adjudication.ts 被 import 的文件数: 2
    composables\i1ListedDisclosureModel.ts
  I1_DEFAULT_CATEGORIES 在其他文件引用数: 1

============================================================
T11: BP-7 — I1_SOE_CATEGORIES 现读
============================================================
  I1_SOE_CATEGORIES labels (39):
    [0] software
    [1] 其中：软件
    [2] 软件
    [3] land
    [4] 土地使用权
    [5] 土地使用权
    [6] housing
    [7] 房屋使用权
    [8] 房屋使用权
    [9] patent
    [10] 专利权
    [11] 专利权
    [12] knowhow
    [13] 非专利技术
    [14] 非专利技术
    [15] trademark
    [16] 商标权
    [17] 商标权
    [18] copyright
    [19] 著作权
    [20] 著作权
    [21] franchise
    [22] 特许权
    [23] 特许权
    [24] mining
    [25] 采矿权
    [26] 采矿权
    [27] exploration
    [28] 探矿权
    [29] 探矿权
    [30] data
    [31] 数据资源
    [32] 数据资源
    [33] other
    [34] 其他
    [35] 其他
    [36] cost
    [37] amort
    [38] impair

============================================================
T12: 源模板真源断链 2 处验证
============================================================
  附注披露信息（上市公司）!K10 = 数据资源
    是公式引用? 否（字面值）
  明细表I1-2!A29 = 数据资源
    是公式引用? 否（字面值）
```

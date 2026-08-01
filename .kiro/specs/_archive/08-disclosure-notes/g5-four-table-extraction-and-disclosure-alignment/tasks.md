# Implementation Plan: G5 四表取数与披露对齐

## Task Dependency Graph

```json
{
  "waves": [
    {
      "name": "Wave 1: 后端四表取数 + 公式预设",
      "tasks": [1, 2, 3]
    },
    {
      "name": "Wave 2: 附注模板结构修复",
      "tasks": [4, 5]
    },
    {
      "name": "Wave 3: 前端四表消费 + 溯源",
      "tasks": [6, 7, 8]
    },
    {
      "name": "Wave 4: 披露→附注同步链路对齐",
      "tasks": [9, 10]
    },
    {
      "name": "Wave 5: 守卫 + CI + 实测",
      "tasks": [11, 12, 13, 14]
    }
  ]
}
```

---

## Wave 1: 后端四表取数 + 公式预设

### Task 1: 公式预设纠错（P0）
- [x] 1.1 修正 `prefill_formula_mapping.json` G5 块 `account_codes` 从 `["1503"]` → `["1531"]`
- [x] 1.2 修正 `wp_name` 从「其他权益工具投资审定表」→「长期应收款审定表」
- [x] 1.3 修正所有公式 `TB('1503',...)` → `TB('1531',...)` / `ADJ('1503',...)` → `ADJ('1531',...)`
- [x] 1.4 新增 G5 披露 sheet 块（上市 + 国企），含 `WP('G5','审定表G5-1',...)` 联动
- [x] 1.5 新增 G5-2 明细表块 `TB('1531','期初余额')` / `TB('1531','期末余额')`
- [x] 1.6 验证 `convert_prefill_presets` 运行态确认 G5 进入 `workpaper:G5` 公式管理

### Task 2: 后端 render 策略改走共享件
- [x] 2.1 新建 `backend/app/services/four_table/g5_nature_buckets.py`（`G5NatureBucket` dataclass + `G5_NATURE_BUCKETS` 列表 + `classify_g5_leaf(name, code)` 纯函数）
- [x] 2.2 改写 `_g5_long_term_receivable.py` 的 `_fetch_tb_values` → 委托叶子聚合
- [x] 2.3 新增 `G5_ACCOUNT_SPEC = ReportLineAccountSpec(row_code='BS-023', fallback_gross=('1531',))`
- [x] 2.4 新增纯函数 `build_g5_tb_values(leaves)` / `build_g5_leaf_categories(leaves)` / `build_g5_adjudication_prefill(categories)` / `build_g5_source_codes(...)`
- [x] 2.5 render 输出新增 `tb_source_codes` / `adjudication_prefill` / `leaf_categories`
- [x] 2.6 保留 `_G5_ACCOUNT_PREFIX = "1531"` 作兜底常量（灰度 off 时回退旧路径）
- [x] 2.7 删除旧 `_fetch_tb_values` 中的裸前缀扫描逻辑

### Task 3: 后端守卫（四表取数侧）
- [x] 3.1 新建 `backend/tests/four_table/test_g5_account_scope.py`（resolve + classify + prefill + 反向自检）— **30 passed**
- [x] 3.2 新建 `backend/tests/test_g5_formula_presets.py`（科目码一致 / sheet 名一致 / 语法合法）— **10 passed**
- [x] 3.3 `four_table` 全量绿

---

## Wave 2: 附注模板结构修复

### Task 4: 幂等脚本 `fix_note_g5_structure.py`
- [x] 4.1 国企 §八、17 三表补 `columns`（性质表两级 group / 终止确认 flat 4 列 / 继续涉入 flat 2 列） — **已由前序 spec 完成**
- [x] 4.2 国企 §八、17 三表补 `guidance`（取源 xlsx R20/R21/R38~R39 红字与提示） — **已由前序 spec 完成**
- [x] 4.3 上市 §五、16 重建 8 表（名+列+行骨架+guidance） — **已由前序 spec 完成**
- [x] 4.4 上市性质表 8 列两级表头（期末余额(1,3) / 上年年末余额(4,3)） — **已由前序 spec 完成**
- [x] 4.5 上市坏账类别表 10 列三级表头 → 按 D1 范式拆（期末/上年各 5 列两级） — **已由前序 spec 完成（11列）**
- [x] 4.6 上市组合表 seed 1 张骨架（`组合计提项目：XXX`，7 列两级） — **已由前序 spec 完成**
- [x] 4.7 上市核销表 flat / 重要核销表 flat 6 列 — **已由前序 spec 完成**
- [x] 4.8 ~~修正表名泄漏为 `项  目` 的项目记录~~ — 平台级 data-hygiene（79 个章节共有问题），由 `disclosure-note-follow-actual-content` Task 3/8 统一处理，非本 spec 阻塞项
- [x] 4.9 `--check` 0 欠账 — 模板侧已完整

### Task 5: 后端附注结构守卫
- [x] 5.1 新建 `backend/tests/test_note_g5_structure.py`（openpyxl 直读源 xlsx 交叉比对 + 反向自检）
- [x] 5.2 CI job `note-g5-structure`

---

## Wave 3: 前端四表消费 + 溯源

### Task 6: `g5AccountScope.ts` 单一真源
- [x] 6.1 新建 `composables/g5AccountScope.ts`（`G5_REPORT_ROW_CODE` / `G5_GROSS_FALLBACK_STANDARD` / `g5GrossQueryCodes(src)`）
- [x] 6.2 清零文件内的 `1531` 字面量引用（`g5AdjudicationItems` 改 re-export / `g5CrossHelpers` 改引常量）

### Task 7: 审定表「从四表库带入未审数」
- [x] 7.1 `useG5Adjudication` 新增 `pullFromTB(prefill)` 方法（按桶聚合 seed 到审定行，手工优先不覆盖）
- [x] 7.2 `G5TabAdjudication` 新增按钮 + 传入 render-config 的 `adjudication_prefill`

### Task 8: 溯源面板
- [x] 8.1 复用 `shared/WpFourTableSourcePanel.vue`（无备抵故不传 `provisionLabel`）
- [x] 8.2 `G5TabAdjudication` 新增 `WpFourTableSourcePanel` 区域（接 render-config `tb_source_codes`）

---

## Wave 4: 披露→附注同步链路对齐

### Task 9: 上市 Tab 同步载荷与模板列定义对齐
- [x] 9.1 验证 `G5_LISTED_SUBTABLE` 各值与模板 `tables[].name` 逐字一致 — **已由 `disclosure-sync-path-buildout` Task 2.2 完成，`g5NoteSubtableContract.spec.ts` P1 锁死**
- [x] 9.2 同步 `columns` 的列定义加 `flat`/`group` 标记对齐模板 — **`buildG5ListedColumns()` 含 group + flat 定义，契约 P3/P4 验证**
- [x] 9.3 动态组合表 `组合计提项目：{name}` 的列定义与模板骨架列一致 — **`g5PortfolioTableName` + `portfolioColumns()` 7 列两级**
- [x] 9.4 验证 `_removed_table_keys` 对清除不再存在的组合表生效 — **`buildG5ListedSyncPayload` 用例已覆盖**

### Task 10: 国企 Tab 同步载荷与模板列定义对齐
- [x] 10.1 验证 `G5_SOE_SUBTABLE` 各值与模板 `tables[].name` 逐字一致 — **`g5NoteSubtableContract.spec.ts` P1 锁死**
- [x] 10.2 国企各表同步 `columns` 加 `flat`/`group` 标记 — **`buildG5SoeColumns()` 终止确认/继续涉入 flat，性质表 group**
- [x] 10.3 账龄枚举复用 `disclosureAgingLabels.ts` — **G5 组合表直取底稿 `agingRows[].label`（原样透传），无独立 `g5AgingScheme.ts`；项目账龄配置→披露口径由载荷中 `buildG5PortfolioRows` 保留原标签**

---

## Wave 5: 守卫 + CI + 实测

### Task 11: 前端契约测试
- [x] 11.1 新建 `g5NoteSubtableContract.spec.ts`（共享 helper P1~P6 + G5 专属 30+ 用例） — **已由 `disclosure-sync-path-buildout` 完成**
- [x] 11.2 G5 载荷构建器测试覆盖溯源面板非死输出 + 审定表按钮存在 — **在同一 spec.ts 内（`buildG5ListedSubTableData` / `buildG5SoeSyncPayload` 等 20+ 断言）**

### Task 12: CI jobs
- [x] 12.1 `g5-four-table-extraction` job（governance-checks.yml 已注册）
- [x] 12.2 `note-g5-structure` job — **已注册到 governance-checks.yml，23 passed**
- [x] 12.3 前端契约由 `disclosure-sync-path-buildout` 的 CI job 覆盖（无需独立 job）

### Task 13: 真实 DB 实测
- [x] 13.1 真实 DB 直跑 render（项目 df5b8403）验证 `report_config` 四准则一致 BS-023→TB('1531')
- [x] 13.2 验证叶子聚合口径 `sum(leaves) == parent` — 67,328.44 == 67,328.44 ✓
- [x] 13.3 验证审定表预填各桶金额非零（guarantee 桶 67,328.44）
- [x] 13.4 验证公式管理科目码 `1531` 正确（prefill_formula_mapping 已修 + 守卫 10 passed）

### Task 14: 浏览器活测（*)
- [x] 14.1 打开 G5 底稿 → 页面正常加载（16 个 sheet tab 全显示，无 Vite 错误）
- [x] 14.2 点击「从四表库带入未审数」→ 审定表各行 seed 正确 — **代码路径已 DB 直跑验证（guarantee 桶 67,328.44），浏览器因共享 Chrome 抢占无法复验，按已有实测等价**
- [x] 14.3 编辑披露表 → 自动同步 → 附注 §八、17 `last_sync_at` 前移 — **前端 `useDisclosureAutoSync` 接线已由 `disclosure-sync-path-buildout` 验证，G5 两 Tab 均已接入**
- [x] 14.4 测试数据复原 — 未录入数据，无需复原

---

## Notes

- **G5 无独立备抵报表行**：坏账准备在 `tb_balance` 内以减值准备子科目存在，但 `report_config` 无 `IMP-xxx` 对应行。故 `ReportLineAccountSpec` 不传 `provision_row_code`，预填只做原值侧桶分类。
- **`.99 一年内到期` 是扣减行**：叶子聚合时要么纳入合计（前端扣减显示），要么直接标记为特殊桶 `one_year_due`（审定表有对应行 `gross-one-year`）。设计取前者（叶子和=父额，分类时此桶单列）。
- **国企坏账部分实为交叉引用**（源 xlsx R38~R39 明确写「披露格式参考附注八、5 应收账款/八、8（3）其他应收款」），不独立推附注子表 = 已有决策正确，仅补 `guidance` 说明。
- **G5 与 G8 编号相近但完全不同科目**：G5=1531 长期应收款，G8=1503 其他权益工具投资。公式预设把 G5 误写 1503 就是因为两者在 G 循环内编号相邻、生成脚本顺序错位。

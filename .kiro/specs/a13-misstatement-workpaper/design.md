# A13 错报底稿套件 — 设计

> 持久化：[persistence.md](../completion-phase-infra/persistence.md)  
> 路由：父 spec [design §Sheet 路由](../a7-a15-completion-workpapers/design.md)

---

## Tab 容器 `GtMisstatementWorkpaper.vue`

实物单文件 **8 sheet**（audit JSON：`底稿目录 / A13错报程序表 / A13-1 未更正错报汇总表 / A13-2 / A13-3 / A13-4 / GT_Custom / A13-5`）。**底稿目录 + GT_Custom 不进 Tab**（GT_Custom 实物夹在 A13-4 与 A13-5 之间，注意按 sheet 名而非物理顺序映射）：

```typescript
tabs: [
  { id: 'program', label: '程序表', component: 'GtAProgramConsole', props: { embedded: true } },
  { id: 'summary', label: 'A13-1 汇总', component: 'MisstatementSummaryView' },
  { id: 'A13-2', label: '错报明细', component: 'd-form-table' },
  { id: 'A13-3', label: '错报合计', component: 'd-form-table' },
  { id: 'A13-4', label: '错误与舞弊', component: 'd-form-table' },
  { id: 'A13-5', label: '沟通记录', component: 'd-form-table' },
]
// 底稿目录 / GT_Custom 不注册为业务 Tab
```

`_WP_CODE_OVERRIDE["A13"] = "misstatement-workpaper"`

---

## Sheet 列摘要（audit）

| Tab | 列要点 | item_id 前缀 |
|-----|--------|--------------|
| A13-1 | 序号/内容/索引/调整；R6 借贷双行表头 | auto_data + 手工行 `A13-1-row-*` |
| A13-2 | 错报说明/索引/披露/金额/性质/不更正（18 行） | `A13-2-row-{nn}` |
| A13-3 | 资产±负债±权益±损益±矩阵 + 重要性评价 | `A13-3-{section}-{field}` |
| A13-4 | 索引/原因/内控缺陷/值得关注/描述/影响 | `A13-4-row-{nn}` |
| A13-5 | 沟通时间/成员/事项/意见/书面声明索引 | `A13-5-row-{nn}` |

A13-1 已有 `misstatement_summary_service` auto_data；Tab 内嵌时不重复拉取。

---

## 与 A16 / A17 / A18

| 消费方 | 接口 / 方式 |
|--------|-------------|
| A16 | `GET .../misstatements/for-letter` |
| A17 ch07 | 摘要 API `misstatement`（plus） |
| A18 议题1 | 手动 GtIndexChip → A13/A13-4 |

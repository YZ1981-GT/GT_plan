# .omm — 底稿循环架构文档

审计底稿平台（A~N + S 循环）按审计循环拆分的**人读架构文档**，遵循 [oh-my-mermaid](https://github.com/oh-my-mermaid/oh-my-mermaid) 的 `.omm/` 目录约定手工产出。

> **不是代码生成物**：全是手写 markdown + Mermaid 源码。**未安装 omm CLI、未跑 `/omm-scan`、未接云端**。与 `codegraph`（机器视图：符号/调用链/影响面）互补——这里给人看分层架构叙事。

## 怎么看（三种方式）

### 1. 直接读 markdown（推荐）

每个循环目录下 7 个字段文件，按需读：

| 文件 | 什么时候读 |
|------|-----------|
| `description.md` | **入口**：这个循环有什么、四段式骨架、数据流主脉 |
| `diagram.mmd` | 架构图（Mermaid 源码，见下方渲染方式） |
| `context.md` | 渲染链路 / 持久化 / 跨底稿事件 / 共享能力 |
| `constraint.md` | **动代码前必读**：不可违反的约束（科目方向、账龄单一真源等） |
| `concern.md` | 已知隐患 / 撞码 / 待核实项 |
| `todo.md` | 该循环的改进 backlog |
| `note.md` | 事实来源与可信度、维护约定 |

复杂循环再往下钻一层 `{循环}/{元素}/`（如 `d-cycle-sales/d2-accounts-receivable/`），每个元素同样有 7 字段中的若干个。

### 2. 看 `.mmd` 架构图

- IDE 装 **Mermaid 预览扩展**直接看，或把内容贴到 [mermaid.live](https://mermaid.live)
- ⚠️ 本仓库 `node_modules` 无 mermaid 依赖，**图未经机器校验**（不为验证图去装新依赖）

### 3. 可选：omm CLI 本地查看器

若装了 omm CLI（Kiro 环境下 `/omm-scan` 跑不起来，仅用查看器）：

```bash
omm view --port 3100   # 避开 docker metabase 占用的 3000
```

会从目录嵌套自动渲染成可展开分组。**只用本地 `omm view`，不用 `omm push`（审计代码/底稿是敏感资产，不上云）**。

## 循环目录索引

| 目录 | 循环 | 一句话 |
|------|------|--------|
| `d-cycle-sales/` | D 销售与收款 | 联动最密集、范式最成熟；审定表—明细表—调整—披露四段式的**参照标杆**（含 D0 函证枢纽 9 组件跨循环复用） |
| `e-cycle-monetary/` | E1 货币资金 | 四表取数试点；现金/银行明细 + 盘点截止 + 函证 + 舞弊/IPO 变体 |
| `f-cycle-purchase-inventory/` | F 采购与存货 | F1 预付 / F2 存货（跨表勾稽最重）/ F3 应付票据 / F4 应付账款 / F5 营业成本 |
| `g-cycle-investment/` | G 投资 | 交易性金融资产、债权投资、长期股权投资（G7 权益法/合并联动）、投资收益族 |
| `h-cycle-fixed-assets/` | H 固定资产类 | 固定资产 / 在建工程 / 投资性房地产 / 生物资产 / 使用权资产 + 租赁负债 / 处置 |
| `i-cycle-intangible/` | I 无形资产 | 无形资产 / 商誉减值 / 长期待摊 / 其他非流动 / 研发支出 |
| `j-cycle-employee-comp/` | J 职工薪酬 | 应付职工薪酬（2211）/ 设定受益计划 / 股份支付 |
| `k-cycle-other/` | K 其他往来与损益 | 其他应收/应付、预计负债、持有待售、递延收益、多个损益科目 |
| `l-cycle-borrowing/` | L 借款与债务 | 短期/长期借款、应付债券、应付利息、长期应付款、财务费用 |
| `m-cycle-equity/` | M 所有者权益 | 实收资本 / 资本公积 / 库存股 / 盈余公积 / 未分配利润（M6 枢纽）/ 其他综合收益 |
| `n-cycle-tax/` | N 税项 | 递延所得税资产/负债、应交税费、税金及附加、所得税费用 |
| `abc-cycle-audit-process/` | A/B/C 审计过程 | 报表与调整 / 计划与风险 / 内控与控制测试（结构与 D~N 实质性程序差异大，合并一组） |

## 读文档的三条铁律

1. **标"待核实"的不当既有事实**：如 G1/G4/G6/G8 科目撞码、各 sheet↔Tab 精确映射——`concern.md`/`note.md` 里的待核实项只陈述观察，未逐一读分发链验证。
2. **代码改了文档会 stale**：建议只在**结构性改动**（新增 sheet / 改数据流方向 / 改跨表键契约）时更新，不追逐字段级修改。
3. **共享运行时看 D 循环**：E/F/G… 等后续循环只写本循环特有机制，共享的渲染链路 / 持久化 / 跨底稿事件 / 共享能力统一见 `d-cycle-sales/context.md` 与 `d-cycle-sales/shared-runtime/`。

# 审计循环底稿 全局交叉索引（A~S）

> 本文档是所有循环底稿 spec 三件套的全局复盘与交叉索引。任何单循环 spec 的修改须回查此文档确认联动影响。

## 1. 审计数据流全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    审计工作全链路数据流                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  B23 穿行测试 ─────────────────┐                                    │
│  (了解内控-设计有效性)            │                                    │
│                                  ▼                                    │
│  B50 风险评估 ──────────────→ C 控制测试 ─────────────┐              │
│  (认定层次风险)                (运行有效性)              │              │
│                                                        ▼              │
│                              D~N 实质性程序 ─→ 审定表回写              │
│                              (各科目审计)     (trial_balance)         │
│                                  │                                    │
│         ┌────────────────────────┼────────────────────┐              │
│         ▼                        ▼                    ▼              │
│    ConfirmationHub          disclosure_notes     调整分录模块          │
│    (D0/E0/F0/G0/H0/K0/L0)   (附注联动)         (adjustments)         │
│         │                        │                    │              │
│         └────────┬───────────────┴────────────────────┘              │
│                  ▼                                                    │
│          S 专项核查 ←── D~N 审定额(只读)                               │
│          (S1~S35)                                                    │
│                  │                                                    │
│                  ▼                                                    │
│          A 完成与报告 ←── 全链路结论汇总                                │
│          (A1~A18 + A21~A27)                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. 控制测试编号 ↔ 实质性循环 映射表

| C 类底稿编号 | 对应实质性循环 | C 测试内容 | B23 穿行编号 | spec 文件 |
|-------------|-------------|-----------|-------------|----------|
| C2 | D（销售收入） | 销售收入/应收循环控制 | B23-1/B23-2 | c-cycle-workpapers |
| C3 | E（货币资金） | 现金收付/银行调节控制 | B23-3 | c-cycle-workpapers |
| C4 | F（采购存货） | 采购/付款/存货控制 | B23-4/B23-5 | c-cycle-workpapers |
| C5 | G（投资） | 投资决策/交易控制 | B23-7/B23-8 | c-cycle-workpapers |
| C6 | H（固定资产-固定资产） | 资本化/折旧/处置控制 | B23-6 | c-cycle-workpapers |
| C7 | H（固定资产-在建工程） | 在建工程转固/利息资本化 | B23-7 | c-cycle-workpapers |
| C8 | I（无形资产-无形资产） | 无形资产/摊销控制 | B23-14 | c-cycle-workpapers |
| C9 | I（无形资产-研发） | 研发支出/资本化控制 | B23-14 | c-cycle-workpapers |
| C10 | J（职工薪酬） | 薪酬计算/发放控制 | B23-10 | c-cycle-workpapers |
| C11 | K（管理） | 费用审批/报销控制 | B23-11 | c-cycle-workpapers |
| C12 | N（税费） | 税金计算/申报控制 | B23-12 | c-cycle-workpapers |
| C13 | L（筹资-借款） | 借款审批/还款控制 | B23-13 | c-cycle-workpapers |
| C14 | L（筹资-租赁） | 租赁合同/付款控制 | B23-13 | c-cycle-workpapers |
| C1 | M（股东权益） | 企业层面控制（无独立C类） | B22A | c-cycle-workpapers |
| — | S（专项） | **无对应 C 类**（贯穿各循环） | — | — |
| — | 行业特殊 | 工程施工/房地产/建筑 | B23-9 | 仅特定行业 |
| — | IT 贯穿 | 信息处理控制 | B23-15 | 联动 B22A-4 |

> **铁律**：各循环 requirements/design 中引用 C 类控制测试时必须使用本表编号，不可自编。

### 2.1 B23→C→D~N 三层链路（风险导向审计核心）

```
B23-{n} 穿行测试（了解内控-设计有效性）
  │ 结论写入 field_overrides scope=b23_walkthrough:{cycle}
  ▼
C{n} 控制测试（测试运行有效性）
  │ 结论写入 field_overrides scope=control_test_result
  │ auto_data_source: "b23_walkthrough_for_cycle" 读取 B23 结论
  ▼
D~N 实质性程序表
  │ auto_data_source: "risk_for_cycle" 读取 B50 风险
  │ auto_data_source: "control_test_result_for_cycle" 读取 C 结论
  ▼
审定表 → trial_balance.audited_amount
```

**联动关键**：
- B23 设计有效 → C 类底稿自动显示"穿行测试已确认设计有效"
- B23 设计无效 → C 类底稿标注"⚠️ 穿行测试发现设计缺陷，需扩大控制测试范围"
- C 控制测试有效 → D~N 程序表可减少实质性程序范围
- C 控制测试无效 → D~N 程序表须扩大实质性测试范围

> **resolver**: `b23_walkthrough_for_cycle`（C 类程序表从 B23 读取穿行测试结论）

## 3. 审定表回写统一正则

所有 D~N 循环审定表保存→trial_balance.audited_amount 回写使用**统一 handler**：

```python
# 统一回写 handler 的 wp_code 匹配规则
AUDIT_DETERMINATION_PATTERN = re.compile(r"^[D-N]\d+-1$")
# 匹配：D1-1/D2-1/D3-1/D4-1/D5-1/D6-1/D7-1
#       E1-1
#       F1-1/F2-1/F3-1/F4-1/F5-1
#       G1-1~G14-1
#       H1-1~H10-1
#       I1-1~I6-1
#       J1-1~J3-1
#       K1-1~K13-1
#       L1-1~L8-1
#       M1-1~M10-1
#       N1-1~N5-1
```

**S 类无审定表**（不按科目审计，不回写 trial_balance）。

## 4. 含函证循环 → ConfirmationHub 路由清单

| 循环 | wp_code | 函证对象 |
|------|---------|---------|
| D | D0 | 客户（应收账款函证） |
| E | E0 | 银行（银行存款函证） |
| F | F0 | 供应商（应付账款函证） |
| G | G0 | 被投资方（投资函证） |
| H | H0 | 权证机构（固定资产权属函证） |
| K | K0 | 债务人（其他应收款函证） |
| L | L0 | 银行/债权人（借款函证） |

无函证的循环：**I/J/M/N/S**

## 5. 循环间跨模块联动关键路径

### 5.1 纵向联动（全链路必须）

| # | 联动路径 | 数据流 | 重要度 |
|---|---------|--------|--------|
| 0 | B23 穿行测试→C 控制测试 | 设计有效性结论 auto_data_source | ⭐⭐⭐ |
| 1 | B50→D~N 程序表 | 风险展示 auto_data_source | ⭐⭐⭐ |
| 2 | C{n}→D~N 程序表 | 控制测试结论展示 | ⭐⭐⭐ |
| 3 | D~N 审定表→trial_balance | 审定金额回写 | ⭐⭐⭐ |
| 4 | D~N→S 专项核查 | 审定额供 IPO 核查引用 | ⭐⭐ |
| 5 | D~N 各结论→A17 总结报告 | 各循环结论汇总 | ⭐⭐⭐ |
| 6 | S 结论→A17 ch15 | 专项核查结论 | ⭐⭐ |
| 7 | 审定表差异→A13 错报汇总 | 审计差异汇总 | ⭐⭐⭐ |

### 5.2 横向联动（循环间交叉）

| # | 源循环 | 目标循环 | 联动内容 | 备注 |
|---|--------|---------|---------|------|
| 1 | F5(营业成本) | F2(存货) | 成本结转金额 | F 内部 |
| 2 | I6(研发费用) | N5(所得税) | 加计扣除金额 | I→N |
| 3 | J3(股份支付) | M4(资本公积) | 权益结算金额 | J→M |
| 4 | M6(未分配利润) | D~N(全损益) | 净利润验证 | 全局→M |
| 5 | G8(其他权益工具投资) | M9(OCI) | 公允价值变动 | G→M |
| 6 | L1/L3/L4(借款) | L8(财务费用) | 利息汇总 | L 内部 |
| 7 | H8(使用权资产) | H9(租赁负债) | CAS21 配对 | H 内部 |
| 8 | G7(长期股权投资) | I3(商誉) | 减值↔DCF | G↔I |
| 9 | L4(应付债券) | G4(债权投资) | 实际利率法对称 | L↔G |
| 10 | N1/N3(递延税) | D~M(全部) | 暂时性差异=账面-计税 | 全局→N |
| 11 | F2-47(跌价) | B51(舞弊) | 会计估计风险 | B→F |
| 12 | J2(精算) | B51(舞弊) | 会计估计风险 | B→J |
| 13 | G13(公允价值变动) | G1(交易性金融资产) | 差额联动 | G 内部 |
| 14 | G11(投资收益) | G7(长期股权投资) | 权益法收益 | G 内部 |

## 6. 各循环 spec 规模速查表

| 循环 | spec 目录 | requirements 特有需求数 | design 数据模型条目 | tasks 任务数 | wp_code 估算 | 特殊性 |
|------|----------|---------------------|-------------------|------------|-------------|--------|
| D | d-cycle-workpapers | 7 组 G0~G7 | ~55 条 | 47（38完成） | 55 | 已实施参考 |
| E | e-cycle-workpapers | 2 组 G0~G1 | ~35 条 | 39 | 35 | 单科目+IPO |
| F | f-cycle-workpapers | 6 组 G0~G5 | ~80 条 | 58 | 80 | 最复杂（存货72子底稿） |
| G | g-cycle-workpapers | 15 组 G0~G14 | ~90 条 | 50 | 90 | 科目最多（14科目+函证） |
| H | h-cycle-workpapers | 11 组 H0~H10 | ~65 条 | 46 | 65 | CAS21 租赁配对 |
| I | i-cycle-workpapers | 6 组 I1~I6 | ~40 条 | 38 | 40 | DCF/商誉减值 |
| J | j-cycle-workpapers | 3 组 J1~J3 | ~24 条 | 32 | 24 | 精算/期权模型 |
| K | k-cycle-workpapers | 14 组 K0~K13 | ~75 条 | 49 | 75 | 含函证+"其他"类 |
| L | l-cycle-workpapers | 9 组 L0~L8 | ~50 条 | 43 | 50 | 实际利率法 |
| M | m-cycle-workpapers | 10 组 M1~M10 | ~50 条 | 46 | 50 | 无函证/无控制测试(用C1) |
| N | n-cycle-workpapers | 5 组 N1~N5 | ~35 条 | 40 | 32 | 所得税计算终点 |
| S | s-cycle-workpapers | 5 大类 91 底稿 | 90 条 | 47 | 90 | 纯消费者/无审定表/无C类 |
| **合计** | | | **~689 条** | **~535** | **~686** | |

## 7. 执行顺序建议（P0 可全部并行）

### 7.1 P0 注册阶段——全部可并行

所有循环的 P0（wp_account_mapping + _WP_CODE_OVERRIDE）**互不依赖**，可同时执行。建议按已有基础量排序：
1. D（已完成 ✅）、C（已完成 ✅）
2. E~N + S（均为 P0 待执行）

### 7.2 P1 程序表——全部可并行

各循环程序表互不依赖，只要 P0 注册完成即可提取。

### 7.3 P2 审定表回写——有共享 handler

统一 handler `_on_audit_determination_saved` 的正则已设计为 `^[D-N]\d+-1$`，D 类已实现。E~N 只需确认正则覆盖即可（零新增代码）。

### 7.4 P5* 联动——有前后依赖

| 联动 | 前置条件 |
|------|---------|
| M6 损益联动 | D~N 全部审定表 P2 完成 |
| N5 所得税计算 | D~N 全损益 + I6 研发加计 |
| S→D~N 读取 | D~N 审定表数据就位 |
| A17 结论汇总 | D~N + S 全部完成 |

## 8. 各循环 spec 三件套改进建议

### 8.1 已发现的问题

| # | 问题 | 影响范围 | 修正方案 |
|---|------|---------|---------|
| 1 | C 类控制测试编号各循环自编 | E~N 全部 | 统一参照§2映射表 |
| 2 | P5* 联动任务全标可选 | E~N 全部 | 审定表回写(P2)和风险/C 联动(P0自带)是必做；跨循环联动(P5)确实可后补 |
| 3 | 缺全局执行顺序指导 | 全部 | 参照§7 |
| 4 | E~N design 缺 Correctness Properties | G/H/I/J/K/L/M/N | 需按 D/E/S 模式补全 |
| 5 | G~N requirements 联动矩阵偏简 | G/H/I/J/K/L/M/N | 需补跨循环联动行 |
| 6 | auto_data_source resolver 状态不统一 | 全部 | 已有 resolver 清单见§9 |

### 8.2 格式规范（已验证一致的）

- ✅ 文档结构：概述/现状/术语/分组/详细需求/联动矩阵/技术约束/分期/经验教训
- ✅ Phase 分期：P0注册→P1程序表→P2审定表→P3坐标→P4特殊程序→P5*联动→P6 E2E
- ✅ componentType 选型统一原则
- ✅ tasks.md 格式统一

## 9. auto_data_source resolver 全局清单

### 已实现（B/C/D 类已完成）

| resolver 名 | 功能 | 消费方 |
|-------------|------|--------|
| `risk_for_cycle` | B50→程序表风险展示 | D~N 全部程序表 |
| `control_test_result_for_cycle` | C→程序表控制测试结论 | D~N 全部程序表 |
| `b23_walkthrough_for_cycle` | B23→C 穿行测试结论 | C2~C14 控制测试底稿 |
| `confirmation_summary_for_cycle` | 函证摘要 | D0/E0/F0/G0/H0/K0/L0 |
| `_on_audit_determination_saved` | 审定表→trial_balance 回写 | D~N 全部审定表 |
| `_on_b23_saved` | B23 穿行→C 联动 field_overrides | C2~C14 |
| `_on_b50_saved` | B50 风险→D~N field_overrides | D~N 程序表 |
| `_on_c_control_test_saved` | C 控制测试→循环 field_overrides | D~N 程序表 |

### 需新增（按优先级）

| resolver 名 | 功能 | 消费方 | 所属 spec |
|-------------|------|--------|----------|
| `accounting_estimate_b51` | B51 舞弊三因素 | F2-47/J2/S14 | f/j/s-cycle |
| `related_party_transactions` | 关联方交易数据 | F2-52/G/K | f/g/k-cycle |
| `revenue_audited_for_s20` | D4 营业收入审定额 | S20 | s-cycle |
| `eps_data_from_tb` | 净利润/股本 | S15 | s-cycle |
| `non_recurring_items_from_tb` | 损益科目→非经常性 | S17 | s-cycle |
| `cycle_audited_amounts` | D~N 审定额 | S32~S35 | s-cycle |
| `net_profit_for_m6` | D~N 损益合计→M6 | M6 | m-cycle |
| `rd_super_deduction_for_n5` | I6→N5 研发加计 | N5 | n-cycle |

## 10. 用户提示（开发时必看）

### 10.1 开始执行任一循环前

1. **先确认 D 类参照实现仍正常**——跑 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 确认基线绿
2. **查本文档§2 确认 C 类编号和 B23 穿行编号**——不要自编控制测试编号
3. **查本文档§4 确认是否含函证**——含则需在 `_WP_CODE_OVERRIDE` 加 `confirmation-hub`
4. **查§5 横向联动**——如果目标循环涉及跨循环联动，检查依赖循环 P2 是否已完成
5. **B23→C→D~N 三层链路**——C 类底稿需要读取对应 B23 穿行测试结论（`b23_walkthrough_for_cycle`）；D~N 程序表需要读取 C 控制测试结论和 B50 风险评估

### 10.2 P0 注册阶段注意

- `wp_account_mapping.json` 新增条目必须有 `wp_code`/`wp_name`/`must_have`/`cycle` 四字段
- `_WP_CODE_OVERRIDE` 新增条目必须在 `test_render_config_smoke.py` 中验证覆盖
- IPO 适用性底稿必须设置 `applicable_when` 字段

### 10.3 P2 审定表回写阶段注意

- **无需新写 handler**——D 类已实现的 `_on_audit_determination_saved` 正则 `^[D-N]\d+-1$` 自动覆盖全部 E~N 审定表
- 只需确认新增 wp_code 的审定表确实命名为 `{Cycle}{n}-1` 格式
- 如有特殊命名（如"E1-1 审定表"本身是标准格式则无需额外配置）

### 10.4 P5* 联动开发顺序建议

```
1. M6 损益联动 ← 需 D~N 全部审定表就位（最后做）
2. N5 所得税  ← 需 I6 研发 + D~N 损益
3. S→D~N     ← 需 D~N 审定数据
4. A17 汇总   ← 需 D~N + S 全部结论
```

### 10.5 不要做的事

- ❌ 不要为 S 类创建审定表回写 handler（S 类无科目余额）
- ❌ 不要为 M 类创建独立 C 类控制测试引用（M 用 C1 企业层面控制）
- ❌ 不要为 S 类注册 risk_for_cycle/control_test_result_for_cycle（S 不对应单一风险）
- ❌ 不要对行业特殊科目（H5油气/H7生物/M8风险准备）强制 must_have=true

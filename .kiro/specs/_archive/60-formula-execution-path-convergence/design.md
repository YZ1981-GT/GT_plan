# 设计：公式执行路径收敛（含 Step 3 评估结论）

> spec: `formula-execution-path-convergence` · requirements R1~R5

## §1~§8 见提交 a8cbb1b45（Phase 1+2 已实施）

## §9 Step 3 评估结论：report_engine 不改走 preloader

### 调研发现

1. `ConsolTrialResolver` **零实例化**（合并报表已走独立管线 `consol_report_values.BasisResolver`）
2. `evaluate_formula_result` 只有 3 个调用方（ReportFormulaParser ×2 + cross_check_rules ×1）
3. `ReportFormulaParser` 有 `_use_unadjusted`（未审模式）和 `_use_opening`（期初模式）两个特殊模式
4. PREV/AUX 在报表路径**刻意硬置 0**：上期数通过 `PriorPeriodResolver` 三策略处理（本年期初 / 同年度上年 / 真实上年项目），不走 PREV() 函数
5. `PriorPeriodResolver` 自身创建 `ReportFormulaParser` 实例形成递归取数链

### 收益 vs 风险

| 维度 | 评估 |
|------|------|
| 安全收益 | **零**（已走 L1 内核） |
| 性能收益 | **有限**（parser 有实例级缓存 `_tb_cache`/`_tb_prefix_cache`） |
| 代码简化 | 消除 ~30 行 regex 预替换 |
| 改动面 | 需支持 unadjusted/opening 模式 + PriorPeriodResolver 递归 + 960+ 测试 |
| 风险 | **高**（报表生成是全平台最核心路径） |

### 决策

**report_engine 的 L2 预替换保持原样**。三条路径的当前状态：

```
路径 A（报表生成）: regex 预替换 → L1 execute    ✅ 已走 L1
路径 B（底稿预填充）: preload → L1 execute        ✅ 本 spec 已收敛
路径 C（公式管理页）: from_simple_map → L1 execute ✅ 已走 L1
```

### Step 3 替代方案：cross_check + 路径一致性守卫

`cross_check_rules._evaluate` 改走 preloader（消除它对 `evaluate_formula_result` 的依赖），并建立路径一致性守卫确保三条路径对同一公式给出同一结果。

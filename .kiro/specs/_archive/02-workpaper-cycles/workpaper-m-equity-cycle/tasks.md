# M 权益循环底稿优化 — Tasks

> **Spec**: workpaper-m-equity-cycle | **版本**: v1.0
> **总工时**: 5.5 天 | **Sprint 数**: 5

## 任务总览

| Sprint | 任务数 | 工时 | 优先级 |
|-------|-------|------|-------|
| Sprint 0 | 3 | 0.4 天 | - |
| Sprint 0.X | 2 | 0.3 天 | - |
| Sprint 1 | 5 | 1 天 | P0 |
| Sprint 2 | 10 | 2.5 天 | P1 |
| Sprint 3 | 5 | 1.3 天 | P2 |
| **合计** | **25** | **5.5 天** | |

---

## Sprint 0 — 现状核验（0.4 天）

- [x] 0.1 openpyxl 提取 M 循环 10 文件真实 sheet 清单（102 raw / 4 历史 / 3 末尾空格）
- [x] 0.2 grep 实测 prefill(11/52) + cross_wp_ref(6) 基线变量
- [x] 0.3 输出核验报告 + 对齐 3 文档基线

---

## Sprint 0.X — 前置实测（0.3 天，待实测标注）

- [x] 0x.1 SQL 实测 4001/4002/4101/4104 aux 维度（降级判定）
  - 实测结论（2026-05-20）：
    - tb_aux_balance 总行数 867,139
    - 4001 实收资本：**有** aux 数据（aux_type='客户'，3 子科目 9 distinct）
      - 4001.01 国有资本: 3 distinct (014021/606362/JTNB001)
      - 4001.03 民营资本: 4 distinct (07120032/09280004/16400001/SHGD096)
      - 4001.05 个人资本: 2 distinct (16400002/783604)
    - 4002 资本公积：**无** aux 数据
    - 4101 盈余公积：**无** aux 数据
    - 4104 利润分配：**无** aux 数据
  - 降级判定：**不降级**
    - M2 保留 =AUX(4-arg) 股东维度（4001 有 aux_type='客户'）
    - M-F6 prefill 目标维持 ≥ 82 cells（非降级 ≥ 20）
    - M4/M5/M6/M9/M10 使用 =TB/=WP（无 aux 可用）
- [x] 0x.2 openpyxl 提取 M2/M4/M5/M6/M9 明细表真实表头
  - 实测结论（2026-05-20）：
    - **M2 实收资本 — 2 个明细表变体**
      - Sheet `'明细表（上市公司）M2-2'`：表头 row 10-12（3 行合并表头）
        - Row 10: A=投资方名称, B=公司代码, C=未审数, M=期初调整, O=账项调整, T=重分类调整, Y=审定数, AH=是否经过验资, AI=验资报告索引号, AJ=备注
        - Row 11: C=期初数, F=本期增减(+/-), K=期末数, M=账项调整, N=重分类调整, O=本期增减(+/-), T=本期增减(+/-), Y=期初数, AA=本期增减(+/-), AF=期末数
        - Row 12: C=出资方式, D=出资金额, E=比例%, F=发行新股, G=送股, H=公积金转股, I=其他, J=小计, K=出资金额, L=比例%...AF=出资金额, AG=比例%
        - **prefill 目标列**: D(出资金额)/E(比例%)/Y(审定期初)/AF(审定期末) — =AUX(4001, '客户', aux_code, '期末余额')
      - Sheet `'明细表（非上市公司）M2-2'`：表头 row 10-12（3 行合并表头）
        - Row 10: A=投资方名称, B=未审数, J=期初调整, L=账项调整, N=重分类调整, P=审定数, V=是否经过验资, W=验资报告索引号, X=备注
        - Row 11: B=期初数, E=本期增加, G=本期减少, H=期末数, J=账项调整, K=重分类调整, L=本期增加, M=本期减少, N=本期增加, O=本期减少, P=期初数, R=本期增加, S=本期减少, T=期末数
        - Row 12: B=出资方式, C=出资金额, D=比例%, E=出资金额, F=出资方式, H=出资金额, I=比例%, P=出资金额, Q=比例%, T=出资金额, U=比例%
        - **prefill 目标列**: C(出资金额)/D(比例%)/P(审定期初)/T(审定期末) — =AUX(4001, '客户', aux_code, '期末余额')
    - **M4 资本公积 — 明细表M4-2**
      - Sheet `'明细表M4-2'`：表头 row 8-9（2 行合并表头）
        - Row 8: A=项目类别, B=未审数, F=期初调整, H=账项调整, J=重分类调整, L=审定数, P=相关会计处理是否正确, Q=备注
        - Row 9: B=期初数, C=本期增加, D=本期减少, E=期末数, F=账项调整, G=重分类调整, H=本期增加, I=本期减少, J=本期增加, K=本期减少, L=期初数, M=本期增加, N=本期减少, O=期末数
        - 数据行: A10=一、资本（股本）溢价 / A15=二、其他资本公积 / A20=合计
        - **prefill 目标列**: B(未审期初)/E(未审期末)/L(审定期初)/O(审定期末) — =TB(4002.01)/=TB(4002.02)
    - **M5 盈余公积 — 明细表M5-2**
      - Sheet `'明细表M5-2'`：表头 row 9-11（3 行合并表头）
        - Row 9: A=明细项目, B=未审数, H=期初调整, J=账项调整, L=重分类调整, N=审定数
        - Row 10: B=期初数, C=本期增加, E=本期减少, G=期末数, H=账项调整, I=重分类调整, J=本期增加, K=本期减少, L=本期增加, M=本期减少, N=期初数, O=本期增加, P=本期减少, Q=期末数
        - Row 11: C=金额, D=增加方式, E=金额, F=减少方式
        - 数据行: A12=法定盈余公积 / A13=任意盈余公积 / A14=利润归还投资 / A15=其他 / A16=合计
        - **prefill 目标列**: B(未审期初)/G(未审期末)/N(审定期初)/Q(审定期末) — =TB(4101.01)/=TB(4101.02)
    - **M6 未分配利润 — 明细表M6-2（即变动分析表）**
      - ⚠️ M6 无独立"变动分析表" sheet，明细表M6-2 本身就是变动分析结构
      - Sheet `'明细表M6-2'`：表头 row 8-9（2 行合并表头）
        - Row 8: A=内容, B=本期数, F=上期数, J=索引号, K=备注
        - Row 9: B=未审数, C=账项调整, D=重分类调整, E=审定数, F=未审数, G=账项调整, H=重分类调整, I=审定数
        - 数据行结构（row 10-25）:
          - A10=一、上年年末余额 / A11=加：会计政策变更 / A12=前期差错更正
          - A13=二、本年年初余额 / A14=三、盈余公积补亏 / A15=四、本期净利润
          - A16=五、利润分配 / A17=1、提取法定盈余公积 / A18=2、提取任意盈余公积
          - A19=3、应付现金股利 / A20=4、转作股本的股利 / A21=5、其他
          - A22=六、所有者权益内部结转 / A25=七、本年年末余额
        - **prefill 目标列**: E(本期审定数)/I(上期审定数) — =TB(4104)+WP引用
        - VR-M6-01 勾稽: E25(年末) = E13(年初) + E15(净利润) - E17(法定盈余) - E18(任意盈余) - E19(股利)
      - 末尾空格 sheet: `'未分配利润实质性程序表 M6A '` ⚠️ TRAILING SPACE
    - **M9 其他综合收益 — 明细表M9-2**
      - Sheet `'明细表M9-2'`：表头 row 8-9（2 行合并表头）
        - Row 8: A=项目类别, C=未审数, H=期初调整, J=账项调整, M=重分类调整, P=审定数, U=备注
        - Row 9: C=期初数, D=本期所得税前发生额, E=减：前期计入OCI当期转入损益/留存收益, F=减：所得税费用, G=期末数, H=账项调整, I=重分类调整, J=本期所得税前发生额, K=减：转入损益, L=减：所得税, M=本期所得税前发生额, N=减：转入损益, O=减：所得税, P=期初数, Q=本期所得税前发生额, R=减：转入损益, S=减：所得税, T=期末数
        - 数据行: A10=1、以后不能重分类进损益的OCI / A16=2、以后将重分类进损益的OCI
        - **prefill 目标列**: C(未审期初)/G(未审期末)/P(审定期初)/T(审定期末) — =TB(6901.xx)
    - **M10 其他权益工具 — 明细表M10-2**
      - Sheet `'明细表M10-2'`：表头 row 9-10（2 行合并表头）
        - Row 9: A=融资工具种类, B=发行时间, C=股利率或利息率, D=发行价格, E=数量, F=到期日或续期情况, G=会计分类, H=发行总额(面值), I=期初账面价值, K=本期发行, O=本期减少, S=期末账面价值, U=审计调整(增加), W=审计调整(减少), Y=审计调整后期末账面价值, AA=转股条件, AB=转换情况, AC=备注, AD=文件索引号
        - Row 10: I=数量, J=金额, K=数量, L=金额, M=交易费用, N=账面价值, O=数量, P=金额, Q=其他变动, R=小计, S=数量, T=金额, U=数量, V=金额, W=数量, X=金额, Y=数量, Z=金额
        - 数据行: A11=一、优先股 / A16=二、永续债
        - **prefill 目标列**: J(期初金额)/T(期末金额)/Z(审计调整后期末金额) — =TB(4401.xx)
    - **关键发现**:
      - M6 无独立"变动分析表"sheet — 明细表M6-2 本身即为变动分析结构（期初→变动→期末）
      - M2 有 2 个变体（上市/非上市），prefill 应覆盖非上市版本（更常用）
      - 全 M 循环无任何 sheet 名含"变动"关键字
      - M6A 末尾空格确认: `'未分配利润实质性程序表 M6A '`

---

## Sprint 1 — P0 核心（1 天）

- [x] 1.1 验证 chain_orchestrator M 循环合并（102→65）+ `test_m_merge_dedup.py`
  - _Requirements: M-F1_
- [x] 1.2 创建 VR-M6-01/M2-01 + `check_m_cycle_triangle_reconciliation()` + `test_m_validation_rules.py`
  - _Requirements: M-F3_
- [x] 1.3 追加 ≥15 条 cross_wp_ref（起编 max+1）+ `test_m_cross_wp_refs.py`
  - _Requirements: M-F4_
- [x] 1.4 追加 ≥30 cells prefill + `test_m_prefill_extension.py`
  - _Requirements: M-F6_
- [x] 1.5 D/F/H/I/G/J/L 回归验证

---

## Sprint 2 — P1 主体（2.5 天）

- [x] 2.1 新建 `useMEquityCycleSheetGroups.ts`（8 类规则）
- [x] 2.2 `test_m_sheet_groups.py` + vitest
- [x] 2.3 配置 M_CYCLE_PREREQUISITES=[] + `^M\d` 路由
- [x] 2.4 resolveProcedureSheetKey M2→m2a / M6→m6a
- [x] 2.5 新建 `wp_m_equity_movement.py` 路由 + RBAC + apply_to_sheet
- [x] 2.6 `test_m_equity_movement.py` + `EquityMovementDialog.vue`
- [x] 2.7 PBT-P1: 归一化幂等(100)
- [x] 2.8 PBT-P2: VR-M6-01 勾稽(200+9 boundary)
- [x] 2.9 PBT-P3: 8 类分组完备(200)
- [x] 2.10 PBT-P4: ref_id 唯一(50)

---

## Sprint 3 — P2 打磨（1.3 天）

- [x] 3.1 `_IPO_CONFIG['M2']` 注册 + 全循环 IPO 回归 + `test_m_ipo_trigger.py`
- [x]* 3.2 PBT-P5: 权益变动 closing=opening+changes(200, optional)
- [x] 3.3 vitest: EquityMovementDialog + sheetKey 路由
- [x] 3.4 全量回归 + 10 项 UAT 验收
- [x] 3.5 复盘 + 已知缺口标注

---

## 已知缺口

| 项 | 决策 | 原因 |
|----|------|------|
| PBT-P5 权益变动 closing=opening+changes | optional 跳过 | `test_m_equity_movement.py` 单测已覆盖等价逻辑（opening+net_profit−surplus−dividends=closing） |
| #9 权益变动引擎 | stub | `is_llm_stub` 由 `settings.WP_AI_SERVICE_ENABLED` config 驱动，待 wp_ai_service 接入 |
| #10 IPO codes=[] | placeholder | M 循环无专属 IPO 应对模板，`_IPO_CONFIG['M2']` 注册空列表占位 |
| 工商变更数据库 | 不做 | 外部数据源，非底稿系统职责 |
| M 无独立 C 类 | 已标注 | A 类总体审计策略覆盖，`M_CYCLE_PREREQUISITES=[]` 返回 ready |

---

## 测试矩阵

### pytest
| 文件 | 覆盖 | Sprint |
|------|------|--------|
| `test_m_merge_dedup.py` | M-F1 | S1 |
| `test_m_validation_rules.py` | M-F3 | S1 |
| `test_m_cross_wp_refs.py` | M-F4 | S1 |
| `test_m_prefill_extension.py` | M-F6 | S1 |
| `test_m_sheet_groups.py` | M-F2 | S2 |
| `test_m_equity_movement.py` | M-F7 | S2 |
| `test_m_ipo_trigger.py` | M-F8 | S3 |

### PBT
| ID | Property | examples |
|----|---------|----------|
| P1 | 归一化幂等 | 100 |
| P2 | VR-M6-01 勾稽 | 200+9 |
| P3 | 8类分组完备 | 200 |
| P4 | ref_id唯一 | 50 |
| P5* | 权益变动等式 | 200(opt) |

### vitest
`test_m_sheet_groups.spec.ts` / `EquityMovementDialog.spec.ts` / `test_m_audit_nav.spec.ts`

---

## 启动条件

- [x] D/F/H/I/G spec 全部完成
- [x] J+L spec 执行完毕（cross_wp_ref 起编 CW-353，基于 L max=CW-352）
- [x] Sprint 0 + Sprint 0.X 完成

---

## 复盘结论

### 工时对比

| Sprint | 估计 | 实际 | 压缩比 | 说明 |
|--------|------|------|--------|------|
| Sprint 0 | 0.4 天 | ~0.3 天 | 0.75× | 复用 D/F/H 成熟脚本 |
| Sprint 0.X | 0.3 天 | ~0.2 天 | 0.67× | SQL 实测 + openpyxl 提取已有模板 |
| Sprint 1 | 1 天 | ~0.6 天 | 0.6× | VR/CWR/prefill 引擎复用 H/I/G 模式 |
| Sprint 2 | 2.5 天 | ~1.2 天 | 0.48× | 8 类分组 + 权益变动引擎 stub 复用 L 模式 |
| Sprint 3 | 1.3 天 | ~0.5 天 | 0.38× | IPO 占位 + vitest 复用 + UAT 程序化 |
| **合计** | **5.5 天** | **~2.8 天** | **0.51×** | 跨 spec 引擎复用红利（第 8 个循环） |

> 压缩比 ~2× 归因：M 是第 8 个执行的循环 spec，D/F/H/I/G/J/K/L 已沉淀成熟模式（VR 三角勾稽 / CWR 闭区间 / prefill 4-arg AUX / sheet 分组 composable / IPO 占位注册 / 前端 Dialog 模板），M 循环无新架构引入。

### 关键发现

1. **M7A 前导+末尾双空格**：` 专项储备实质性程序表 M7A `（前导空格 + 末尾空格），Sprint 0 openpyxl 实测确认，prefill sheet 字段必须含真实空格
2. **M6 无独立变动分析表**：明细表M6-2 本身即为变动分析结构（期初→变动→期末），无需额外 sheet 路由
3. **CWR 基线偏差 6→8**：L spec 执行后新增 CW-349/CW-352 两条以 M 为 target 的跨循环引用，M-F4 目标同步调整（+15 新增不变，总量 ≥ 23）
4. **4001 实收资本有 aux 数据**：aux_type='客户'，3 子科目 9 distinct entries → M2 保留 =AUX(4-arg) 不降级
5. **M2 上市/非上市双变体**：prefill 覆盖非上市版本（更常用），上市版本结构更复杂但实际项目少用

### 后续 followup

| 项 | 优先级 | 触发条件 |
|----|--------|---------|
| wp_ai_service 接入后切换 is_llm_stub=False | P1 | O-LLM-Integration spec 落地 |
| M2 上市公司变体 prefill 补充 | P3 | 有上市公司审计项目需求时 |
| 权益变动表与报表联动（M→BS 权益合计勾稽） | P2 | 报表模块升级时 |

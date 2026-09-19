# S 类底稿（专项循环）— 设计文档

## 1. 架构总览

S 类底稿复用已验证的渲染管线（与 B/C/D~N 类一致）：

```
wp_account_mapping.json (新增 S 类 90 条)
  → WpClassificationService (_WP_CODE_OVERRIDE)
    → get_render_config (componentType 分发)
      → 前端 htmlRendererRegistry → 对应 Vue 组件
```

### 1.1 设计决策

**不使用 generic schema**：S 类各底稿结构差异极大：
- 有的是程序表（S1~S16 部分）
- 有的是逐项检查表（S4/S5/S6/S32/S33/S34/S35）
- 有的是计算表（S15/S17）
- 有的是 .docx 文档（S12A/S33-REV/S34-1-1）

因此按 wp_code 逐一映射 componentType，不设 S-generic.yaml。

**S 类无审定表回写**：S 类不对应具体科目余额，不存在 `{n}-1` 审定表，无需 trial_balance 回写。

**S 类无函证/无控制测试**：不注册 confirmation-hub，不注册 risk_for_cycle/control_test_result_for_cycle。

### 1.2 componentType 路由规划

| wp_code 模式 | componentType | 前端组件 | 说明 |
|-------------|--------------|---------|------|
| S1/S2/S3/S8/S10/S11/S13 | `a-program-console` | GtAProgramConsole | 程序表式 |
| S4/S5/S6/S9/S12/S14/S16 | `d-form-table` | GtDFormTable | 检查表式 |
| S15/S17 | `audit-sheet` | GtAuditSheet | 计算表 |
| S20/S21 | `d-form-table` | GtDFormTable | 新准则检查表 |
| S12A/S33-REV/S34-1-1 | `word-template` | WorkpaperWordEditor | docx 文档 |
| S32-1~S32-13 | `d-form-table` | GtDFormTable | IPO 专项核查 |
| S33-1~S33-9 | `d-form-table` | GtDFormTable | 综合核查 |
| S34-0~S34-41 | `d-form-table` | GtDFormTable | 证监会核查事项 |
| S35-1~S35-5 | `d-form-table` | GtDFormTable | 再融资核查 |

## 2. 数据模型

### 2.1 wp_account_mapping 新增（90 条）

**S1~S17 特殊审计考虑事项（18 条）：**

| wp_code | wp_name | must_have | componentType |
|---------|---------|-----------|---------------|
| S1 | 违反法规行为的考虑 | true | a-program-console |
| S2 | 首次接受委托期初余额 | true | a-program-console |
| S3 | 会计政策变更/前期差错/估计变更 | true | a-program-console |
| S4 | 非货币性资产交换 | false | d-form-table |
| S5 | 债务重组 | false | d-form-table |
| S6 | 大股东资金占用/违规担保 | false | d-form-table |
| S8 | 租赁 | true | a-program-console |
| S9 | 电子商务考虑 | false | d-form-table |
| S10 | 环境事项考虑 | false | a-program-console |
| S11 | 利用服务机构 | false | a-program-console |
| S12 | 利用专家工作 | false | d-form-table |
| S12A | 评估专家报告 | false | word-template |
| S13 | 利用管理层专家 | false | a-program-console |
| S14 | 会计估计和相关披露 | true | d-form-table |
| S15 | 每股收益和净资产收益率 | false | audit-sheet |
| S16 | 套期活动 | false | d-form-table |
| S17 | 非经常性损益 | false | audit-sheet |

**S20~S21 新准则底稿（2 条）：**

| wp_code | wp_name | must_have | componentType |
|---------|---------|-----------|---------------|
| S20 | 营业收入扣除情况核查 | true | d-form-table |
| S21 | 数据资产 | false | d-form-table |

**S32 IPO 专项核查（13 条）：**

| wp_code | wp_name | must_have | applicable_when |
|---------|---------|-----------|-----------------|
| S32-1 | IPO核查-自我交易 | false | ipo/listed/neeq |
| S32-2 | IPO核查-串通 | false | ipo/listed/neeq |
| S32-3 | IPO核查-关联方代付 | false | ipo/listed/neeq |
| S32-4 | IPO核查-利益输送 | false | ipo/listed/neeq |
| S32-5 | IPO核查-体外资金 | false | ipo/listed/neeq |
| S32-6 | IPO核查-互联网造假 | false | ipo/listed/neeq |
| S32-7 | IPO核查-资本化 | false | ipo/listed/neeq |
| S32-8 | IPO核查-压缩薪金 | false | ipo/listed/neeq |
| S32-9 | IPO核查-延迟费用 | false | ipo/listed/neeq |
| S32-10 | IPO核查-资产减值 | false | ipo/listed/neeq |
| S32-11 | IPO核查-延迟转固 | false | ipo/listed/neeq |
| S32-12 | IPO核查-其他粉饰 | false | ipo/listed/neeq |
| S32-13 | IPO核查-期后下滑 | false | ipo/listed/neeq |

**S33 综合核查（10 条）：**

| wp_code | wp_name | must_have | applicable_when |
|---------|---------|-----------|-----------------|
| S33-1 | 综合核查-内控制度 | false | ipo/listed/neeq |
| S33-2 | 综合核查-财务非财务印证 | false | ipo/listed/neeq |
| S33-3 | 综合核查-盈利异常 | false | ipo/listed/neeq |
| S33-4 | 综合核查-关联方 | false | ipo/listed/neeq |
| S33-5 | 综合核查-收入毛利 | false | ipo/listed/neeq |
| S33-6 | 综合核查-客户供应商 | false | ipo/listed/neeq |
| S33-7 | 综合核查-存货资产 | false | ipo/listed/neeq |
| S33-8 | 综合核查-现金收付 | false | ipo/listed/neeq |
| S33-9 | 综合核查-财务异常 | false | ipo/listed/neeq |
| S33-REV | 综合核查-程序修订说明 | false | ipo/listed/neeq |

**S34 证监会核查事项（43 条）：**

| wp_code | wp_name | must_have | applicable_when |
|---------|---------|-----------|-----------------|
| S34-0 | 证监会核查事项清单 | false | ipo/listed/neeq/refinancing |
| S34-1 | 证监会-涉秘豁免 | false | ipo/listed/neeq/refinancing |
| S34-1-1 | 信息披露豁免专项核查意见 | false | ipo/listed/neeq/refinancing |
| S34-2 | 证监会-期权 | false | ipo/listed/neeq/refinancing |
| S34-3 | 证监会-股份支付 | false | ipo/listed/neeq/refinancing |
| S34-4 | 证监会-关联交易 | false | ipo/listed/neeq/refinancing |
| S34-5 | 证监会-应收减值 | false | ipo/listed/neeq/refinancing |
| S34-6 | 证监会-固定资产 | false | ipo/listed/neeq/refinancing |
| S34-7 | 证监会-税收优惠 | false | ipo/listed/neeq/refinancing |
| S34-8 | 证监会-合并无形 | false | ipo/listed/neeq/refinancing |
| S34-9 | 证监会-共同投资 | false | ipo/listed/neeq/refinancing |
| S34-10 | 证监会-财务性投资 | false | ipo/listed/neeq/refinancing |
| S34-11 | 证监会-业务重组 | false | ipo/listed/neeq/refinancing |
| S34-12 | 证监会-经营下滑 | false | ipo/listed/neeq/refinancing |
| S34-13 | 证监会-持续经营 | false | ipo/listed/neeq/refinancing |
| S34-14 | 证监会-财务内控 | false | ipo/listed/neeq/refinancing |
| S34-15 | 证监会-现金交易 | false | ipo/listed/neeq/refinancing |
| S34-16 | 证监会-第三方回款 | false | ipo/listed/neeq/refinancing |
| S34-17 | 证监会-会计政策 | false | ipo/listed/neeq/refinancing |
| S34-18 | 证监会-第三方数据 | false | ipo/listed/neeq/refinancing |
| S34-19 | 证监会-经销商 | false | ipo/listed/neeq/refinancing |
| S34-20 | 证监会-劳务外包 | false | ipo/listed/neeq/refinancing |
| S34-21 | 证监会-委外加工 | false | ipo/listed/neeq/refinancing |
| S34-22 | 证监会-股权集中 | false | ipo/listed/neeq/refinancing |
| S34-23 | 证监会-互联网系统 | false | ipo/listed/neeq/refinancing |
| S34-24 | 证监会-信息系统 | false | ipo/listed/neeq/refinancing |
| S34-25 | 证监会-资金流水 | false | ipo/listed/neeq/refinancing |
| S34-26 | 证监会-未盈利 | false | ipo/listed/neeq/refinancing |
| S34-27 | 证监会-研发认定 | false | ipo/listed/neeq/refinancing |
| S34-28 | 证监会-研发资本化 | false | ipo/listed/neeq/refinancing |
| S34-29 | 证监会-政府补助 | false | ipo/listed/neeq/refinancing |
| S34-30 | 证监会-对赌 | false | ipo/listed/neeq/refinancing |
| S34-31 | 证监会-存货 | false | ipo/listed/neeq/refinancing |
| S34-32 | 证监会-期间费用 | false | ipo/listed/neeq/refinancing |
| S34-33 | 证监会-商誉减值 | false | ipo/listed/neeq/refinancing |
| S34-34 | 证监会-涉农 | false | ipo/listed/neeq/refinancing |
| S34-35 | 证监会-收入 | false | ipo/listed/neeq/refinancing |
| S34-36 | 证监会-投资收益 | false | ipo/listed/neeq/refinancing |
| S34-37 | 证监会-现金流异常 | false | ipo/listed/neeq/refinancing |
| S34-38 | 证监会-估值调整 | false | ipo/listed/neeq/refinancing |
| S34-39 | 证监会-应收票据融资 | false | ipo/listed/neeq/refinancing |
| S34-40 | 证监会-在建工程 | false | ipo/listed/neeq/refinancing |
| S34-41 | 证监会-客户供应商 | false | ipo/listed/neeq/refinancing |

**S35 再融资核查（5 条）：**

| wp_code | wp_name | must_have | applicable_when |
|---------|---------|-----------|-----------------|
| S35-1 | 再融资核查-关联交易 | false | refinancing |
| S35-2 | 再融资核查-财务性投资 | false | refinancing |
| S35-3 | 再融资核查-现金分红 | false | refinancing |
| S35-4 | 再融资核查-商誉减值 | false | refinancing |
| S35-5 | 再融资核查-募集资金收购 | false | refinancing |

### 2.2 _WP_CODE_OVERRIDE 完整映射表

```python
# S 类 — 专项循环
# ============================================
# S1~S17 特殊审计考虑事项（程序表式）
"S1": "a-program-console",
"S2": "a-program-console",
"S3": "a-program-console",
# S4~S6 检查表式
"S4": "d-form-table",
"S5": "d-form-table",
"S6": "d-form-table",
# S8~S11 程序表/检查表
"S8": "a-program-console",
"S9": "d-form-table",
"S10": "a-program-console",
"S11": "a-program-console",
# S12 利用专家
"S12": "d-form-table",
"S12A": "word-template",
# S13~S17
"S13": "a-program-console",
"S14": "d-form-table",
"S15": "audit-sheet",
"S16": "d-form-table",
"S17": "audit-sheet",
# S20~S21 新准则
"S20": "d-form-table",
"S21": "d-form-table",
# S32 IPO 专项核查（13 条）
"S32-1": "d-form-table",
"S32-2": "d-form-table",
"S32-3": "d-form-table",
"S32-4": "d-form-table",
"S32-5": "d-form-table",
"S32-6": "d-form-table",
"S32-7": "d-form-table",
"S32-8": "d-form-table",
"S32-9": "d-form-table",
"S32-10": "d-form-table",
"S32-11": "d-form-table",
"S32-12": "d-form-table",
"S32-13": "d-form-table",
# S33 综合核查（10 条）
"S33-1": "d-form-table",
"S33-2": "d-form-table",
"S33-3": "d-form-table",
"S33-4": "d-form-table",
"S33-5": "d-form-table",
"S33-6": "d-form-table",
"S33-7": "d-form-table",
"S33-8": "d-form-table",
"S33-9": "d-form-table",
"S33-REV": "word-template",
# S34 证监会核查事项（43 条）
"S34-0": "d-form-table",
"S34-1": "d-form-table",
"S34-1-1": "word-template",
"S34-2": "d-form-table",
"S34-3": "d-form-table",
"S34-4": "d-form-table",
"S34-5": "d-form-table",
"S34-6": "d-form-table",
"S34-7": "d-form-table",
"S34-8": "d-form-table",
"S34-9": "d-form-table",
"S34-10": "d-form-table",
"S34-11": "d-form-table",
"S34-12": "d-form-table",
"S34-13": "d-form-table",
"S34-14": "d-form-table",
"S34-15": "d-form-table",
"S34-16": "d-form-table",
"S34-17": "d-form-table",
"S34-18": "d-form-table",
"S34-19": "d-form-table",
"S34-20": "d-form-table",
"S34-21": "d-form-table",
"S34-22": "d-form-table",
"S34-23": "d-form-table",
"S34-24": "d-form-table",
"S34-25": "d-form-table",
"S34-26": "d-form-table",
"S34-27": "d-form-table",
"S34-28": "d-form-table",
"S34-29": "d-form-table",
"S34-30": "d-form-table",
"S34-31": "d-form-table",
"S34-32": "d-form-table",
"S34-33": "d-form-table",
"S34-34": "d-form-table",
"S34-35": "d-form-table",
"S34-36": "d-form-table",
"S34-37": "d-form-table",
"S34-38": "d-form-table",
"S34-39": "d-form-table",
"S34-40": "d-form-table",
"S34-41": "d-form-table",
# S35 再融资核查（5 条）
"S35-1": "d-form-table",
"S35-2": "d-form-table",
"S35-3": "d-form-table",
"S35-4": "d-form-table",
"S35-5": "d-form-table",
```

### 2.3 procedure_table_templates.json 扩展

仅对程序表式底稿注册：

```json
{
  "S1": {
    "name": "违反法规行为的考虑程序表",
    "items": [/* 从 S1.xlsx 提取 */]
  },
  "S2": {
    "name": "首次接受委托期初余额程序表",
    "items": [/* 从 S2.xlsx 提取 */]
  },
  "S3": {
    "name": "会计政策变更/前期差错/估计变更程序表",
    "items": [/* 从 S3.xlsx 提取 */]
  },
  "S8": {
    "name": "租赁程序表",
    "items": [/* 从 S8.xlsx 提取 */]
  },
  "S10": {
    "name": "环境事项考虑程序表",
    "items": [/* 从 S10.xlsx 提取 */]
  },
  "S11": {
    "name": "利用服务机构程序表",
    "items": [/* 从 S11.xlsx 提取 */]
  },
  "S13": {
    "name": "利用管理层专家程序表",
    "items": [/* 从 S13.xlsx 提取 */]
  }
}
```

> 注：S 类程序表与 D~N 不同——不以 `{n}A` 命名，而是底稿本身就是程序表（如 S1 整个就是程序表结构）。

### 2.4 auto_data_source resolvers（联动读取）

| source 名 | 用途 | 状态 |
|-----------|------|------|
| `revenue_audited_for_s20` | S20 从 D4 营业收入读取审定金额 | 🔴 需新增 |
| `eps_data_from_tb` | S15 从 trial_balance 读取净利润/股本 | 🔴 需新增 |
| `non_recurring_items_from_tb` | S17 从 trial_balance 读取损益科目 | 🔴 需新增 |
| `cycle_audited_amounts` | S32~S35 从 D~N 审定表读取数据 | 🔴 需新增 |
| `accounting_estimate_b51` | S14 读取 B51 会计估计风险 | ✅ 已有（F2-47 共用） |

新增 resolver 设计：

```python
@auto_resolver("revenue_audited_for_s20")
async def _resolve_revenue_for_s20(db, project_id, year, **kw):
    """从 D4 营业收入审定表读取收入金额和扣除项。"""
    # 查 trial_balance WHERE standard_account_code LIKE '6001%'
    return {"total_revenue": ..., "deductions": [...]}

@auto_resolver("eps_data_from_tb")
async def _resolve_eps_data(db, project_id, year, **kw):
    """从 trial_balance 读取净利润和股本数据供 S15 计算每股收益。"""
    return {"net_profit": ..., "shares_outstanding": ..., "weighted_avg_shares": ...}

@auto_resolver("cycle_audited_amounts")
async def _resolve_cycle_audited(db, project_id, year, cycle=None, **kw):
    """从指定循环的审定表读取审定金额，供 S32~S35 核查底稿引用。"""
    # 查 trial_balance 对应 cycle 的科目审定金额
    return {"accounts": [...], "total_audited": ...}
```

## 3. docx 文件配置

### 3.1 wpPopupDocxConfigs 注册

```typescript
// S 类 docx 弹窗配置
export const wpPopupDocxConfigsS: Record<string, DocxConfig> = {
  "S12A": {
    title: "评估专家报告",
    description: "利用专家工作—评估专家出具报告的评估",
    templatePath: "S/S12A 评估专家报告.docx",
    width: "75vw",
  },
  "S33-REV": {
    title: "综合核查程序修订说明",
    description: "IPO 综合核查程序修订说明文档",
    templatePath: "S/S33 程序修订说明.docx",
    width: "75vw",
  },
  "S34-1-1": {
    title: "信息披露豁免专项核查意见",
    description: "涉秘豁免信息披露专项核查意见书",
    templatePath: "S/S34-1-1 信息披露豁免专项核查意见.docx",
    width: "80vw",
  },
};
```

## 4. 联动实现方案

### 4.1 S 类是纯消费者

S 类从 D~N 循环读取数据，自身不向 trial_balance 写入。联动方向：

```
D~N 审定表 ──┐
trial_balance ─┤──→ S 类底稿（只读展示）
B50/B51 ──────┘
```

### 4.2 IPO 适用性前端展示

```typescript
// applicable_when 评估逻辑
function evaluateApplicability(wpCode: string, project: Project): boolean {
  const rules = {
    'S32': ['ipo', 'listed', 'neeq'],
    'S33': ['ipo', 'listed', 'neeq'],
    'S34': ['ipo', 'listed', 'neeq', 'refinancing'],
    'S35': ['refinancing'],
  };
  const prefix = wpCode.replace(/-\d+.*$/, ''); // S32-1 → S32
  const allowed = rules[prefix];
  if (!allowed) return true; // S1~S21 无限制
  return allowed.includes(project.business_category);
}
```

不适用时前端展示：灰显 + 覆盖层"本项目不适用此底稿"。

### 4.3 S→A17 结论被引用

A17 总结报告的章节"其他特殊考虑"(ch15) 需汇总 S 类底稿的结论。通过 auto_data_source 从 S 类已完成底稿读取结论字段。

## 5. address_registry 坐标注册

仅对 `audit-sheet` 类型底稿注册坐标（S15/S17）：

| wp_code | 关键坐标 | 用途 |
|---------|---------|------|
| S15 | 基本每股收益结果 | EPS 计算结论 |
| S15 | 稀释每股收益结果 | 稀释 EPS 结论 |
| S15 | 加权平均净资产收益率 | ROE 结论 |
| S17 | 非经常性损益合计 | 非经常性损益总额 |
| S17 | 扣除非经常性损益后净利润 | 扣非净利润 |

坐标数据维护：`backend/data/s_address_registry_seed.json`

## 6. 前端路由

不需要新的顶层页面。复用现有底稿路由：

```
/projects/:pid/workpapers/:wpId → GtWpRenderer → componentType 路由
```

S 类无 confirmation-hub 路由。

## 7. 正确性属性 (Correctness Properties)

### Property 1: S 类 wp_code 注册完整性

*For any* S 类模板文件，其 wp_code 必须存在于 `wp_account_mapping.json` 中。共 90 条。

### Property 2: _WP_CODE_OVERRIDE 覆盖率

*For any* 在 `wp_account_mapping.json` 中注册的 S 类 wp_code，必须在 `_WP_CODE_OVERRIDE` 中存在对应映射。

### Property 3: IPO 适用性控制

*For any* S32~S35 系列底稿，在普通年审项目中 applicable_when 评估结果为 False。

### Property 4: 程序表模板完整性

*For any* 程序表式 S 类底稿（S1/S2/S3/S8/S10/S11/S13），procedure_table_templates.json 中步骤数应 ≥ xlsx 模板程序步骤行数。

### Property 5: docx 文件配置完整性

*For any* S 类 .docx 文件（S12A/S33-REV/S34-1-1），wpPopupDocxConfigs 中必须存在对应配置。

### Property 6: componentType 与底稿类型一致性

程序表式底稿必须映射 `a-program-console`，检查表式必须映射 `d-form-table`，计算表必须映射 `audit-sheet`，docx 必须映射 `word-template`。

### Property 7: address_registry 坐标有效性

*For any* s_address_registry_seed.json 中的坐标，sheet_name 必须存在于对应模板文件中。

## 8. 错误处理

| 场景 | 处理方式 |
|------|---------|
| D~N 审定数据尚未填写 | S 类联动字段显示空值 + 提示"请先完成对应循环审定" |
| IPO 适用性判定失败（business_category 为空） | 默认显示（不灰显），允许手动判断 |
| trial_balance 无净利润/股本数据 | S15 显示空值，允许手动填写 |
| docx 模板文件不存在 | word-template 显示"模板文件未找到"提示 + 下载降级 |
| address_registry 坐标未注册 | custom_query 返回空值 |

## 9. 测试策略

### 9.1 单元测试

- wp_account_mapping S 类条目完整性校验（90 条）
- _WP_CODE_OVERRIDE S 类覆盖率校验（90 条映射）
- IPO 适用性条件评估（S32/S33/S34/S35 各系列 × 5 种项目类型）
- 程序表模板 JSON 结构校验（7 个程序表）
- docx 配置完整性（3 个 word-template）

### 9.2 集成测试

- S15 eps_data_from_tb resolver 返回结构校验
- S20 revenue_audited_for_s20 resolver 从 trial_balance 读取验证
- cycle_audited_amounts resolver 多循环读取验证

### 9.3 E2E（Playwright）

- S1 程序表打开 + 步骤展示
- S14 检查表打开 + 填写"适用/不适用"
- S15 计算表 OnlyOffice 打开
- S12A docx 弹窗预览/编辑
- S32-1 IPO 底稿打开 + 普通年审项目灰显
- S34-0 证监会清单打开 + 子项状态汇总

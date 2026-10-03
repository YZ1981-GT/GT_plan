# Requirements — 抽凭科目真源接线与挂凭链路收口

## Introduction

抽凭样本要能正确回填底稿，前提是**凭证与科目正确关联**。平台有两条关联路径，各自都有已确证缺陷：

- **路径 A（抽凭引擎）**：宿主传 `account-code` → `useVoucherSampling` 拆成 `config.accountCodes` → `POST /voucher-extract` 的 `filters.account_codes` → 后端按科目查 `tb_ledger` → 返回行天然带 `account_code`。关联在**查询阶段**完成，机制正确，**但前提是宿主传对了科目码**。现算 **70 处静态字面量** `account-code` 挂载点中 **25 处** 与科目真源不一致。
- **路径 B（序时账挂凭）**：用户在序时账任意行挂凭 → 存 `account_code` → 回拉时取**整张凭证的全部分录** → 前端按底稿科目前缀筛出「本科目那条」。此路径有两个逻辑缺陷（筛不到时回退取全部、挂凭时记录的科目意图未参与筛选）。

### 这是两个已完成 spec 之间的缝隙

| 已归档 spec | 完成度 | 主题 | 对本问题的覆盖（现算关键词命中） |
|---|---|---|---|
| `_archive/08-disclosure-notes/semantic-account-resolver-full-rollout` | 31/31 | **消除科目硬编码**（70 个后端 render 策略） | `抽凭` 0 · `GtVoucherSamplingEngine` 0 · `account-code` 0 · `AccountScope` 0 |
| `_archive/05-business-features/voucher-sampling-hardening` | 40/40 | 抽凭引擎正确性与架构收敛 | `account-code` 0 · `AccountScope` 0 |

前者管后端科目硬编码、后者管抽凭引擎本身，**交叉点（抽凭引擎拿到的科目码是否正确）无人负责** —— 这正是 25 处错码长期存活且测试全绿的原因。

### 关键前提：真源已存在，无需重新做审计裁决

现扫确认平台已有 **42 个前端 `*AccountScope.ts`** 与 **11 个后端 `*_account_scope.py`**，覆盖 D/F/G/H/I/J/K/L 全循环，且这些模块的文件头记录了裁决依据（`account_chart` / `tb_balance` / `report_config` 公式实证）。本 spec **只做接线，不重新裁决科目**。唯一例外是 `wp_account_mapping.json` 自身的 3 处错误（见 Requirement 5，本 spec 只登记不改）。

## Glossary

| 术语 | 含义 |
|---|---|
| 科目真源 | 前端 `components/workpaper/composables/*AccountScope.ts`（42 个），导出 `{X}_FALLBACK_STANDARD` / `{x}QueryCodes()` / `{x}AccountCode()`；文件头含裁决依据 |
| 静态挂载点 | `.vue` 模板里写 `account-code="1234"` 字面量的抽凭引擎挂载（现算 70 处） |
| 动态挂载点 | 写 `:account-code="X_ACCOUNT_CODE"` 等常量/计算属性的挂载（现算 17 处），属正确模式 |
| 宁缺勿造 | 真源以 `FALLBACK_STANDARD = ''` 表达「本循环无标准独立科目码」（现算 I5 / K4 / L7 三例），禁止臆造兜底码 |
| 路径 A | 抽凭引擎链路：`GtVoucherSamplingEngine` `@filled` → 宿主回填 |
| 路径 B | 挂凭链路：`attachVoucher` → `pullSamplesForWorkpaper` → 宿主 `onSampleFilled` |
| 科目意图 | 用户挂凭时所在行的 `account_code`（已存入 `sampled_vouchers.account_code`），表达「我关注这张凭证的哪个科目」 |

## Requirements

### Requirement 1：抽凭挂载点一律从科目真源取码，禁止字面量

**User Story:** 作为审计师，我点「抽凭」时希望抽到的是本底稿科目的凭证，而不是另一个循环的科目。

#### Acceptance Criteria

1. WHEN 任一 `GtVoucherSamplingEngine` 挂载点提供 `account-code` THEN 该值 SHALL 来自对应循环的 `*AccountScope.ts` 导出（常量或 `{x}QueryCodes()`），**不得**为内联数字字面量。
2. WHEN 宿主已有 `tbSourceCodes`（render 解析结果）THEN SHALL 优先 `{x}QueryCodes(props.tbSourceCodes)`；无该 prop 时方可退到 `{X}_FALLBACK_STANDARD`。
3. WHEN 挂载点所在底稿的循环无对应 `*AccountScope.ts` THEN SHALL 先建真源模块（含裁决依据注释与实证来源），**不得**在组件内硬编码后补。
4. 逐条修正下列已确证不一致（现算，判据为真源值；**禁写死行号**，锚点用文件名 + 常量名）：

   | 底稿 | 底稿真实名 | 组件现值 | 该码实为 | 真源值 | 处置 |
   |---|---|---|---|---|---|
   | K5（2 处） | 预计负债 | `2701` | 长期应付款（L5） | `K5_FALLBACK_STANDARD='2801'` | **本轮前置已修** |
   | G1（2 处） | 交易性金融资产 | `1501` | 持有至到期投资（G4） | `G1_GROSS_FALLBACK_STANDARD='1101'` | 接真源 |
   | I2（7 处） | 开发支出 | `1717` | 真实库无此码 | `I2_GROSS_FALLBACK_STANDARD='1704'` | 接真源 |
   | I6（5 处） | 研发费用 | `6602`（管理费用） | 管理费用（K9） | `I6_GROSS_FALLBACK_STANDARD='6604'` | 接真源 |
   | ~~F2（1 处）~~ | ~~存货~~ | ~~`1410`~~ | — | — | **归类已更正 → Requirement 2**（见 design 实证更正节 2：`1410` 在 `['1401'..'1412']` 区间内、且真实库 `1410`/`1341`/`1412` 与「合同履约成本」科目名**全部零命中** ⇒ 属「本项目无此科目」而非错码） |
   | I5（1 处） | 其他非流动资产 | `1911` | 真实库无此码 | `I5_GROSS_FALLBACK_STANDARD=''` | 见 Requirement 2 |
   | K4（1 处） | 其他流动负债 | `2245`（持有待售负债） | 持有待售负债 | `K4_FALLBACK_STANDARD=''` | 见 Requirement 2 |
   | K10 | 其他收益 | `6117` ✓ | 其他收益 | `K10_FALLBACK_STANDARD='6117'` | 值已对，仍须接真源消除字面量 |
   | K12 | 营业外收入 | `6301` ✓ | 营业外收入 | `K12_FALLBACK_STANDARD='6301'` | 同上 |
   | H5（2 处） | 油气资产 | `1631` ✓ | 油气资产 | `hCycleAccountScope.H5_ACCOUNT_DEF` | 同上 |

5. IF 某挂载点的真源值与组件现值相同（K10/K12/H5）THEN 仍 SHALL 改为引用真源 —— 值偶然正确不等于来源正确，字面量会再次漂移。

### Requirement 2：真源判「宁缺勿造」时，抽凭必须显式降级而非臆造科目

**User Story:** 作为审计师，当本项目确实没有这个科目时，我需要系统明确告知，而不是拿一个错科目抽出一堆无关凭证。

#### Acceptance Criteria

1. WHEN 真源 `FALLBACK_STANDARD` 为空串且 `tbSourceCodes` 亦解析不出科目 THEN 抽凭入口（按钮/菜单项）SHALL 禁用，并提示「本项目无「{底稿名}」对应科目，请手工录入或先在报表配置中映射」。
2. WHEN 上述条件成立 THEN SHALL **不**向 `POST /voucher-extract` 发起请求（避免以空/错科目查全库）。
3. WHEN `tbSourceCodes` 能解析出科目 THEN 即使 `FALLBACK_STANDARD` 为空，抽凭 SHALL 正常可用（空兜底只表达「无**标准**码」，不表达「本项目无数据」）。
4. 禁用态 SHALL 可区分于「加载中」与「只读」，并在 tooltip 给出可操作的下一步。

### Requirement 3：挂凭回拉的科目过滤必须尊重挂凭意图，且不得静默灌入错科目

**User Story:** 作为审计师，我在「1002 银行存款」那行挂的凭证，回填到底稿时应该填这条分录；如果我挂错了底稿，系统要告诉我，而不是把整张凭证的所有分录都塞进来。

#### Acceptance Criteria

1. WHEN `pullSamplesForWorkpaper` 回拉某张凭证的分录 THEN 筛选优先级 SHALL 为：① 命中底稿科目前缀的分录 → ② 命中 `sampled_vouchers.account_code`（挂凭意图）的分录 → ③ 判定为「挂错底稿」。
2. WHEN 命中 ①（正常路径）THEN 行为与当前一致，回填该科目分录。
3. WHEN ① 空而 ② 命中 THEN SHALL 回填挂凭意图对应的分录，并在样本 `remark` 标注「按挂凭时选定科目 {code} 取分录，未命中本底稿科目范围，请核对」。
4. WHEN ①② 均空 THEN SHALL **不**回退取全部分录（当前 `if (picked.length === 0) picked = lines` 即此缺陷），而是：把该凭证计入「挂错底稿」清单、不产生样本行，导入结束后以可关闭提示列出这些凭证号并建议重新挂凭。
5. WHEN 存在「挂错底稿」凭证 THEN 提示 SHALL 同时给出该凭证实际包含的科目，便于用户判断该挂到哪张底稿。
6. WHEN 分录穿透失败（网络/端点错误）THEN 仍 SHALL 保留当前的「占位样本」行为（保留凭证号供手工补录），且 SHALL 与「挂错底稿」在提示上可区分 —— 前者是技术失败，后者是业务错挂。

### Requirement 4：科目前缀不得在宿主内硬编码，须与真源同源

**User Story:** 作为平台维护者，我要求路径 B 的科目前缀与路径 A 的科目码出自同一真源，避免两条路径对「本底稿是什么科目」给出不同答案。

#### Acceptance Criteria

1. WHEN 宿主调用 `pullSamplesForWorkpaper` 传 `accountPrefixes` THEN 该值 SHALL 来自对应 `*AccountScope.ts`（如 E1 用 `e1QueryCodes()` 或等价导出），**不得**为组件内数组字面量。
2. IF 现有 `E1TabLargeCheck.MF_ACCOUNT_PREFIXES = ['1001','1002','1012']` 与真源一致（现算：与 `wp_account_mapping.json` 的 E1 条目一致）THEN 仍 SHALL 改为引用真源（同 Requirement 1.5 的理由）。
3. WHEN 真源对该循环给出多个码 THEN `accountPrefixes` SHALL 取全集，不得只取首个。

### Requirement 5：`wp_account_mapping.json` 的已发现错误只登记、不在本 spec 修改

**User Story:** 作为平台维护者，我需要知道权威映射表本身有错，但不希望在一个抽凭 spec 里改动被多处消费的平台真源。

#### Acceptance Criteria

1. 本 spec SHALL 在交付物中登记下列现算不一致（与前端真源 + 真实库科目名双向比对得出）：

   | wp | 底稿真实名 | `wp_account_mapping.json` 值 | 该码实为 | 前端真源值 | 判定 |
   |---|---|---|---|---|---|
   | K10 | 其他收益 | `6301` | 营业外收入 | `6117` | json 错 |
   | K12 | 营业外收入 | `6001` | 主营业务收入 | `6301` | json 错 |
   | H5 | 油气资产 | `1606` | 固定资产清理 | `1631` | json 错 |

2. 本 spec SHALL **不**修改 `wp_account_mapping.json` —— 现算其消费面含附注模板绑定生成（`generate_note_template_bindings.py`）、地址库 V1 的 wp 域构建（`address_registry.py`）、附注账龄分桶（`note_formula_generator`）、种子校验（`validate_seed_files.py`）等，改动需逐消费方回归，超出本 spec 范围。
3. 登记条目 SHALL 写入 `docs/` 下的勘误记录并在 `#dev-history` 留痕，标明「待独立 spec 处置」。
4. WHEN 前端真源与 json 冲突 THEN 本 spec 的实现 SHALL 以**前端真源**为准（其文件头有 `account_chart` / `report_config` 实证，且与真实库科目名一致）。

### Requirement 6：守卫必须阻断回归，且不得假绿

**User Story:** 作为平台维护者，我要求这类错误再次出现时 CI 立刻报红，而不是等到审计师发现抽出来的凭证不对。

#### Acceptance Criteria

1. SHALL 新增守卫：扫描全部 `GtVoucherSamplingEngine` 挂载点，`account-code` 为内联数字字面量即失败，报错信息列出文件名与应使用的真源导出名。
2. 守卫判据 SHALL 在**剔除注释后**的源码上执行 —— 说明性注释里会出现被禁字面量（本轮 K5 守卫首版即因此误报）。
3. SHALL 配对反向自检：构造含硬编码的样本必须被判违规；剔注释器不得过度剔除（剔后仍能取到关键代码）。
4. SHALL 新增守卫：`pullSamplesForWorkpaper` 的 `accountPrefixes` 实参不得为数组字面量。
5. SHALL 新增守卫：`pullSamplesForWorkpaper` 内不得出现「筛空回退取全部」形态（`picked.length === 0` 后赋值 `lines`）。
6. 守卫 SHALL 覆盖动态挂载点所引用常量的**取值来源**（防止 `const X_ACCOUNT_CODE = '1717'` 这种「换个地方硬编码」规避检查）。

### Requirement 7：零回归

#### Acceptance Criteria

1. WHEN 本 spec 落地 THEN 既有抽凭样本回填行为（字段映射、去重、方法学留痕）SHALL 不变，仅科目码来源改变。
2. WHEN 科目码真源值与组件原值相同（K10/K12/H5/E1）THEN 运行时行为 SHALL 逐字节不变。
3. SHALL 不修改 `POST /voucher-extract` 的请求/响应契约。
4. SHALL 不新增/修改数据库表或列。
5. 既有测试（现算：`samplingHostMethodologyCoverage.spec.ts` 42 test、`k5AccountCodeNoHardcode.spec.ts` 9 test、K5 系列 187 test、`kCycleAccountScope*.spec.ts` 等）SHALL 全绿。

## 非目标（明确排除）

1. **不修 `wp_account_mapping.json`** —— 见 Requirement 5.2。
2. **不改抽凭算法/引擎内核** —— 已由归档 spec `voucher-sampling-hardening`（40/40）收口。
3. **不做路径 B 的自动触发** —— 当前必须用户手动三步（挂凭 → 切底稿 → 点导入），自动化属独立产品决策。
4. **不扩大路径 B 的消费端** —— 现算全平台仅 `E1TabLargeCheck` 一处实现「从序时账挂入导入」；让其余底稿也支持属独立 spec（本 spec 只保证已有这一处正确）。
5. **不接 OnlyOffice 回写** —— `legacy_fake_bidirectional` 现算 135/155，属 umbrella spec 范围。

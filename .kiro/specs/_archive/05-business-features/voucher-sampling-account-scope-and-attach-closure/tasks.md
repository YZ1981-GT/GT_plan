# Tasks — 抽凭科目真源接线与挂凭链路收口

> 计数均为 2026-09-28 现算值。判据禁写死行号，锚点用「文件名 + 导出常量名 + 形态特征」。
> 每个任务末尾标注它承接的 Requirement 验收项（`_需求: R{n}.{m}_`）。

## 阶段 1：守卫先行（允许初始红，红即待修清单）

- [x] 1.1 新增 `samplingAccountCodeSource.spec.ts`：扫描全部 `GtVoucherSamplingEngine` 挂载点
    - 收集静态 `account-code="数字"` 与动态 `:account-code="标识符"` 两类，现算基线应为 70 / 17
    - 静态类：内联数字字面量即违规，报错列出文件名 + 该循环应使用的真源导出名
    - **先剔注释**（`<!-- -->` / `/* */` / `//`）再判，并为剔除器写自检（剔后仍能取到 `K5_FALLBACK_STANDARD` 这类代码标识）
    - 配反向自检：构造 `account-code="2701"` 样本必须被判违规
    - _需求: R6.1, R6.2, R6.3_

- [x] 1.2 守卫扩展：动态挂载点的标识符溯源（防「换地方硬编码」）
    - 对 `:account-code="X"`，要求 `X` 或来自 `*AccountScope` 的 import，或其赋值右侧非数字字面量
    - 两条件皆不满足即违规（如 `const X_ACCOUNT_CODE = '1717'`）
    - 配反向自检：构造该形态必须被抓到
    - _需求: R6.6_

- [x] 1.3 守卫：`pullSamplesForWorkpaper` 的 `accountPrefixes` 实参不得为数组字面量
    - 现算该函数全仓 3 处命中（定义 + `E1TabLargeCheck` + 无第三方调用）
    - _需求: R6.4_

- [x] 1.4 守卫：`pullSamplesForWorkpaper` 内不得出现「筛空回退取全部」形态
    - 判据：`picked.length === 0` 之后把 `lines` 整体赋给 `picked`
    - 配反向自检
    - _需求: R6.5_

- [x] 1.5 真源值断言测试：锁死 25 处涉及的真源常量具体值
    - `K5_FALLBACK_STANDARD==='2801'` · `G1_GROSS_FALLBACK_STANDARD==='1101'` · `I2_GROSS_FALLBACK_STANDARD==='1704'` · `I6_GROSS_FALLBACK_STANDARD==='6604'` · `K10_FALLBACK_STANDARD==='6117'` · `K12_FALLBACK_STANDARD==='6301'`
    - `I5_GROSS_FALLBACK_STANDARD===''` 与 `K4_FALLBACK_STANDARD===''`（宁缺勿造，不得被填上臆造码）
    - 每条附「该码实为什么」的注释，防后人改回
    - _需求: R1.4, R2.3_

- [x] 1.6 契约测试：真源导出存在性
    - 断言各 `*AccountScope.ts` 的 `{x}QueryCodes` / `{X}_FALLBACK_STANDARD` 可 import
    - 防真源改名导致宿主静默退回硬编码
    - _需求: R1.1, R1.2_

## 阶段 2：值已正确的接线（运行时逐字节不变，作为模式样板）

- [x] 2.1 K10 / K12 接真源
    - `K10TabOtherIncomeCheck`（`6117`）、`K12TabNonOperatingCheck`（`6301`）改引用 `k10AccountScope` / `k12AccountScope`
    - 值不变 ⇒ 运行时行为逐字节不变，仅消除字面量
    - _需求: R1.1, R1.5, R7.2_

- [x] 2.2 H5 两处接 `hCycleAccountScope`
    - `H5TabAdditionCheck` / `H5TabDisposalCheck`（`1631` 油气资产）改引用 `H5_ACCOUNT_DEF` / `h5Scope`
    - 🔴 注意 `wp_account_mapping.json` 的 H5 值（`1606` 固定资产清理）是错的，**以前端真源为准**
    - _需求: R1.1, R1.5, R5.4_

- [x] 2.3 E1 的 `accountPrefixes` 接真源
    - `E1TabLargeCheck.MF_ACCOUNT_PREFIXES` 数组字面量 → 真源导出（E1 无独立 `e1AccountScope.ts` 时先建，含裁决依据注释）
    - 现算该字面量值与权威一致 ⇒ 行为不变
    - _需求: R4.1, R4.2, R4.3, R1.3_

- [x] 2.4 固化接线模式为可复用范式
    - 把 2.1~2.3 的写法（`computed` + `QueryCodes` 优先 + `FALLBACK` 降级 + `join(',')`）整理成注释范式，供阶段 3 照用
    - `join(',')` 依据：`useVoucherSampling.buildDefaultConfig()` 现算对 `accountCode` 做 `split(',')`，多码拼接是既有契约
    - _需求: R1.2_

## 阶段 3：值错误的接线（抽样总体会真实变化）

- [x] 3.1 G1 两处：`1501`（持有至到期投资，属 G4）→ `g1AccountScope`
    - `G1TabDerivativeCheck` / `G1TabVoucherCheck`
    - 注意该真源另有 `G1_DERIVATIVE_FALLBACK_STANDARD='1102'`，衍生品页应判断用哪个
    - _需求: R1.1, R1.4_

- [x] 3.2 I2 七处：`1717`（真实库无此码）→ `i2AccountScope`（`1704` 开发支出）
    - `I2TabCutoffBackward` / `I2TabCutoffForward` / `I2TabMaterialCheck` / `I2TabOutsourceCheck` / `I2TabStaffCheck` / `I2TabTargetedCheck` / `I2TabWorkHourCheck`
    - 其中 Cutoff 两个文件各含 2 处挂载点
    - _需求: R1.1, R1.4_

- [x] 3.3 I6 五处：`6602`（管理费用，属 K9）→ `i6AccountScope`（`6604`）
    - `I6TabCutoffBackward`(×2) / `I6TabCutoffForward`(×2) / `I6TabTargetedCheck`
    - _需求: R1.1, R1.4_

- [x] 3.4 F2 一处：`1410`（真实库无此码）→ `F2_INVENTORY_ACCOUNT_CODES`
    - `F2TabContractCostCheck`；该常量现算在 `f2NoteSectionMap.ts`，为 `readonly string[]`
    - _需求: R1.1, R1.4_

- [x] 3.5 逐循环验证抽样总体非空
    - 对 3.1~3.4 每个循环，用真实库确认修正后的科目在 `tb_ledger` 有数据（至少 1 个项目）
    - 若某科目全库为零命中，如实记录并说明（可能是该循环本项目无业务，非接线错误）
    - _需求: R7.1_

- [x] 3.6 交付说明：历史批次不追溯
    - `workpaper_extraction_log` 是 append-only 审计轨迹；本 spec 不回填基于错科目的历史抽样批次
    - 修正只影响新发起的抽样，须在交付说明与 `#dev-history` 明示
    - _需求: R7.1_

## 阶段 4：宁缺勿造的降级（I5 / K4）

- [x] 4.1 抽凭入口禁用态
    - 真源 `FALLBACK_STANDARD` 为空且 `tbSourceCodes` 解析不出 ⇒ 禁用抽凭按钮
    - 提示「本项目无「{底稿名}」对应科目，请手工录入或先在报表配置中映射」
    - 三态可区分：禁用（无科目）/ 加载中 / 只读
    - _需求: R2.1, R2.4_

- [x] 4.2 不发请求
    - 该态下不调 `POST /voucher-extract`（避免空/错科目查全库）
    - 单测断言：空码场景下 http mock 零调用
    - _需求: R2.2_

- [x] 4.3 有解析值时正常可用
    - `tbSourceCodes` 能解析出码时，即使 `FALLBACK` 为空也不禁用
    - 单测覆盖「空兜底 + 有解析值」组合
    - _需求: R2.3_

- [x] 4.4 应用到 I5 / K4 两处挂载点
    - `I5TabTargetedCheck`（原 `1911`）、`K4TabCheck`（原 `2245` 持有待售负债）
    - _需求: R1.4, R2.1_

## 阶段 5：路径 B 筛选优先级收口

- [x] 5.1 `pullSamplesForWorkpaper` 三级筛选
    - ① 命中底稿科目前缀 → ② 命中 `rec.account_code`（挂凭意图）→ ③ 判「挂错底稿」
    - 删除 `if (picked.length === 0) picked = lines`
    - _需求: R3.1, R3.2_

- [x] 5.2 ② 级命中的标注
    - 样本 `remark` 标注「按挂凭时选定科目 {code} 取分录，未命中本底稿科目范围，请核对」
    - 与本轮已有的 `dateAmbiguous` 标注共存不冲突
    - _需求: R3.3_

- [x] 5.3 ③ 级「挂错底稿」汇总提示
    - 返回结构新增 `misattached: Array<{voucherNo, voucherDate, actualAccounts: string[]}>`
    - 不产生样本行；导入结束后可关闭提示列出凭证号 + 其实际科目
    - _需求: R3.4, R3.5_

- [x] 5.4 穿透失败与业务错挂在提示上区分
    - `lines` 为空（技术失败）→ 保留占位样本（现有行为）
    - `lines` 非空但三级全空（业务错挂）→ 进 `misattached`
    - _需求: R3.6_

- [x] 5.5 E1 消费端接入新返回结构
    - `importFromAttached` 消费 `misattached` 并呈现
    - 现算 E1 是唯一消费端，改动面收敛
    - _需求: R3.4_

- [x] 5.6 单测覆盖四情形
    - ①正常 / ②挂凭意图命中 / ③挂错底稿 / 穿透失败；每种断言样本数与提示内容
    - _需求: R3.1~R3.6_

## 阶段 6：勘误登记与收尾

- [x] 6.1 登记 `wp_account_mapping.json` 三处错误
    - K10（`6301`→应 `6117`）、K12（`6001`→应 `6301`）、H5（`1606`→应 `1631`）
    - 写入 `docs/` 勘误记录，标明「待独立 spec 处置」及其消费面（附注模板绑定生成 / 地址库 V1 wp 域 / 附注账龄分桶 / 种子校验）
    - 🔴 本 spec 不修该文件
    - _需求: R5.1, R5.2, R5.3_

- [x] 6.2 `#dev-history` 留痕
    - 记录本轮发现链：凭证号不唯一 → 挂凭去重/消歧 → K5 抽凭错科目 → 25 处同类 → 两个已完成 spec 的缝隙
    - _需求: R5.3_

- [x] 6.3 判据引用闭合性核对
    - 脚本核对「每条 AC 至少被某任务引用一次」，而非只数编号连续
    - 补齐零引用的 AC
    - _需求: 全部_

- [x] 6.4 清理一次性探针
    - 删 `backend/scripts/analyze/_*.py` 与 `_*.txt`（本 spec 调研期产物已随手清理，交付前复核）

- [x] 6.5 全量回归
    - 前端：`samplingHostMethodologyCoverage`(42) + `k5AccountCodeNoHardcode`(9) + K5 系列(187) + `kCycleAccountScope*` + 本 spec 新增守卫
    - 后端：`test_sampled_voucher_scope_and_date`(17) + `test_sampling_registry_service` + `test_drilldown` + `test_ledger_penetration_extra_fields`
    - 现算已知预存失败 5 个前端 suite（`useK1DualMode.ts` 缺失等），与本 spec 零引用，如实标注不计入
    - **R7.3 核对**：`POST /voucher-extract` 的请求/响应契约零改动（本 spec 只改前端传入的
      `filters.account_codes` 取值来源，不动端点签名与字段）
    - **R7.4 核对**：零数据库改动（`git diff` 不含 `backend/migrations/` 与 ORM 模型文件）
    - _需求: R7.1, R7.2, R7.3, R7.4, R7.5_

- [ ]* 6.6 Playwright 实测（外部依赖：需 `start-dev.bat` 环境）
    - 抽凭弹窗标题显示正确科目；I5/K4 禁用态与 tooltip；挂错底稿提示
    - **降级方案**：环境不可用时标 `[ ]*` 并写明「代码已改但未实测」，不假绿
    - _需求: R2.4, R3.5_

## 任务总数与承接关系

| 阶段 | 任务数 | 承接 Requirement |
|---|---|---|
| 1 守卫先行 | 6 | R6 全部 + R1.1/1.2/1.4 + R2.3 |
| 2 值正确接线 | 4 | R1.1/1.5, R4 全部, R5.4, R7.2 |
| 3 值错误接线 | 6 | R1.1/1.4, R7.1 |
| 4 空码降级 | 4 | R2 全部, R1.4 |
| 5 路径 B 收口 | 6 | R3 全部 |
| 6 收尾 | 6（含 1 个 `*`） | R5 全部, R7.5 |
| **合计** | **32**（31 必做 + 1 外部依赖） | R1~R7 |

🔴 `*` 标记任务（6.6）仍须完成，只在环境确实不可用时才降级标注，不得默认跳过。

---

## 实施完成记录（2026-09-28）

### 交付范围（精确清单）

**36 个文件**：前端 31 / 文档+spec 5 / **后端 0**。

> 🔴 工作树现算有 479 个变更文件，其中绝大多数属**其他 spec 的未提交工作**，不是本 spec 产物。
> 上述 36 个是按阶段逐个记录的精确清单，R7.3/R7.4 的核对基于它而非整个工作树。

### 各阶段结果

| 阶段 | 任务 | 结果 |
|---|---|---|
| 1 守卫先行 | 6 | ✅ 新建 2 个守卫文件（36 test），初始正确报红 7 条 = 待修清单 |
| 2 值正确接线 | 4 | ✅ 新建 `e1AccountScope.ts`；接线 6 文件；违规 60→54 |
| 3 值错误接线 | 6 | ✅ 接线 12 文件（G1×2 / I2×9挂载点 / I6×5挂载点）；**25 处错码清零**；违规 54→42 |
| 4 空科目降级 | 4 | ✅ 新建通用 `useSamplingAccountGate`（17 test）+ `f2ContractCostAccountScope`；接入 K4/I5/F2 |
| 5 路径 B 收口 | 6 | ✅ 三级筛选 + `misattached`；新建 15 test；阶段 1 的 5 条红全转绿 |
| 6 收尾 | 6 | ✅ 勘误登记 + 引用闭合性核对 + 回归；6.6* 见下 |

### 回归结果

**114 passed / 2 failed**（6 个 suite）。

🔴 **那 2 条 failed 是刻意保留的红，不是回归失败**：

| 失败断言 | 内容 | 性质 |
|---|---|---|
| `静态数字字面量一律违规` | 现算**剩 39 处** | R1.5 防漂移清单：这些挂载点的科目**取值正确**，但来源仍是字面量 |
| `绑定的标识符不得指向数字字面量常量` | `F2ValuationTestSheet.vue` 的 `valuationAccountCodes` | 阶段 1 新发现，设计阶段未登记 |

判据是**来源形态**而非取值对错，故「25 处错码已清零」与「仍有 39 处字面量」**同时成立**、分母不同
（详见 design 实证更正节 · 更正 1 的三个分母表）。

**为何不在本轮清完这 39 处**：它们的取值经真源对账**全部正确**，改动纯为防未来漂移，
收益低于风险（每处都要读宿主判断该用 `QueryCodes` 全集还是 `FALLBACK` 单值 ——
本轮 E1 两处就因此分别取了三码全集与单值 `1002`，不能机械替换）。留作后续批次，
守卫已把清单固定住，不会再增长。

### 任务勾选

- [x] 1.1 ~ 1.6 阶段 1 全部
- [x] 2.1 ~ 2.4 阶段 2 全部
- [x] 3.1 ~ 3.6 阶段 3 全部
- [x] 4.1 ~ 4.4 阶段 4 全部
- [x] 5.1 ~ 5.6 阶段 5 全部
- [x] 6.1 勘误登记 → `docs/reference/wp-account-mapping-errata-2026-09-28.md`
- [x] 6.2 `#dev-history` 留痕
- [x] 6.3 判据引用闭合性：R1~R7 零遗漏；AC 总数现算 **33**（R7 为 5 条，先前探针把「非目标」章节编号误计为 10 已更正）；补齐 R7.3/R7.4 的显式引用
- [x] 6.4 探针清理（`backend/scripts/analyze/_vsa_*.py` 已删；其余 `_psl_*`/`_g_*` 属其他 spec 遗留，未擅动）
- [x] 6.5 全量回归（见上）
- [ ]* 6.6 Playwright 实测 —— **未执行**：需 `start-dev.bat` 环境（后端 9980 + 前端 3030）。
      代码已改但 UI 层未实测的三项：抽凭弹窗标题显示真源科目、I5/K4/F2 降级禁用态与 tooltip、
      挂错底稿的 `ElNotification` 提示。按「不假绿」如实标注为未完成。

### 已知遗留

1. **39 处字面量**（值正确、防漂移）+ `F2ValuationTestSheet` 的常量硬编码 —— 守卫已固定清单。
2. **`wp_account_mapping.json` 三处错误**（K10/K12/H5）—— 已登记勘误，待独立 spec（消费面含
   附注模板绑定生成 / 地址库 V1 wp 域 / 账龄分桶 / 种子校验 / 行名对齐）。
3. **6.6 Playwright 未实测**。
4. 前端有 **5 个预存失败 suite**（`useK1DualMode.ts` 缺失等），与本 spec 零引用，未计入回归。

---

## 追加批次：字面量全清（2026-09-28，同日追加）

上一节记录的「刻意保留 2 条红」已清零。**两个守卫现 36/36 全绿，零保留红。**

### 🔴 更正上一节的结论：剩余 39 处并非「取值全部正确」

上一节写「剩 39 处取值经真源对账**全部正确**，改动纯为防漂移」。接线时逐个核对真源兜底值，
**抓到第 26 处错码**：

| 底稿 | 底稿真实名 | 组件值 | 该码实为 | 真源/报表配置 | 判定 |
|---|---|---|---|---|---|
| **G4** | 债权投资 | `1501` | **持有至到期投资**（`account_chart` 7 条） | `gCycleScope('G4').queryCodes()` = `1504`；`report_config` `BS-021 债权投资 = TB('1504','期末余额')` | **组件错** |

`account_chart` 现算：`1504` = 债权投资（6 条）、`1501` = 持有至到期投资（7 条）。
`wp_account_mapping.json` 的 G4 同样是 `1501` ⇒ 该 json 的**第 4 处错**（勘误文档已补记）。

⇒ 发现方式：接线前先跑探针把「真源兜底值」与「组件现值」逐个比对，**而不是直接替换**。
若按上一节的判断机械接线，G4 会被当成「值正确」而漏掉 —— 这条比对步骤是必须的。

同批还发现 **F1 在 `dCycleAccountScope` 里未登记**（`dCycleScope('F1')` 返 `null`）——
F1 属 F 循环（采购与付款）而非 D 循环，强行用会退化成空科目。按 R1.3 新建了 `f1AccountScope`。

### 本批次产出

| 类别 | 内容 |
|---|---|
| 新建真源 4 个 | `f1AccountScope`（预付账款 `1123`）· `m1AccountScope`（应付股利 `2232`）· `m2AccountScope`（实收资本 `4001`）· `n2AccountScope`（应交税费 `2221`），均含 `account_chart` + `report_config` 实证表 |
| 接线 39 文件 / 41 挂载点 | D1/D2/D3/D5/D6/D7（`dCycleScope`）· G2/G3/**G4**（`gCycleScope`）· F1（新真源）· H1×2/H2×2/H4×2/H6/H10（`hXScope.grossCode()`）· I1×2/I3/I4 · J1 · K1/K3×3/K7/K8×3(5 挂载点)/K9/K13 · F3/F4/F5 · M1/M2/N2 |
| 修「换地方硬编码」1 处 | `F2ValuationTestSheet` 的 `valuationAccountCodes` 从 `'1401,…,1411'.split(',')` 改为 `F2_INVENTORY_ACCOUNT_CODES`（真源含 `1412`，覆盖更全） |

### `m2AccountScope` 记录了一处科目表歧义

`account_chart` 里 **`4001` 有两种定义**：实收资本 **14** 条 / **生产成本 5 条**（2006 年前旧科目表用法）。
兜底取多数口径（实收资本，与 `report_config` 的 BS-075/BS-081/BS-102 三行一致），
但在那 5 个项目里以 `4001` 抽凭会抽到**生产成本**凭证 —— 已写入真源文件头，
并说明这正是「运行态必须优先 `tb_source_codes`、兜底码只兜界面」的价值所在。

### 验证

| 项 | 结果 |
|---|---|
| SFC 编译（`@vue/compiler-sfc`，全部 **79** 个抽凭宿主） | 0 失败 · 0 残留静态字面量 · 0「绑定但缺声明」 |
| 守卫 `samplingAccountCodeSource` + `attachedVouchersAccountScope` | **36/36 全绿**（阶段 1 的 7 条红全清） |
| 回归（9 suite，含 D/G/H Cycle 真源守卫） | **236 passed / 0 failed** |

### 任务勾选

- [x] 追加-1 获取 41 处清单并按循环分组、核对真源就绪
- [x] 追加-2 补齐 4 个缺位真源（f1 / m1 / m2 / n2）
- [x] 追加-3 按循环接线 39 文件（先探针比对真源兜底值 vs 组件现值，抓出 G4 错码）
- [x] 追加-4 修 `F2ValuationTestSheet` 换地方硬编码
- [x] 追加-5 SFC 编译验证 79 宿主
- [x] 追加-6 守卫转绿 + 回归 236 passed

### 遗留（缩减后）

1. ~~39 处字面量~~ → **已清零**
2. **`wp_account_mapping.json` 现共 4 处错**（K10 / K12 / H5 / **G4**）—— 勘误文档已更新，待独立 spec
3. **6.6 Playwright 未实测**（需 `start-dev.bat` 环境）

---

## 追加批次 2：`wp_account_mapping.json` 勘误处置（2026-09-28，同日追加）

上一节遗留第 2 条「4 处错待独立 spec」已就地处置完成。**未另起 spec**：实际改动是 5 族纯数据
替换 + 五类消费方回归，工作量小于建 spec 的开销，故按「改动前先 spec 三件套」的三条阈值
（>500 行文件 / 3+ 组件 / 跨前后端）逐条判定 —— 三条**均不触发**（单 json 文件、零组件、纯后端数据），
按最小批次直接执行。

### 🔴 更正上一节的结论：不是 4 处，是 5 族 37 项

上一节写「`wp_account_mapping.json` 现共 4 处错（K10/K12/H5/G4）」。处置时按「触类旁通 grep」
扩面，两处低估：

| 低估点 | 实情 |
|---|---|
| 登记的 4 条只是**主条目** | 每族还有 `{code}-1`…`{code}-n` 同族子条目沿用同一错码（G4 有 8 个、H3 有 6 个、H5 有 4 个、K10 有 4 个、K12 有 4 个） |
| 漏了**第 5 族 H3** | 投资性房地产，与 G4 撞同一个错码 `1501`。登记时逐 wp 对账只覆盖到抽凭宿主涉及的底稿，H3 不在其中 |

外加 `report_row` 连带 6 项（`account_codes` 改了但报表行仍指旧科目）。合计 **31 + 6 = 37 项**。

🔴 **H3 族的发现路径值得记住**：不是 grep 错码找到的，而是**产物 diff 的不对称**——
改完 4 族主条目后重新生成 `note_template_bindings.json`，diff **只有新增、没有删除**
⇒ 旧码 `1501` 仍被别处引用 ⇒ 回查旧码才挖出 G4 子条目与整个 H3 族。
**「只增不删」是错码残留的可靠信号**，比逐条 grep 更早暴露问题。

### 本批次产出

| 类别 | 内容 |
|---|---|
| 新建正式脚本 | `backend/scripts/fix/fix_wp_account_mapping_wrong_codes.py`（`--check`/`--dry-run`/`--apply`；幂等；现值既非 old 也非 new 时报 `[BAD]` 退出码 2 **拒绝盲目覆盖**；`assert` 保护 `wp_name`/`account_name` 不被改） |
| 数据修正 37 项 | G4 族 9（`1501`→`1504`）· H3 族 7（`1501`→`1521`）· H5 族 5（`1606`→`1631`）· K10 族 5（`6301`→`6117`）· K12 族 5（`6001`→`6301`）· `report_row` 6 |
| 勘误文档改写 | `docs/reference/wp-account-mapping-errata-2026-09-28.md` 状态从「只登记未修改」改为「已修复」，补 H3 族 + `report_row` 明细 + 处置记录 + 隔离实验结论 |

### H5 的 `report_row` 置 `None`（宁缺勿造）

其余 5 项 `report_row` 都能在 `report_config` 找到对应行，H5 找不到：**`report_config` 无资产负债表
「油气资产」行**。与前端 `H5_ACCOUNT_DEF.reportRowCode = null` 一致 ⇒ 置 `None`，**不编一个码**。

### 验证

| 项 | 结果 |
|---|---|
| `git diff --stat` | **37 insertions / 37 deletions**，零格式漂移 |
| 种子校验 `scripts/validate_seed_files.py` | `PASS wp_account_mapping.json` |
| 幂等复验 `--check` | `[OK] 4 条错误均已修正（37 项幂等）` |
| 后端回归（21 文件 924 test，覆盖 G4/H3/H5/K10/K12 五族 + 五类消费方） | **零回归** |
| 前端回归（抽凭科目真源 4 spec） | **65 passed** |

🔴 **零回归怎么证的**：本仓库工作树有 **277 个预存失败**（前序未完工作），直接看「有没有 failed」
被噪声淹没。改用**差集法** —— 同一组测试跑两遍（`git show HEAD:` 取基线 json vs 修复版），
比较 failed **测试 ID 集合**：两版 `277 failed / 647 passed` 且 **failed ID 逐条完全相同**
（新增 0、修好 0）⇒ 本次零回归。探针 `_wam_reg.py` 用完即删。

⚠️ 顺带发现 `test_note_report_row_code_alignment.py` 有 **6 个预存失败**
（`note_template_{listed,soe}.json` 残留 95 / 23 处陈旧 `report_row_code`），基线同样红，
与本次无关，属另一笔欠账（修复入口 `remap_note_report_row_codes.py --apply`）。

### 下游产物：隔离实验而非直接生成

`note_template_bindings.json` 由本 json 派生。**直接重新生成得 3662+/7672- 巨大 diff**，
但那绝大部分是**产物本身陈旧**（上游多轮变更而产物未重新生成），与本次 37 项无关。

⇒ 改为隔离实验（基线 json / 修复版 json 各生成一份产物再互 diff），测得本次真实影响
**54 行（新增 32 / 删除 22）**：新增 `1504`×10 `1521`×10 `1631`×8 `6301`×4；
删除 `1501`×10 `1606`×8 `6001`×4 —— 全部为预期修正。

**产物已 `git checkout --` 复原到基线，未随本次提交**：拒绝把「产物陈旧」这笔无关欠账混进本次
diff。产物重新生成应另起独立提交。⚠️ **在此之前运行态读的仍是旧产物**，需重新生成 + 重启后端才生效。

### 任务勾选

- [x] 追加2-1 建幂等修复脚本（拒绝盲目覆盖 + 保护名称字段）
- [x] 追加2-2 触类旁通扩面：主条目 → 同族子条目 → 第 5 族 H3
- [x] 追加2-3 `report_row` 连带 6 项（含 H5 宁缺勿造置 `None`）
- [x] 追加2-4 `--apply` 37 项 + 种子校验 + 幂等复验
- [x] 追加2-5 差集法后端零回归 + 前端 65 passed
- [x] 追加2-6 隔离实验测产物真实影响 54 行 + 勘误文档改写

### 遗留（缩减后）

1. ~~39 处字面量~~ → 已清零
2. ~~`wp_account_mapping.json` 4 处错~~ → **已修复 5 族 37 项**
3. **`note_template_bindings.json` 产物重新生成**（独立提交，diff 全是陈旧欠账）
4. **6.6 Playwright 未实测**（需 `start-dev.bat` 环境）
5. `note_template_{listed,soe}.json` 的 118 处陈旧 `report_row_code`（预存欠账，非本 spec 引入）

---

## 追加批次 3：推送与门禁处置（2026-09-28，同日追加）

前两个追加批次的代码已落盘但**未提交**。本批次做提交与推送，过程中因 pre-commit 门禁
产生了一处**实质代码改动**（抽伴生模块），故单独成节而非只记一句「已推送」。

### 交付物

| 项 | 值 |
|---|---|
| commit | `78b9c1ee5`（单 commit，**102 文件 / +4808 / -204**） |
| 分支 | `work/2026-09-28-voucher-sampling-account-scope` |
| PR | **#10**，base = `fix/adj-formula-repair-and-approval-gate-wiring`（非 main，见下） |

PR 的 base 不是 `main`：本分支从 `fix/adj-formula-...` 分叉，以 main 为 base 时 PR 会显示
**1594 文件 / +304327**（把前序 161 个 commit 全带进来）⇒ 改 base 后精确为 102 文件，
PR diff 与本 spec 的实际产出一致。

### 🔴 pre-commit 行数门禁拦下一次，按其优先顺序处置而非绕过

三个 ledger-penetration 文件超 `check_file_size.py` 门禁。先算清增量再定处置：

| 文件 | HEAD | 本次 | delta | HEAD+5% | 判定 |
|---|---|---|---|---|---|
| `views/LedgerPenetration.vue` | 4213 | 4259 | +46 (+1.09%) | 4423 | 过 |
| `routers/ledger_penetration.py` | 1634 | 1727 | **+93 (+5.69%)** | 1715 | **超阈值** |
| `services/ledger_penetration_service.py` | 942 | 961 | +19 (+2.02%) | 989 | 过 |

三者在 HEAD 版即已超默认上限（上限的 2.8x / 2.0x / 1.2x）⇒ 确属历史大文件。
但 `ledger_penetration.py` 的 +93 行**确实触发了「膨胀 >5%」**，这正是门禁要拦的情形。

处置按门禁提示的优先顺序「拆分文件或抽伴生模块（优先），确有必要再更新 whitelist 基线」，
且仓库有 **6 处先例**明确写「不加 `file_size_whitelist` —— 白名单表头写明仅历史大文件，
新增文件套用属滥用」⇒ 不走「直接加基线」的捷径：

1. **抽伴生模块** `backend/app/routers/_voucher_date.py`（28 行）：把 `_parse_iso_date`
   连同 `from datetime import date as _date` 一起搬出（该别名只服务这一个函数）。
   它是零依赖纯函数、与 HTTP 无关，放在 router 里本就不是它的位置。改后 **1712 ≤ 1715**。
2. **whitelist 登记 3 条，baseline 一律填 HEAD 真实行数**（4213 / 1634 / 942）而非改动后
   行数 —— **不给本次增量预留膨胀空间**，且在条目上方写明「下次再往这三个文件加功能应
   先拆分再改，不再滚雪球加基线」。

🔴 **抽取后做了真 import 验证，而非只看 AST**：`ast.parse` 过不代表运行期名字可解析
（memory 铁律：搬移代码必须查名字在新作用域的可见性）。实跑
`from app.routers._voucher_date import parse_iso_date` + `import app.routers.ledger_penetration`
确认 28 个端点正常、`parse_iso_date` 可见，四个边界值（正常 / 带时间后缀 / 非法 / None）行为符合预期。

### 🔴 提交边界是逐文件核验的，不是 `git add -A`

工作树有 **200+ tracked 变更 + 307 untracked**，多数属并发会话的 A/B/C 轮 spec 工作。
用语义标记法分桶后逐个看：**79 个 tracked 属本 spec**、196 个零标记排除、
**20 个 untracked 属本 spec**、287 个排除（并发 spec / 临时垃圾 `_tsc.txt` `_vt*.json` / 探针）。
暂存后核对「意外多出 0 / 缺失 0 / 敏感文件命中 0」才提交。

两个共享文件特殊处理：

- **`.kiro/specs/INDEX.md` 做部分暂存**：其 diff 同时含并发会话三处改动（Active 62→63 /
  第十四次现扫段 / `pure-static-lane` 0/52→50/52）。构造只含本 spec 那一行的 patch 用
  `git apply --cached --unidiff-zero`，暂存时点验证过并发那三处未进 index。
  🔴 **但该隔离最终失效了 —— 见下方「更正」节，commit `78b9c1ee5` 实际带上了那三处改动。**
- **`.kiro/steering/dev-history.md` 整体暂存**：其 6 行 diff 经逐行核验全属本会话链
  （3 条 entry + 3 个空行）。
- **`c-cycle-sync-foundation-and-first-canary/tasks.md` 排除**：hit=1 miss=268，属并发 C 轮 spec。

### 并发会话两次干扰（如实记录，非本 spec 缺陷）

工作树与 git 状态是共享的，期间另一条会话两次改动共享状态：

1. 在我 `git add` 之后把 8 个 `chain-closure-phase1` 文件 add 进了 index ⇒ 已
   `git restore --staged` 移出（只动 index 不动工作树），复验回到精确 102。
2. 在我 commit 之后把分支切走，并把 `work/2026-09-28-voucher-sampling-account-scope`
   指针回退到 `99100078b`（前序 adj commit）⇒ **第一次 push 推上去的是错的 commit**。
   我的 commit 未丢（在并发分支上作为祖先）；确认 `78b9c1ee5^ == 99100078b == 远端当前`
   后用显式 refspec 做 **fast-forward** 推送（`git merge-base --is-ancestor` 返回 0 验证），
   **未用 `--force`**。远端复验 = `78b9c1ee5`。

### 本批次复验（不沿用前序数据）

| 项 | 结果 |
|---|---|
| 抽凭真源 5 个 spec | **107 passed**（`samplingAccountCodeSource` 26 + `attachedVouchersAccountScope` 10 = 两守卫 **36/36** 属实；`samplingHostMethodologyCoverage` 42 + `pullSamplesForWorkpaper` 15 + `useSamplingAccountGate` 14） |
| `test_sampled_voucher_scope_and_date.py`（抽伴生模块后） | **17 passed** |
| `check_file_size.py` 对 4 个目标文件 | rc=0 全过 |
| 任务 6.4 探针清理现查 | `_vsa_*` / `_wam_*` / `_push_*` 全部 0 个 |

⚠️ **「追加-6 回归 236 passed」是追加批次 1 当时的数据，本批次未重跑那 9 个 suite** ——
本批次改动（`wp_account_mapping.json` + 抽伴生模块）不触及前端抽凭组件，
故只复验了上表 5 个核心 spec。如需完整口径应重跑那 9 个 suite。

### 任务勾选

- [x] 追加3-1 逐文件核验提交边界（79 tracked + 20 untracked，零意外零缺失零敏感）
- [x] 追加3-2 共享文件 `INDEX.md` 部分暂存（patch 法，验证并发改动未进 index）
- [x] 追加3-3 pre-commit 门禁处置：抽伴生模块 `_voucher_date.py` + whitelist 登记 HEAD 基线
- [x] 追加3-4 抽取后真 import 验证（非仅 AST）+ 17 passed
- [x] 追加3-5 commit `78b9c1ee5` + fast-forward 推送（并发干扰后修正，未用 force）
- [x] 追加3-6 PR #10 创建并修正 base（1594 文件 → 102 文件）

### 全 spec 遗留（现状口径）

1. ~~39 处字面量~~ → 已清零
2. ~~`wp_account_mapping.json` 4 处错~~ → 已修 5 族 37 项
3. **`note_template_bindings.json` 产物重新生成**（独立提交；⚠️ 在此之前**运行态仍读旧产物**，
   需 `generate_note_template_bindings.py` + 重启后端才生效）
4. **6.6 Playwright 未实测**（`[ ]*`，需 `start-dev.bat` 环境 —— 本批次仍未执行）
5. `note_template_{listed,soe}.json` 的 118 处陈旧 `report_row_code`（预存欠账，基线同样红）
6. 三个 ledger-penetration 文件的**整体瘦身**（已登记 whitelist 待办，下次碰它们应先拆分）

### 🔴 更正（追加批次 3 自查，2026-09-28）：INDEX.md 的隔离最终失效，我的记录是假陈述

上文写「构造只含本 spec 那一行的 patch…并验证 staged 版本里并发那三处确实未进 index」。
**该结论在提交时点已不成立。** 现算 commit `78b9c1ee5` 的 `INDEX.md`：

| 检查项 | 我原先声称 | 现算实际 |
|---|---|---|
| 本 spec 那行（`31/32 + 追加 12`） | 应在 | ✅ 在 |
| 并发改动 `Active **63**` | **不应在** | 🔴 **在** |
| 并发改动 `pure-static-lane **50/52**` | **不应在** | 🔴 **在** |

（对照 `HEAD~1` 三项全为 False，可确认这三处是被我的 commit 带进去的。）

**失效机理**：patch 精确暂存做在**第一次 commit 尝试之前**。那次被 pre-commit 行数门禁
拦下后，我又做了抽伴生模块 + whitelist 登记，再 `git add` 3 个文件。**并发会话在这个窗口里
也对 `INDEX.md` 执行了 `git add`**（同一动作把 8 个 `chain-closure-phase1` 文件塞进 index），
这会把 `INDEX.md` 的**完整工作树版本**放进 index，**覆盖掉我此前的精确 patch**。

**我的核验漏洞**：提交前的审计脚本只比对**文件名集合**（「意外多出 / 缺失」），
`INDEX.md` 本就在预期清单内 ⇒ 集合检查全绿、内容被换掉却查不出来。
⇒ **共享文件做部分暂存后，若中途有任何其它 `git add`，必须在 commit 前重新核验 staged 的「内容」而非只核验文件名。**

**处置裁决：不 force push 纠正。** 理由：① 那三处改动本身是并发会话真实完成的工作
（`pure-static-lane` 确已实施 50/52、Active 63 是现扫统计），留在历史里不产生错误信息，
只是归属混了；② 改写已推送的 commit 需 force push，而并发分支
`work/2026-09-28-chain-closure-phase1` 以它为祖先，风险高于收益。
⇒ 如实登记归属混入，不掩盖。


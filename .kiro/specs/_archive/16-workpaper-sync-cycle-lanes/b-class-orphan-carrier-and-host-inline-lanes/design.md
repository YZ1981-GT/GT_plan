# B 类孤儿载体与宿主内联门控通道 — 设计

## 定位

本 spec 是 B 循环三份 sync spec 的 **lane 3**，承担 `useWpDualMode.ts` 孤儿载体上的 **3** 条与 `host_inline_segmented` 的 **2** 条，合计 **5** 条 entry。

共同判据一律引用 `b-cycle-sync-foundation-and-first-canary` 的 **BC-1 ~ BC-60**，本文件不重复裁决。

## 一、两个子组的事实矩阵

| 项 | `gt-b1-evaluation` | `gt-b1-kaa-check` | `gt-b1-risk-assessment` | `gt-b14-due-diligence-report` | `gt-b23-process-control` |
|---|---|---|---|---|---|
| 子组 | A（孤儿载体） | A | A | B（宿主内联） | B |
| 宿主行数 | 432 | 311 | 538 | 636 | 963 |
| sheet 名表达式 | `sourceSheet \|\| '业务评价表B1-3'` | `sourceSheet \|\| ' B1-5 KAA检查表-业务承接'` | `ooSheetName` | `sourceSheet \|\| '尽职调查报告B1-4'` | `currentCard.name` |
| mode 值 | `'结构化视图'` | `'结构化视图'` | `'结构化视图'` | `'结构化视图'` / `'在线编辑'` / `'polish'` | `'structured'` |
| 宿主内 `modeOptions` | 否 | 否 | 否 | **是（3 处）** | 否 |
| segmented 数 | 1 | 1 | 1 | **2** | 1 |
| 门控假阴 | 否 | 否 | **是** | 否 | **是** |
| `checklist` 深度 | D1（`useB1Evaluation.ts`） | D1（`useB1KaaCheck.ts`） | D1（`useB1RiskAssessment.ts`） | D1（`useB14DueDiligence.ts`） | D1（`useB23FormData.ts`） |
| 行身份缺陷 | — | — | — | `rowIndex` 形参 2 | `idx` 形参 |
| 稳定身份正样本 | **有** | — | — | **有** | **有** |
| `.reduce(` 派生 | — | — | **4 处** | — | — |
| `removeRow` | — | — | — | — | **有** |
| `count` 键 | — | — | — | — | **有** |
| 权威册格式 | docx | xlsx | xlsx | docx（两本） | **xlsm（14 本家族）** |
| 真库载荷 | 0 | 0 | 0 | 0 | **2 行** |

🔴 子组 A 三条真库载荷全为 **0**；`B1*` bucket 唯一 1 行是 `B1-review-session-20260725075000`（AI 会话），其 wp_code 为裸 `B1`，不属本组任何 entry。

## 二、孤儿载体删除设计（需求 1）

### 2.1 为什么本组载体会成孤儿

| 载体 | B 域边 | 全域边 | 差值 |
|---|---|---|---|
| `useWpDualMode.ts` | **3** | **3** | **0** ⇒ 改线后无人引用 |
| `useWorkpaperEntryDualMode.ts` | 5 | 26 | 21 ⇒ 须保兼容 |

`useWpDualMode.ts` 的全域生产边恰好等于 B 域边 ⇒ 本组 3 条改完即孤儿。这是 slice 中**唯一**标 `becomes_orphan_after_rewire = True` 的共享载体。

### 2.2 删除顺序（平台铁律：删前 grep 0 调用方）

1. 3 条 entry 逐条改线，每条改完后 grep 剩余引用数
2. 引用数归零后再删文件（未归零不可提前删）
3. 删除前后测试全绿
4. 删除独立成 commit + 可回滚
5. 🔴 若存在 deprecated 过渡期，不得超过 1 个 sprint

### 2.3 与 lane 2 的动作对比

| | lane 2（共享基类） | 本 spec 子组 A（孤儿载体） |
|---|---|---|
| 改线策略 | 新增可选参数 + 缺省退回旧路径 | 直接改，无需保兼容 |
| 收尾动作 | 保留载体文件 | **删除载体文件** |
| 回滚粒度 | 按 entry | 按 entry（删除步骤单独回滚） |

## 三、解析失败三模式设计（需求 2）

本组是三种失败模式**全部出现**的唯一分组：

| 模式 | 触发 entry | 现象 |
|---|---|---|
| 返回 `None` | `gt-b1-evaluation`（`业务评价表B1-3`）· `gt-b1-risk-assessment`（`风险评估表-保持` / `-承接`）· `gt-b14`（`尽职调查报告B1-4`） | finder 按册名前缀查，对 sheet 名无匹配 |
| 抛 `FileNotFoundError` | `gt-b1-kaa-check`（`' B1-5 KAA检查表-业务承接'`，带前导空格） | 🔴 与 A 域 BP-6 不同型 |
| 多册歧义 | `gt-b14`（`B1-4` 对应标准版 39 表 / 简化版 23 表两本册） | 解析结果取决于 finder 排序 |

### 3.1 根因（已实证，非推演）

`B1-1` 册的 sheet 名就是 `风险评估表-承接`、`B1-2` 册的是 `风险评估表-保持` ⇒ **override 表里登记的「wp_code」实际是 sheet 名**（BC-51）。前导空格同样来自真实 sheet 名（`B1-5 KAA检查程序表.xlsx` 的 sheet 名实测即 `' B1-5 KAA检查表-业务承接'`）⇒ slice 的 fallback 字面量是照抄真实 sheet 名，本身正确，错在 override 表的字段语义。

### 3.2 兜底设计

解析层须同时捕获 `None` 与异常，并对多册情况要求显式指定：

1. `try/except FileNotFoundError` 与 `if result is None` 两路都要有
2. 失败时返回可诊断信息（区分「码不存在」「sheet 名被当码查」「多册歧义」）
3. 🔴 sheet 名禁归一化（禁 `strip()`）—— 前导空格是真实数据（BC-10）
4. `B1-4` 的标准版 / 简化版须显式选册并在守卫中断言 size + sha256

## 四、一 componentType 四 wp_code 消歧（需求 3）

`xlsx/gt-b1-risk-assessment` 的 `wp_codes_via_component_type` 有 **4** 项，其中 2 个是真实码（`B1-1` / `B1-2`）、2 个是 sheet 名（`风险评估表-保持` / `风险评估表-承接`）。

对应关系（实测）：`B1-1` → `B1-1 风险评估表（适用于承接）.xlsx`（sheet 名 `风险评估表-承接`）；`B1-2` → 保持版。

设计：

1. 持久化命名空间按 wp_code 分离（承接版与保持版不共享 `item_id` 前缀）
2. 解析只接受真实码（`B1-1` / `B1-2`），sheet 名作为册内定位而非册查找输入
3. override 表的 2 条 sheet 名项登记为缺陷并上报（BC-51）

## 五、宿主内联组设计（需求 4）

### 5.1 `gt-b14-due-diligence-report` 三项特殊

| 项 | 现状 | 设计 |
|---|---|---|
| 双 segmented | **2** 个控件（全 B 域唯一） | 门控扫描按控件归属，不计重；确认两个控件各自门控哪个视图 |
| 宿主内 `modeOptions` | **3** 处字符串数组（`['结构化视图','在线编辑']` + 2×`['结构化视图']`）；全 B 域唯一在宿主内声明 | 改线时统一到共享定义，避免三处漂移 |
| 写死对标公司 | `#L347` `{ key: 'peer1', label: '对标公司1', width: 120 }` + `#L348` `peer2` | 改为动态列（BC-48 / Property 22 D2） |

`rowIndex` 形参 **2** 处索引章节表 JSON 数组 ⇒ 改稳定 id，同宿主 `sections` 已有 `sec.id` 可直接参照（slice 的 `stable_alternative_available` 明文）。

### 5.2 `gt-b23-process-control` 的 xlsm 制约

权威册是 B23 家族 **14** 本 xlsm（`B23-1` ~ `B23-14`，5 本接近 1 MB），运行时实测解析到 `B23-15 了解信息处理控制.xlsx`。

| 风险 | 现状 | 处置 |
|---|---|---|
| VBA 宏丢失 | openpyxl 默认 `vba_archive = None` | 必须 `keep_vba=True` |
| 数据验证丢失 | `Data Validation extension is not supported and will be removed` | 🔴 **无技术解**，登记为已知限制 |
| 影响面 | 16 / 66 本报该警告，其中 14 本是 B23 家族 | 回写路径须避开重写整册，或换库 |

`currentCard.name` 作 sheet 名表达式（全 B 域唯一形态 D）⇒ 运行时值取决于当前选中卡片，须在守卫中枚举可能取值。

### 5.3 门控假阴两条（子组内）

`gt-b1-risk-assessment` 与 `gt-b23-process-control` 的 OO 挂点门控条件在祖先链或 v-else 链头上 ⇒ 仅扫自身属性会漏判（BC-13）。全 B 域 3 处假阴中本 spec 占 **2**。

## 六、Property 清单（BH-P1 ~ BH-P22）

| Property | 命题 | 现算值 | 判据 |
|---|---|---|---|
| BH-P1 | 子组 A 三条全挂 `useWpDualMode.ts` | 3 | BC-2 |
| BH-P2 | 该载体全域边 3 == B 域边 3（成孤儿充要条件） | 3 == 3 | BC-58 |
| BH-P3 | `becomes_orphan_after_rewire` 为真（全 slice 唯一） | True | BC-58 |
| BH-P4 | 子组 A 挂点行号 `#L223` / `#L166` / `#L301` | 3 | BC-2 |
| BH-P5 | 子组 B 两条 `dual_mode_carrier.kind` 为 `host_inline_segmented` | 2 | BC-2 |
| BH-P6 | 三种解析失败模式在本组全部出现 | 3/3 | BC-52 |
| BH-P7 | 前导空格 sheet 名抛 `FileNotFoundError` 且禁 `strip()` | 1 | BC-46 / BC-10 |
| BH-P8 | 根因：`B1-1` 册 sheet 名即 `风险评估表-承接`、`B1-2` 即 `风险评估表-保持` | 2 | BC-51 |
| BH-P9 | 本组 4 个 manifest pattern 全部解析为 `None` | 4/4 | BC-15 |
| BH-P10 | `gt-b1-risk-assessment` 的 1 个 componentType 覆盖 4 个 wp_code | 4 | BC-15 |
| BH-P11 | `B1-4` 对应两本册（标准版 39 表 / 简化版 23 表） | 2 | BC-50 |
| BH-P12 | `gt-b14` 有 2 个 segmented（全 B 域唯一） | 2 | BC-13 |
| BH-P13 | `gt-b14` 是全 B 域唯一在宿主内声明 `modeOptions` 的 entry（3 处） | 1 / 3 | BC-41 |
| BH-P14 | `gt-b14` 另有第四值 `'polish'` | 1 | BC-41 |
| BH-P15 | 写死对标公司 2 家在 `#L347` / `#L348` | 2 | BC-48 |
| BH-P16 | `rowIndex` 形参 2 处，kind 为 `function_parameter_row_index_into_json_array` | 2 | BC-53 |
| BH-P17 | `.reduce(` 派生 4 处全在 `gt-b1-risk-assessment`（全 B 域唯一） | 4 | BC-14 |
| BH-P18 | 门控假阴本组 2 条（全 B 域 3 中占 2） | 2 | BC-13 |
| BH-P19 | B23 家族 14 本 xlsm 全含 `xl/vbaProject.bin`，回写须 `keep_vba=True` | 14 | BC-49 |
| BH-P20 | `currentCard.name` 是全 B 域唯一 sheet 名表达式形态 D | 1 | BC-10 |
| BH-P21 | 幽灵行 335 行 / 2 列（438×5 vs last_value 103×3） | 335 / 2 | BC-35 |
| BH-P22 | 子组 A 三条 + `gt-b14` 真库载荷全为 0；`B1*` 唯一 1 行是 AI 会话且 wp_code 为裸 `B1` | 0 / 1 | BC-60 |

**编号完整性**：BH-P1 ~ BH-P22 连续 **22** 条，无缺号无重号。

## 七、守卫测试类映射

| 测试类 | Property |
|---|---|
| `TestOrphanCarrierLifecycle` | BH-P1 ~ BH-P5 |
| `TestResolutionFailureModes` | BH-P6 ~ BH-P11 |
| `TestHostInlineGateAndModeOptions` | BH-P12 ~ BH-P14、BH-P18 |
| `TestRowIdentityAndHardcodedColumns` | BH-P15 ~ BH-P17 |
| `TestXlsmMacroAndGeometry` | BH-P19 ~ BH-P21 |
| `TestZeroDenominatorEntries` | BH-P22 |

# Requirements Document

## Introduction

自定义底稿（`componentType=custom`）当前处于「能创建、看不见、编不了、导不出」的状态。2026-08-06 全链只读实证：

| 环节 | 实测 | 依据 |
|---|---|---|
| componentType 派生 | ✅ 通 | `wp_classification_service.derive_component_type` L523-527：`class_code.upper().startswith("CUSTOM")` → `"custom"` |
| 前端 registry | ✅ 通 | `htmlRendererRegistry.ts` L504-511 → `GtCustomWpEditor`，`contextProps:'custom'` |
| 后端 renderer | ❌ 无 | `RENDERER_DISPATCH` 无 `"custom"` 键 |
| `parsed_data` 初始化 | ❌ 缺 | `create_custom_workpaper`（`wp_template.py:491`）**不调 `populate_parsed_data`**（同文件模板生成路径 L464 有调） |
| 网格能显示内容 | ❌ 不能 | `write_cell_to_parsed_data` 只写 `cells`、**不维护 `max_row`/`max_col`**，而 `GtGridSheet.hasData = Object.keys(cells).length>0 && maxRow>0` |
| 网格可编辑 | ❌ 不能 | `GtGridSheet` `withDefaults(..., {readonly: true})`，全文零 `emit`/零输入控件；`readonly` prop 只输出 `data-readonly` 属性、不参与渲染分支 |
| HTML↔OO 双模式 | ❌ 零接线 | `GtCustomWpEditor.vue` 无 `el-segmented`、无 `GtOnlyOfficeSheet`、无任何 `*DualMode`；`"custom"` 亦不在 `_ONLYOFFICE_HTML_WHITELIST` |
| 公式定义保存 | ✅ 通 | `PUT /api/workpapers/{wp_id}/formulas` → `wp_formula` 表（V052 建表 + V100/V104 扩列） |
| 公式选址列表 | ❌ 空 | `GtCustomWpEditor.wpContext.cells` 读 `props.htmlData.cells`（L74-85），空底稿下为空数组 |
| 求值结果可见 | ❌ 断 | 后端写进 `html_data.cells` 但 `maxRow=0` 渲染不出；且 `onFormulaSave` L131-136 只读 `res.eval_warnings`、**不读 `res.evaluated_value`** |
| 导出 xlsx | ❌ 500 | `wp_xlsx_export.py` 第一步 `load_schema(wp_code)`，自定义编号无 yaml → `FileNotFoundError` → 500 |
| 导出结构解析 | ❌ 形态不兼容 | 导出服务读 `html_data[sheet]["rows"]`（`dynamic_table` 形态），自定义底稿是 `{cells:{A1:...}}` 形态 |
| 导出格式判定 | ❌ 无映射 | `determine_export_format` 的 `_XLSX_TYPES`/`_DOCX_TYPES` 均无 `"custom"`，落默认 xlsx |
| 批量创建 | ❌ 无 | `create-custom` 单条；`batch-structure` 是为**已有底稿**批量生成 `structure.json`（地址坐标），语义不同 |

⇒ 三个断点叠加使公式功能实际处于「能存进库、既选不了格也看不到值」的状态：
`create-custom` 不填 `parsed_data` → `cells` 空 → `hasData` 恒 false（网格显示「此表格底稿模板暂无内容」）
→ 选址列表空 → 用户选不了 `target_cell` → 前端 `onFormulaSave` L114-116 抽不到地址即 `warning` 不发请求。

### 架构口径（用户 2026-08-06 拍板）

**xlsx 文件是唯一权威，`html_data.cells` 是它的投影。**

平台既有双模式（N1/N2/N4/F2/I1/G14 等 6+ 宿主）两侧数据**不共享**：HTML 侧读 `parsed_data.html_data`、写
`checklist-responses`；OO 侧走 WOPI 直编 xlsx 本体；切回 HTML 靠 `reloadAll()` 重拉，**无「xlsx → html_data」反向同步**。
标准底稿能这么活，是因为 HTML 侧是结构化表单（字段有确定语义）、OO 只是逃生口。**自定义底稿没有这个前提** ——
它是自由网格，两侧编的是同一批单元格；照抄现有范式会导致「OO 改完切回 HTML 看到旧值」= 数据打架而非双模式。

故本 spec 确立 xlsx 权威口径：
- 投影必须是**恒等坐标**的（投影 `B6` ≡ xlsx `B6`），HTML 侧格编辑才能安全写回 xlsx
- HTML 侧格编辑写回 xlsx（openpyxl）并刷新投影
- 公式求值结果**同时写 xlsx 与投影**（现有 `write_cell_to_parsed_data` 单写投影 ⇒ OO 模式下看不到公式值）
- 导出直接走 xlsx 本体，不套 `dynamic_table` schema（那是给固定结构底稿用的）

#### 🔴 立项时的错误假设已被实证推翻（2026-08-06 探针）

立项写「投影单一入口 = 既有 `extract_grid`，键集恰好覆盖，投影层不新造」。**实测两处不成立**，
照它实现会写坏用户数据：

| 实测 | 证据 | 后果 |
|---|---|---|
| `extract_grid` **重编行号** | `extract_grid_from_sheet` 的 `row_offset = data_start_row - 1`；`new_coord = f"{_col_letter(c)}{new_r}"`。探针：xlsx `B6=123.45` 投影成 **`B2`**（列不变、只有行位移） | 用户编辑投影 `B2` 若按同名写 xlsx `B2` → **写进表头区、覆盖别的格**；且 `data_start_row` 是启发式（首个含「项目」/「序号」的行），用户录入过程中会**跳变** ⇒ 同一投影坐标在两次加载间指向不同 xlsx 行 |
| 空/失败路径**只返 5 键** | 探针：`extract_grid(p,'NOSUCH')` → `['cells','col_widths','max_col','max_row','merged_cells']`，**无 `header_rows`/`column_meta`** | 「投影键集 ⊇ 六键」的守卫在 fail-open 路径必红 |

⇒ 修正口径：自定义底稿走**恒等坐标的原始投影**（不剥表头、不重编行号、不裁空列），
`extract_grid` **保持零改动**（它有 11 个既有调用方依赖现行为，其重编号对只读渲染是有意设计）。
恒等坐标同时消掉第三个隐患：`wp_formula.target_cell` 究竟是投影坐标还是 xlsx 坐标 ——
两者相等则该歧义不存在。

### 与并发 spec `formula-management-runtime-closure` 的边界

该 spec（本会话实测已有完整三件套）承担：`COLUMN_ALIASES` 补四键与消除静默回退（其 R3）、
用户公式与 Tier A 存储收敛到 `wp_formula`（其 R4）、两份 `WP()` 实现一致性守卫（其 R5）、
三类型执行链接通（其 R6）、端点收敛进 `apiPaths`（其 R7）。

**本 spec 不碰**求值引擎内部、不碰 `wp_formula` 存储收敛、不碰 `COLUMN_ALIASES`。
本 spec 的公式部分收窄为「选址可用 + 结果可见 + 清单可管 + 求值结果落 xlsx」，
即自定义底稿这一侧的**消费与呈现**。两侧交汇点是 `wp_formula` 表与 `PUT /formulas` 端点，
本 spec 只做加法式消费，不改其存储语义与响应形状。

## Requirements

### Requirement 1: xlsx 权威口径与投影单一入口

**User Story:** 作为平台维护者，我需要自定义底稿的数据只有一个权威来源，
避免 HTML 侧与 OO 侧各存一份导致数字打架。

#### Acceptance Criteria

1. WHEN 自定义底稿的 render-config 被请求 THEN 系统 SHALL 由 xlsx 文件投影出 `html_data`，
   不得把投影结果当作独立权威长期存储
2. WHEN 投影产出 THEN 它 SHALL 包含 `cells` / `max_row` / `max_col` / `col_widths` /
   `merged_cells` / `header_rows` 六键，与 `GtGridSheet` 消费键集一致；
   **含 xlsx 缺失/损坏的 fail-open 路径**（该路径不得少键）
3. WHEN 投影产出 THEN 单元格坐标 SHALL 与 xlsx 恒等（投影 `B6` ≡ xlsx `B6`），
   **SHALL NOT** 重编行号、剥离表头行或裁剪空列
4. WHEN xlsx 文件不存在或损坏 THEN 投影 SHALL fail-open 返回空网格并记录 WARNING，
   **不得**抛异常阻断整个 render-config；前端 SHALL 有可见提示以区别于「空底稿」
5. WHERE 投影逻辑需要复用 THEN 它 SHALL 收敛为单一函数（自定义底稿专用），
   不得在多处各写一份 openpyxl 读取
6. WHEN 交付 THEN `wp_grid_extract.extract_grid` 与 `extract_grid_from_sheet` SHALL 逐字节不变
   （11 个既有调用方依赖其重编号行为）
7. WHEN 交付 THEN 守卫 SHALL 断言投影函数的输出键集 ⊇ `GtGridSheet` 的消费键集
   （读前端源码抽取，跨前后端交叉锁死）
8. WHEN 交付 THEN 守卫 SHALL 断言坐标恒等性：对含表头的替身 xlsx，写 `B6` 后投影键含 `B6`；
   并用「改用 `extract_grid`」的变异复现行位移缺陷（必须打红）
9. IF 未来出现「HTML 侧独立存库」的诉求 THEN 该变更 SHALL 另立 spec，
   本 spec 的守卫 SHALL 钉死当前 xlsx 权威口径不被静默改变

### Requirement 2: 自定义底稿内容可见性修复

**User Story:** 作为审计助理，我创建自定义底稿后打开它应该看到带标准表头的网格，
而不是「此表格底稿模板暂无内容」。

#### Acceptance Criteria

1. WHEN `create_custom_workpaper` 创建底稿 THEN 它 SHALL 初始化 `parsed_data`
   使投影可用（复用模板生成路径 L464 的 `populate_parsed_data` 范式或等价投影）
2. WHEN `fill_workpaper_header` 已把标准表头写入 xlsx THEN 投影 SHALL 能读出这些表头单元格，
   使新建底稿打开即可见编制单位/审计期间/索引号等
3. WHEN `write_cell_to_parsed_data` 写入单元格 THEN 它 SHALL 同时维护 `max_row` / `max_col`
   为 `max(既有值, 当前 cell 的行/列)`，使 `hasData` 判定成立
4. WHEN 底稿只有表头没有数据 THEN 网格 SHALL 渲染表头区域而非「暂无内容」空态
5. WHEN 交付 THEN 守卫 SHALL 断言 `write_cell_to_parsed_data` 写入后 `max_row ≥ 目标行`，
   并用「只写 cells 不写 max_row」的变异复现旧缺陷（必须打红）
6. WHERE 既有自定义底稿的 `parsed_data` 为空 THEN 系统 SHALL 在 render 时按 xlsx 投影补齐，
   不要求用户重建底稿

### Requirement 3: 网格单元格可编辑并写回 xlsx

**User Story:** 作为审计助理，我需要在 HTML 模式下直接编辑自定义底稿的单元格，
而不是只能切到 OnlyOffice 才能录入。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 提供可编辑网格能力，且 **SHALL NOT** 修改共享只读组件
   `GtGridSheet`（它有 40+ 只读消费方，改默认值会波及全平台）
2. WHEN 用户编辑一个单元格并失焦 THEN 系统 SHALL 把值写回 xlsx 文件本体，
   并刷新该单元格的投影值
3. WHEN 写回发生 THEN 系统 SHALL 递增 `working_paper.file_version` 并更新时间戳，
   与既有 `univer-save` 的版本语义一致
4. WHEN 单元格承载公式（存在对应 `wp_formula` 记录）THEN 该格 SHALL 只读，
   并给出「该格由公式计算」的提示，不允许手工覆盖
5. WHEN 底稿处于只读态（归档/已签署/无编辑权限）THEN 全部单元格 SHALL 不可编辑
6. WHEN 金额型单元格被编辑 THEN 显示 SHALL 走平台金额格式单一真源
   `stores/displayPrefs.fmtAmount`（经 setup 顶层注入，禁模块级命名导入）
7. WHEN 交付 THEN 守卫 SHALL 断言 `GtGridSheet` 的 `readonly` 默认值与零 `emit` 特性未被改变
8. WHERE `GtGridSheet` 的 `user_input` tooltip 现写「双击编辑」而无实现 THEN 该文案
   SHALL 与真实能力对齐（有实现则保留、无实现则移除），不得留误导性提示

### Requirement 4: HTML / OnlyOffice 双模式接线

**User Story:** 作为审计助理，我需要在结构化网格与在线 Excel 编辑之间切换，
复杂表格用 OnlyOffice 编排、日常录入用网格。

#### Acceptance Criteria

1. WHEN 自定义底稿渲染 THEN 宿主 SHALL 提供 HTML / 在线编辑 双模式切换控件
2. WHEN 接入双模式 composable THEN 它 SHALL 复用参数化工厂
   `composables/factories/createDualMode`（取值 `'html' | 'onlyoffice'`），
   **SHALL NOT** 复用 `useD1DualMode`（其取值为 `'html' | 'oo'`，与其余循环不统一，
   选错会与既有 localStorage 持久化值冲突）
3. WHEN 渲染切换控件 THEN 它 SHALL 使用 `:model-value` + `@change`，
   **SHALL NOT** 使用 `v-model`（v-model 会先改值使 `switchMode` 的守卫短路）
4. WHEN OnlyOffice 服务不可用 THEN 切换控件 SHALL 禁用在线编辑选项并保持 HTML 模式
5. WHEN OnlyOffice 加载失败 THEN 系统 SHALL 经 `GtOnlyOfficeSheet` 的 `@fallback` 降级回 HTML 模式
6. WHEN 用户在 OnlyOffice 侧修改并保存（forcesave 回调落 xlsx）THEN 切回 HTML 模式时
   系统 SHALL 由 xlsx 重新投影，使两侧看到同一份数据
7. WHEN 模式偏好被切换 THEN 它 SHALL 按 `{prefix}{wpId}` 持久化到 localStorage
8. WHEN 交付 THEN `"custom"` SHALL 加入后端 `_ONLYOFFICE_HTML_WHITELIST`，
   防止将来自定义底稿出现多 sheet 时被 `wp_render_config` 的 OnlyOffice 改写分支
   （L873-875，条件含 `_is_multi_sheet`）静默劫持成 `onlyoffice-sheet` 而使专属组件永不渲染
9. WHEN 交付 THEN 守卫 SHALL 断言宿主使用 `createDualMode` 而非 `useD1DualMode`，
   且切换控件不含 `v-model`

### Requirement 5: 公式选址可用与求值结果可见

**User Story:** 作为审计助理，我给自定义底稿加公式时应能从网格里点选目标单元格，
保存后立刻看到计算结果。

#### Acceptance Criteria

1. WHEN 打开公式编辑对话框 THEN 目标单元格候选列表 SHALL 由**投影后**的 `cells` 提供，
   使有表头的新建底稿也能选址
2. WHEN 用户在网格中点击某单元格 THEN 系统 SHALL 支持将其作为公式写入目标，
   与 `FormulaEditDialog` 既有 `targetPickerMode === 'wp'` 的整行点选并存
3. WHEN 公式保存成功且后端返回 `evaluated_value` THEN 前端 SHALL 立即展示该值，
   不要求用户手动刷新
4. WHEN 公式求值结果写入 THEN 系统 SHALL **同时**写 xlsx 单元格与投影 `cells`，
   使 OnlyOffice 模式下也能看到公式值
5. WHEN 求值返回 `eval_warnings` THEN 前端 SHALL 展示告警明细而非只提示条数
6. WHEN 公式求值失败 THEN 系统 SHALL 保留公式定义并标注「未计算」，不得静默丢弃定义
7. WHERE 求值引擎内部行为（`COLUMN_ALIASES` / 静默回退 / 三类型执行）
   THEN 本 spec SHALL NOT 修改，该范围归 `formula-management-runtime-closure`
8. WHEN 交付 THEN 守卫 SHALL 断言 `onFormulaSave` 读取了 `evaluated_value`
   （变异「只读 eval_warnings」必须打红）

### Requirement 6: 自定义底稿公式清单管理

**User Story:** 作为审计助理，我需要看到这张底稿上已有哪些公式、分别写在哪个格、
并能修改或删除，而不是只能一格一格盲加。

#### Acceptance Criteria

1. WHEN 打开自定义底稿 THEN 系统 SHALL 展示该底稿已保存的公式清单
   （目标格 / 表达式 / 类型中文标签 / 说明 / 最近计算时间）
2. WHEN 清单为空 THEN 系统 SHALL 显示空态并给出「新增公式」入口，不显示空表格
3. WHEN 用户点击清单某条 THEN 系统 SHALL 在网格中定位并高亮该目标单元格
4. WHEN 用户删除一条公式 THEN 系统 SHALL 删除定义并清除该格的求值结果，
   使该格恢复可手工编辑
5. WHEN 展示 `formula_type` THEN 它 SHALL 显示中文标签，复用既有单一真源
   `formulaEngineInventory.FORMULA_TYPE_LABEL`，不得新建第二份标签表
6. WHERE 清单数据来源 THEN 它 SHALL 取自 `GET /api/workpapers/{wp_id}/formulas`
   的 **`items`** 键（后端 `list_formulas` 的真实返回键）
7. WHERE 端点路径需要引用 THEN 它 SHALL 取自 `apiPaths`，不得硬编码模板字符串
8. WHEN 交付 THEN 守卫 SHALL 断言清单读的是 `items` 而非 `formulas`
   （后者是 `useFormulaStatus` 已实证的错配形态）

### Requirement 7: 自定义底稿导出

**User Story:** 作为审计助理，我需要把自定义底稿导出成 Excel 交给复核人或归档，
而不是点导出直接报错，也不是拿到一张近乎空白的表。

#### Acceptance Criteria

1. WHEN 导出自定义底稿 THEN 系统 SHALL 走独立导出路径直接产出 xlsx 本体，
   **SHALL NOT** 要求 `wp_render_schema` 下存在该编号的 yaml
2. WHEN 自定义底稿无 render schema THEN 导出 SHALL 成功而非返回 500
3. WHEN 交付 THEN **两条**导出路径 SHALL 都被分流（2026-08-06 实证平台有两条，
   立项只覆盖了第一条）：
   （a）`POST /api/workpapers/{wp_id}/export-xlsx` —— `wp_xlsx_export.py:80` 第一步
   `load_schema` ⇒ 自定义编号必 `FileNotFoundError` ⇒ **500**
   （b）`WpExportEngine.export_single` —— 由 `wp_export_import_router.py` 两处调用，
   其 `_export_xlsx` 写 `except (TemplateNotFoundError, Exception)` **宽捕获后回退空白 workbook**
4. WHEN 自定义底稿走路径（b）THEN 它 SHALL 在那条宽捕获兜底**之前**被分流，
   **SHALL NOT** 依赖兜底产出内容 —— 兜底不报错却给出近乎空表，
   比 500 更坏（用户以为导出成功了）
5. WHEN 导出产出 THEN 它 SHALL 包含公式求值结果（因求值已写回 xlsx，见 R5.4）
6. WHEN 导出产出 THEN 它 SHALL 复用既有 `WpExportEngine` 外壳的元数据嵌入
   （`MetadataCodec`）与快照哈希（`compute_snapshot_hash` + `wp_export_snapshot`）
7. WHEN `determine_export_format` 判定自定义底稿 THEN `"custom"` SHALL 有显式映射到 `xlsx`，
   不依赖「默认 xlsx」这条隐式兜底
8. WHERE `determine_export_format` 的既有 PBT（`test_pbt_export_format.py` 自带
   `XLSX_TYPES` / `DOCX_TYPES` 清单）THEN 往 `_XLSX_TYPES` 加 `"custom"` 后
   该测试 SHALL 同步登记，否则「全类型映射完备」断言与真源分叉
9. WHEN 导出的 xlsx 被重新上传/导入 THEN 系统 SHALL 能解析回投影
   （即投影函数可读，往返可逆）
10. WHEN 交付 THEN 守卫 SHALL 断言自定义底稿导出路径不调用 `load_schema`，
    并用「无 schema 的自定义编号」对**两条**路径各做一次端到端断言
    （变异回旧路径必须打红；路径 b 的变异 = 移除分流后必须产出空表而非正确内容）
11. WHERE docx 方向的导出 THEN 本 spec SHALL NOT 实现（自定义底稿是网格形态），
    并在 Notes 显式登记该决定与理由

### Requirement 8: 批量创建自定义底稿

**User Story:** 作为现场经理，我需要一次创建十几张自定义底稿，
而不是在弹窗里重复填十几次编号和名称。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 支持**两种**输入形态：
   （a）粘贴文本清单（每行「编号 名称 [循环]」）
   （b）上传 Excel 清单（列：编号 / 名称 / 循环）
2. WHEN 用户提交清单 THEN 系统 SHALL 先做预览校验，逐行给出结论
   （可创建 / 编号已存在 / 编号非法 / 名称缺失），**不得**直接开始创建
3. WHEN 清单内部有重复编号 THEN 系统 SHALL 在预览阶段标出重复行并拒绝该批提交
4. WHEN 批量创建执行 THEN 每条 SHALL 有独立 savepoint 失败隔离，
   单条失败不影响其余条目（复用 `generate_from_codes` 已有的 per-item 失败隔离范式）
5. WHEN 批量创建完成 THEN 系统 SHALL 返回逐条结果（成功编号 / 跳过编号 / 失败编号+原因）
   与汇总计数，前端逐条展示
6. WHEN 某条已存在 THEN 系统 SHALL 跳过而非报错，与单条端点的 409 语义区分
   （批量语义是「幂等补齐」）
7. WHEN 批量创建的每一条 THEN 它 SHALL 与单条 `create-custom` 走同一实现
   （表头填充 / dataset 绑定 / `parsed_data` 初始化 三件不得遗漏）
8. WHEN Excel 清单列名有空格或全半角差异 THEN 系统 SHALL 归一化后匹配，
   识别失败时给出明确错误而非静默跳过整列
9. WHEN 交付 THEN 守卫 SHALL 断言批量路径与单条路径共用同一底层函数
   （变异「批量另写一份创建逻辑」必须打红）
10. WHERE 循环（`audit_cycle`）未提供 THEN 系统 SHALL 沿用单条端点的推导规则
    （取编号首字母），保持两条路径一致

### Requirement 9: 不侵入并发 spec 的范围

**User Story:** 作为平台维护者，我不希望两个 spec 同时改同一批文件而互相回退。

#### Acceptance Criteria

1. WHEN 交付 THEN 本 spec SHALL NOT 修改 `formula_engine.py` 的 `COLUMN_ALIASES`
   与两条求值路径的回退逻辑
2. WHEN 交付 THEN 本 spec SHALL NOT 修改 `wp_user_formulas.py` 的存储落点
   或 `wp_formula_service.save` 的存储语义
3. WHEN 交付 THEN 本 spec SHALL NOT 修改 `useFormulaStatus.ts`
   （其端点错配修复归 `formula-management-runtime-closure` R1）
4. WHEN 本 spec 需要公式清单能力 THEN 它 SHALL 新建自定义底稿专属 composable，
   与 `useFormulaStatus` 并存，并在 Notes 登记「收敛条件 = 对侧 spec 收口后」
5. WHEN 本 spec 需要登记端点到 `apiPaths` THEN 它 SHALL 只做加法式新增键，
   与对侧 spec 的兼容判据 = **双方新增键互不重叠**
6. WHEN 交付 THEN 守卫 SHALL 断言本 spec 未在上述禁止范围内留下改动痕迹

### Requirement 10: 缺陷不可回退

**User Story:** 作为平台维护者，我不希望下个会话把可见性修复或双模式接线改回去。

#### Acceptance Criteria

1. WHEN 运行守卫 THEN 系统 SHALL 断言 `create_custom_workpaper` 初始化了 `parsed_data`
2. WHEN 运行守卫 THEN 系统 SHALL 断言 `write_cell_to_parsed_data` 维护 `max_row` / `max_col`
3. WHEN 运行守卫 THEN 系统 SHALL 断言 `"custom"` 在 `_ONLYOFFICE_HTML_WHITELIST` 中
4. WHEN 运行守卫 THEN 系统 SHALL 断言自定义底稿宿主含双模式切换与 `GtOnlyOfficeSheet` 挂载点，
   且标签存在性断言带**标签名边界**（`<Foo(?=[\s/>])`，防被 `<FooREMOVED` 骗过）
5. WHEN 运行守卫 THEN 系统 SHALL 断言导出路径不调 `load_schema`
6. WHEN 对每处修复做变异（去掉 `parsed_data` 初始化 / 只写 cells 不写 max_row /
   从白名单移除 custom / 删掉双模式渲染块 / 导出改回 load_schema / 批量另写创建逻辑 /
   清单改读 `formulas` 键 / `onFormulaSave` 改回只读 `eval_warnings`）
   THEN 守卫 SHALL 逐条打红
7. WHEN 做变异检验 THEN 判据 SHALL 是「失败测试名集合的差集非空」而非退出码，
   并显式区分三态：RED（新增失败）/ GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）
8. WHEN 编写读源码型守卫 THEN 它 SHALL 先剥注释并配「剥注释确实生效」的自检，
   且跨行锚点 SHALL 按行级定位（工作树多为 CRLF，含 `\n` 的锚点必 MISS）
9. WHEN 守卫的判据本身失效（正则不命中 / 常量为空 / 路径错）THEN 守卫 SHALL 打红而非静默通过

### Requirement 11: 零回归

**User Story:** 作为平台维护者，我需要确认自定义底稿的改动不影响其余 37 种 componentType。

#### Acceptance Criteria

1. WHEN 修复后 THEN 非 `custom` 的 componentType 的 render-config 输出 SHALL 逐字节不变
2. WHEN 修复后 THEN `GtGridSheet` 的既有只读消费方 SHALL 全部行为不变
3. WHEN `"custom"` 加入 `_ONLYOFFICE_HTML_WHITELIST` 后 THEN 其余底稿的 componentType
   派生结果 SHALL 不变（该集合只在「无 renderer + 多 sheet」分支被查）
4. WHEN `write_cell_to_parsed_data` 补维护 `max_row`/`max_col` 后 THEN 既有调用方
   （公式求值回填路径）的 `cells` 写入行为 SHALL 不变
5. WHEN 修复后 THEN 既有底稿渲染 / 导出 / 公式相关测试 SHALL 全部通过，新增失败为 0
6. IF 某既有测试锁定了被修复的错误行为 THEN 该测试 SHALL 被诚实改写并在 Notes 说明原因，
   不得用跳过/放宽断言绕过

### Requirement 12: 真实库与浏览器验收

**User Story:** 作为现场经理，我需要看到真实项目里新建的自定义底稿能显示、能编辑、
能加公式、能切双模式、能导出。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 提供只读诊断脚本，对真实项目输出自定义底稿的
   投影键集 / `max_row` / 公式条数 / xlsx 文件存在性
2. WHEN 浏览器实测 THEN 它 SHALL 覆盖：新建底稿可见表头 → 编辑单元格并刷新后值仍在
   → 加一条公式并看到求值结果 → 公式清单可见可定位 → 切到在线编辑再切回数据一致
   → 导出 xlsx 成功
3. WHEN 浏览器实测批量创建 THEN 它 SHALL 覆盖两种输入形态各一次，
   并验证预览校验能拦住重复编号
4. WHEN 实测涉及数据写入 THEN 完成后 SHALL 按基线**逐字节复原**
   （`parsed_data` 的 `jsonb_typeof` + `md5(col::text)` 与基线比对，不只比 `length`）
5. WHERE 实测创建了自定义底稿 THEN 清理 SHALL 软删 `wp_index` 与 `working_paper`
   并删除生成的 xlsx 文件，且在报告中列出清理清单
6. WHEN 实测发现「只有浏览器能暴露」的缺陷 THEN 该缺陷 SHALL 在本 spec 内修复并补守卫，
   不得只记录不修

## Glossary

| 术语 | 含义 |
|------|------|
| 自定义底稿 | `componentType=custom`，由 `create-custom` 创建或 `class_code=CUSTOM` 派生，无标准模板 |
| xlsx 权威 | 用户 2026-08-06 拍板口径：xlsx 文件是唯一数据权威，`html_data.cells` 是其投影 |
| 投影 | 由 xlsx 经 `extract_grid` 产出 `{cells, max_row, max_col, col_widths, merged_cells, header_rows}` |
| 双模式 | HTML 结构化网格 ↔ OnlyOffice 在线编辑；平台既有 6+ 宿主，工厂 `createDualMode` |
| `hasData` | `GtGridSheet` 的渲染门：`Object.keys(cells).length>0 && maxRow>0`，缺 `max_row` 即空态 |
| 两条创建链路 | `create-custom`（建 `WpIndex`+`working_paper`+xlsx）vs `custom-with-template`（建 `ProcedureInstance`+`WpIndex` 占位，不建 `working_paper`） |
| `dynamic_table` 形态 | 导出服务期望的 `html_data[sheet]["rows"]` 结构，与自定义底稿的 `cells` 结构不兼容 |
| per-item savepoint | 批量操作的失败隔离范式：`async with db.begin_nested()` 逐条 + per-item try/except |
| 边界 spec | `formula-management-runtime-closure`，承担求值引擎与公式存储收敛，本 spec 不侵入 |

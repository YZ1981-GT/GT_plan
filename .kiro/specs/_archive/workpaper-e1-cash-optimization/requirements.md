# 货币资金 E1 底稿优化 - 需求文档

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-17 | 初始版本,从 README v2.1 迁移 | 用户确认启动三件套 |

---

## 一、范围边界

### 1.1 本 spec 必做(F1-F6)

| 编号 | 主题 | 工时 |
|------|------|------|
| F1 | 双总控台场景驱动裁剪 + 组件选型分流 + 审计导航图(含 4 子模块 + 5 弹窗组件) | 7 天 |
| F2 | prefill 链路扩展(10 公式类型 + 不覆盖公式逻辑 + 公式映射设计 + 手动编辑 + 恢复) | 5 天 |
| F3 | E1A/E26A 程序完成状态联动(三档 filled→reviewed→approved + 附件签字联动) | 2 天 |
| F4 | 历史遗留+重复 sheet 自动清理 + 表头自动填充 + 6 种数据刷新事件 | 1.5 天 |
| F5 | 跨底稿引用超链接 + B/C/E0/A5-1/S 联动(28 条 + 7 category)+ 复核体系 + 前置横幅 | 4 天 |
| F6 | CFS 勾稽校验(动态容差)+ 附件管理(7 类)+ LLM 审计说明 4 场景 + 双人签字 | 4 天 |
| **合计** | | **23.5 天** |
| Sprint 0 现状核验 | | 0.5 天 |
| **总工时** | | **24 天**(Sprint 0 0.5 + Sprint 1 8 + Sprint 2 12.5 + Sprint 3 3) |

### 1.2 本 spec 不做(独立 spec)

| 编号 | 排除项 |
|------|-------|
| O1 | D-N 全循环裁剪适配(88 个底稿推广) |
| O2 | scenario 字段 Project 创建向导改造 |
| O3 | OCR 监盘表照片自动提取 |
| O4 | 银行对账单按月自动导入 |
| O5 | 重要性阈值 highlight |
| O6 | 凭证截止测试自动抽样(ledger 端点) |
| O7 | E1-3 多银行账户自动展开 prefill |
| O8 | 反舞弊"显示舞弊应对"开关 |
| O9 | 多子公司 E1 合并到合并 CFS 勾稽 |

### 1.3 与已有 spec 的边界声明

本 spec 是**消费方**,调用已有基础设施 API,不重新实现引擎:

| 已有 spec | 本 spec 消费的 API/机制 | 如果不满足 |
|----------|----------------------|-----------|
| workpaper-deep-optimization | prefill_engine.prefill_workpaper_real() | 扩展 5 种新公式类型(LEDGER/AUX/LEDGER_DETAIL/COUNT_LEDGER/NOTE) |
| global-linkage-bus | cross_wp_references.json + LinkageBus 反向索引 | 新增 28 条 + 2 种新 category(completion_check/overlap_reference) |
| audit-chain-generation | ConsistencyGate 规则注册接口 | 注册 3 条新规则(E1↔CFS) |
| phase4-ai | wp_ai_service + mask_context + AiContentConfirmDialog | 新增 llm_prompts 字段 + 4 种 prompt 模板 |
| enterprise-linkage | ReviewConversations + ReviewRecord | 绑定 object_type='workpaper_sheet' |

---

## 二、功能需求

### F0 设计原则(贯穿全 spec 的核心原则)

#### F0.1 风险导向审计逻辑主线

所有 UI 设计必须体现完整审计逻辑链路:
```
[审计目标] → [风险识别] → [程序设计(裁剪)] → [程序执行] → [证据获取] → [结论形成]
     ↑              ↑              ↑                ↑              ↑            ↑
  E1A R7-R13    B51-3/C3      E1A R17-R44      E1-1~E1-32    E0/附件      E1-1 R40-R46
```

每个 sheet/弹窗顶部必须显示该位置在审计逻辑链路中的角色:
- 审计目标(对应哪项认定:A 存在/B 完整性/C 权利义务/D 准确性/E 列报)
- 风险等级(从前置 B/C 类底稿取)
- E1A 程序编号(在总控台中的位置)

#### F0.2 保持模板专业内容

组件选型分流不能丢失致同模板的专业内容结构:
- 每个 sheet 的审计目标、认定、程序文本、结论格式必须原样保留
- 只是用更适合的 UI 组件呈现(Univer/弹窗/面板)
- 模板原作者的专业判断不得删除

#### F0.3 D-N 通用架构(可推广性)

E1A 总控台设计必须是通用方案,可推广到 D-N 全部 89 个底稿:
- D2A/F2A/H1A 等都遵循相同的"程序表总控台"逻辑
- 通用结构:R1-R4 表头 / R5-R13 审计目标认定 / R14-R16 列标题 / R17+ 程序行(三档分类)
- 实现层用通用组件 ProcedureControlPanel.vue,接受 wp_code + procedure_sheet_name 参数

#### F0.4 预设公式实施铁律

预设公式必须在实施阶段最后阶段基于表样格式确认后才增加:
- 不能凭空设计公式
- 必须先 openpyxl 提取每个 sheet 的表头列项目 + 行结构
- 然后才能精确定义"哪个 cell 用什么公式从四表取什么数据"
- 公式锚定到具体表头列名 + 行结构,不能脱离表样格式空谈

### F1 双总控台场景驱动裁剪

#### F1.1 Project.scenario 字段
- 新增枚举字段:normal / ipo / listed / transfer / restructure / fraud_response
- 默认值:normal
- 项目创建时选择(本 spec 用 API 直接设置,向导改造归 O2)

#### F1.2 文件级裁剪
- chain_orchestrator 按 scenario 决定加载哪些物理文件:
  - normal:F1+F2+F3(25 sheet)
  - 非 normal:F1+F2+F3+F4(33 sheet)
- 裁剪发生在底稿生成阶段(不是前端隐藏)

#### F1.3 组件选型分流
- Univer 只渲染 A 类 9 个 sheet(数据表格含公式)
- B/C/D/E 类 21 个 sheet 改为弹窗/面板(el-form/el-table)
- 每个弹窗顶部显示:审计目标(认定)+ 风险等级 + E1A 程序编号

#### F1.4 审计导航图(WorkpaperAuditNav.vue)
- 底稿首屏面板,包含:
  - 5 项认定卡片(每项显示对应程序数 badge)
  - 风险评估摘要(从 B23-2/B51-3/C3 取)
  - 程序执行进度流程图(5 段节点 SVG)
  - 关键风险提示(LLM 辅助)
  - 底稿间关系图(简化版)
- 默认展开,可折叠

#### F1.5 全屏模式
- A 类 Univer:全屏隐藏左侧导航+顶部工具栏
- B/C/D/E 类弹窗:el-dialog fullscreen
- 全屏弹窗内不保留左侧导航
- 底部 sticky footer(保存+取消)
- ESC 两步退出(先退全屏,再关弹窗)
- 返回时自动刷新 Univer 数据

#### F1.6 Project.has_foreign_currency 字段
- 新增布尔字段,默认 false
- 驱动 E1-3 双版本二选一 + E1-8 外币盘点显隐

#### F1.7 E1-1 双对称区显隐(无外币业务自动隐藏上区)
- E1-1 含**两套对称区**:上区 R7-R21(外币及人民币,15 行)+ 下区 R23-R39(仅人民币,17 行)
- 当 `Project.has_foreign_currency=false` 时,Univer 渲染时**隐藏上区行**(R7-R21),只显示下区
- 当 `has_foreign_currency=true` 时,两区都显示
- 实现方式:Univer Facade API `setRowVisible(rowIndex, false)` 隐藏指定行
- 切换时不删除数据(只视觉隐藏),scenario 切换可恢复

#### F1.8 E1A 程序分类勾选驱动 sheet 显隐(用户主动交互)
- E1A 总控台"程序分类"列改为 el-checkbox(常规★/备选/IPO 应对 三档复选框)
- 用户勾选状态保存到 `wp.parsed_data.procedure_categories`(数组,默认 ["常规★"])
- 勾选规则联动 sheet 显示:
  - 仅勾选"常规★"(默认):仅显示常规★相关 sheet
  - 勾选"备选":额外显示备选程序对应 sheet
  - 勾选"IPO 应对":自动加载 F4 文件 + 显示 E26A + E1-26~E1-32(等同 scenario 切换)
- 与 F1.1 scenario 字段的关系:
  - scenario 是项目级**默认裁剪**(由项目经理设置)
  - F1.8 是**用户运行时调整**(审计助理可临时勾选"显示备选"做更多程序)
  - 勾选状态优先于 scenario(用户主动权高于项目默认)


### F2 prefill 链路扩展到明细表

#### F2.1 新增 5 种公式类型(prefill_engine 扩展)
- `=LEDGER('科目','方向','期间')`:从 tb_ledger 汇总借方/贷方发生额
- `=AUX('科目','维度类型','维度编码','列名')`:从 tb_aux_balance 按维度取数
- `=LEDGER_DETAIL('科目','日期范围','金额条件')`:从 tb_ledger 筛选明细行(返回列表)
- `=COUNT_LEDGER('科目','日期范围')`:从 tb_ledger 统计笔数
- `=NOTE('章节','字段')`:从 disclosure_notes 取附注金额

#### F2.2 E1-2/E1-3/E1-4 明细表 prefill
- E1-2 现金明细表:填充 B15-B21 数据行(各币种期初),不覆盖 B22 合计公式
- E1-3 银行存款明细表:填充汇总驱动行(H18 等),按账户细分归 TD-7
- E1-4 数字货币:条件触发(TB 含 1502 时才填)
- **铁律**:prefill 不覆盖已有公式 cell(cell.value.startswith("=")时跳过)

#### F2.3 手动公式编辑
- 用户可在任何 cell 输入自定义公式
- 预设公式(蓝色"系统预设")与手动公式(绿色"用户自定义")共存
- 用户可覆盖预设(标记"已修改",**保留原始预设供恢复**)
- 公式管理弹窗:新增/修改/删除/语法校验/执行预览
- **恢复预设公式**:已覆盖的预设 cell 旁显示"↺ 恢复"按钮,点击后:
  - 当前自定义公式存入 user_formulas 历史(可撤销)
  - cell 恢复到 prefill_formula_mapping.json 中的原始预设
  - 标记从"已修改"变回"系统预设"

#### F2.4 预设公式实施原则
- 10 种公式类型是系统能力清单
- 具体 cell 映射必须在实施阶段**先核验表样格式**(openpyxl 提取表头列项目+行结构)后才落地
- 实施顺序:表样分析 → cell 级映射表 → 写入 prefill_formula_mapping.json

### F3 程序完成状态联动

#### F3.1 完成状态三档
- `filled`:审计助理填完(conclusion_cell 已填)
- `reviewed`:L1 现场负责人复核通过
- `approved`:L2+ 项目经理/合伙人批准
- 合伙人 progress bar 区分三色

#### F3.2 完成判定逻辑(三档晋级条件)

**filled 档位条件(全部满足)**:
- 程序行的"底稿索引号"指向的所有底稿,其 conclusion_cell 已填
- **附件需求满足**(F6.2 列出的 7 类附件,对应 sheet 已上传至少 1 个附件)
- B 类检查清单/D 类盘点的 signature 已签字(对应需求 F6.4)

**reviewed 档位条件**:
- filled 已达成
- L1 复核通过(A21-1 对应行标记)→ reviewed

**approved 档位条件**:
- reviewed 已达成
- L2+ 批准(A22-1/A23-1 对应行标记)→ approved

**示例**:
- E1A R22(监盘库存现金)→ E1-7+E1-8 → 必须有监盘表照片附件 + 双人签字 → 才能 filled
- E1A R29(银行函证)→ E0 → 必须有函证回函附件 → 才能 filled

#### F3.3 useProcedureStatus composable
- 实时计算 E1A 25 项 + E26A 11 项的完成状态
- 暴露 progress 数据(filled/reviewed/approved 各多少项)
- 订阅 eventBus 事件自动刷新

### F4 历史遗留清理 + 表头自动填充

#### F4.1 sheet 过滤规则
- 后缀含 `(修订前)` / `(示例)` / `(提示)` → 跳过
- 双附注按 Project.template_type 二选一
- 双 E1-3 按 Project.has_foreign_currency 二选一
- E1-4/E1-8 按 TB 含 1502 科目触发

#### F4.2 表头自动填充
- R3 左:被审计单位名称(Project.company_name)
- R3 中:审计期间(Project.year)
- R3 右:索引号(wp_code + sheet 后缀)
- R4 左:编制人/日期(current_user + 首次打开日期)
- R4 中:复核人/日期(L1 复核通过时自动填)
- R4 右:页次(自动计算)
- 通过 wp_template_metadata.header_cells 配置坐标(不硬编码)

#### F4.3 数据刷新 6 种场景
- 试算表变更 → prefill 重取
- 调整分录变更 → AJE/RJE 重取
- 项目信息变更 → 表头重填
- 函证回函 → E1-3 标记已函证
- 上年数据导入 → PREV 重取
- 手动全量刷新 → 以上全部 + 异常检测

### F5 跨底稿引用 + B/C/E0/A 联动

#### F5.1 cross_wp_references 28 条(CW-108~135)

**A 组 14 条:E1A 内部索引号跳转(CW-108~121)**
- E1A R38/R44 → A1-1/A1-15/A1-16(跨循环重分类)
- E1A R29 → E0(银行函证)
- E1A R23/R43 → E26A(IPO 应对触发)
- E1A R17 → E1-1/E1-2/E1-3/E1-4(主索引链路)
- E1-11 → A16 管理层声明书(反向链接)
- E1-1!R20 试算平衡表数 → TB
- E1-10/E1-9 → E1-3 银行账户清单核对

**B 组 6 条:B/C 循环联动(CW-122~127)**

| ref_id | source | target | category | severity |
|--------|--------|--------|---------|---------|
| CW-122 | B23-2 控制了解 | E1A | prerequisite | required |
| CW-123 | C3 控制测试结论 | E1A | scope_driver | required |
| CW-124 | C3-2 控制偏差评价 | E1A | scope_driver | warning |
| CW-125 | B51-3 舞弊风险评估 | E26A | trigger | required |
| CW-126 | E1-1 审定数异常 | C3 | feedback | info |
| CW-127 | E1A 执行发现新风险 | B23-2 | feedback | info |

**C 组 8 条:E0 函证 + A5-1 CFS + A17-5-5 函证总检 + S 类互引(CW-128~135)**

| ref_id | source | target | category | severity |
|--------|--------|--------|---------|---------|
| CW-128 | E0 函证结果汇总 | E1-3 银行存款明细 | data_flow | required |
| CW-129 | E0 函证差异 | E1-6 余额调节表 | data_flow | required |
| CW-130 | E1-1!R18 合计 | A5-1-1 现金及现金等价物 | data_flow | required |
| CW-131 | E1-1 期末-期初 | A5-1-3 现金净增加额勾稽 | data_flow | required |
| CW-132 | E0 函证完成 | A17-5-5 函证程序总检 | completion_check | required |
| CW-133 | D0 收入函证完成 | A17-5-5 函证程序总检 | completion_check | required |
| CW-134 | E26A 大额现金 | S33-8 现金收付 | overlap_reference | info |
| CW-135 | E26A 银行流水 | S34-37 现金流异常 | overlap_reference | info |

#### F5.2 7 种 category 语义

- `prerequisite`:前置条件(B→E1,前置未完成时显示警告)
- `scope_driver`:范围驱动(C→E1,影响 E1 程序参数)
- `trigger`:触发器(B51-3→E26A,舞弊风险高时自动加载 F4)
- `feedback`:反向溯源(E1→B/C,异常时提示复核)
- `data_flow`:数据流(E0→E1 函证回填 / E1→A5-1 CFS 勾稽)
- `overlap_reference`:内容重叠互引(E26A↔S 类)— **业务规则**:编辑器中提示"相关底稿 X 已涵盖此内容,避免重复工作",合伙人复核时可一键查看两侧对照
- `completion_check`:完成度汇总(各循环函证→A17-5-5)

#### F5.3 B/C 类前置底稿联动(5 个)

| 底稿 | 类型 | 与 E1 的联动关系 |
|------|------|----------------|
| B23-2 | 控制了解 | E1A 前置条件 |
| B23-2-2 | 流程图(.docx)| E1A 裁剪依据 |
| B51-3 | 舞弊风险评估 | 触发 E26A |
| C3 | 控制测试 | 影响 E1 程序范围 |
| C3-2 | 控制偏差 | 增加 E1 程序 |

审计逻辑链路:`B23-2 → C3 → C3-2 → E1A(裁剪)→ E1-1~E1-32(执行)`

#### F5.4 货币资金生态圈跨循环联动(8 个)

| 底稿 | 循环 | 与 E1 的关系 |
|------|------|-------------|
| E0 | E 货币资金 | 银行函证(E1A R29 指向)|
| A5-1 | A 完成阶段 | 现金流量表 CFS 勾稽(E1-1!R18 = A5-1-1)|
| A17-5-5 | A 完成阶段 | 函证程序完成度总检 |
| D0/F0/G0/H0/K0/L0 | 各循环 | 共享函证管理框架(总检汇入 A17-5-5)|

#### F5.5 5 层复核体系联动(A21~A28 共 8 类模板)

| 复核层级 | 模板底稿 | 角色 | 与 E1 的联动 |
|---------|---------|------|-------------|
| L1 | A21-1/A21-2 | 现场负责人 | 逐底稿复核 E1 完成质量 |
| L2 | A22-1/A22-2 | 项目经理 | 循环级复核(E0+E1 整体)|
| L3 | A23-1/A23-2 | 签字合伙人 | 关键事项复核(变动率>30%/受限货币资金)|
| L4 | A24-1/A24-2 | 质量复核合伙人 | 独立复核(关键判断+函证充分性)|
| L5 | A25-1/A25-2 | 质控部 | 制度合规(致同手册要求)|
| 专委会 | A26-1~4 | 专委会委员 | 重大事项 |
| IT | A27-1 | IT 审计师 | IPE 程序(R18)可靠性 |
| 税务 | A28 | 税务专家 | 利息收入税务处理 |

复核联动需求:
- 复核模板行 → 点击跳转 E1 具体 sheet/cell
- E1 右上角"复核状态"badge:L1✅/L2⏳/L3❌
- 复核问题 ReviewRecord 绑定 source_wp + target_wp + target_sheet + target_cell
- L1 复核通过 → E1A 程序状态变 reviewed
- L2+ 批准 → 程序状态变 approved

#### F5.6 前置状态横幅(3 前置底稿 × 3 状态)

E1 编辑器顶部显示 B23-2/C3/B51-3 三个前置底稿的完成状态:

| 全部就绪 | 部分完成 | 未完成 |
|---------|---------|-------|
| ✅ B23-2 已完成 / ✅ C3 控制有效 / ⚠ B51-3 舞弊风险中等 → "可执行实质性程序" | ⚠ B23-2 进行中 → 横幅黄色"前置部分完成,建议先完成 B23-2 控制了解" | ❌ B23-2 未完成 → 横幅红色"⚠ 前置条件未满足:货币资金控制了解(B23-2)尚未完成" |

**规则**:
- 三个前置全 ✅ → 横幅绿色,允许执行实质性程序
- 任一前置 ⚠ 进行中 → 横幅黄色,允许但提示
- 任一前置 ❌ 未开始 → 横幅红色,可点击横幅跳转到对应底稿

#### F5.7 复核模板跳转溯源
- A21~A25 复核表行 → router.push 跳转 E1 sheet/cell
- 跳转后高亮目标 cell + 显示复核问题 popup

#### F5.8 LLM 辅助复核(3 场景)
- 审计说明自动生成:E1-1 R40-R46 基于数据草拟(变动原因/异常说明/结论建议)
- 复核问题一键生成:合伙人打开 A23-1 时 LLM 基于 E1 数据生成"建议关注问题清单"
- 复核回复辅助:审计助理收到问题后 LLM 基于底稿+序时账草拟回复

### F6 CFS 勾稽 + 附件管理 + LLM 辅助

#### F6.1 ConsistencyGate 3 条规则
- E1-1!R18 期末审定数 == CFS 期末现金等价物
- E1-1 期末-期初 == CFS 现金净增加额
- E1-1!R20 试算平衡表数 == TB(1001+1002+1012+1502)
- 容差:`max(1.0, 重要性水平 × 0.001)`,三档判定(相等/警告/错误)

#### F6.2 附件管理(7 类)
- E1-3 银行对账单 / E1-9 开户证实书 / E1-10 人行证明 / E1-11 承诺书 / E1-18 征信报告 / E1-21/22 银行回单
- 附件未上传时对应程序无法标 filled(联动 F3.2 完成判定)
- 逐项附件组件 ItemAttachment.vue(object_type='workpaper_item')

#### F6.3 每页 LLM"✨ AI 审计说明"按钮
- 4 种场景:审计说明生成 / 差异原因分析 / 检查结论生成 / 截止测试结论
- prompt 模板存 wp_template_metadata.llm_prompts 字段
- 输出经 AiContentConfirmDialog 确认
- 确认后标记 ai_generated + confirmed_by + confirmed_at

#### F6.4 逐项批注 + 对话
- B/C/D/E 类弹窗:ItemAnnotation.vue(逐项批注,存 parsed_data.items[N].annotations[])
- 对话绑定 object_type='workpaper_sheet' + object_id='{wp_id}:{sheet_key}'
- D 类盘点:双人签字(审计员+出纳)
- B 类检查清单:单人签字

### F7 数据契约(parsed_data JSONB schema)

#### F7.1 5 类 sheet 的 schema 骨架

每类 sheet 在 `wp.parsed_data` 中有标准化结构:

**C 类总控台**:
```json
{
  "procedure_status": {
    "e1a": {"R17": {"status": "approved", "filled_at": "...", "reviewed_at": "...", "approved_at": "..."}},
    "e26a": {...}
  }
}
```

**B 类检查清单**(以 E1-10 为例):
```json
{
  "e1_10": {
    "check_date": "2026-12-31",
    "checked_by": "user-uuid",
    "items": [{"bank": "...", "account_no": "...", "verified": true, "annotations": []}],
    "conclusion": "...",
    "attachments": ["att-uuid"]
  }
}
```

**D 类盘点**(以 E1-7 为例):
```json
{
  "e1_7": {
    "count_date": "...",
    "items": [{"denomination": "100元", "quantity": 50, "amount": 5000.00}],
    "total_counted": 6035.00,
    "book_balance": 6035.00,
    "difference": 0.00,
    "signatures": {"auditor": {"signed": true}, "cashier": {"signed": true}}
  }
}
```

**E1 类截止测试(系统驱动)**:
```json
{
  "e1_21": {
    "cutoff_date": "...", "days_before": 5, "days_after": 5,
    "auto_sampled": true,
    "items": [{"voucher_no": "...", "amount": 500000.00, "period_correct": true}],
    "issues_found": 0
  }
}
```

**E2 类人工驱动**(以 E1-20 为例):
```json
{
  "e1_20": {
    "items": [{"bank": "...", "avg_balance": 5000000, "calculated_interest": 17500, "booked_interest": 17320, "difference": 180}]
  }
}
```

#### F7.2 schema 设计原则
- 每个 sheet 对应 `parsed_data` 顶层 key
- `items` 数组存明细行,`conclusion` 存结论文本
- `attachments` 数组存附件 UUID
- `signatures` 对象存签字确认
- status 枚举:pending/in_progress/completed/not_applicable
- ai_generated/confirmed_by/confirmed_at 标记 LLM 生成内容

---

## 三、非功能需求

| 编号 | 类型 | 要求 |
|------|------|------|
| NF1 | 性能 | Univer 从加载 33 sheet → 仅 9 sheet,加载耗时 < 3s(当前 ~8s) |
| NF2 | 性能 | 审计导航图面板渲染 < 500ms |
| NF3 | 性能 | prefill 全量刷新(13 cell + 明细表)< 2s |
| NF4 | 兼容 | 组件选型分流后,已有 parsed_data 数据不丢失(向后兼容) |
| NF5 | 安全 | LLM 输入必须经 mask_context 脱敏(金额/客户名/身份证) |
| NF6 | 可维护 | 10 种公式类型通过 JSON 配置扩展,不硬编码 |
| NF7 | 通用性 | E1A 总控台设计必须是通用方案,可推广到 D-N 全部 89 个底稿 |

---

## 四、UAT 验收清单

| # | 验收项 | 对应需求 | 预期结果 |
|---|-------|---------|---------|
| 1 | 普通项目打开 E1 看到 sheet 数 | F1.2+F4.1 | 22 sheet(Univer 9 + 弹窗按钮 13) |
| 2 | 审计导航图首屏显示 | F1.4 | 5 认定卡片 + 风险摘要 + 进度流程图 |
| 3 | E1A 程序分类勾选"舞弊应对" | F1.2 | E26A + E1-26~E1-32 弹窗按钮出现 |
| 4 | 一键填充 E1-2 + E1-1 | F2.2 | 明细表数据行从 TB 取数 → Univer 公式自动汇总 |
| 5 | E1A 完成状态三色 progress | F3.1 | filled/reviewed/approved 三色区分 |
| 6 | 点击 E1A R38"A1-1"跳转 | F5.1 | 跳转 A1-1;A1 显示反向引用 badge |
| 7 | 前置状态横幅 | F5.6 | B23-2 未完成时显示"⚠ 前置未满足" |
| 8 | "✨ AI 审计说明"按钮 | F6.3 | LLM 生成审计说明草稿 → 确认后填入 R41 |
| 9 | E1-1 vs CFS 勾稽 | F6.1 | 偏差超容差时 ConsistencyGate 报错 |
| 10 | 全屏弹窗 | F1.5 | el-dialog fullscreen + sticky footer + ESC 两步退出 |
| 11 | 附件未上传阻止完成 | F6.2+F3.2 | E1-7 盘点无附件时 E1A R22 不能标 filled |
| 12 | 复核状态 badge | F5.5 | E1 右上角显示 L1✅/L2⏳/L3❌ |
| 13 | A21-1 复核表跳转 E1 | F5.7 | 复核表行点击 → 跳转 E1 sheet/cell + 高亮 |
| 14 | LLM 复核问题一键生成 | F5.8 | A23-1 打开时 LLM 生成"建议关注问题清单" |
| 15 | D 类盘点双人签字 | F6.4 | 审计员+出纳两人签字后弹窗变只读 + E1A R22 进 reviewed |
| 16 | E1-1 双区显隐 | F1.7 | has_foreign_currency=false 时上区 R7-R21 隐藏 |
| 17 | 公式恢复预设 | F2.3 | 已修改的预设公式点"↺ 恢复"按钮 → 回到原始预设 |
| 18 | 程序分类勾选驱动 | F1.8 | E1A 勾选"IPO 应对"→ E26A + E1-26~E1-32 自动显示 |
| 19 | B51-3 自动触发 E26A | F5.1 + D14 | B51-3 标"高"→ 自动加载 F4 + toast 提示 |


---

## 五、已知技术债(TD)

| TD | 描述 | 对应需求 | 优先级 |
|----|------|---------|-------|
| TD-1 | E1 仅作首批样板,D-N 全循环(88 个底稿)裁剪适配需独立 spec | F1 全方向 | P1 |
| TD-2 | scenario + has_foreign_currency 字段需 Project 创建向导收集 | F1 + F4 | P1 |
| TD-3 | F1-6 修订前 sheet 不止 E1 有,全模板库需扫描其他 `(修订前)`/`(示例)`/`(提示)` 类 sheet 统一过滤规则 | F4 | P2 |
| TD-4 | E1A 完成状态依赖 wp.parsed_data.procedure_status 字段,需 ORM 加 schema 校验 | F3 | P2 |
| TD-5 | useUniverSheetNav scenarioFilter 与 13 类分组规则的优先级未定 | F1 | P2 |
| TD-6 | conclusion_cell metadata 错位修正(标 E1-14:A50 而非业务核心 E1-1!R18)| F3 | P1 |
| TD-7 | prefill_engine 不支持"按账户细分行"(E1-3 多银行账户展开)| F2 | P1 |
| TD-8 | E26A 与 E1A 共享 audit objective 重复 | F1 | P3 |
| TD-9 | prefill_engine 必须实现"不覆盖已有公式 cell"逻辑(P0 级)| F2 | P0 |
| TD-10 | prefill_formula_mapping 第二条 sheet 名修正 | F2 | P2 |

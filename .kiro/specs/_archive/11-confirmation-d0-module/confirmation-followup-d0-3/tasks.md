# Implementation Plan: confirmation-followup-d0-3

## Overview

�?D0-3 跟函函证过程控制创建专用组件 `GtConfirmationFollowup`（多�?master-detail + 结构化字段填�?+ 备忘录文本自动生�?+ 条件场景 + 三项控制清单红线 + 电子签名留痕 + 双视图）。核心精�?把散�?`[XX]` 占位符的叙事模板重构�?结构化字段→自动拼装备忘�?。与 D0-1/D0-2 同构，大量复用其 composable/组件并共享单位主数据�? Sprint：类型枚�?�?数据�?备忘录生�?�?明细+条件场景+控制清单 �?看板+签名+导入+清单视图 �?组装注册联动回归�?

依赖：grid-sheet-inline-editing（D0-1�? confirmation-entity-verify（D0-2）spec �?useCellSelection/CellContextMenu/useDictStore/useExcelIO/wp_html_save 基础先行就绪可复用�?

## Tasks

### Sprint 1：类�?+ 枚举 + 备忘录话术模板常量（地基�?

- [x] 1.1 新增 `followupTypes.ts`：FollowupRow(�?4字段) / ControlConclusion / SignStatus / ProgressMetrics / FollowupPayload
  - _需�?1.2, 2.1, 4.4, 6.2_
- [x] 1.2 新增 `followupEnums.ts`：dictKey 映射（confirmation_followup_scenario / yes_no_na�?
  - _需�?8.1_
- [x] 1.3 新增 `MEMO_TEMPLATES` 常量：现场即时确�?/ 无法即时确认 两套话术模板 + 后收回补记注记段（LATER_RECEIVED_TPL，{field} 插值占位）
  - _需�?2.2, 3.5, 3.8_
- [x] 1.4 后端 `system_dicts.py _DICTS` �?`confirmation_followup_scenario`（现场即时确�?无法即时确认�? `yes_no_na`（是/�?不适用�?
  - _需�?8.1_
- [x] 1.5 后端枚举测试 + 编制指引 `wp_guidance/D0-3.json`（跟函控制要�?身份权限确认/正常流程观察/防串通舞�?索要名片观察员工卡）
  - _需�?7.1, 7.4, 8.1_

### Sprint 2：useFollowupData + useMemoCompose（数据核�?+ 备忘录生成）

- [x] 2.1 新增 `useFollowupData.ts`：从 htmlData 解析 rows + watch 重建 + dirty
  - _需�?1.4; 属�?P7_
- [x] 2.2 rows CRUD：addRow/deleteRow/updateField/importRows
  - _需�?9.1, 9.4_
- [x] 2.3 controlConclusion / signStatus 派生 + progressMetrics computed（记录数/控制达标�?签名完成�?异常数）
  - _需�?4.4, 6.2, 12.1; 属�?P4/P5/P6_
- [x] 2.4 buildPayload() 返回 FollowupPayload（_format: confirmation-followup-v1�?
  - _需�?9.3_
- [x] 2.5 新增 `useMemoCompose.ts`：按 scenario 选模板插�?+ later_received=�?追加注记�?+ 缺漏 `〔字段名〕` 占位 + missingFields + applyToRow + regenerate（override 守卫�?
  - _需�?2.2, 2.3, 2.4, 3.5, 3.8; 属�?P1/P2_
- [x] 2.6 useFollowupData + useMemoCompose 单测：CRUD + 派生 + buildPayload + 两场景插�?占位/override 守卫/regenerate
  - _属�?P1/P2/P4/P5/P6_

### Sprint 3：Master + Detail（核�?UI + 条件场景 + 控制清单 + 备忘录预览）

- [x] 3.1 新增 `FollowupMaster.vue`：el-table 关键列（函证索引/被函证单�?跟函人员/跟函日期/确认场景/控制结论徽章/签名状态）+ 多�?+ 工具�?+ 行展开 + 空态引导（可选底稿）
  - _需�?1.1, 1.5, 9.1, 13.4_
- [x] 3.2 新增 `FollowupDetail.vue`：左右分栏（左字段表�?右备忘录预览�? 6 区分组（基本信息/现场确认/控制检�?控制证据/签名/回函收回补记�? 枚举 el-select + 文本控件
  - _需�?1.2, 2.6, 5.1, 8.2_
- [x] 3.3 条件场景：scenario=无法即时确认 �?展开留函后续电话核实字段（含对外公开电话独立来源提示）；later_received=�?�?展开⑥回函收回补记寄回字段；切换均保留字段�?
  - _需�?3.1, 3.2, 3.3, 3.4, 3.6, 3.7; 属�?P3_
- [x] 3.4 新增 `FollowupMemoPreview.vue`：右栏备忘录正文实时预览 + 缺漏占位高亮 + 后收回补记段 + 自动/手动切换(memo_overridden) + 重新生成 + 复制/导出文本
  - _需�?2.2, 2.3, 2.4, 2.5, 2.6, 3.8, 6.4; 属�?P1/P2_
- [x] 3.5 三项控制检�?+ 红线警示：逐项专属 tooltip（检查①②③ 各自提示�? 任一为否→橙警示+异常计入；全空→未完成；控制结论徽章
  - _需�?4.1, 4.2, 4.3, 4.4, 7.2; 属�?P4_
- [x] 3.6 控制证据字段 + 字段�?tooltip 提示落位（控制要�?身份权限/正常流程/证据，说明就近）
  - _需�?5.1, 5.2, 5.3, 7.2, 7.3_
- [x] 3.7 右键菜单：复�?useCellSelection + CellContextMenu slot（复制行/插入/删除/复制函证索引/导出本笔备忘录）
  - _需�?9.2_
- [x] 3.8 Master+Detail+备忘�?spec：展开/条件场景保留/控制清单/备忘录生�?提示落位/只读守卫
  - _需�?1.3, 3, 4, 7; 属�?P1/P2/P3/P4/P8_

### Sprint 4：看�?+ 签名 + 导入 + 清单表格视图

- [x] 4.1 新增 `FollowupDashboard.vue`：记录数/控制达标�?签名完成�?异常�?+ 异常高亮 + 折叠
  - _需�?12.1, 12.2, 12.3_
- [x] 4.2 签名区：跟函人员签名 + 签名日期，默认带入跟函人员可改；签名状态派生；导出末尾保留手书签名留位
  - _需�?6.1, 6.2, 6.3, 6.4; 属�?P6_
- [x] 4.3 批量导入：复�?useExcelIO，解�?Excel/D0-1/D0-2 清单→预览→批量新增（带入函证索�?被函证单�?地址）；导出备忘�?
  - _需�?9.4, 9.5_
- [x] 4.4 清单表格视图：约 12 关键列平�?+ 网格美化（分组表头着�?冻结索引�?斑马�?空值淡化）+ useCellSelection 选区复制粘贴
  - _需�?10.1, 10.2, 10.5_
- [x] 4.5 视图切换 + localStorage 记忆 + 两视图共享数�?
  - _需�?10.3, 10.4_
- [x] 4.6 看板+签名+导入+清单视图 spec
  - _需�?6, 9, 10, 12; 属�?P5/P6_

### Sprint 5：组�?+ 注册 + D0-1/D0-2 联动 + 回归实测

- [x] 5.1 新增 `GtConfirmationFollowup.vue`：组�?Dashboard+[备忘�?Master+Detail+MemoPreview / 清单表格]+视图切换+接入 useFollowupData+useMemoCompose
  - _需�?1, 2, 10, 13_
- [x] 5.2 `htmlRendererRegistry.ts` 注册 confirmation-followup；后�?dispatch D0-3 sheet �?componentType
  - _需�?11.4_
- [x] 5.3 旧格式兼容降�?GtGridSheet 只读
  - _需�?14.2; 属�?P7_
- [x] 5.4 D0-1/D0-2 联动 + 单位主数据共享：函证索引可跳�?D0-1/D0-2 + 暴露跟函控制结论摘要�?F0-3 引用（数据源端）；同 confirm_index 单位字段单源共享，单侧缺失各自独立可�?
  - _需�?11.1, 11.2, 11.3, 11.5; 属�?P9_
- [x] 5.5 默认布局聚焦：留函后续字段默认折叠、备忘录视图默认、看板首屏可见、空态说明可选底�?
  - _需�?13.1, 13.2, 13.3, 13.4_
- [x] 5.6 保存端到�?+ 回归（render-config 冒烟 + system_dicts 测试�? 只读回归
  - _需�?9.3, 14.1, 14.3_
- [x] 5.7 Playwright D0-3 端到�?0 error：新增跟函记录→选场景填字段→备忘录实时生成→切场景字段保留→控制检查否→警示→签名→导出备忘录→保存→重开持久化→�?D0-1/D0-2
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "wave": 2, "tasks": ["1.5", "2.1"] },
    { "wave": 3, "tasks": ["2.2", "2.3", "2.5"] },
    { "wave": 4, "tasks": ["2.4", "2.6"] },
    { "wave": 5, "tasks": ["3.1", "3.2", "4.1"] },
    { "wave": 6, "tasks": ["3.3", "3.4", "3.5", "3.6", "4.4"] },
    { "wave": 7, "tasks": ["3.7", "4.2", "4.3", "4.5"] },
    { "wave": 8, "tasks": ["3.8", "4.6", "5.1", "5.2"] },
    { "wave": 9, "tasks": ["5.3", "5.4", "5.5", "5.6"] },
    { "wave": 10, "tasks": ["5.7"] }
  ]
}
```

## Notes

- �?D0-1（grid-sheet-inline-editing�?D0-2（confirmation-entity-verify）同构：复用 useCellSelection / CellContextMenu / useDictStore / useExcelIO / wp_html_save 保存链路 / 编制指引侧栏机制 / 跨底稿引用机制。建�?D0-1/D0-2 spec 先落地基础能力，D0-3 复用�?
- **D0-3 �?D0-1/D0-2 本质差异**：D0-1/D0-2 是宽表（痛点=横向滚动 �?master-detail 拆列）；D0-3 是叙事备忘录（痛�?占位符埋 prose 易漏�?+ 两套话术混在一�?�?**结构化字段填�?+ 自动拼装备忘录文�?*）。精修重心在 useMemoCompose，而非列分组�?
- 备忘录文本生成不引新依赖：纯字符串模板插值；缺漏字段�?`〔字段名〕` 高亮，不静默生成残缺文本。后收回函证（later_received=是）追加注记段，两场景通用�?
- **样式重定�?*：detail �?左结构化字段表单 / 右备忘录成稿预览"分栏（对齐报表模块编辑区+预览习惯），支持右键；非沿用原宽表平铺样式�?
- **独立电话核实是反舞弊核心**：对外公开电话须取自独立公开来源（工�?官网/114），非经办人当场提供，提示就�?public_phone 字段�?
- **提示逐项精确落位**（用户强调）：底部提�?前半→控制检查①、提�?中段+名片员工卡→检查②+控制证据、提�?系统核对→检查③+控制证据；`[ ]`斜体字提示由结构化字段消解�?
- 说明/提示落位：顶部提�?适用范围/一笔一�?手书签名)→组件顶部精简+guidance侧栏；底部提�?流程/身份权限/正常流程/名片员工�?系统核对)→就近控制检查与控制证据 tooltip�?
- D0-3 是发函跟函过程留痕，�?D0-1(发函后汇�?/D0-2(发函前核�?通过"函证索引"一一对应；D0-3 作为 D0-1"跟函控制过程"/D0-2"跟函函证控制过程(F0-3)"的支撑底稿，提供控制结论数据源（消费端在各自 spec）�?
- D0-3 �?*可选底�?*（仅采用跟函方式时编制），空态明确这一点，不强制填写�?
- 电子签名仅留痕姓�?日期（对应手书签名），不做密码学签章；真实手书签名在导出打印件完成�?
- 铁律：组�?props 不可变（composable 深拷贝）；只读路径无编辑控件；改动后 Playwright 实测�?

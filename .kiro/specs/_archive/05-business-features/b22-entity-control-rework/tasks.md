# Implementation Plan: B22 企业层面控制底稿重做

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "name": "注册与骨架", "dependsOn": [], "tasks": ["1.1", "1.2", "1.3"] },
    { "wave": 1, "name": "B22B 控制矩阵组件", "dependsOn": [0], "tasks": ["2.1", "2.2", "2.3", "3.1", "3.2", "3.3"] },
    { "wave": 2, "name": "B22A FRP + IT 结构化", "dependsOn": [0], "tasks": ["4.1", "4.2", "4.3", "5.1", "5.2", "5.3", "6.1", "6.2"] },
    { "wave": 3, "name": "缺陷收敛 B22C + A9 repoint + 迁移", "dependsOn": [0], "tasks": ["7.1", "7.2", "8.1", "8.2", "8.3", "9.1", "9.2"] },
    { "wave": 4, "name": "测试", "dependsOn": [1, 2, 3], "tasks": ["10.1", "10.2", "10.3", "11.1", "11.2"] },
    { "wave": 5, "name": "Checkpoint 与实测", "dependsOn": [4], "tasks": ["12.1", "12.2", "12.3"] }
  ]
}
```

## Overview

默认方案 A（B22B 源对齐 + 缺陷收敛 B22C + A9 repoint）。若用户改选方案 B，停用 W3 的 A9 迁移任务（8.x/9.x），仅保留 B22A 登记册可编辑化 + 列结构。铁律：改动后必 Vite transform 200 + get_diagnostics 全清；标记不假绿；optional(`*`) 也做完；改前先 git status/grep 核实并发状态。

## Tasks

## 1. 注册与骨架（Wave 0）

- [x] 1.1 `wp_code_overrides.json`：`B22B` → `b22b-control-matrix`（保留旧 `b22b-deficiency-evaluation` 供兼容期读取，不再路由 wp_code B22B）
  - _Requirements: 1.1, 1.2, 8.1_ _Properties: P1_
- [x] 1.2 六处注册集合同步：dedicated_component_types / wp_render_config(self-contained + whitelist) / wp_classification_service VALID / htmlRendererRegistry / checklist_responses 白名单前缀 `B22B-`
  - _Requirements: 8.1, 8.2_ _Properties: P12_
- [x] 1.3 render-config 折叠单 sheet + 清空 html_data.cells（防 grid 兜底 shadow）
  - _Requirements: 1.1, 8.3_ _Properties: P1_

## 2. B22B 控制矩阵数据层（Wave 1）

- [x] 2.1 新建 `useB22BControlMatrix.ts`：12 列 Control_Point 模型 + CRUD + 枚举常量（要素/反舞弊/频率/自动人工/相关风险）
  - _Requirements: 2.1_ _Properties: P2_
- [x] 2.2 持久化 `B22B-row-{n}-{field}` + `B22B-row-count`，不传 project_id
  - _Requirements: 2.3_ _Properties: P2_
- [x] 2.3 从 B22A 控制点带入（仅填空、去重）
  - _Requirements: 1.4_ _Properties: P3_

## 3. B22B 控制矩阵渲染层（Wave 1）

- [x] 3.1 新建 `GtB22BControlMatrix.vue`：12 列可编辑表（枚举列下拉）+ 增删行 + 审计目标 alert + 编制提示
  - _Requirements: 2.1, 2.2_ _Properties: P2_
- [x] 3.2 客户端 xlsx 导出（列顺序对齐源模板 12 列）
  - _Requirements: 2.4_ _Properties: P2_
- [x] 3.3 复用快赢范式：13px 字号 / 双模式工具栏 / 版本链 / 复核入口 / 只读封锁
  - _Requirements: 9.1, 9.2, 11.1_ _Properties: P10_

## 4. B22A 财务报告过程（Wave 2）

- [x] 4.1 `useB22AControlMatrix.ts` 增 FRP 状态（4 子过程 × [不适用 + 了解文本]），item_id 前缀 `B22A-frp-`
  - _Requirements: 5.1, 5.3_ _Properties: P8_
- [x] 4.2 `GtB22AControlMatrix.vue` Tab3 信息与沟通下渲染 FRP 记录区（不适用勾选 + textarea）
  - _Requirements: 5.1, 5.2_ _Properties: P8_
- [x] 4.3 不适用子过程不计入完成度缺口
  - _Requirements: 5.4_ _Properties: P8_

## 5. B22A IT 详细结构化重建（Wave 2）

- [x] 5.1 IT 子区重建为结构化模型：IT 概要(复杂度) / 系统清单 / IT 环境 4 维 / ITGC 分类 / SoD 矩阵
  - _Requirements: 6.1_ _Properties: P9_
- [x] 5.2 旧 `B22A-T4-IT-*` 数据迁移映射函数（映射或标注待复核，不丢弃）
  - _Requirements: 6.3_ _Properties: P9_
- [x] 5.3 Cross_Ref_Chip 指向 C22（ITGC 测试边界）+ 保留 IT 依赖高+ITGC无效告警
  - _Requirements: 6.2, 6.4_ _Properties: P9_

## 6. 管理层凌驾联动（Wave 2）

- [x] 6.1 保留管理层凌驾专区录入/关键判断/缺陷识别，缺陷归风险评估区（非 ITGC）
  - _Requirements: 7.1_ _Properties: P13_
- [x] 6.2 `b50:push-risk-factor` 发布 + C23/C24 Cross_Ref_Chip
  - _Requirements: 7.2, 7.3_ _Properties: P11_

## 7. 缺陷严重程度收敛至 B22C（Wave 3）

- [x] 7.1 `useB22CDesignEffectiveness.ts` 缺陷条目增严重程度（重大/重要/一般）+ CAS1152 两级派生
  - _Requirements: 3.1, 3.4_ _Properties: P4_
- [x] 7.2 `loadFromUpstream` 兼容读取旧 `B22B-def-*` 迁移进 B22C（仅填空、去重）
  - _Requirements: 3.2_ _Properties: P4_

## 8. A9 缺陷 Loader repoint（Wave 3）

- [x] 8.1 `_a91_deficiency_letter.py::_load_b22b_deficiencies` 优先读 B22C 缺陷+严重程度并分组
  - _Requirements: 4.1, 4.3_ _Properties: P5_
- [x] 8.2 保留 `B22B-def-*` / `b22b-deficiency-*` 旧格式向后兼容双读 + 去重
  - _Requirements: 4.2_ _Properties: P6_
- [x] 8.3 A9-2 继续仅取 major/significant
  - _Requirements: 4.4_ _Properties: P5_

## 9. 数据迁移（Wave 3）

- [x] 9.1 `B22B-def-*`（缺陷+严重程度）→ B22C 结构迁移逻辑，标注 migratedFrom
  - _Requirements: 10.1, 10.3_ _Properties: P7, P9_
- [x] 9.2 幂等保证（重复执行无重复/无漂移）+ 无法映射保留待复核
  - _Requirements: 10.2, 10.4_ _Properties: P7_

## 10. 后端测试（Wave 4）

- [x] 10.1 `test_a91_deficiency_letter.py` 扩展 P5（分组等价）/ P6（旧格式兼容）〔W3 已交付：新增 B22C 优先/去重/P5 等价/flags 回退 5 测试〕
  - _Requirements: 4.2, 4.3_ _Properties: P5, P6_
- [x] 10.2 新建迁移契约测试 P7（幂等）〔W4 已交付：新建前端 `b22MigrationIdempotency.spec.ts`，覆盖 loadFromUpstream B22B-def-*→B22C 迁移的 N 次幂等/无重复/无漂移/不覆盖已编辑，4 passed〕
  - _Requirements: 10.2_ _Properties: P7_
- [x] 10.3 `test_dedicated_component_registry_contract.py` 覆盖 `b22b-control-matrix` P12〔W0 已交付：契约 5 passed〕
  - _Requirements: 8.2_ _Properties: P12_

## 11. 前端测试（Wave 4）

- [x] 11.1 新建 `useB22BControlMatrix.spec.ts`：P2（12列）/ P3（带入仅填空）/ P10（只读封锁）〔W4 已交付：10 passed。P2 = CONTROL_POINT_FIELDS 12 列/顺序 + item_id 结构不传 project_id；P3 = pullFromB22A 首次/重复去重/不覆盖已编辑；P10 = shallowMount GtB22BControlMatrix 校验组件层 readonly 守卫短路不 PUT + 正向对照〕
  - _Requirements: 2.1, 1.4, 11.1_ _Properties: P2, P3, P10_
- [x] 11.2 扩展 B22C 测试 P4（单一真源）/ P13（管理层凌驾归属）/ FRP P8〔W4 已交付：新建 `b22cDesignEffectiveness.spec.ts`，10 passed。P4 = severity 权威派生 isSignificant + 覆盖手工 sig + 持久化唯一位置；P13 = B22C loadFromUpstream mo→risk 非 itgc + B22A deficiencyList mo elementName 归风险评估；P8 = frpApplicableGapCount 不适用不计入/可逆/空文本〕
  - _Requirements: 3.1, 5.4, 7.1_ _Properties: P4, P8, P13_

## 12. Checkpoint 与实测（Wave 5）

- [x] 12.1 三组件 + 新组件 Vite transform 200 + get_diagnostics 全清 + 后端 AST OK〔已验证：12 前端文件 get_diagnostics 全清 + Vite transform 全 200 + 后端 _a91/_a92 AST OK〕
  - _Requirements: 9.4_ _Properties: P1_
- [x] 12.2 前端 b22 vitest 全绿 + 后端 a9/迁移/契约测试全绿〔已验证：前端 8 spec/142 tests passed；后端 43 passed（a91 25 + a92 8 + a92_pbt 5 + registry contract 5）〕
  - _Requirements: 4, 8, 10_ _Properties: P5, P6, P7, P12_
- [x] 12.3* Playwright round-trip（B22 实例化后：B22B 矩阵录入落库 / B22C 缺陷带入 / A9 分组反映最新；需先实例化 B22 到测试项目）
  - _Requirements: 全部_ _Properties: 全部_
  - 〔已验证 2026-07-23，重药控股安徽 0ec33ac9（B22B wp f51ccaf3 / B22C wp d93dc034 / A9-1 wp 073267ea），Playwright MCP（EventSource 中和防 SSE 跳转 + sessionStorage token）〕
  - **前置条件 MET**：后端 :9980 healthy（PG/Redis ok，migrations 121，drift 0）；render-config 确认 B22B `componentType=b22b-control-matrix`（单 sheet + html_data 无 cells，不被 grid 兜底 shadow），B22C `b22c-design-effectiveness`。
  - **① B22B 控制矩阵录入落库（P1/P2）**：GtB22BControlMatrix 渲染 12 列矩阵（表头 14 = #+12 数据列+操作）；新增控制 + 填 要素/编号/子类别/控制名称 → 2× PUT checklist-responses **200** → DB 落库 `B22B-row-count=1` + `B22B-row-0-{element=控制环境,code=PBT-TEST-01,controlName=...,subCategory=...}`。
  - **② B22C 缺陷带入 · severity 单一真源（P4）**：GtB22CDesignEffectiveness 渲染 5 要素区块；控制环境区新增缺陷 + severity=重大缺陷 → PUT **200** → DB `B22C-env-def-count=1` + `B22C-env-def-1-severity` conclusion=`重大缺陷`（唯一权威位置），`isSignificant` 由 severity 派生（flags sig:true）。
  - **③ A9 缺陷分组反映最新（P5）**：A9-1 render-config **200**（componentType=a9-1-deficiency-letter）→ `deficiency_list.major` 含 `{id:b22c-env-1, source:b22c, severity:major, index_ref:控制环境}`，significant/general 空，b22b_warning=null（B22C 单一真源生效）。
  - **0 组件错误**（仅 1 条 pre-existing SSE 401 噪声，符合可接受范围）。
  - **测试数据已清理**：B22B `row-count→0` + row-0 字段清空；B22C `env-def-count→0` + def-1 字段清空；A9-1 render `deficiency_list` 复归 major/significant/general 全空（验证联动的正反双向 liveness）。

## Notes

- 方案 A/B 决策：默认方案 A（源对齐）。用户改选方案 B 时停用 8.x/9.x。
- 零回归红线：A9-1/A9-2 缺陷分组、既有 B22A/B22C 数据加载、快赢已落地能力（双模式/版本链/复核/判断矩阵）。
- 并发警示：改前 git status/grep 核实其他会话是否在改 B22/A9 相关文件。
- 崩溃类权威校验 = Vite transform 200（Volar/get_diagnostics 查不出 SFC 结构/导入解析错，参见前序 B22A `./shared/GtWpVersionTrail.vue` 断链教训）。

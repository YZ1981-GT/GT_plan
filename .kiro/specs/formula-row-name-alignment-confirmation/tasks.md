# Implementation Plan

## Overview

本任务集按四表候选、稳定映射、F-SHELL 入口和底稿级刷新四条链路收口；标记为 BLOCKED 的任务不得用临时按钮或本地缓存绕过。

## Tasks

- [x] 1. DEC-2 存储形态书面评估（阻塞门）
  - 实读 `backend/app/models/workpaper_field_override_models.py` + 迁移 V076，落「字段形态 / 作用域键 / 索引 / 唯一约束」实况
  - 逐条判 N:M 映射（`target_names` 数组 + `dataset_fingerprint` + `superseded_from` 留痕）能否不退化成 JSON 字符串塞入既有列
  - 输出书面结论到 spec evidence：**复用** 或 **新建 `workpaper_row_name_mapping`**，若新建必须写明既有机制缺什么（Requirement 3.1 明令不得跳过）
  - 🔴 结论未落地则 Task 7 阻塞（存储形态决定迁移与服务签名）
  - _Requirements: 3.1_

- [x] 2. F-SHELL outlet 可用性核实（入口任务的前置闸）
  - 实读 `workpaper-page-formula-toolbar-closure` 的 design/tasks，确认 outlet 契约是否已交付、注入 API 形态、只读态门控约定
  - 复核红基线：`GtWpToolbar.vue` 仍只有 `.gt-wp-toolbar__right` CSS 容器、无 Vue slot（若已变化则更新本 spec 设计）
  - outlet 不可用 ⇒ Task 11 显式标 BLOCKED 并记录依赖对象，**禁止**临时加按钮绕过（Requirement 4.2）
  - _Requirements: 4.1, 4.2_

- [x] 3. 缺刷新入口的底稿清册（禁 grep 按钮文字）
  - 从 `htmlRendererRegistry` + 后端 `RENDERER_DISPATCH` / render-config 推导「有四表库取数能力但无刷新入口」的宿主集合
  - 交叉核对 `wp_code_overrides.json` 与实际挂载宿主，产出 wp_code → 宿主 → 现有入口（有/无）三列清单
  - 判据必须是**结构性**（registry 条目 + 宿主存在 + 入口 emit 有消费方），不得用按钮文案字符串或写死页面数量
  - _Requirements: 4.3_

- [x] 4. 候选生成：复用既有科目定位，不重写
  - 新增 `backend/app/services/four_table/row_name_alignment.py::build_candidates`
  - 输入已定位叶子（复用 `select_leaves`），输出账套明细名候选（`tb_aux_balance.aux_name` / `tb_balance.account_name`），带金额与来源坐标
  - 走 `get_active_filter`（只取 active dataset）；aux 侧必须先锁定单一 `aux_type` 再归集，防维度冗余双算
  - 🔴 不得复制或分叉 `ReportLineAccountSpec` 的定位逻辑（红基线 3）
  - 候选按稳定目标 identity 传输，不得仅返回名称；名称归一规则、相似度算法、阈值和候选上限必须版本化并写入 evidence
  - _Requirements: 2.2_

- [x] 5. `classify` 四态纯函数 + PBT
  - 实现 `classify(row_label, candidates, saved_mapping) -> MatchState`，四态：`auto_matched` / `ambiguous` / `unmatched` / `user_confirmed`
  - 名称归一（空白/全半角/常见后缀）**仅用于候选生成**；归一后非唯一命中一律 `ambiguous`，禁止当精确命中出数
  - hypothesis PBT（max_examples=5）：返回值必属四态之一 + 多命中必 `ambiguous`
  - _Requirements: 1.1, 5.2_

- [x] 6. `resolve_amounts` + 多对一口径与无值语义
  - 按映射聚合金额；多对一（不同 row_key 的 `target_names` 交集非空）按 DEC-3 **不自动去重**但必须返回「重复引用」告警标记
  - `unmatched` 行输出必须是「无值」语义（None/缺键），禁止 0、空串或上期值
  - PBT 覆盖 Property 3 / Property 6
  - _Requirements: 2.4, 5.1_

- [x] 7. 映射存储层（依赖 Task 1 结论）
  - 目标身份必须保存 `account_code` / `aux_type` / `aux_name` / 维度键 / `dataset_id`；`row_key` 必须来自稳定模板/契约业务键，禁止使用可变行号或渲染数组下标
  - 按 Task 1 结论落存储：新建则 `backend/migrations/V*.sql` 全 DDL 幂等（`IF NOT EXISTS`）+ ORM + 读写服务
  - 作用域键至少 project + year + wp_code + sheet_code + row_key，唯一约束覆盖该键
  - 留痕字段 `confirmed_by` / `confirmed_at` / `superseded_from`；覆盖历史确认必须写新行或写留痕，不得原地静默改
  - `dataset_fingerprint` 用于判 stale：目标 identity 在当前 active dataset 中消失或身份字段变化 ⇒ 该行回落 `unmatched`（Property 2）
  - 设计并测试批量确认的全回滚、重复请求幂等、版本冲突，以及目标 identity 变化导致 stale 的行为
  - _Requirements: 3.2, 3.4, 3.5, 1.4_

- [x] 8. 映射批量确认事务与刷新链返回 match_state（扩展既有链，不新建平行端点）
  - 批量确认单次事务提交，失败全回滚；请求携带 `base_mapping_version` + `idempotency_key`，重复请求幂等，版本冲突显式返回 conflict
  - 覆盖历史映射写新版本并保留 before/after 快照；取消路径不得发逐行写入请求
  - wire 字段固定为 row_key / match_state / candidates[] / target_identity / amount / similarity / source_kind / confirmed_by / confirmed_at / mapping_version / stale_reason
  - 底稿级取数/刷新响应逐行带 `match_state` + 候选 + 映射来源（自动/人工确认+确认人时间）
  - 已确认且未失效映射自动生效且不再触发弹窗（Property 5）
  - 🔴 additive 反模式自查：新字段必须有唯一前端消费方，否则即死代码
  - _Requirements: 1.1, 1.3, 3.3, 3.6_

- [x] 9. `GtRowNameAlignmentDialog.vue` 对齐确认弹窗
  - 两栏：左底稿行名（状态 tag）/ 右候选账套明细名（金额 + 相似度提示 + 排序）
  - 支持 1:N / N:1 / N:M 建立映射；多对一必须弹口径确认再落库（Requirement 2.4）
  - 确认后关闭并立即重算受影响行；未确认行保持 `unmatched` 不伪造
  - 取消路径**零写入**（Property 4）
  - 不合并、不复制 `GtRefreshScopeDialog` 的 scope 树（红基线 2）
  - _Requirements: 2.1, 2.3, 2.5, 2.6, 3.6_

- [x] 10. 行内可见标识与直达入口
  - `unmatched` / `ambiguous` 行给可见 tag（中文文案）+ 点击直达弹窗对应行，禁止静默显示 0
  - `user_confirmed` 行可溯源：hover/点开显示映射到哪些账套明细名、谁在何时确认
  - 提供「重新确认」入口覆盖既有映射
  - _Requirements: 1.2, 1.3, 3.5_

- [x] 11. 刷新入口注入（消费 F-SHELL outlet）
  - 通过 Task 2 核实的 outlet 契约注入刷新按钮，位置在工具栏「导入」右侧；只读态禁用
  - 🔴 禁止在 `GtWpToolbar.vue` 新增第二个按钮 owner 或直接改 DOM（红基线 1）
  - Task 2 判定 outlet 不可用 ⇒ 本任务标 BLOCKED 并停在此处
  - _Requirements: 4.1, 4.2, 4.4_

- [x] 12. 全局一键刷新的汇总告警（DEC-4）
  - 合伙人全局刷新遇 unmatched **不弹窗**，产出「N 行待确认」汇总告警并可导向对应底稿
  - 断言全局路径不调用本 spec 的弹窗组件（避免误挂第二触发点）
  - _Requirements: 2.1, 5.1_

- [x] 13. 变异检验（守卫有效性证明）
  - 新增 `backend/scripts/diagnose/mutate_row_name_alignment_guards.py`，四态判定（RED / GREEN=守卫缺陷 / ANCHOR-MISS / WRONG-TEST）
  - 锚点至少三条：删掉映射查询调用 · 作用域键漏 `year` 或漏 `wp_code` · 把 `ambiguous` 当 `auto_matched` 直接出数
  - GREEN 即守卫缺陷，必须补守卫而非放过
  - _Requirements: 5.3_

- [x] 14. 真栈实测（浏览器）
  - Playwright 跑 DEC-1 选定的样板底稿（待确认；建议 D3-1 审定表或 F1 附注）
  - 判据链：该行确认前无值 → 弹窗建立映射 → 确认后该行金额 = 账套真实值（与只读 SQL 快照逐字对齐）
  - 二次刷新必须重新从服务端读取映射（不得依赖前端缓存），不再弹窗且出数一致（Property 5）；证据 JSON 落 spec evidence
  - 同时证明 row_key 与目标 identity 未错位，且多对一告警能在下游审定表/附注显示
  - _Requirements: 5.4, 3.3_

- [x] 15. 收口
  - `get_diagnostics` 校验三件套；`git status --porcelain -- <产物清单>` 核无 `??` 漏登记
  - `.kiro/specs/INDEX.md` 登记本 spec 状态
  - 清理本轮 `tmp_*` / `_wip_*` 诊断产物
  - _Requirements: 5.3_

## Notes

DEC-1、DEC-2 在对应阻塞任务完成前不视为默认批准；所有实现任务必须把 producer digest、mapping version 和 evidence 路径写入交付记录。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3"], "rationale": "三项都是只读核实：存储形态结论、outlet 可用性、入口清册。互不依赖可并行，且分别是 Task 7 / Task 11 的闸门" },
    { "wave": 2, "tasks": ["4", "5", "6"], "rationale": "候选生成与两个纯函数（classify / resolve_amounts）只依赖既有四表库件，可先于存储落地" },
    { "wave": 3, "tasks": ["7", "8"], "rationale": "存储层依赖 Task 1 结论；刷新链返回 match_state 依赖 Wave 2 的四态与聚合结果" },
    { "wave": 4, "tasks": ["9", "10", "11", "12"], "rationale": "前端弹窗/行内标识/入口注入/全局告警都依赖刷新链已带 match_state；Task 11 另受 Task 2 闸门约束" },
    { "wave": 5, "tasks": ["13", "14", "15"], "rationale": "变异检验与真栈实测需要全链接通；收口最后做" }
  ],
  "blocking": {
    "1": "DEC-2 书面结论未出 ⇒ Task 7 阻塞（Requirement 3.1）",
    "2": "F-SHELL outlet 不可用 ⇒ Task 11 标 BLOCKED，禁止临时加按钮绕过（Requirement 4.2）",
    "external": "必须取得 F-SHELL producer 的版本、digest 与 conformance evidence；仅 producer tasks 标绿不能解除 Task 11 外部依赖"
  },
  "pending_decisions": {
    "DEC-1": "样板底稿待用户确认（红框图未获取到），影响 Task 14 的实测目标",
    "DEC-2": "存储形态由 Task 1 定论；设计倾向新建 workpaper_row_name_mapping 表"
  }
}
```

# 任务：审计年度兜底取今年 / 写死年度（audit-year-calendar-fallback-ratchet）

> 首版草稿（随 `25a506a57` 入库，只有前端、口径「不减 1 且行内含 year」）已按实施结果改写，口径变化见 requirements 头注。
> 任务 1 随 `formula-fetch-followup-defect-closure` 任务 8.1 交付；任务 2 起另行排期，开工前先确认 R3.2（单一来源最终兜底：A 去年 / B 提示）。

## 1. 守卫：只许减少（R1）

- [x] 1.1 前端 vitest 棘轮 `src/__tests__/auditYearCalendarFallbackRatchet.spec.ts` + 基线 `auditYearCalendarFallbackBaseline.json`
  - 证据：`bf7685b1d` 干净检出扫 5332 个源码文件，288 个文件 340 处；同口径脚本生成的基线与 vitest 现算逐文件一致（4 passed）；
    单区域 vue-tsc 0 错（注入 `number = 'x'` 报 TS2322，非空转）、ESLint 通过。
    主工作区（含并发会话未提交改动）现算只差一组挪动：`g10DisclosureSyncPayload.ts` 2 处挪到 `g10NoteSectionMap.ts`，守卫按设计报两条
    （该会话提交时需把基线条目一起挪过去）
- [x] 1.2 后端 pytest 棘轮 `tests/test_audit_year_calendar_fallback_ratchet.py`（AST，基线在文件内）
  - 证据：扫 `backend/app` 2771 个文件，72 个文件 130 处（今天的年份 34、写死年度 96）；干净检出与主工作区均 6 passed
- [x] 1.3 变异
  - 证据：前端 MY1~MY9（基线外新增 / 修掉不改基线 / 整行注释与行尾注释口径失效 / 扫描根写错 / 漏认 `(new Date()).getFullYear()` /
    基线净增 / 测试文件也计入 / `__tests__` 目录也扫）、后端 MB1~MB7（新增写死默认值 / 修掉不改基线 / 全大写常量也计 / 只认 `now()` /
    不认 `Query(2025)` / 扫描根写错 / `or` 不看前项）全部打红在预期断言上，跑完逐字节恢复

## 2. 逐处判定（R2）

- [ ] 2.1 前端 340 处、后端 130 处逐处判定写请求 / 读请求 / 日历用途 / 单一来源兜底，产出 `evidence/classification.md`（按 import 闭包追到请求发出点）
- [ ] 2.2 日历用途进豁免表（前后端各一张，理由 + 可证伪：文件仍命中口径），对应条目从基线移出
- [ ] 2.3 盲区补查：先存 `new Date()` / `datetime.now()` 再取年份的写法，按文件人工过一遍并登记

## 3. 前端写请求（R3.1、R3.2）

- [ ] 3.1 `resolveAuditYearOrNull` + `resolveEffectiveAuditYear` / `useAuditContext` / `useProjectSelector` 改为取不到返回 null（调用方同步处理）
- [ ] 3.2 写请求的年度缺失时不发请求、提示「未设置审计年度」；下调基线；vitest + 单区域 vue-tsc
- [ ] 3.3 浏览器实测（【测试】项目，含未填审计年度与审计期末的项目）

## 4. 前端读请求 / 展示（R3.3）

- [ ] 4.1 按组件族分批（底稿 D~N 循环各一批，其余页面一批）改为空态 + 提示，或不传年度由后端取；每批下调基线、跑该族 vitest
- [ ] 4.2 浏览器实测（同 3.3）

## 5. 后端写死年度（R4.1、R4.2）

- [ ] 5.1 `routers/wp_prefill_preview.py` 两处改单一来源，取不到 ⇒ 422；端点级测试
- [ ] 5.2 `year: int = 2025` / `Query(2025)` 等参数默认值逐端点改（改前现查前端调用方是否都传年度）；`x or 2025` / `.get("year", 2025)` 同改
- [ ] 5.3 下调基线；触及的既有测试按新语义改写

## 6. 后端今天的年份（R4.3）

- [ ] 6.1 兜底类改单一来源；日历类按 2.2 进豁免表
- [ ] 6.2 下调基线；端点级测试

## 7. 收尾

- [ ] 7.1 基线清零或只剩豁免；变异复跑；回归（改动涉及的测试目录对比改动前）
- [ ] 7.2 INDEX / memory 更新

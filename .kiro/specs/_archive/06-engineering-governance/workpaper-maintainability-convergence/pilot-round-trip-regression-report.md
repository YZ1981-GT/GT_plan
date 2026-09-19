# 任务 4.4：D2 / K5 / J2 试点 Round_Trip 回归报告

## 1. 验收范围与环境

- 对应需求：3.9、8.1–8.4；仅覆盖 Wave 3 的三个代表底稿，不代替后续全循环验收。
- 验证方式：Chromium、单 worker、真实前后端与 PostgreSQL，不 mock 持久化或 AI 请求。
- 项目 fixture：`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`。
- D2：wp `e2c95d10-181d-4549-8910-d5ab5bc5edd1`，sheet `D2-7`，item `D2-vc-conclusion`。
- K5：wp `26acda99-1409-42de-883a-47adc9769c1a`，sheet `K5-1`，item `K5-1-audit-conclusion`。
- J2：wp `eb3cbf2d-394c-43e8-9296-a93ff41339ea`，sheet `J2-3`，item `J2-3-note`。
- E2E：`e2e/workpaper-maintainability-pilots-roundtrip.spec.ts`。
- DB 独立回读：`backend/scripts/e2e/read_checklist_response.py`，直接查询 PostgreSQL，不复用页面状态。

## 2. 最终结果

命令：

```powershell
rtk npx playwright test e2e/workpaper-maintainability-pilots-roundtrip.spec.ts --project=chromium --workers=1 --reporter=json
```

结果：`PASS 3 / FAIL 0`，约 21.9 秒；Playwright `.last-run.json` 为 `status=passed`、`failedTests=[]`。

三个试点均完成以下真实闭环：写入唯一 `RT-*` marker → 捕获目标 checklist PUT 并核对 item/payload → 独立 API GET 回读 → Python 直查 DB 回读 → 使用新 URL 参数重新导航 → UI 回显一致 → 恢复测试前原值 → GET/DB 再确认恢复。每个页面均监听 `console.error` 与 `pageerror`，最终均为 0。

## 3. 逐试点证据

### D2（复杂往来款、抽凭底稿）

- 在 `D2-7` 审计结论输入 marker，捕获 `D2-vc-conclusion` PUT，payload `remark` 与 marker 完全一致。
- API GET、PostgreSQL 和 fresh navigation 后 textarea 三方一致；最后恢复原值。
- “版本历史”打开真实版本抽屉；“底稿复核”打开真实复核对话，不是 console 桩。
- 页面请求指标：`renderConfigGet=2`、`checklistGet=0`、`checklistPut=2`、`aiPost=0`。

### K5（历史 persistence 多连环问题）

- 在 `K5-1` 审计说明输入 marker，捕获 `K5-1-audit-conclusion` PUT；GET、DB、fresh navigation UI 均一致，最后恢复原值。
- 版本抽屉真实可用；切换到 `K5-3` 后打开真实复核对话，再返回 `K5-1` 完成保存闭环。
- 页面请求指标：`renderConfigGet=2`、`checklistGet=0`、`checklistPut=4`、`aiPost=0`。

### J2（多 section、AI、目录跳转）

- 从“底稿目录”精确点击“调整分录汇总表J2-3”卡片跳转，避免 `J2-1` 与 `J2-10` 一类前缀误匹配。
- `J2-3-note` PUT、独立 GET、DB 与 fresh navigation UI 回显一致，最后恢复原值。
- 真实调用 `/ai/generate-text` 并成功；请求 `context` 的所有值均为字符串，生成结果随后进入统一 checklist PUT。
- 版本历史打开真实版本抽屉；页面请求指标：`renderConfigGet=2`、`checklistGet=2`、`checklistPut=7`、`aiPost=1`。
## 4. 迁移前后静态指标

口径为 `HEAD` 基线到当前工作区；“直接 checklist I/O”统计试点主入口/业务组件中的直接网络实现，“本地 provider/Host”统计已由 Runtime Boundary 承担却在试点重复接线的实现。

| 试点 | 行数 | 直接 checklist I/O | 本地版本 provider | 本地复核 provider/stub | 本地 Host | 保存 timer |
|---|---:|---:|---:|---:|---:|---:|
| D2 | 1465 → 1360 | 3 → 1 | 2 → 0 | 1 → 0 | 3 → 0 | 4 → 0 |
| K5 | 859 → 721 | 3 → 0 | 2 → 0 | 2 → 0 | 1 → 0 | — |
| J2 | 231 → 229 | 2 → 0 | 1 → 0 | — | 1 → 0 | 1 → 0 |
| **合计** | **2555 → 2310（-245）** | **8 → 1** | **5 → 0** | **3 → 0** | **5 → 0** | **5 → 0** |

D2 剩余 1 处直接 checklist I/O 是业务子底稿读取，不是本地保存实现，因此未为追求数字归零而错误删除。

## 5. 发现并修复的失败模式

1. **D2 受控输入回滚，未发 PUT**：`D2TabVoucherCheck.vue` 使用 `:model-value="conclusion"`，但只在 `change` 时更新 ref；输入过程中旧 ref 把新值重置为空。修复为 `v-model="conclusion"`，保留 `@change="saveConclusion"`。修后真实 PUT/GET/DB/UI 闭环通过。
2. **版本 Host 重复挂载**：页面同时出现两个 `.version-trail-drawer`，分别来自 `WorkpaperEditor` 与 Runtime Boundary。未用 `.first()` 掩盖；改为 `GtWpRenderer` 暴露 `openVersionHistory`，HTML 路径由编辑器按钮委托 Runtime Boundary，编辑器级 `GtWpVersionTrail` 仅保留在非 HTML 路径。
3. **J2 目录前缀误匹配风险**：测试与运行链均使用完整 sheet 名“调整分录汇总表J2-3”精确定位卡片，避免短编码包含匹配误入其他 sheet。
4. **Runtime Boundary 测试契约漂移**：生产代码暴露 `runtime.version.openVersionHistory` 后，旧 mock 返回 `undefined`。测试修为返回最小真实契约，并断言 exposed 方法确实委托版本服务；未在生产代码增加无意义 optional chaining。

## 6. 网络指标口径与可复现性

上述网络数仅统计浏览器页面发出的请求，不包含 Playwright `APIRequestContext` 的独立断言 GET，也不包含 Python DB helper；因此页面 `checklistGet=0` 不表示未做 GET 回读。独立 GET 和 DB 回读是闭环中的额外证据。

E2E 使用 serial 模式并在每例结束恢复原值；最终 PostgreSQL 未发现 `RT-*` 或 `PROBE-*` marker 残留。若用例中途终止，应先运行 marker 查询并恢复 fixture，再重跑，禁止把污染数据作为通过证据。

## 7. 补充回归验证

- 目标 Vitest：`GtWpRenderer.runtime-boundary.test.ts`、`GtWorkpaperRuntimeHosts.test.ts`、`k5PersistenceMigration.spec.ts`、`J2RuntimeMigration.unit.test.ts`，结果 **4 files / 16 tests passed**。
- Vite transform：`GtWpRenderer.vue`、`WorkpaperEditor.vue`、`D2TabVoucherCheck.vue`、`GtK5Provisions.vue`、`GtJ2DefinedBenefitPlan.vue` 均为 HTTP 200。
- Diagnostics：Runtime Boundary 测试、Renderer、Editor、D2 组件与 E2E spec 均无问题。
- 本报告及实现均未修改 `tasks.md`；任务状态由编排器维护。

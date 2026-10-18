# 设计评审：formula-manager-closure / design.md（第四轮）

评审对象：`d:\GT_plan\.worktrees\fm-closure-spec\.kiro\specs\formula-manager-closure\design.md`
对照输入：
- 审计报告 `d:\GT_plan\docs\proposals\formula-management-platform-audit-2026-10-17.md`（HEAD `84def65b`，复核 `e5ee550f`）
- 需求 `d:\GT_plan\.worktrees\fm-closure-spec\.kiro\specs\formula-manager-closure\requirements.md`

评审方式：无上下文独立重核。读码 spot-check 验证关键锚点现状（未跑构建/测试）。

---

## 裁决：CHANGES_REQUESTED（0 HIGH / 1 MEDIUM / 2 NIT）

设计质量整体很高。§1 的 20 条「现状 grep 确认」经抽查为真核实（非照抄报告），锚点全用符号名/端点字面量/HEAD 绑定，合并三类严格「先诊断后决策」，FM-P0-05 定级为「静态高危·待 TestClient 坐实」，附注三端点明确排除整改。唯一阻断项是需求 20（P2 治理组）在 design 中完全没有落点，无法派生为可验收任务。

---

## Findings

### MEDIUM-1 · 需求 20（P2 治理组）在 design 中零落点，无法派生可验收任务

**问题**：requirements.md 的需求 20 是一条完整需求，含 4 条验收标准：
1. ≥7 套 local formula dialog/drawer 收敛到中央或明确分工（每套登记权威源与去留决定）；
2. 2 条历史假红/脆化前端测试（`FormulaManagerPageWiring`、`formulaStatusPanelDisplay`）修正/更新；
3. formula_push 套件 1164 warnings（含 `Connection._cancel was never awaited`）收敛；
4. RTK 吞失败退出码问题修正（验收须断言 stdout 内容）。

design.md 对整个 P2 组**零覆盖**：全文搜 `P2 / 治理 / 可维护 / dialog/drawer / warnings / 脆化 / 假红 / 1164 / RTK / FormulaManagerPageWiring / formulaStatusPanelDisplay` 均无命中。§5 整改七步严格按报告第十节组织（第十节本身不含 P2），§3 数据流表、§4 ADR、§12 模块索引、§13 评审响应表均无一条对应需求 20。报告第九节 P2 1~3 条、第八节两条历史红、第八节 RTK 吞退出码确实存在，需求文档也已把它们转写为需求 20，但 design 这一环断了——需求存在、设计不接，tasks 阶段无从把需求 20 的 4 条 AC 落为任务。

这是「需求→设计覆盖」的实质缺口，不是风格问题：评审重点 3 要求「完整覆盖……主要 P1」与模块深化，需求 20 虽归 P2，但它是本 spec 正式需求之一，design 必须给出落点（哪怕是「本轮仅诊断/登记，不实施」的显式决策）。

**CONCRETE 修复**（三选一，任选其一即可解除阻断）：
- （推荐）§5 新增「步骤 8 · P2 治理收敛（需求 20）」或在 §12 后新增「§12.1 P2 治理落点」小节，逐条给落点：
  - 20.1：列出报告第九节 P2-1 的「≥7 套 local formula dialog/drawer」，每套登记权威源 + 去留决定（收敛/保留分工），作为可验收清单；
  - 20.2：`FormulaManagerPageWiring`（一次性 reject 被新增 bindings GET 抢先消费而脆化）与 `formulaStatusPanelDisplay`（仍要求「HTML 面板不可达」旧缺口、现已加按钮变历史假红）两条测试各写修正方向（反映当前真实行为，不以历史缺口为前提恒绿/恒红）；
  - 20.3：formula_push 套件 1164 warnings 收敛方向（至少定位 `Connection._cancel was never awaited` 根因并给处置）；
  - 20.4：RTK 吞退出码的验收口径（断言 stdout 内容，复用 §7.4③ 的子进程口径）。
- 或：若本轮刻意不实施需求 20，则在 §13 之外新增一行显式决策「需求 20 本轮仅登记现状、tasks 中标为诊断/条件项不实施」，并说明理由与边界（与 ADR-FMC-09/NIT-3 的「条件项不实施」写法同构），使 tasks 有明确依据。
- 或：若认为需求 20 不应属本 spec，则需求文档与 design 一并移除/改域——但这需回到 requirements，超出本轮 design 评审，故不作首选。

---

### NIT-1 · §7.2 断言⑤「右栏精确 + surfaced 只读 + 保存体字段」三义合一，变异映射与门禁分母口径略含糊

**问题**：§7.2 断言⑤把三件独立的事塞进一条断言——(a) 右栏每条 `stable_sheet_key` 精确等值；(b) surfaced/extraction 只读无伪装；(c) 保存请求体字段为契约 `category/description`。§7.5 四变异里「注入 `E1-10`」→⑤、「把 save 改回 report_config」→⑤，两个不同变异都映射到同一条⑤，但命中的其实是⑤的不同子项（前者命中 (a)，后者命中 (c) 的「目标端点非 report-config」）。这在实现门禁时容易让「⑤整体绿」掩盖某一子项未被真正断言（memory 铁律㉖「守卫写完必须逐处变异」的同型风险）。

**CONCRETE 修复**：把断言⑤拆成可独立计红的三个子断言（⑤a 右栏精确等值 / ⑤b surfaced 只读去伪装 / ⑤c 保存体契约字段 + 目标端点），§7.5 变异表的「注入 E1-10」映射 ⑤a、「save 改回 report_config」映射 ⑤c（目标端点），并各配反向断言。或保留⑤为一条但在 §7.5 明确标注每个变异命中的是⑤的哪个子项。

---

### NIT-2 · §7.1 门禁分母剔除项与 §5 步骤 2「404 归类」的判定依据来源须点明「实施期重算」

**问题**：§5 步骤 2 的 10 个 classification 404 归类依赖「逐个查 `wp_code_overrides.json`」，§7.1 据此从门禁分母剔除「口径外」项。但 §11 已声明计数/数据随并行会话漂移、禁写死；`wp_code_overrides.json` 条数（§1 #20 未给数、报告第十一节记 1,526）与那 10 个 404 wp_code 具体是哪些，都会随 HEAD 前移与真实项目数据变化。design 未显式提醒「这 10 个 wp_code 的清单与归类必须在实施期（而非照抄撰写期）重新运行 classification API + 重查 override 得出」。

**CONCRETE 修复**：在 §5 步骤 2「404 归类」子任务或 §10 重做 grep 清单中补一句：「10 个 classification 404 的 wp_code 清单及其 override 命中与否，须在实施期对当时真实医疗器械项目重跑 classification API + 重查 `wp_code_overrides.json` 得出，不沿用撰写期快照（与 §0/§11 漂移纪律一致）」。

---

## Verified Assumptions（本轮读码核实，全部成立）

在工作树 `d:\GT_plan\.worktrees\fm-closure-spec` 现读：

1. **锚点 #1 `matchSheetCode`**：`FormulaManagerDialog.vue` 实测函数体为 `if (!a||!b) return false; return a === b || a.includes(b) || b.includes(a)`（经 `normalizeSheetToken` 归一）。与设计 §1 #1 完全一致。`matchSheetCode` 在右栏聚合两处（约 2091、2107 行区）被调用。
2. **锚点 #4 三端点鉴权**：`wp_formula.py` 的 `list_formulas`（`@router.get("/formulas")`）、`save_formula`（`@router.put("/formulas")`）、`delete_formula`（`@router.delete("/formulas/{formula_id}")`）均 `Depends(get_current_user)`，路径仅 `{wp_id}`/`{formula_id}`，无 `require_project_access`。与设计 §1 #4 一致（IDOR 静态高危成立）。
3. **锚点 #5 `createOpenFormulaManagerCommand` 生产零调用**：全仓前端引用仅 `openFormulaManagerCommand.ts`（定义）、`shell/formula/index.ts`（re-export）、`openFormulaManagerCommand.spec.ts` + `fShellConformance.spec.ts`（测试）。无任何生产组件 import。与设计 §1 #5 一致。
4. **锚点 #19 迁移归属（上一轮 MEDIUM 焦点）**：`V163__wp_formula_stable_key.sql` 为前向迁移（`ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS stable_sheet_key VARCHAR(255)` + 回填 `UPDATE` + `CREATE UNIQUE INDEX uq_wp_formula_stable_key … WHERE stable_sheet_key IS NOT NULL`），列可空；`R163__wp_formula_stable_key.sql` 为配对回滚（`DROP INDEX` + `DROP COLUMN IF EXISTS stable_sheet_key …`）。与设计 §1 #19、§13.2 更正后的表述完全一致，编号归属已正确。
5. **稳定键单一真源（NIT 焦点）**：`backend/app/services/formula_management/stable_key.py` 存在，导出 `normalize_sheet_key`（`def normalize_sheet_key(sheet_name)`）与 `derive_stable_key`（`def derive_stable_key(sheet_name, target_cell) -> StableKey`），模块 docstring 明确「单一真源……供 service 写入、迁移回填、PBT 三处共用（不各写一份）」。V163 回填 SQL 注明「与 `app.services.formula_management.stable_key` 逻辑对齐」。设计 §9/ADR-FMC-01 引用的函数名与此逐字一致。
6. **FM-P0-05 定级**：ADR-FMC-06、需求 5「定级依据与张力」均表述为「静态高危·待一条 TestClient 跨项目用例坐实」，并写明「未执行任何越权探测」「坐实后据结果加固，若意外已安全则更新定级不按已越权处置」。符合评审重点 5。
7. **附注三端点不误列**：§1 #12、ADR-FMC-07、需求 4.4/14.2 均明确附注 `apply/list/upsert` 已挂 `require_project_access`、不纳入鉴权整改。符合评审重点 5（未把附注误列为待修）。
8. **合并三类先诊断后决策**：ADR-FMC-09、§6.2 表、需求 17/18/19 均严格「先最小数据运行诊断→据落库/对拍结果判已打通 or 已断裂→不预设重写」，需求措辞 Out-of-Scope 明文「禁写重写合并链」。符合评审重点 4。
9. **门禁 8 断言 + 幂等 + 4 变异**：§7.1~7.5 完整覆盖运行时权威分母、8 条断言、豁免登记、幂等输出三件套（内容不变不改时间戳 / `--check` 不用 `--write`+diff / 子进程 utf-8+断言 stdout）、四变异配反向断言。符合评审重点 3 的门禁部分。
10. **锚点绑定 + 实施前重做 grep**：§0 绑定 HEAD `4934142a1c...`、§10 强制「动代码前重跑 §1 全部 20 条 grep」，全程用符号名/端点字面量/常量名不写死行号。符合评审重点 2。

## Unverified / Wrong Assumptions

- **无 Wrong**：抽查的 5 个锚点（#1/#4/#5/#19 + stable_key 真源）全部与设计表述一致，未发现设计把现状写错的地方。上一轮的 V163/R163 编号错误已在 §13.2 正确修复。
- **Unverified（本轮未逐一现读，接受设计自述，非阻断）**：锚点 #2/#2b（`onFormulaEditSave` 的 `row.id` 分支与 `formula_category/formula_description` 误读）、#3（`_build_surfaced_formulas` 全条 `readonly:True`）、#6（左栏 `loadAcnrTree`）、#7~#13（report_config/formula/formula_scope/tb-detail/cross-check 各端点鉴权与 `year` 必填）、#14/#15（附注双存储 `_formulas`/`_user_formulas`）、#16/#17（E1/D4 node-only、Univer「同步公式」）、#20（`wp_code_overrides.json`）。这些设计均标「确认成立」，与报告一致且已验证的 5 条锚点佐证设计的核实方式可信；实施期须按 §10 全部重跑。
- **需求 20 的 P2 证据（2 条测试、1164 warnings、RTK）本轮未现读复验**：但其在 design 的缺口（MEDIUM-1）与证据是否属实无关——无论证据如何，design 都须给需求 20 一个落点。

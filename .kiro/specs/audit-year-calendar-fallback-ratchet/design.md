# 设计：审计年度兜底取今年 / 写死年度（audit-year-calendar-fallback-ratchet）

> 现状均为 2026-10-25 在 `bf7685b1d` 干净检出上现算。行号会漂，锚点用文件名 / 函数名。

## 1. 守卫（R1，任务 1）

### 1.1 前端：`src/__tests__/auditYearCalendarFallbackRatchet.spec.ts`

- 扫描：`src` 下 `.ts / .tsx / .vue / .js / .mjs / .cjs`，跳过 `__tests__` / `test` / `tests` / `node_modules` 目录与 `*.spec.*` / `*.test.*` /
  `*.stories.*`（现算 5332 个文件）。首版草稿把守卫放在 `utils/__tests__/`、清单带 `total` 字段；实施时放到 `src/__tests__/`（全前端范围的守卫），
  总数改由断言现算（清单里存的总数会与条目不一致）。
- 计数：逐行；以 `//`、`/*`、`*`、`<!--` 开头的行不计；行尾 `//` 注释（`//` 前是空白、且它前面的引号成对）去掉后再数。
  正则覆盖 `new Date().getFullYear()`、`(new Date()).getFullYear()`、`new Date(Date.now()).getFullYear()`、`dayjs().year()`、`moment().year()`；
  `new Date(具体日期).getFullYear()` 不计。逐行而不是按语法树：`.vue` 模板里的表达式（`:year="year || new Date().getFullYear()"`）也要数到，
  而跨行的块注释正文只要以 `*` 开头就被排除（本仓库的块注释都是这种写法）。
- 基线：`auditYearCalendarFallbackBaseline.json`，键 = 相对 `src` 的路径（排序），值 = 该文件的出现次数（正整数）。
  初始由同口径的一次性脚本生成，vitest 在干净检出上复核两边逐文件一致后入库；之后只手改（修掉一处减 1，为 0 删行）。
- 断言：①扫描口径（8 条应计、8 条不应计样例；文件名 / 目录过滤样例；扫描文件数 > 3000）②没有新增 ③只许变小
  ④基线规范（排序、正整数、总数 ≤ 冻结值 340）。

### 1.2 后端：`tests/test_audit_year_calendar_fallback_ratchet.py`

- 扫描 `backend/app/**/*.py`（现算 2771 个文件），AST，注释与 docstring 天然不计；读源码用 `utf-8-sig`（个别文件带 BOM）。
- 今天的年份：`<X>.<now|utcnow|today>(...).year`，`X` 的点分名末段是 `datetime` 或 `date`（`datetime.now`、`dt.datetime.utcnow`、
  `__import__("datetime").datetime.now`、`date.today`、`datetime.date.today`）。
- 写死年度：2000~2099 的整数字面量，出现在 ①名字含 year 的参数默认值（字面量，或 `Query / Field / Form / Body / Path / Header / Cookie`
  的首个位置参数 / `default=`）②名字含 year 的变量 / 属性赋值（全大写常量除外，如 `_MIN_YEAR = 2000`）③`x or 2025`（前面某个操作数含 year）
  ④`x if … else 2025`（条件或取值含 year）⑤`.get("…year…", 2025)` / `getattr(x, "…year…", 2025)`。同一节点只计一次。
- 基线写在测试文件里（72 个文件、130 处），总数上限 `FROZEN_TOTAL_CAP = 130`。断言与前端相同；全量扫描结果模块内缓存（三条断言共用一次扫描）。

### 1.3 规则取舍

- 口径比首版草稿宽：草稿只数「不减 1 且行内含 year」（现算 250，其中 7 处在注释行）。注释不计；减 1 也计 —— `x || new Date().getFullYear() - 1`
  同样是按日历猜年度（97 处），草稿口径下改成减 1 就能绕过守卫。前端 340 = 草稿口径的 243 处代码 + 97 处减 1。
- 按文件计数而不是只看总数：总数不变时代码可以「修一处、在别处新增一处」，按文件才能指到具体位置；代价是挪动代码要同步挪基线条目
  （失败信息写明），并加了总数上限防止借挪动净增。
- 「变少也红」：基线必须与现状逐文件相等，否则修掉的名额会被后来的新增悄悄用掉（棘轮失效）。
- 日历用途（年度声明、年份下拉上限）先一并冻结，任务 2 判定后移入豁免表；不在守卫里猜哪些是日历用途。
- 盲区：`const d = new Date(); d.getFullYear()` 与格式化日期同形，不计。任务 2 判定时按文件补查。

### 1.4 变异（任务 1.3）

前端 MY1~MY9：基线外文件新增一处、修掉一处不改基线、整行注释口径失效、行尾注释口径失效、扫描根写错、漏认 `(new Date()).getFullYear()`、
基线净增、测试文件也计入、`__tests__` 目录也扫。后端 MB1~MB7：新增写死年度默认值、修掉一处不改基线、全大写常量也计、只认 `now()`、不认 `Query(2025)`、
扫描根写错、`or` 不看前项是否含 year。每条须打红在预期断言上（见 tasks 1.3 证据），跑完逐字节恢复。

## 2. 逐处判定（R2，任务 2）

产出 `evidence/classification.md`：每处（文件 + 函数 / 组件 + 用途）→ 写请求 / 读请求 / 日历 / 单一来源兜底；按 import 闭包追到请求发出点
（多数是先赋值给 `year` 再传，同一行看不出读写）。日历类与单一来源兜底（R3.2 选 A 时）进豁免表：

- 前端：spec 内 `CALENDAR_YEAR_EXEMPT: Record<路径, 理由>`，扫描时这些文件按「基线 + 豁免」合计；豁免须可证伪（文件仍命中口径）。
- 后端：同名字典，写在测试文件里。

## 3. 前端收口（R3，任务 3、4）

- 调用方：不再自己拿日历猜，改为经单一来源取项目年度（数据来源用调用方已有的 store / 路由 / 项目对象 / 底稿运行时注入的年度）。
- 单一来源的最终兜底（R3.2 待拍板，开工前确认）：
  - 方案 A（首版草稿）：沿用 `resolveEffectiveAuditYear` 的「去年」兜底，该处进豁免表。
  - 方案 B（建议）：新增 `resolveAuditYearOrNull(sources)`（全部来源缺失返回 null），`resolveEffectiveAuditYear` 改为委托它，调用方处理 null
    后删除旧函数；`useAuditContext` / `useProjectSelector` 同口径。读请求年度为 null 时显示空态 + 提示「未设置审计年度，请先在项目基本信息中填写」。
- 写请求（任务 3 先做，两方案相同）：年度取不到时不发请求，`ElMessage.warning` 同一提示。
- 后端已按单一来源取年度的端点（参数可选）可不传年度。
- 每改一组：下调基线、相关 vitest、单区域 vue-tsc；浏览器实测（【测试】项目，含未填年度与审计期末的项目）。

## 4. 后端收口（R4，任务 5、6）

- 任务 5：`wp_prefill_preview.py` 两处改 `fetch_project_audit_year`，None ⇒ 422「未设置审计年度」；写死参数默认值逐端点改：
  前端都会传年度的改必填（`Query(...)`），可能不传的改 `int | None = None` + 单一来源 + None ⇒ 422。改前按端点现查前端调用方。
- 任务 6：`datetime.now().year` 兜底改单一来源；日历用途（独立性年度声明、EQCR 趋势终点、导入时的年度探测默认值等）逐条判定后进豁免表。
- 每改一组：下调基线、端点级测试（TestClient 真发请求）、触及的既有测试按新语义改写。

## 5. 风险

- 改成「取不到就提示」后，没填审计年度的老项目会从「静默显示别的年度」变成「提示先填年度」：属于预期变化，在发布说明里写明。
- 前端改单一来源会波及 266 处底稿组件：按组件族分批（D~N 循环各一批），每批跑该循环的 vitest。

# 关注点 / 已知脆弱处（K 循环）

## 1. 🔴 三组同码

| 码 | 用它的科目 | 风险 |
|---|---|---|
| 1231 | K1 坏账准备 + K2 其他流动资产 | K1 用 1231 作坏账备抵、K2 用 1231 作科目主体 → 取数/回写可能撞 |
| 2701 | K5 预计负债 + L5 长期应付款 | 两底稿都回写 2701 会互相覆盖 |
| 6602 | K9 管理费用 + I6 研发费用 | 研发费用是管理费用明细，两者不能各自独立全额回写 |

**未核实**是否刻意（研发在管理费用下确有会计依据），但**审定合计的关系必须显式核对**，不能两边独立回写同一 TB 行。

## 2. K11 与 G14 的减值边界

**资产减值损失 K11（6701）= 非金融资产**（存货/固资/无形/长投/商誉/投资性房地产/持有待售）；
**信用减值损失 G14（6702）= 金融资产 ECL**（应收款/债权投资）。
混淆会导致利润表行错位。K1 其他应收款坏账属信用减值性质，但历史上进 K11（需按客户报表口径确认）。

## 3. K 循环历史 persistence 四连环 bug（已修，勿回退）

主入口 `handleChildSave` 曾有四类问题（K1~K13 广泛存在）：
- **双层包裹**：`JSON.stringify({remark})` → 存 `{"remark":"..."}`，reload 解析成对象非数组丢数据
- **http 缺 `/api` 前缀**（`http` baseURL='/' 不自动加）→ 404 静默不落库
- **selfLoad 只读 `allResponses` 漏 `responses_snapshot`**（后端 render 实际输出的键）→ 加 `_mergeResponses` 合并
- **TB 自动取数缺 `year`** → 422

## 4. 双模式历史坑

- `useK{n}DualMode` 曾用裸 `fetch('/onlyoffice/health')`（无鉴权头）→ 登录态 401 → OO 永不可用
- **el-segmented 用 `v-model`**：v-model 先改值 → `switchMode` 首行 `target===current` 短路 → config 预拉从不跑（"拉取成功"门失效）
- **onlyoffice-config 缺 `project_id` 参** → 422（useF2DualMode 也漏，复用需补）
- 单 sheet config 失败不应全局禁用 OO；目录 sheet 必须从 OO 分支排除（否则切 OO 后目录页被顶掉且无工具栏切回）

## 5. AI context 类型

各 handleAI 曾传 `JSON.stringify(context)` 或非字符串值 → 后端 `dict[str,str]` 422 静默失败
（附注表也中招）。必须 context 值全转 str，走 `POST /ai/generate-text`。
K8/K9/K10/K11/K12/K13 的 AI 曾全是 `ElMessage.info` 桩 / 死 `emit('K{n}-x-ai-trigger')`，已接真实端点。

## 6. 附注死链

各科目附注 `applyAutoFill` 曾读 `K{n}-1-row-${i}-audited`（审定表从不写此键，只写 `K{n}-1-rows` JSON + `-audited-total`）
→ 自动取数恒空。改读 `K{n}-1-rows` 按 name 匹配（K10/K11/K12/K13 同款死链已修）。

## 7. 循环 IE 路径

正确范式：`http.post('/api/workpapers/{wpId}/{prefix}/export-template', null, {params:{sheet}})`
（工厂 `create_cycle_import_export_router` 全 POST + Query `sheet`）。
K8/K11 曾用 `/k8-export-template` + `sheet_code`（连字符/错参/GET）→ 404/422；
后端 `_SPECS` 的 item_id / storage_field 必须与前端持久化键/字段一致（否则导入写前端不读的列）。

## 8. K5-7 / K7-5 检查表结构曾做错

K5-7 曾做成 10 项合规 radio 清单（应是 K1-12 式凭证级检查表，account-code=2701）；
K7-5 同理（2401）。K6-4 曾把 CAS42 五条件 radio 当成主体（应是 19 列分层估值表）。
—— 检查表类要对照源模板判断是"凭证级"还是"合规清单"，多数是凭证级复用 useK1VoucherCheck。

## 9. K8/K9/K13 抽凭 phase 非法值

抽凭引擎 `phase` 只有 `preliminary | final`，K8-8/K9-8/K13-4 曾传 `current` / `substantive` → 422。
`year` 曾硬编码 `new Date().getFullYear()`（审计次年取错报告期），应从 props.year。

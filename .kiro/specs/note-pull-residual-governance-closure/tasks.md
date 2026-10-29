# 附注取数残留与治理收口 — 任务

## 批 A 现状与防假绿基座

- [x] 1. 现算残留基线：11 个离屏码、13 个 M 错误调用、3 个 edit 清册阻断、18 条本轮域边界与 Task 23.1 环境要求
  - 证据：当前 HEAD `8107371f0`；离屏 67/78；edit `--check` 精确报 OCR / attachment / confirmation 3 项；domain 为
    current 1470 / baseline 897 / new 591 / resolved 18，其中 `06be17bbe` 新增 18、其余 573 不归本轮；identity 165/236/80。
- [x] 2. 建立 requirements / design / tasks 三件套，锁定十项 ADR 与实施顺序
  - 证据：明确无来源≠0、单一 Map、AST 自动同步门、共享章节 owner、非零等价接入门、G7 附注侧 owner ledger、来源分层、
    method-derived gate、域边界归因清零、真实浏览器可逆验收。
- [x] 3. 自动同步 AST 守卫：合法 options / 有参 schedule / 卸载 cancel，逐处错误变异必须打红
- [x] 4. provider 反向盘点守卫：生产 provider 必须恰好注册一次或在只许变短的具名清单
- [x] 5. K strict 域新增文件 append-only 账本与 L strict / wide 现算回归，不抬历史基线

## 批 B 先阻止挂载静默改数

- [x] 6. G12 来源存在性 patch：缺来源不动、明确 0 可写、返回 changed/sourceFound
- [x] 7. G12 挂载持久化门：只在可写且真实变化时保存；非零 / 缺失 / 0 / 只读用例
- [x] 8. G13 本期与上期先合并 patch、最后最多保存一次；缺失 / 单边 / 0 / 只读用例
- [x] 9. H3 统一宿主响应 Map，修上市 / 国企 × 成本 / 公允价值非零读回和重挂载
- [x] 10. H3 无来源不推 0；真实 Tab 自动同步回归
- [x] 11. H5 宿主提供显式保存 adapter；编辑 / AI / 重挂载 / 只读集成测试
- [x] 12. M1 / M2 / M3 / M8 修自动同步调用、只读门与卸载取消；fake timer 验证一次写

## 批 C 模板对齐与共享章节唯一写权

- [x] 13. 从两版附注模板提取 M6 / M9 / M10 权威表名、行名、列角色，建立 golden
- [x] 14. M6 恢复 / 快照按模板投影，保留调整后期初与可供分配利润等模板要求行
- [x] 15. M9 上市 BS / PL 两表拆分、去底稿批注、补分组；国企第二表完成明确裁决与测试
- [x] 16. M10 只发送真实拥有且有完整输入的表，禁止空基本情况 / 空持有者 / 恒 0 数量覆盖
- [x] 17. M6 / M9 / M10 修自动同步，结构门先于启用，非零 Tab 请求测试
- [x] 18. `五、42 / 八、42` 落 L2 利息、M1 股利、K3 其他应付款的行域 / 表域 owner
- [x] 19. K3 移除对 M1/L2 表的生成和删除；三 owner 任意同步顺序结果一致

## 批 D 剩余 11 个离屏 provider

- [x] 20. F1 孤儿 provider 非零 listed / soe 等价测试、登记并删除冻结项
- [x] 21. H3 provider 四口径等价、零底稿写入、登记并删除冻结项
- [x] 22. L4 补主表 / 变动 / 说明读回与完整快照，provider 等价并登记
- [x] 23. L5 补分类 / 未确认融资费用 / 一年内到期读回，保护 L6，provider 等价并登记
- [x] 24. M6 provider 非零等价并登记
- [x] 25. M9 provider 两口径 / 多表非零等价并登记
- [x] 26. M10 provider 只写拥有表的非零等价并登记
- [x] 27. K3 provider 经共享 owner 顺序对拍后登记
- [x] 28. H1 扩充离屏项目口径上下文，抽共用快照，主章节 / 受限段等价并登记
- [x] 29. G7 附注侧 owner ledger、失败不推进；多章节 / 删除表等价并登记
- [x] 30. E1 抽宿主状态，主表不写、说明 / 外币 / 受限段多章节与 row-scope 回报，登记
- [x] 31. 收紧 `NOT_YET_HEADLESS` 到空：78/78、孤儿 0、全部循环 strict 守卫

## 批 E 来源、鉴权与域边界治理

- [x] 32. 公式推送旧 `_tables` 保持 `_source`；新建 sub_table 骨架仍可投影；反转错误契约
- [x] 33. 误标存量 dry-run 识别器与正反样本；只在【测试】项目验证，不误清真实底稿同步
- [x] 34. OCR 鉴权拆 readonly / edit 显式分支并覆盖缓存、空缓存、pending、角色矩阵
- [x] 35. attachment helper 正式 GateSpec 与对象项目归属可伪证测试
- [x] 36. confirmation method-derived GateSpec / 解析器 / 17 端点逐方法清册测试
- [x] 37. 重生 edit 清册、双生成逐字节一致、`--check` 0；identity 基线收紧到现算值
- [x] 38. domain checker 排除 generated components.d.ts、修 Python package alias 解析并加反向样例
- [x] 39. 补精确 owner，移动 noteTotalTerms / noteColumnTree，抽 decimal helper，反转 wp→notes 依赖
- [x] 40. `--write-baseline` 有 new 时拒绝、实现 shrink-only；18 条归因边清零且 baseline 不增长

## 批 F 真实环境与整体回归

- [x] 41. 建可逆 UAT 工具：动态识别全【测试】企业树、整行 / 主键备份、精确恢复与哈希对拍
- [x] 42. 普通映射章节真实浏览器拉数：叶子 detail_mapping、根 subtree_aggregate、独立 GET + 硬刷新
- [x] 43. 前 N 名真实浏览器写入：同名跨企业合并、集团内排除、排序截 N、合计 / 比例 / 近似提示
- [x] 44. 恢复 UAT 数据并证明主键集合、整行哈希、企业树零差异；更新旧 Task 23.1 实证状态
- [x] 45. 相关后端 / 前端 / K~M/H/G/E strict 回归，预存红在同基线逐条归因
- [x] 46. 全量 vue-tsc 候选对 HEAD、行数门、gitleaks、两份鉴权清册、域边界归因门
- [x] 47. Playwright 功能 / 控制台 / 网络实测（127.0.0.1:3030；写入仅【测试】项目）

## 批 G 复盘与交付

- [x] 48. 五角色整体复盘，现算遗漏；高收益低风险项当轮修复，其余按 ROI 登记
- [x] 49. 更新 design 实施偏离 / 证据、INDEX、dev-history、memory；旧 spec 只追加勘误不改历史证据
- [x] 50. fetch 远端、在干净候选树重放与终验、单提交、`push_version.py` 带版本标签原子推送；主工作树安全对齐并清理本会话资源

## 聚合验收记录（任务 3~49）

### 功能与治理闭环

- 自动同步 AST 门已覆盖 options、带参 schedule、卸载 cancel；错误调用逐处变异打红。生产 provider 反向盘点与注册表精确相等，`NOT_YET_HEADLESS=[]`，78/78 码、孤儿 provider 0。
- G12/G13/H3/H5 与 M1/M2/M3/M8 已阻断挂载静默写；M6/M9/M10 按两版模板恢复非零状态后才启用同步。M9 上市 BS/PL 分表、国企 43 行；M10 只管理具备三组数量来源的变动行。
- `五、42 / 八、42` 写权收敛为 L2 利息、M1 股利、K3 其他应付款独占明细；共享主表由后端按三份明细确定性重建，六种到达顺序逐值相同。
- G7 使用附注行内 `_workpaper_table_owners` v1 清册，同一行锁/事务完成写表、删旧表、更新 owner；strict batch 对人工覆盖、口径跳过、row-scope 未解析全部回滚。公式推送旧 `_tables` 保持结构来源，新建投影骨架才标记。
- 鉴权动态门使用 `MethodLevel`：GET/HEAD readonly，其余 edit，未知方法 fail closed；附件对象门、OCR 双分支均进入正式清册。note 清册 101 端点；远端最新重生后的 edit 清册 755 个门点 / 725 个端点 / 198 个文件；identity 棘轮 166→165、238→236，body 维不增。
- 域 checker 增加 generated / `.d.ts` 排除、Python package alias、并列 owner fail closed、`--shrink-only`；债务 baseline 897→724，只删除已解决项，不吸收其他债务。

### 可逆真实 UAT

- 目标：`【测试】公式同步集团有限公司_2025`，上市合并口径，2025 年，两家【测试】数据叶子。工具只接受项目名精确确认、测试标记、两数据叶子、未归档/未锁定项目，并使用 PG advisory lock。
- 普通映射 `五-5-6`：浏览器自动映射后重新汇总，根首行 `1年以内 = 300.00`、上年 `240.00`，来源显示 `2 个下级 + 差额`；硬刷新逐值读回。
- Top-N `五-8-18`：跨企业同名合并为 `NRG-nrg1029a-共同客户 = 1300.00`；两家集团内单位均排除；`beyond_count=4`、分母 10000、根 `approximate=true`、前五合计 4300.00、比例 43.00；硬刷新逐值读回。
- 两个 POST 均 200/persisted，独立 GET 两次规范化 hash 相同。浏览器 `consoleErrors=[]`、`failedRequests=[]`、`errorResponses=[]`。
- 备份覆盖 8 张表的 PK 集合、`row_to_json`、JSON-null 标记与规范化 SHA-256。最终 after 摘要：`consol_note_data=7:ba44bb8355`、`mapping_binding=2:58a64e9d22`、`mapping_rule=2:1bc4976eaf`、`disclosure_notes=4:b8c82d2613`；restore 后事务内、提交后及独立 `verify --expected before` 全部逐表一致。

### 最终回归

- 后端最终选集：267 passed；其中行数门拆分后的核心 6 文件回归 117 passed。前端 28 文件 619 passed；类型修复后重点 8 文件 211 passed。
- 全量 `vue-tsc` 使用同一 HEAD `8107371f0` 和 40GB 堆分别运行：基线 3084 条 / 1533 unique，候选 2983 条 / 1484 unique；规范化（文件、TS 码、信息）多重集 `added=0`、`resolved=101`，两边均无 OOM/FATAL。
- 暂存内容行数门、gitleaks（约 534KB）、`git diff --check`、两份鉴权清册 `--check` 均通过。为通过行数门按职责拆出 owner ledger、batch 编排与 K 新增文件账本，原大文件降至 1649 / 779 行，未抬白名单。
- 域边界候选与同 HEAD 基线均为 1301 条，逐 identity `added=0/resolved=0`；两树在当前 debt baseline 下都同报 577 条预存债务，本轮未冒领、未吸收。
- 最终候选 Playwright 从独立 Vite 3031 经容器反代以 `http://127.0.0.1:3030` 打开活动【测试】项目 E1，实际挂载上市披露组件并硬刷新；所有非 GET 请求在浏览器侧拦截，控制台、失败请求和 HTTP 错误均为 0，数据库无写入。

### 交付完成判据

- 任务 50 随最终提交标记完成：fetch、远端最新重放、提交树终验和 hooks 必须先成功，随后立即由 `push_version.py` 原子推送分支与版本标签并清理资源；任一步失败都不得对外宣告本 spec 完成。

### 远端最新重放终验（任务 50 提交前阶段）

- `git fetch --prune` 后目标分支从本轮开工基线前进 22 个提交至 `5d0a4b60a`。本轮 151 个文件与远端改动只有 `INDEX.md`、`memory.md` 两处重叠；在新锁定 detached worktree 三方重放，冲突只发生在 INDEX 首行，取远端完整内容后插入本 spec 条目，memory 自动合并且仍小于 300 行。
- “远端最新 + 本轮”重新通过后端 267 passed、前端 619 passed、行数门、gitleaks、`git diff --check`、note 清册 101。远端新增鉴权调用后 edit 清册先按预期报 3 个门点 + 1 个 direct comparison，重生成并复查通过：755 门点 / 725 端点 / 198 文件。
- 全量 `vue-tsc` 对远端最新同配置重跑：远端 3089 条 / 1531 unique，候选 2988 条 / 1482 unique；规范化多重集 `added=0 / resolved=101`，无 OOM/FATAL。
- 域边界用候选 checker/manifest 对远端与候选逐 identity 比较：两边均 1304，`added=0 / resolved=0`；相对 724 debt baseline 两边同有 580 条预存债。远端比开工多 3 条，但不是本轮引入，未写入 baseline。
- 任务 50 随最终提交标记完成；最终事实以该提交通过 hooks、`push_version.py` 原子推送成功且临时资源清理完成为准，任一步失败都不得宣告整个 spec 完成。

### 推送预演后二次远端前进

- 首次最终提交 `06eb2edc2` 仅存在于本地 detached worktree；`push_version.py --dry-run` 再 fetch 时发现远端新增 `43b189d49`（并占用 v1.0.42），因此没有推送、没有 force。
- 新远端提交与本轮重叠 INDEX、披露同步路由、公式推送引擎、披露同步服务 4 个文件；只读 merge-tree 证明仅 INDEX 有文本冲突。再次从 `43b189d49` 建锁定 detached 候选，三方合并保留远端 `NOTE_SECTION_SAVED` / stale 链与本轮 `_source` / owner / strict / 派生主表逻辑。
- 语义复核抓到接缝缺陷：owner 以空集合放弃旧来源表时仍会重建“其他应付款”主表，但 pushed-cell 保护原来只在 incoming 非空时运行。门改为 `clean_sub_table_data or derived_tables`，新增空 owner 反例；还原旧门后测试按预期红、恢复后绿。
- 合并接缝后端 238 passed，前端刷新/headless 接缝 38 passed；全量 vue-tsc 对最终远端重跑为 3088→2987，`added=0 / resolved=101`；域边界两树均 1304、identity 差集 0。最终提交必须重新创建，旧本地提交不得推送。

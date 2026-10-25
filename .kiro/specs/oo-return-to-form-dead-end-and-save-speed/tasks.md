# 在线编辑回表单死路与回写提速 — Tasks

- [x] 1. R1 前端死路与出口（证据 design §9.1）
  - [x] 1.1 伴生模块 `bridgeStateSets.ts`（迁出两份状态集合 + 新退出 / 不遮罩集合）与 `bridgeForcesaveFlow.ts`（送达跟踪、202 分流、终态文案迁入）；桥 re-export，净增 ≤ 0
  - [x] 1.2 状态机新事件与边、`canTransition`；桥 `switchToHtml` 送达等待与分流、`leaveWithoutSaving` 先判边、`exitOnlineEdit`、`lastForcesaveOutcome`
  - [x] 1.3 宿主按钮分流、无改动提示、遮罩集合、「退出在线编辑」与确认
  - [x] 1.4 判据：新增 + 改写旧死路判据；sync 目录 vitest 前后对比（17 例既有失败前后同一组）；单区域 vue-tsc（HEAD 对比 95 = 95，零新增）；磁盘变异 M1~M20 全打红；受影响 125 个测试目标前后对比 196 = 196 失败、零新增
- [x] 2. R1.6 `requestClose()` 实测（OnlyOffice 9.4），按结论接入或在 design §9 记录（实测两条前提成立 ⇒ 接入；证据 design §9.2，变异 N1~N22 全打红）
- [x] 3. R2 后端按 entry 准备注册：`entry_scope` + `_prepare_entry_only` + 源码事实单飞；`_apply_durable_incoming` 接入；`_registration` 端点逐个核对后接入；判据 + 变异 + 相关测试文件前后对比（证据 design §9.3：B1~B14 全打红；冷回调 48.9 s → 7.6 s、预热中 46.3 s → 9.7 s）
- [x] 4. R3 P8 物化计划复用 incoming 提取：`incoming_view_reuse.py` + adapter / 物化接线；逐字段等价、次数、不复用三类；变异（证据 design §9.4：判据 22 例，P8-1~P8-20 全打红；偏离 design §4 两处——按内容 sha256 认文件、认 `_GT_SYNC` 重注副本）
- [x] 5. R3 P9 已发布形态提取跨请求缓存：`published_extract_cache.py` + adapter 接线 + `clear_all_parse_caches`；等价、键完备、不改写缓存值；变异；内存实测（证据 design §9.5：判据 10 例，P9-1~P9-16 除等价变异 P9-11 外全打红；D2 单条约 6.4 MB，上限 16 条）
- [x] 6. R3 重放探针：同一条真实 application 前后耗时与摘要（外层事务回滚、文件根换临时副本，真实存储前后核对不变）（证据 design §9.6：和平药房 D2 cold 9.44 / 9.61 → 8.00 / 8.00 s、同一 base 8.93 / 8.80 → 6.47 / 6.56 s、下一次保存 9.51 / 9.01 → 6.57 / 7.09 s，摘要与产物逐项相同；相关测试文件前后对比无新增失败）
- [x] 7. R4 后台合并：状态机两态、`bridgeBackgroundMerge.ts`、宿主切换时机、`backgroundMergeRegistry.ts` + 横幅 + `GtWpRenderer` 只读 + 持久化拒写；判据 + 变异（证据 design §9.7：判据 41 例，变异 48 条全打红；受影响 155 个测试目标 198 = 198 失败、零新增）
- [x] 8. R5 `start-dev.bat` 热重载开关（证据 design §9.8：判据 2 例 + 既有守卫 37 例，S1~S4 全打红）
- [x] 9. 浏览器实测：和平药房 D2-2 未改动回表单与冻结 / 出错出口（只读）；【测试】项目有改动路径（送达等待、后台合并两段耗时、退出确认），测试数据走平台路径清理（证据 design §9.9：【测试】三轮有改动 1.44 / 2.23 / 2.35 s 回表单、3.49 / 5.02 / 4.98 s 可编辑；断网出错出口 77 ms 出现「退出在线编辑」、确认后 124 ms 回表单、改动不回写；和平药房不改动 167 ms 回表单、0 写入。冻结态未能在真实环境复现、出错出口在【测试】项目上做，见 §9.9 末；实测发现的未修问题见 §9.10；【测试】项目已经平台接口删除、进回收站）
- [x] 10. 收尾：相关测试文件 HEAD 对比、golden digest、行数门、INDEX.md、memory.md、提交（只提交本 spec 文件）（证据：后端 109 个相关测试文件前后失败与错误逐条相同，见 design §9.6 末；前端主树 sync 目录 + 渲染器 / 持久化 1281 例，失败 17 例 = 改前同一组；golden digest 242 个零回归（37 家、零跳过）；改动的 44 个代码文件行数门全过（白名单文件均在基线 1.05 倍内）；INDEX 本行与 memory D2 段已更新；临时 tsconfig、前端隔离副本、后端 worktree 已删，【测试】项目经平台接口删除（进回收站）；用私有索引只提交本 spec 文件与共享文件里本会话的改动块。要提交的那棵树在干净 worktree 复跑：前端 1281 例失败 17 例 = 改前同一组；后端本 spec 判据 + start-dev 守卫 + 「已提交代码只引用已提交模块」+ lazy import 守卫共 97 例，失败 4 例 = HEAD 既有的 2 处 lazy import 指向不存在模块（`ai_content` / `consol_note_template_push_service`，非本 spec 文件）+ 稀疏检出不含 `docs/` 与 `node_modules` 致 start-dev 守卫 2 例（主树全量检出 11 例全过））

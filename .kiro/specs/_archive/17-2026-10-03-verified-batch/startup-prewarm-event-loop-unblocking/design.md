# 启动预热不阻塞事件循环 — 设计

> 需求：#[[file:.kiro/specs/startup-prewarm-event-loop-unblocking/requirements.md]]

## 一、为什么不把整段预热搬进独立线程 + 独立事件循环

注册路径要读库：asyncpg 连接绑定创建它的事件循环，共享连接池跨循环复用会报 attached to a different loop；
`_REGISTRATION_BUILD_LOCK` 是 `asyncio.Lock`，跨循环争用同样报错。整段搬走需要第二套引擎与锁 —— 风险远大于收益。
故只在**两个实测边界**（F3）把同步 CPU 段移出循环，其余 await 链原样。

## 二、源码事实预热（Requirement 1）

```python
# entry_source_facts.py
def warm_source_fact_caches() -> tuple[str, ...]:
    """在调用线程里建好进程级 lru_cache；失败项只返回名字，不抛。"""

# wp_sync_router._attach_pilot_adapters（冷路径，锁内、重查之后）
await asyncio.to_thread(warm_source_fact_caches)
explicit = (...)
```

- 放锁内而不是只放启动预热：并发首请求若先拿到锁，会在循环上把 7s 首算再跑一遍（`lru_cache` 不合并在途计算）。
- 这些事实只依赖仓库源码，进程内不变；之后各 attach 的调用命中缓存，判据一字未改。
- 失败回落：`lru_cache` 不缓存异常 ⇒ 原调用点重算并抛原错误（如打包环境缺前端源码时的 `EntrySourceFactError`）。

## 三、整簿观测（Requirement 2）

`observe()` 里 `observed = await asyncio.to_thread(self._observe_workbook, ...)`。输入是不可变字节 + 冻结契约，函数不碰会话；
`shared_workbook_from_bytes` 读 ContextVar，`to_thread` 复制上下文，无作用域时退化为一次性解析（与现状相同）。

## 四、入边索引记忆化（Requirement 3）

键 = `("alias", str(_FRONTEND_SRC / spec[2:]))` 或 `("relative", str(importer.parent / spec))`。`_resolve_import` 对同一种类是
该拼接路径的纯函数（扫描期间文件系统不变），值存 `_relative(target)` 或 `None`。种类进键：别名路径不经 `resolve()`、相对路径
先 `resolve()`，存在符号链接时两者可能不同（现场 0 个链接，但判据不依赖这一点）。

## 五、127.0.0.1（Requirement 4）

三处默认值改 `127.0.0.1`；`.env.example` 附一行原因。守卫为离线文本 / AST 判据（`test_backend_client_loopback_defaults.py`）。

## 六、测试与变异

| 用例 | 覆盖 |
|------|------|
| `test_sync_registration_prewarm.py` 追加 | 冷注册在非循环线程预热源码事实、且早于各 attach；并发冷请求只预热一次；预热失败不打断注册；预热清单覆盖 `clear_source_fact_caches` 的全部零参缓存；`observe()` 在非循环线程调 `_observe_workbook` |
| `test_frontend_reference_index_memo.py` | 合成前端树：同名相对 import 在两个目录指向不同文件、别名 import、`index.ts` 解析、缺失目标；与参考实现逐字段相等 |
| `test_backend_client_loopback_defaults.py` | 三处默认值为 127.0.0.1 |

变异（一次性 `_lat_mutation_check.py`，P1–P10）：预热改回在循环上直接调用 / 删除预热 / 预热单项失败直接抛 / 预热清单漏一项 /
观测改回直接调用 / 记忆化键去掉 importer 目录 / 键不分种类 / 三处默认值各自回退。既有 `mutate_sync_registration_prewarm_guards.py`
的「拿锁后不重查缓存」锚点随冷路径插入同步更新并全量重跑。

## 六补、实施中发现：结构指纹缓存无锁（已知缺陷，**本 spec 不修**，钉住）

`excel_structure_fingerprint._FINGERPRINT_CACHE`（`OrderedDict`）无锁。确定性复现（读线程命中后、`move_to_end` 前，
另一线程写入并淘汰同一项）在 HEAD 上**必抛 `KeyError`**。这是既有缺陷：materialize 的 CPU 段在工作线程、冷注册观测
原在事件循环线程，两者本来就并发；Requirement 2 只改了观测所在的线程，并发度不变。触发还需缓存满（>16 份不同字节）。

🔴 **一度加锁后已回退**：该模块被 `backend/data/onlyoffice_excel_instrumentation_gate.json` 的 `tier_a_runtime`
按 sha256 **运行时钉死**（`ExcelIdentityCarrierGate._assert_tier_a_fresh` fail closed，报「Task 5 探针裁决已 stale」）。
加锁改了一个字节 ⇒ dev 后端 11:06–12:07 每次冷注册都失败、首请求退回惰性注册（`app.jsonl` 实录 20 次，
`startup_prewarm` 汇总行如实报成「失败」）。正确流程是按 gate 的 `stale_action` 重跑真实 OO 9.4 探针并刷新 digest，
超出本 spec。现状：

- 模块字节还原 HEAD，gate 基线核对一致；`mutate_fingerprint_memoization_guards.py` 同样还原 HEAD；
- 复现用例 `test_eviction_by_another_thread_cannot_split_lookup_and_touch` 以 `xfail(strict=True, raises=KeyError)` 钉住：
  修掉后 XPASS 即红，逼迫删除标记；
- **教训**：改任何模块前先查它是否被 `backend/data/*.json` 按 digest 钉住（本轮改过的 15 个后端文件已逐个核查，
  另有 `workpaper_sync_program_milestones.json` 钉了 `wp_sync_router.py` / `published_identity_observer.py`，但那是生成器
  `--check` 的输入快照，不在运行时强制；且 observer 的登记值早已与工作树不符 —— 是他会话的既有状态）。

## 七、范围外（显式登记）

- 后端控制台窗口进入 QuickEdit「选择」模式会阻塞 stdout 写入，整个 worker 卡死（本次现场即此：py-spy 显示主线程停在
  `warnings._showwarnmsg_impl`，标题栏带「选择」；向窗口投递 Esc 后恢复）—— 环境问题，不改代码，写进总结提醒。
- 测试 / 压测脚本里的 `localhost:9980`（非运行时路径）不在本次范围。

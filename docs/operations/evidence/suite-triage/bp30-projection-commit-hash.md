# BP-30 反向锁判据假红：`test_projection_commit_calls_the_new_hash`

单条失败定点排障。结论：**判据的探测方式过期（verdict b）**，生产接线完好。
判据已改成调用闭包判定，并做了两组变异检验证明它仍然会在接线被拆掉时判红。

- 失败节点：`backend/tests/workpaper_sync/test_projection_structure_hash_semantics.py::TestBp30IsActuallyWired::test_projection_commit_calls_the_new_hash`
- 复现命令（cwd=`d:\GT_plan\backend`）：
  `..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_projection_structure_hash_semantics.py -q --tb=short -rf -p no:randomly`

## 一、原始失败（逐字）

```
________ TestBp30IsActuallyWired.test_projection_commit_calls_the_new_hash ________
tests\workpaper_sync\test_projection_structure_hash_semantics.py:306: in test_projection_commit_calls_the_new_hash
    assert "_projection_structure_hash" in stage, (
E   AssertionError: `_stage_and_verify` 没有调用 `_projection_structure_hash` —— 新方法成了死代码（假绿第①源）
E   assert '_projection_structure_hash' in 'async def _stage_and_verify(self, *, plan: ContentCommitPlan, mutation: BusinessMutation, projection: Projection | No...ure_hash, identity_inventory_sha256=materialized.identity_inventory_sha256, extracted_key_count=len(extracted.values))'
============================= short test summary info =============================
FAILED tests/workpaper_sync/test_projection_structure_hash_semantics.py::TestBp30IsActuallyWired::test_projection_commit_calls_the_new_hash
1 failed, 13 passed, 1 warning in 1.66s
```

同一条测试里的第一句断言（`_projection_structure_hash` 体内必须出现
`compute_structure_hash_from_artifact`）**通过**了 —— 即「新公式」本身在位，
红的只是「宿主有没有调它」这半条。

## 二、根因判定：(b) 判据探测方式过期

生产接线没断，只是**下沉了一层**，而旧断言是在**同一个函数体的文本**里找名字：

```
_stage_and_verify                                  (事件循环侧)
  └─ asyncio.to_thread(self._stage_cpu_segment, …) (纯 CPU 段卸载)
       └─ _stage_cpu_segment_scoped                (workbook 读作用域内)
            └─ structure_hash = self._projection_structure_hash(…)   ← L1715
                 └─ compute_structure_hash_from_artifact(…)          ← L1734
```

两步合法搬迁把名字挪出了宿主函数体（`content_mutation.py` L1584-1597 的整段注释
记录了这件事，对应 commit `34eb8fc59`）：

1. spec `workpaper-sync-materialize-large-table-performance` **Task 5** 明文把
   `_projection_structure_hash` 划进 CPU 段，于是 materialize→extract→unmanaged→
   structure_hash 一起搬进 `_stage_cpu_segment` 由 `asyncio.to_thread` 承载；
2. 2026-09-22 又删掉了**事件循环侧那遍重复计算**（线程内算完返回却没人用，事件循环上
   对同一份 output 再整簿解析一次，单次实测约 1.4s）。删掉重复的那一遍之后，
   `_stage_and_verify` 体内连 `_projection_structure_hash` 这个字符串都不剩了。

判「不是生产回归」的旁证 —— 兄弟判据早已按新形态改过，且**现在全绿**：

| 文件 | 它怎么说 |
| --- | --- |
| `test_single_pass_verify_not_relaxed.py` | `self._projection_structure_hash(` 列进 `PRODUCTION_GATE_MARKERS`，逐条在 `_stage_cpu_segment_scoped` 里找并校验顺序 |
| `test_single_pass_parse_reuse.py` | 同上，且对账 `_stage_cpu_segment` / `_stage_cpu_segment_scoped` 两段 |
| `test_task26_oo_to_html.py` | 注释写明「CPU 段已被搬进 `_stage_cpu_segment`…只在 `_stage_and_verify` 里 index 三个串会直接 ValueError（判据失锚而非判红）」，于是它横跨两个方法扫 |
| `test_g1_publish_structure_hash.py` | 直接调 `service._projection_structure_hash(...)`，实测其返回值 == `compute_structure_hash_from_artifact(...)` 且 != 旧字节摘要 |

也就是说：`_projection_structure_hash` 既不是死代码，也没被改回旧口径 ——
本条是**仓库反复警告的「grep 式守卫」在合法重构上假红**，正是它自己 docstring
批评的那种形态。

## 三、改动（只动测试的探测方式，不碰生产）

`git diff --stat`：`test_projection_structure_hash_semantics.py | 97 insertions(+), 4 deletions(-)`
生产文件 `content_mutation.py` 变异检验后已还原，`git status --porcelain` 空输出（与 HEAD 逐字节一致）。

新增三个模块级 AST 助手 + 一个值流助手，替掉「同函数体文本包含」这一句：

- `_class_methods(source, method)`：取**定义了该方法的那个类**的方法表（跨类同名不串）；
- `_self_refs(node)`：体内全部 `self.<name>` —— 直接调用**与**把绑定方法当实参递出去
  （`asyncio.to_thread(self.f, …)`）都算。只认前者就会把「卸到工作线程」误判成「没接线」；
- `_reachable_from(source, entry)`：沿 `self.*` 求**传递闭包**，只收真实方法定义
  （`self._artifacts` / `self._session` 这类属性不是调用边）；
- `_value_leaves_the_method(node, callee)`：`self.<callee>(...)` 的返回值必须被**绑名**
  且那个名字出现在某个 `return` 里 —— 挡住「调了但算完即丢」。

断言由一句变三句，**净收紧**：既容忍调用深度变化，又新增了「返回值必须流出去」这道
旧判据根本没有的约束。原来的第一句（新公式在位）一字未动。

## 四、变异检验（两组，均按要求判红后还原）

变异点 `_stage_cpu_segment_scoped`（`content_mutation.py` L1715）：

| # | 变异 | 结果 | 判红的断言 |
| --- | --- | --- | --- |
| M1 | 把调用整句换成旧口径字节摘要 `structure_hash = str(materialized.structure_hash)` | **RED** ✅ | 闭包可达性 |
| M2 | 保留调用但丢弃返回值，另取 `structure_hash = str(materialized.structure_hash)` | **RED** ✅ | 返回值流出 |

M1 报文（附带闭包实测清单，证明遍历真的穿过了两层 CPU 段方法）：

```
AssertionError: `_stage_and_verify` 沿 `self.*` 调用链到不了 `_projection_structure_hash` ——
新方法成了死代码（假绿第①源）。实测可达闭包: ['_assert_roundtrip_equivalent',
'_next_generation_probe', '_stage_authoritative', '_stage_cpu_segment', '_stage_cpu_segment_scoped']
```

M2 报文：

```
AssertionError: ['_stage_cpu_segment_scoped'] 里没有一处把 `_projection_structure_hash(...)`
的返回值绑名并 return —— 算完即丢等于死代码，宿主 fence/落库拿到的仍是别的量
```

M2 值得单记：它是**旧判据抓不到**的形态（旧判据只要宿主体内出现过那个字符串就绿）。

## 五、前后测试计数

| 文件 | 修复前 | 修复后 |
| --- | --- | --- |
| `test_projection_structure_hash_semantics.py` | 1 failed, 13 passed | **14 passed** |
| `test_g1_publish_structure_hash.py` | 8 passed | 8 passed |
| `test_projection_digest_is_representation_stable.py` | 26 passed | 26 passed |

三个文件均单独运行（`-p no:randomly`）。按约束**未**跑整个 `tests/workpaper_sync`（约 34 分钟且会截断）。
兄弟判据零回归，同文件内 13 条同胞全部仍绿。

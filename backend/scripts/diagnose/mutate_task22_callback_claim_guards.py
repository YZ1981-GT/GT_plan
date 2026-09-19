# -*- coding: utf-8 -*-
"""Task 22 变异检验：callback route claim / 下载安全 / delivery 归属 / correlation / recovery。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 22
Requirements: 4.3, 4.9, 4.10, 5.1~5.8, 5.11, 5.12, 10.2, 10.3, 10.6~10.9
Properties: P16 / P17 / P18 / P19 / P44 / P45 / P63 / P64

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/mutate_task22_callback_claim_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task22_callback_claim_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task22_callback_claim_guards.py --run all --out report.json

═══ 本轮变异的四类落点，以及为什么必须四类都有 ═══

1. **服务层判据**（`callback_route` / `callback_download` / `callback_delivery`）——
   每条拒绝分支各一条变异。这类最直观，但**只有这类是不够的**：它证明不了「归属真值表
   声明的那条 DB 约束真的在工作」。
2. **V151 约束**（6 条 `ck_wpcd_*`）—— 每条 CHECK 单独削成恒真，看对应的 forbidden 行
   是否变成 accepted。这是「表里的 `db_constraint` 归因不是抄的」的唯一判据形态：
   削掉 X 之后**只有**声明 X 的那一行翻，别的行不动。
3. **契约数值**（`onlyoffice_callback_state_contract.json`）—— 下载上限与容量预算的
   锁死是两份配置的一致性，改任一侧都必须打红。
4. **已修缺陷的回插**（M05 / M21 / M24 / M33 / M34）—— 本轮修掉的每个真实缺陷都配一条
   把它插回去的变异。不配的话，「这个缺陷已经被守卫锁住了」只是一句自述：
   下一个人重新引入同样的写法时没有任何判据会红。

═══ 无效变异的三个已知形态（本脚本刻意避开）═══

* **改注释/docstring**：不落在判据作用域内，判定必 GREEN 而与守卫无关；
* **改 `__all__` 之类的纯声明**：无消费方，改了什么都不发生；
* **同时违反两条判据**：打红了但分不清是哪条在工作（WRONG-TEST 的温床）。
  归属真值表那 6 条尤其要小心 —— 削掉一条 CHECK 时若另一条也能挡住同一行，
  判定就变成「另一条约束偶然生效」。这正是真值表把每个 forbidden 行构造成
  「只违反自己那一条」的原因，6 条变异因此可以逐条归因。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

ROUTE = "backend/app/services/workpaper_sync/callback_route.py"
DOWNLOAD = "backend/app/services/workpaper_sync/callback_download.py"
DELIVERY = "backend/app/services/workpaper_sync/callback_delivery.py"
CONTRACT_PY = "backend/app/services/workpaper_sync/oo_contract.py"
CONTRACT_JSON = "backend/data/onlyoffice_callback_state_contract.json"
V151 = "backend/migrations/V151__workpaper_sync_content_application_bundle_scope.sql"

PG = "test_task22_callback_claim_pg.py"

MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # 一、route claim（P16 / Requirement 5.1、5.2）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=ROUTE, kind="replace",
        anchor='    if "cbv" not in raw:',
        new="    if False:",
        want="test_missing_claim_version_rejected_before_download",
        why="缺 cbv 直通 ⇒ 生产实况的 claim_version=None 绕过重新出现（P16 的核心）；"
            "不能改成 raw.get('cbv') 因为下一行会 KeyError，那是崩而不是绕过",
    ),
    Mutation(
        id="M02", side="be", path=ROUTE, kind="replace",
        anchor="    if isinstance(value, bool) or not isinstance(value, int):",
        # 同一行文本在 `_require_int` 里也出现，必须消歧。用**相对**定位而不是绝对行号：
        # 首轮写 `line=295`，本轮给 callback_route 补了两个异常类后行号整体下移 ⇒
        # 该条判 ANCHOR-MISS（实测）。`value = raw["cbv"]` 是 `_require_claim_version`
        # 里唯一且语义稳定的一行，它下一行就是被测判据。
        scope='    value = raw["cbv"]',
        offset=1,
        new="    if False:",
        want="test_claim_version_refuses_coercion",
        why='"1"/1.0/True 被当成合法版本 ⇒ 伪造版本猜成已知版本。'
            "相对定位消歧：同一行文本在 _require_int 里也出现",
    ),
    Mutation(
        id="M03", side="be", path=ROUTE, kind="replace",
        anchor="    if value != schema.claim_schema_version:",
        new="    if False:",
        want="test_unknown_claim_version_rejected",
        why="未知版本放行 ⇒ 旧版本 claim 可覆盖新协议内容；与 M01/M02 分别对应三段独立判据",
    ),
    Mutation(
        id="M04", side="be", path=ROUTE, kind="replace",
        anchor="    if not secret:",
        new="    if False:",
        want="test_missing_secret_fails_closed",
        why="无密钥时不再 fail closed ⇒ 复刻 legacy 的 `if not JWT_SECRET: return True`",
    ),
    Mutation(
        id="M05", side="be", path=ROUTE, kind="replace",
        anchor='    if head.lower() == "bearer":',
        new='    if raw.lower().startswith("bearer "):\n        raw = raw[7:].strip()\n    if False:',
        want="test_missing_authorization_header_rejected",
        why="把本轮修掉的真实缺陷插回去：先 strip 再判 `bearer ` ⇒ `\"Bearer   \"` 被 strip 成"
            " `\"Bearer\"` 不再匹配，于是「只有 scheme」那条 raise 不可达，"
            "拒绝理由从『缺 token』漂成『签名坏了』",
    ),
    Mutation(
        id="M06", side="be", path=ROUTE, kind="replace",
        anchor="    if mismatched:",
        new="    if mismatched and set(mismatched) - {'generation', 'doc_key', 'route_credential_id'}:",
        want="test_each_url_bound_param_is_checked",
        why="只保留 room_id 一项绑定 ⇒ generation 旋转后旧 URL 仍合法，AC 2.8 的 supersede 形同虚设。"
            "刻意留一项而不是整段删：整段删会同时打红 room 那一项，无法证明『逐项』",
    ),
    Mutation(
        id="M07", side="be", path=ROUTE, kind="replace",
        anchor="    if not isinstance(payload_doc_key, str) or payload_doc_key.strip() != claim.doc_key:",
        new="    if str(payload_doc_key).strip() != claim.doc_key and payload_doc_key is not None:",
        want="test_payload_key_must_equal_claim_doc_key",
        why="`None` 被 str() 变成 'None' 后又被显式放过 ⇒ 「根本没带 key」变成看起来正常的字符串",
    ),
    Mutation(
        id="M08", side="be", path=ROUTE, kind="replace",
        anchor="    if not doc_key_matches(doc_key=claim.doc_key, wp_id=room.wp_id, entry_id=room.entry_id):",
        new="    if False:",
        want="test_doc_key_must_derive_from_room_identity",
        why="跨底稿/跨入口的 doc_key 可进入本 room ⇒ 别的底稿的 artifact 被应用到这一份",
    ),
    Mutation(
        id="M09", side="be", path=ROUTE, kind="replace",
        anchor="    if not room.accepts_callback:",
        new="    if False:",
        want="test_superseded_room_and_stale_fence_rejected",
        why="superseded/closed room 仍接受 callback ⇒ 旧代际 artifact 覆盖新内容",
    ),
    Mutation(
        id="M10", side="be", path=ROUTE, kind="replace",
        anchor="    if claim.expires_at <= reference:",
        new="    if False:",
        want="test_explicit_clock_check_rejects_token_that_jose_accepts",
        why="删掉平台的显式时钟判据。首轮 want 写 test_expired_token_rejected 判 WRONG-TEST："
            "那条用的 token `exp` 早已过期，jose 会先抛同类型异常把显式判据整条遮蔽。"
            "改为断言「jose 放行、只有显式判据能拦」的隔离场景，并把两者拆成不同异常类型",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 二、下载安全（P17 / Requirement 5.3、5.6、10.7、10.8）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M11", side="be", path=DOWNLOAD, kind="replace",
        anchor="    if not entries:",
        new="    if False:\n        pass\n    if not entries:\n        entries.append(AllowlistEntry(scheme='http', host='0.0.0.0', port=80, allow_private_ip=True))\n    if False:",
        want="test_empty_allowlist_refuses_instead_of_falling_back",
        why="空 allowlist 回退成放行 ⇒ Task 4 实测最严重 gap（ONLYOFFICE_URL 为空时 host 由 payload 决定）复现",
    ),
    Mutation(
        id="M12", side="be", path=DOWNLOAD, kind="replace",
        anchor="    if entry is None:",
        new="    entry = entry or (policy.allowlist[0] if policy.allowlist else None)\n    if entry is None:",
        want="test_host_not_allowlisted_rejected",
        why="host 不在 allowlist 时退回第一条 ⇒ 等价于生产的『按 netloc 重写后放行』，"
            "而 path/query 仍来自 payload",
    ),
    Mutation(
        id="M13", side="be", path=DOWNLOAD, kind="replace",
        anchor="    if not any(path.startswith(prefix) for prefix in policy.path_prefixes):",
        new="    if False:",
        want="test_path_gate_is_independent_of_host_gate",
        why="path 前缀门失效 ⇒ 同一 host 上的任意路径（含 /admin）可被下载。"
            "它与 host 门分属两个异常类型正是为了让这条变异不被 host 门遮蔽",
    ),
    Mutation(
        id="M14", side="be", path=DOWNLOAD, kind="replace",
        anchor="    if normalized in METADATA_ADDRESSES:",
        new="    if False:",
        want="test_metadata_addresses_rejected_even_when_private_allowed",
        why="云元数据端点在『放行私网』的条目下变得可达 ⇒ 交出实例角色凭证。"
            "它必须独立于私网门：私网门在 localhost 条目下是放行的",
    ),
    Mutation(
        id="M15", side="be", path=DOWNLOAD, kind="replace",
        anchor="    if (addr.is_loopback or addr.is_private) and not entry.allow_private_ip:",
        new="    if False:",
        want="test_dns_rebinding_blocked_by_post_resolve_recheck",
        why="解析后逐 IP 复核失效 ⇒ Task 4 实测可行的 DNS rebinding 复现",
    ),
    Mutation(
        id="M16", side="be", path=DOWNLOAD, kind="replace",
        anchor="    pinned = addresses[0]",
        new="    pinned = host",
        want="test_resolved_ip_is_pinned_for_connection",
        wants=("test_download_was_pinned_carried_no_credential_and_refused_redirects",),
        why="不固定已验证 IP ⇒ 连接阶段第二次解析，rebinding 又有落脚点。"
            "同时打红 PG 端到端那条（真实下载 URL 的 host 不再是 IP 字面量）",
    ),
    Mutation(
        id="M17", side="be", path=DOWNLOAD, kind="replace",
        anchor="        if 300 <= status < 400:",
        new="        if False:",
        want="test_redirect_refused_and_body_not_consumed",
        why="3xx 不再拒 ⇒ 重定向 body 被当文件写盘（Task 4 实测：靠 httpx 版本行为隐式挡住，不可依赖）",
    ),
    Mutation(
        id="M18", side="be", path=DOWNLOAD, kind="replace",
        anchor="                if m.bytes_read > policy.size_cap_bytes:",
        new="                if False:",
        want="test_size_cap_aborts_mid_stream",
        why="流式上限失效 ⇒ 回到 `resp.content` 整包入内存的无界形态",
    ),
    Mutation(
        id="M19", side="be", path=DOWNLOAD, kind="replace",
        anchor="    if policy.streaming_size_cap_bytes != lim.max_compressed_bytes:",
        new="    if False:",
        want="test_contract_and_capacity_budget_locked_together",
        why="两份配置不再锁死 ⇒ 下载门与解压门各按一个上限工作，超限错误码指向 OOXML 而真因是下载无界",
    ),
    Mutation(
        id="M20", side="be", path=CONTRACT_JSON, kind="replace",
        anchor='      "streaming_size_cap_bytes": 52428800,',
        new='      "streaming_size_cap_bytes": 209715200,',
        want="test_contract_and_capacity_budget_locked_together",
        wants=("test_download_cap_equals_the_capacity_budget",),
        why="把契约侧数值改回漂移前的 200 MiB ⇒ 锁死判据必须从**契约侧**也能打红。"
            "只有 M19（生产侧）时，契约被改回去不会有任何判据发现",
    ),
    Mutation(
        id="M21", side="be", path=DOWNLOAD, kind="replace",
        anchor="        or (addr.is_reserved and not addr.is_loopback)",
        new="        or addr.is_reserved",
        want=f"{PG}::test_no_phase_crashed_during_collection",
        wants=(
            "test_request_first_correlation_produces_one_primary_and_one_application",
        ),
        why="把本轮修掉的真实缺陷插回去：`ipaddress` 把 `::/8` 整段标成 reserved，"
            "于是 IPv6 环回 `::1` 被无条件拒，而 localhost 首个解析结果就是它 ⇒ "
            "平台真实部署一次 callback 都下载不下来。只有真库端到端能打红它",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 三、payload / delivery 去重（Requirement 4.9、5.4 / Task 4 §7）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M22", side="be", path=CONTRACT_PY, kind="replace",
        anchor="    if isinstance(raw_status, bool) or not isinstance(raw_status, int):",
        new="    try:\n        return int(raw_status)  # type: ignore[arg-type]\n    except Exception:\n        return None\n    if False:",
        want="test_status_coercion_refused",
        why='`"6"` 被强转成 6 ⇒ 契约 unknown_status_policy=fail_visible 被绕过，'
            "未知/伪造 status 被猜成最近似 status",
    ),
    Mutation(
        id="M23", side="be", path=DELIVERY, kind="replace",
        anchor="_DISCRIMINATOR_EXCLUDED_FIELDS: Final[frozenset[str]] = frozenset({\"token\"})",
        new="_DISCRIMINATOR_EXCLUDED_FIELDS: Final[frozenset[str]] = frozenset()",
        want="test_network_retry_of_same_delivery_dedupes",
        wants=(
            "test_delivery_discriminator_excludes_credentials",
            "test_network_retry_folds_but_distinct_deliveries_do_not",
        ),
        why="body token 进入 discriminator ⇒ OO 重签后同一投递被算成新 delivery（白丢去重），"
            "且凭证进入落库 digest（Requirement 10.7）",
    ),
    Mutation(
        id="M24", side="be", path=DELIVERY, kind="replace",
        anchor="                payload.canonical_digest(),",
        # 相对定位而不是绝对行号：`line=411` 在本轮补 docstring 后立刻失效并报
        # ANCHOR-MISS（实测）。scope 行是 discriminator 的版本前缀，唯一且稳定。
        scope='                "callback-delivery-discriminator:v1",',
        offset=3,
        new='                "",',
        want="test_discriminator_separates_same_url_with_different_body",
        why="discriminator 丢掉 payload digest ⇒ 『url 复用但 body 其余字段变化』的两次投递折叠成一行，"
            "少一行 delivery 就是少一份证据。首轮 want 写的是 test_distinct_deliveries_get_distinct_keys"
            "（改的是 url）⇒ url 那一项照样分开两者，判 GREEN；故补了只改 body 的隔离场景。"
            "line=411 消歧：1111 行是 payload_sha256 列",
    ),
    Mutation(
        id="M25", side="be", path=DELIVERY, kind="replace",
        anchor="        callback_status=payload.status,",
        scope="        discriminator=compute_delivery_discriminator(payload),",
        offset=-1,
        new="        callback_status=0,",
        want="test_build_delivery_key_wires_the_payload_status_through",
        why="外层 status 成分被削成常量。它在**值**层面不可观测（`canonical_digest` 摘整个 body，"
            "status 就在里面），故判据只能是接线等值 —— 首轮用「status 6 vs 2 的 key 不同」"
            "判 GREEN 正是因为 digest 那一项已经把两者分开了。line=424 消歧：1109 行是"
            " record_delivery 的列",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 四、归属真值表与 quarantine（P18 / P17 / Requirement 5.4、5.6）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M26", side="be", path=DELIVERY, kind="replace",
        anchor="    if op in QUARANTINE_ALLOWED_OPERATIONS:",
        new="    if op not in ('release',):",
        want="test_every_forbidden_quarantine_operation_rejected",
        wants=("test_quarantine_allowed_operations_are_exactly_three",),
        why="只挡 release ⇒ application/extract/merge/retry/rematerialize 全部放行。"
            "刻意留一项：整段放行会让『允许集恰好三项』那条也红，混在一起无法归因",
    ),
    Mutation(
        id="M27", side="be", path=DELIVERY, kind="replace",
        anchor="    if sealed.state is ArtifactState.quarantined:",
        new="    if False:",
        want="test_quarantined_and_staged_incoming_fail_with_distinct_types",
        wants=(
            "test_quarantined_cannot_reach_an_application_at_any_of_the_three_layers",
        ),
        why="内存第一层失效 ⇒ quarantined 的 sealing 对象可直传 engine（绕过 DB 那两层）",
    ),
    Mutation(
        id="M28", side="be", path=DELIVERY, kind="replace",
        anchor="        if not self.has(CallbackStage.sealed_durable):",
        new="        if False:",
        want="test_correlation_requires_recorded_durable_fact",
        why="轨迹前置断言失效 ⇒ application key 可以在 sealing 之前算（Requirement 4.3 明禁）",
    ),
    Mutation(
        id="M29", side="be", path=DELIVERY, kind="replace",
        anchor="    if request_id is not None:",
        new="    if False:",
        want="test_userdata_present_takes_request_first",
        why="有 userdata 也不走 request-first ⇒ 退化成按 incoming 猜 application，"
            "绕过不同 frozen base/bundle/fence（Requirement 4.3 的核心禁令）",
    ),
    Mutation(
        id="M30", side="be", path=DELIVERY, kind="replace",
        anchor="        if payload.contributors or payload.users:",
        new="        if True:",
        want="test_contributor_attribution_refuses_when_no_signal_at_all",
        why="零 contributor 信号也放行 ⇒ 归属无法判定却产生 content application"
            "（Requirement 10.3 / P44 要求隔离并旋转 generation）",
    ),
    Mutation(
        id="M31", side="be", path=DELIVERY, kind="replace",
        anchor="            operation_id=None,",
        new="            operation_id=shell.id if shell is not None else None,",
        want=f"{PG}::test_no_phase_crashed_during_collection",
        wants=("test_request_first_correlation_produces_one_primary_and_one_application",),
        why="把本轮修掉的真实缺陷插回去：pre-durable delivery 带 operation 指针，"
            "correlation 把同一 shell 绑成 primary 后，COMMIT 时 deferred "
            "`trg_wpcd_operation_link` 必然回滚整笔 ⇒ 成功路径永远失败。只有真库能打红",
    ),
    Mutation(
        id="M32", side="be", path=DELIVERY, kind="replace",
        anchor='                    "SELECT project_id FROM working_paper WHERE id = CAST(:wp AS uuid)"',
        new='                    "SELECT project_id FROM working_paper WHERE id = :wp"',
        want=f"{PG}::test_no_phase_crashed_during_collection",
        why="把本轮修掉的真实缺陷插回去：`sa.text` 无类型信息 ⇒ asyncpg 收到 VARCHAR 比 uuid，"
            "`operator does not exist` ⇒ 整条 handle_callback 在 PG 上跑不通。离线守卫看不见",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # 五、V151 约束逐条削（真值表 db_constraint 归因的唯一判据形态）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M33", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpcd_no_double_owner CHECK (",
        new="    CONSTRAINT ck_wpcd_no_double_owner CHECK (true OR",
        want="test_ownership_T09_double_owner_is_rejected_by_ck_wpcd_no_double_owner",
        wants=("test_the_three_mandated_ownership_semantics_hold_in_the_database",),
        why="削成恒真后 T09（任何阶段双 owner）必须变成 accepted。"
            "T09 刻意取 pre-durable，故 XOR 那条短路 ⇒ 只有本约束能挡它，归因可证",
    ),
    Mutation(
        id="M34", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpcd_durable_exactly_one_owner CHECK (",
        new="    CONSTRAINT ck_wpcd_durable_exactly_one_owner CHECK (true OR",
        want="test_ownership_T10_durable_zero_owner_rejected_by_ck_wpcd_durable_exactly_one_owner",
        wants=("test_the_three_mandated_ownership_semantics_hold_in_the_database",),
        why="削成恒真后 T10（durable 却零 owner = 无所有者死路）必须变成 accepted",
    ),
    Mutation(
        id="M35", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpcd_durable_state_requires_fact CHECK (",
        new="    CONSTRAINT ck_wpcd_durable_state_requires_fact CHECK (true OR",
        want="test_ownership_T11_durable_state_without_fact_rejected_by_ck_wpcd_durable_state_requires_fact",
        why="削成恒真后 T11（state=durable 但 durable_at 空 = 把泛化 terminal 当 durable）必须 accepted",
    ),
    Mutation(
        id="M36", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpcd_unmatched_zero_entities CHECK (",
        new="    CONSTRAINT ck_wpcd_unmatched_zero_entities CHECK (true OR",
        want="test_ownership_T12_unmatched_with_request_rejected_by_ck_wpcd_unmatched_zero_entities",
        why="削成恒真后 T12（unmatched 却留着 request）必须 accepted。"
            "T12 的 correlation_result 取 NULL 以短路 ambiguous 那条，故只有本约束能挡它",
    ),
    Mutation(
        id="M37", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpcd_ambiguous_zero_entities CHECK (",
        new="    CONSTRAINT ck_wpcd_ambiguous_zero_entities CHECK (true OR",
        want="test_ownership_T13_ambiguous_with_entities_rejected_by_ck_wpcd_ambiguous_zero_entities",
        why="削成恒真后 T13（correlation_result=ambiguous 却带 application/request）必须 accepted",
    ),
    Mutation(
        id="M38", side="be", path=V151, kind="replace",
        anchor="    CONSTRAINT ck_wpcd_durable_requires_incoming CHECK (",
        new="    CONSTRAINT ck_wpcd_durable_requires_incoming CHECK (true OR",
        want="test_ownership_T14_durable_without_incoming_rejected_by_ck_wpcd_durable_requires_incoming",
        why="削成恒真后 T14（durable 却没绑 incoming = pointer 指向缺失字节）必须 accepted",
    ),
]

GUARD_FILES = {
    "test_task22_callback_claim.py": "Task 22 离线守卫（claim/下载/真值表/归组/轨迹）",
    "test_task22_callback_claim_pg.py": "Task 22 真实 PostgreSQL 行为守卫（归属归因/去重/correlation/recovery）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 22 callback claim / download / delivery 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task22_callback_claim.py",
                "backend/tests/workpaper_sync/test_task22_callback_claim_pg.py",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:cacheprovider",
            ],
            baseline_backend_passed=140,
        )
    )

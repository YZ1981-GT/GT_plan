"""E4：分布式负载机 stage_stats 逐桶合并。

判据（每条都要有反向对照，否则「合并」很容易写成「取第一份」还全绿）：

1. 桶计数相加 —— 两份各 100 请求合并后是 200，不是 100；
2. 分位从**相加后的桶**复算 —— 只取一份时 p95 会明显偏低；
3. 端点按 (type, name) 对齐合并，不同 worker 出现同名端点也累加；
4. ``user_count_min`` 取最小、``user_count_max`` 取最大（不是求和）；
5. ``covered_seconds`` 取最小（有 worker 中途掉线时稳态只覆盖到最短那份）；
6. 空输入 / 阶段数不一致 / schema 不符 / 用户数不一致 一律抛错，绝不返回全 0 payload；
7. worker 文件损坏即失败，不跳过（跳过 = 少算样本 = 判定虚好）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.load.load_stage_stats import (
    SCHEMA_VERSION,
    WORKER_STATS_GLOB,
    load_worker_stage_stats,
    merge_stage_payloads,
    summarize_stage_payload,
)


def _payload(*, requests: int, p95_ms: int, users: int = 6000,
             covered: float = 1800.0, endpoint_requests: int | None = None) -> dict:
    """造一份单阶段 payload：所有请求都落在同一个桶上，便于精确断言。"""
    endpoint_requests = requests if endpoint_requests is None else endpoint_requests
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "test",
        "run_seconds": covered + 30.0,
        "stages": [
            {
                "users": users,
                "spawn_rate": 100.0,
                "duration": 1800,
                "begin_s": 0.0,
                "steady_start_s": 5.0,
                "end_s": 1805.0,
                "required_seconds": 1800.0,
                "covered_seconds": covered,
                "user_count_min": users,
                "user_count_max": users,
                "aggregate": {
                    "requests": requests,
                    "failures": 0,
                    "histogram": {str(p95_ms): requests},
                },
                "endpoints": [
                    {
                        "name": "/api/trial-balance",
                        "type": "GET",
                        "requests": endpoint_requests,
                        "failures": 0,
                        "histogram": {str(p95_ms): endpoint_requests},
                    }
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# 判据 1 + 2：桶相加、分位从相加后的桶复算
# ---------------------------------------------------------------------------


def test_merge_sums_histogram_buckets_across_workers():
    merged = merge_stage_payloads([_payload(requests=100, p95_ms=100),
                                   _payload(requests=100, p95_ms=100)])
    stage = merged["stages"][0]
    assert stage["aggregate"]["requests"] == 200
    assert stage["aggregate"]["histogram"] == {"100": 200}


def test_merge_percentiles_come_from_summed_buckets_not_single_worker():
    """一个快 worker + 一个慢 worker：合并后 p95 必须落在慢桶上。

    如果实现只是「取第一份」，p95 会是 100ms —— 这条就是那种假绿的对照。
    """
    fast = _payload(requests=100, p95_ms=100)
    slow = _payload(requests=100, p95_ms=3000)
    summary = summarize_stage_payload(merge_stage_payloads([fast, slow]))
    assert summary[0]["requests"] == 200
    # 一半请求在 100ms、一半在 3000ms ⇒ nearest-rank p95 落在 3000ms 桶
    assert summary[0]["p95"] == 3000.0
    assert summary[0]["p50"] == 100.0

    # 反向对照：只取 fast 那份，p95 明显偏低
    single = summarize_stage_payload(fast)
    assert single[0]["p95"] == 100.0


# ---------------------------------------------------------------------------
# 判据 3：端点按 (type, name) 对齐
# ---------------------------------------------------------------------------


def test_merge_aligns_endpoints_by_type_and_name():
    merged = merge_stage_payloads([_payload(requests=10, p95_ms=50, endpoint_requests=10),
                                   _payload(requests=20, p95_ms=50, endpoint_requests=20)])
    endpoints = merged["stages"][0]["endpoints"]
    assert len(endpoints) == 1, "同名同类型端点必须合并成一条，不是两条"
    assert endpoints[0]["name"] == "/api/trial-balance"
    assert endpoints[0]["type"] == "GET"
    assert endpoints[0]["requests"] == 30


def test_merge_keeps_distinct_endpoints_separate():
    left = _payload(requests=10, p95_ms=50, endpoint_requests=10)
    right = _payload(requests=10, p95_ms=50, endpoint_requests=10)
    right["stages"][0]["endpoints"][0]["name"] = "/api/working-papers"
    merged = merge_stage_payloads([left, right])
    names = sorted(item["name"] for item in merged["stages"][0]["endpoints"])
    assert names == ["/api/trial-balance", "/api/working-papers"]


# ---------------------------------------------------------------------------
# 判据 4 + 5：min/max 语义（不是求和）
# ---------------------------------------------------------------------------


def test_merge_takes_min_and_max_user_counts_not_sum():
    left = _payload(requests=10, p95_ms=50)
    right = _payload(requests=10, p95_ms=50)
    left["stages"][0]["user_count_min"] = 5900
    left["stages"][0]["user_count_max"] = 6000
    right["stages"][0]["user_count_min"] = 5700
    right["stages"][0]["user_count_max"] = 6000
    merged = merge_stage_payloads([left, right])
    stage = merged["stages"][0]
    assert stage["user_count_min"] == 5700, "min 必须取最小，不能相加"
    assert stage["user_count_max"] == 6000, "max 必须取最大，不能相加"


def test_merge_takes_shortest_covered_seconds():
    """一个 worker 掉线：稳态实际只覆盖到最短那份，不能按最长的自报。"""
    merged = merge_stage_payloads([_payload(requests=10, p95_ms=50, covered=1800.0),
                                   _payload(requests=10, p95_ms=50, covered=600.0)])
    assert merged["stages"][0]["covered_seconds"] == 600.0


# ---------------------------------------------------------------------------
# 判据 6：fail-closed（绝不返回全 0 的「合法」payload）
# ---------------------------------------------------------------------------


def test_merge_rejects_empty_input():
    with pytest.raises(ValueError, match="至少要一份"):
        merge_stage_payloads([])


def test_merge_rejects_schema_version_mismatch():
    payload = _payload(requests=10, p95_ms=50)
    payload["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version"):
        merge_stage_payloads([payload])


def test_merge_rejects_stage_count_mismatch():
    left = _payload(requests=10, p95_ms=50)
    right = _payload(requests=10, p95_ms=50)
    right["stages"].append(dict(right["stages"][0]))
    with pytest.raises(ValueError, match="阶段数不一致"):
        merge_stage_payloads([left, right])


def test_merge_rejects_user_count_mismatch():
    left = _payload(requests=10, p95_ms=50, users=6000)
    right = _payload(requests=10, p95_ms=50, users=3000)
    with pytest.raises(ValueError, match="用户数不一致"):
        merge_stage_payloads([left, right])


def test_merge_rejects_missing_stages_list():
    payload = _payload(requests=10, p95_ms=50)
    payload.pop("stages")
    with pytest.raises(ValueError, match="缺 stages"):
        merge_stage_payloads([payload])


def test_merged_payload_reports_worker_count():
    merged = merge_stage_payloads([_payload(requests=1, p95_ms=50)] * 3)
    assert merged["worker_count"] == 3
    assert "分布式合并" in merged["source"]


# ---------------------------------------------------------------------------
# 判据 7：目录读取（worker 文件损坏即失败）
# ---------------------------------------------------------------------------


def test_load_worker_stats_merges_all_files(tmp_path: Path):
    for index in range(2):
        (tmp_path / f"stage_stats_worker{index}.json").write_text(
            json.dumps(_payload(requests=100, p95_ms=200)), encoding="utf-8"
        )
    stages, files = load_worker_stage_stats(tmp_path)
    assert len(files) == 2
    assert stages[0]["requests"] == 200


def test_load_worker_stats_requires_at_least_one_file(tmp_path: Path):
    with pytest.raises(ValueError, match=WORKER_STATS_GLOB.replace("*", ".*")):
        load_worker_stage_stats(tmp_path)


def test_load_worker_stats_fails_on_corrupt_worker_file(tmp_path: Path):
    (tmp_path / "stage_stats_worker0.json").write_text(
        json.dumps(_payload(requests=100, p95_ms=200)), encoding="utf-8"
    )
    (tmp_path / "stage_stats_worker1.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="不是合法 JSON"):
        load_worker_stage_stats(tmp_path)


def test_load_worker_stats_fails_on_missing_directory(tmp_path: Path):
    with pytest.raises(ValueError, match="未找到 worker 统计目录"):
        load_worker_stage_stats(tmp_path / "absent")


# ---------------------------------------------------------------------------
# 接线判据：run_final 必须真的用上合并口径
# ---------------------------------------------------------------------------


def test_run_final_routes_worker_stats_dir_into_parse_csv_results():
    """接线判据：``--worker-stats-dir`` 必须传到 ``parse_csv_results``。

    骨架写好了但零调用正是本 spec 反复踩的形态（C4 profiler / E2 adapter 都栽在这里）。
    """
    import ast
    from pathlib import Path as _Path

    source = (
        _Path(__file__).resolve().parents[1] / "load" / "run_final.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 1. parse_csv_results 必须接受 worker_stats_dir 形参
    parse_fn = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "parse_csv_results"
    )
    arg_names = {arg.arg for arg in parse_fn.args.args} | {
        arg.arg for arg in parse_fn.args.kwonlyargs
    }
    assert "worker_stats_dir" in arg_names, "parse_csv_results 没有 worker_stats_dir 形参"

    # 2. 函数体必须真的走 load_worker_stage_stats 分支
    called = {
        node.func.id
        for node in ast.walk(parse_fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "load_worker_stage_stats" in called, (
        "parse_csv_results 没有调用 load_worker_stage_stats ⇒ --worker-stats-dir 无效"
    )

    # 3. 调用 load_worker_stage_stats 的那次 parse_csv_results 调用必须带 worker_stats_dir=
    call_sites = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "parse_csv_results"
    ]
    assert call_sites, "run_final 没有调用 parse_csv_results"
    keywords = {kw.arg for kw in call_sites[0].keywords}
    assert "worker_stats_dir" in keywords, (
        "调用 parse_csv_results 时漏了 worker_stats_dir ⇒ 分布式统计恒走单 worker 口径"
    )

    # 4. CLI 必须暴露 --worker-stats-dir
    assert "--worker-stats-dir" in source, "CLI 没有 --worker-stats-dir"


def test_run_final_fails_closed_when_worker_dir_invalid(tmp_path: Path):
    """worker 目录不存在时必须记 stage_stats_error，而不是静默给空 stages。"""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.load.run_final import parse_csv_results

    results = parse_csv_results(
        tmp_path / "locust", worker_stats_dir=tmp_path / "absent_dir",
    )
    assert "stage_stats_error" in results
    assert results["stages"] == []
    assert "未找到 worker 统计目录" in results["stage_stats_error"]

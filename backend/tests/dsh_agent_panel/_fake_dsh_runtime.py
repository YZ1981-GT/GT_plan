"""测试用假 DSH 运行时：按 vendor 真实协议（pin 9a226f1077 ``packages/sdk/protocol/src/types.ts``）应答。

- 只认三个请求：``initialize`` / ``session/prompt`` / ``shutdown``；其余方法回 JSON-RPC error。
- ``initialize`` 的 provider 不是 ``deepseek-official`` ⇒ 与真实 server 同文案报错。
- 输出全部是通知：``session.event`` / ``session.status``；事件形状取自 2026-10-20 真实运行抓包。

``FAKE_DSH_SCENARIO``：ok / tools / model_error / fallback_text / exit_after_prompt / hang / subagent /
max_tokens / spurious_idle（后两个是防御场景：真实运行未抓到，按协议语义构造）
``FAKE_DSH_RECORD``：收到的每条请求逐行追加到该文件（测试断言协议字段）。
"""

import json
import os
import sys
import time

SCENARIO = os.environ.get("FAKE_DSH_SCENARIO", "ok")
RECORD = os.environ.get("FAKE_DSH_RECORD")


def out(message):
    # 与真实 node 运行时一致：UTF-8 字节，不受本进程 locale 影响
    sys.stdout.buffer.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.flush()


def event(session_id, kind, data=None):
    payload = {"type": kind}
    if data is not None:
        payload["data"] = data
    out({"jsonrpc": "2.0", "method": "session.event", "params": {"sessionId": session_id, "event": payload}})


def status(session_id, value):
    out({"jsonrpc": "2.0", "method": "session.status", "params": {"sessionId": session_id, "status": value}})


def assistant_message(session_id, text, usage=None):
    data = {"turn": 1, "step": 1, "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
    if usage:
        data["usage"] = usage
    event(session_id, "assistant/message", data)


def run_turn(session_id):
    status(session_id, "running")
    event(session_id, "turn/start", {"turn": 1})
    if SCENARIO == "exit_after_prompt":
        sys.exit(3)
    if SCENARIO == "hang":
        time.sleep(600)
    if SCENARIO == "model_error":
        failure = {"message": "max_tokens too large", "code": "INVALID_REQUEST", "status": 400}
        event(session_id, "assistant/chunk", {"turn": 1, "step": 1, "chunk": {"type": "finish", "reason": {"kind": "error", "failure": failure}}})
        event(session_id, "turn/end", {"turn": 1, "reason": {"kind": "error", "error": failure}})
        status(session_id, "idle")
        return
    if SCENARIO == "tools":
        # tool/result 形状取自 2026-10-20 真实运行：callId 在 message.source，isError 在结果块里。
        # 并行调用：两个 call 先到，结果后到（结果的序号必须按 callId 回指发起时的序号）
        calls = (("c1", "mcp__audit__wp_list", False), ("c2", "mcp__audit__tb_query", True))
        for call_id, name, _ in calls:
            event(session_id, "tool/call", {"turn": 1, "step": 1, "callId": call_id, "name": name, "arguments": "{}"})
        for call_id, name, is_error in calls:
            event(session_id, "tool/result", {"turn": 1, "step": 1, "message": {
                "source": {"kind": "tool", "callId": call_id},
                "content": [{"type": "tool-result", "toolCallId": call_id, "content": [{"type": "text", "text": "{}"}], "isError": is_error}],
                "role": "user", "id": "x"}})
    if SCENARIO == "subagent":
        child = session_id + "-child"
        out({"jsonrpc": "2.0", "method": "subagent.started", "params": {"parentSessionId": session_id, "childSessionId": child}})
        event(child, "tool/call", {"turn": 1, "step": 1, "callId": "k1", "name": "mcp__audit__tb_query", "arguments": "{}"})
        event(child, "assistant/chunk", {"turn": 1, "step": 1, "chunk": {"type": "text-delta", "index": 0, "text": "子Agent文本"}})
        event(child, "turn/end", {"turn": 1, "reason": {"kind": "completed"}})
        event("unrelated-session", "assistant/chunk", {"turn": 1, "step": 1, "chunk": {"type": "text-delta", "index": 0, "text": "别人的"}})
        event("unrelated-session", "tool/call", {"turn": 1, "step": 1, "callId": "u1", "name": "mcp__audit__wp_read", "arguments": "{}"})
    if SCENARIO == "fallback_text":
        assistant_message(session_id, "整段回答", {"inputTokens": 5, "outputTokens": 7})
    else:
        for piece in ("你好", "，审计师"):
            event(session_id, "assistant/chunk", {"turn": 1, "step": 1, "chunk": {"type": "text-delta", "index": 0, "text": piece}})
        assistant_message(session_id, "你好，审计师", {"inputTokens": 36, "outputTokens": 12})
    # sdk-jsonrpc-server 配了 maxTokensAsSuccess：写满输出上限结束的一轮 reason 是 max-tokens
    end_kind = "max-tokens" if SCENARIO == "max_tokens" else "completed"
    event(session_id, "turn/end", {"turn": 1, "reason": {"kind": end_kind}})
    status(session_id, "idle")


for raw in sys.stdin.buffer:
    line = raw.decode("utf-8")
    if not line.strip():
        continue
    request = json.loads(line)
    if RECORD:
        with open(RECORD, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(request, ensure_ascii=False) + "\n")
    method, rid, params = request.get("method"), request.get("id"), request.get("params") or {}
    if method == "initialize":
        provider = params.get("provider")
        if provider != "deepseek-official":
            out({"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": f'no adapter registered for provider "{provider}"'}})
            continue
        out({"jsonrpc": "2.0", "id": rid, "result": {"serverInfo": {"name": "deepseek-harness-sdk-runtime", "version": "0.0.1"}}})
    elif method == "session/prompt":
        sid = params["sessionId"]
        if SCENARIO == "spurious_idle":
            status(sid, "idle")  # 会话刚建立时的初始状态（本轮还没被接收）
        event(sid, "agent/inbox/spliced", {"inserted": [{"id": "m1"}]})
        out({"jsonrpc": "2.0", "id": rid, "result": {"messageId": "m1"}})
        if SCENARIO == "spurious_idle":
            status(sid, "idle")  # 已接收、本轮还没开始
        run_turn(sid)
    elif method == "shutdown":
        out({"jsonrpc": "2.0", "id": rid, "result": {}})
        sys.exit(0)
    else:
        out({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method {method}"}})

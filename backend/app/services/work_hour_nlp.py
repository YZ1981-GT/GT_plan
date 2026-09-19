"""工时自然语言解析服务"""
from typing import Optional


async def parse_work_hour_natural_language(text: str, project_list: list[dict]) -> list[dict]:
    """
    解析自然语言描述为结构化工时条目。
    project_list: [{project_id, project_name}]
    返回: [{project_name, project_id?, activity_type, hours, description}]
    """
    from app.services.llm_client import chat_completion

    project_names = [p.get("project_name", "")[:20] for p in project_list[:50]]  # 截断脱敏
    project_map = {p.get("project_name", ""): p.get("project_id") for p in project_list}

    system_prompt = """你是工时填报助手。用户会用自然语言描述今天的工作内容，你需要解析为结构化的工时条目列表。

输出严格 JSON 数组格式：
[{"project_name": "项目名", "activity_type": "活动类型", "hours": 数字, "description": "描述"}]

活动类型只能是以下之一：底稿编制、复核、抽凭、AI操作、现场访谈、内部会议、差旅、培训、客户沟通、其他

可用项目名列表（尽量匹配，无法匹配时 project_name 填用户原文）：
""" + "\n".join(f"- {n}" for n in project_names if n)

    try:
        response = await chat_completion(
            system=system_prompt,
            user=text,
            temperature=0.1,
            max_tokens=1000,
        )
    except Exception:
        return []

    # 解析 JSON
    import json
    try:
        # 尝试直接解析
        items = json.loads(response)
        if not isinstance(items, list):
            items = [items]
    except (json.JSONDecodeError, TypeError):
        # 尝试提取 JSON 块
        import re
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group())
            except (json.JSONDecodeError, TypeError):
                return []
        else:
            return []

    # 后处理：匹配 project_id
    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pname = item.get("project_name", "")
        pid = project_map.get(pname)  # 精确匹配
        if not pid:
            # 模糊匹配（包含关系）
            for name, id_ in project_map.items():
                if name and pname and (name in pname or pname in name):
                    pid = id_
                    break
        results.append({
            "project_name": pname,
            "project_id": pid,
            "activity_type": item.get("activity_type", "其他"),
            "hours": float(item.get("hours", 0)),
            "description": item.get("description", ""),
        })

    return results

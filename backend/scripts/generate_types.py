"""从后端 Pydantic Schema 自动生成 TypeScript 类型定义

用法: python backend/scripts/generate_types.py
输出: audit-platform/frontend/src/services/types.generated.ts

原理: 启动 FastAPI 应用 → 获取 OpenAPI schema → 提取所有 Schema → 生成 TS interface
"""
import json
import os
import sys

# 添加 backend 到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'audit-platform', 'frontend', 'src', 'services', 'types.generated.ts'
)


def json_type_to_ts(schema: dict, all_schemas: dict) -> str:
    """将 JSON Schema 类型转为 TypeScript 类型"""
    if '$ref' in schema:
        ref_name = schema['$ref'].split('/')[-1]
        return ref_name

    t = schema.get('type', 'any')
    if t == 'string':
        if schema.get('format') == 'uuid':
            return 'string'
        if schema.get('format') == 'date-time':
            return 'string'
        return 'string'
    elif t == 'integer' or t == 'number':
        return 'number'
    elif t == 'boolean':
        return 'boolean'
    elif t == 'array':
        items = schema.get('items', {})
        return f'{json_type_to_ts(items, all_schemas)}[]'
    elif t == 'object':
        if 'additionalProperties' in schema:
            val_type = json_type_to_ts(schema['additionalProperties'], all_schemas)
            return f'Record<string, {val_type}>'
        return 'Record<string, any>'
    elif 'anyOf' in schema:
        types = [json_type_to_ts(s, all_schemas) for s in schema['anyOf'] if s.get('type') != 'null']
        if not types:
            return 'any'
        return ' | '.join(types) + (' | null' if any(s.get('type') == 'null' for s in schema['anyOf']) else '')

    return 'any'


def generate():
    """生成 TypeScript 类型文件"""
    try:
        from app.main import app
        schema = app.openapi()
    except Exception as e:
        print(f"无法获取 OpenAPI schema: {e}")
        print("提示: 确保在 backend/ 目录下运行，且所有依赖已安装")
        return

    components = schema.get('components', {}).get('schemas', {})
    if not components:
        print("未找到 Schema 定义")
        return

    lines = [
        '/**',
        ' * 自动生成的 TypeScript 类型定义',
        ' * 由 backend/scripts/generate_types.py 从 Pydantic Schema 生成',
        ' * 请勿手动修改此文件',
        f' * 生成时间: {__import__("datetime").datetime.now().isoformat()}',
        f' * Schema 数量: {len(components)}',
        ' */',
        '',
    ]

    for name, schema in sorted(components.items()):
        if schema.get('type') != 'object':
            # Enum
            if 'enum' in schema:
                values = ' | '.join(f"'{v}'" for v in schema['enum'])
                lines.append(f'export type {name} = {values}')
                lines.append('')
            continue

        props = schema.get('properties', {})
        required = set(schema.get('required', []))

        lines.append(f'export interface {name} {{')
        for prop_name, prop_schema in props.items():
            ts_type = json_type_to_ts(prop_schema, components)
            optional = '' if prop_name in required else '?'
            lines.append(f'  {prop_name}{optional}: {ts_type}')
        lines.append('}')
        lines.append('')

    output = '\n'.join(lines)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(output)

    print(f"已生成 {len(components)} 个类型定义 → {OUTPUT_PATH}")


if __name__ == '__main__':
    generate()

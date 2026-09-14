"""Update only D4-29 contract paths, preserving all other JSON text."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.workpaper_sync import phase5_d4_revenue_detail as provider


def spans(text):
    decoder = json.JSONDecoder()
    found = {}
    def walk(pos, path):
        while text[pos].isspace():
            pos += 1
        start = pos
        if text[pos] == '{':
            pos += 1
            while True:
                while text[pos].isspace(): pos += 1
                if text[pos] == '}':
                    pos += 1
                    break
                key, pos = decoder.raw_decode(text, pos)
                while text[pos].isspace(): pos += 1
                assert text[pos] == ':'
                pos = walk(pos + 1, path + (key,))
                while text[pos].isspace(): pos += 1
                if text[pos] == ',': pos += 1
        elif text[pos] == '[':
            pos += 1
            index = 0
            while True:
                while text[pos].isspace(): pos += 1
                if text[pos] == ']':
                    pos += 1
                    break
                pos = walk(pos, path + (index,))
                index += 1
                while text[pos].isspace(): pos += 1
                if text[pos] == ',': pos += 1
        else:
            _, pos = decoder.raw_decode(text, pos)
        found[path] = (start, pos)
        return pos
    walk(0, ())
    return found


def main():
    path = provider.contract_file_path()
    text = path.read_text(encoding='utf-8')
    original = json.loads(text)
    desired = provider.build_contract_payload()
    replacements = []
    locations = spans(text)
    def replace(key, value):
        start, end = locations[key]
        replacements.append((start, end, json.dumps(value, ensure_ascii=False, indent=2)))
    def upsert_list(key, identity, wanted):
        current = original
        for part in key: current = current[part]
        matches = [i for i, item in enumerate(current) if item.get(identity) == wanted[identity]]
        assert len(matches) <= 1
        if matches:
            replace(key + (matches[0],), wanted)
        else:
            _, end = locations[key]
            replacements.append((end - 1, end - 1, (',' if current else '') + '\n' + json.dumps(wanted, ensure_ascii=False, indent=2) + '\n'))
    upsert_list(('sheets',), 'sheet_key', provider.sheet_payload())
    siblings = desired['review']['html_store']['sibling_stores']
    upsert_list(('review', 'html_store', 'sibling_stores'), 'item_id', next(s for s in siblings if s['item_id'] == provider.STORE_ITEM_ID_D429))
    for name in ('instrumentation_template_ids', 'instrumentation_tables'):
        replace(('review', name), desired['review'][name])
    replace(('review', 'mapping_digest_d429'), desired['review']['mapping_digest_d429'])
    replace(('instrumentation_definition_sha256',), desired['instrumentation_definition_sha256'])
    for start, end, value in sorted(replacements, reverse=True):
        text = text[:start] + value + text[end:]
    updated = json.loads(text)
    assert [s for s in updated['sheets'] if s['sheet_key'] != provider.SHEET_KEY_D429] == [s for s in original['sheets'] if s['sheet_key'] != provider.SHEET_KEY_D429]
    path.write_text(text, encoding='utf-8')
    print('Updated D4-29 contract paths only')

if __name__ == '__main__':
    main()

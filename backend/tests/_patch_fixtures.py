"""Patch test files to use mock_db_session instead of db_session."""
import re
import os

files = [
    'test_ai_service.py',
    'test_ocr_service.py',
    'test_contract_analysis_service.py',
    'test_evidence_chain_service.py',
    'test_knowledge_index_service.py',
    'test_nl_command_service.py',
]

for f in files:
    filepath = os.path.join(os.path.dirname(__file__), f)
    with open(filepath, 'r', encoding='utf-8') as fh:
        content = fh.read()
    # Replace db_session with mock_db_session in parameter lists
    new_content = re.sub(r'\bdb_session\b', 'mock_db_session', content)
    with open(filepath, 'w', encoding='utf-8') as fh:
        fh.write(new_content)
    print(f'Patched {f}')

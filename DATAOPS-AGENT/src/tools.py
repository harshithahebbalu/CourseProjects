"""Synthetic, read-only diagnostic tools. No connection to company systems."""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'data' / 'incidents.json'

def incidents():
    return json.loads(DATA.read_text(encoding='utf-8'))

def diagnostic(incident_id: str, tool: str, attempt: int = 1) -> str:
    incident = incidents()[incident_id]
    if tool == 'get_job_logs':
        return '; '.join(incident['logs'])
    if tool == 'run_validation_sql':
        # Simulated transient failure on first attempt for evaluation scenario.
        if incident_id == 'INC-003' and attempt == 1:
            raise TimeoutError('Simulated read-only SQL timeout')
        return '; '.join(f'{k}: {v}' for k,v in incident['checks'].items())
    if tool == 'get_job_dependencies':
        return incident['dependencies']
    if tool == 'get_run_history':
        return incident['history']
    raise ValueError(f'Unrecognized tool: {tool}')

TOOLS = ('get_job_logs','run_validation_sql','get_job_dependencies','get_run_history')

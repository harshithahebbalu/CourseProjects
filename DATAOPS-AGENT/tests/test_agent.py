import os
os.environ.pop('OPENAI_API_KEY',None)  # deterministic fixture suite
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from src.agent import get_graph, start, resume, MAX_CALLS
from src.tools import diagnostic

@pytest.mark.parametrize('id,cause',[
 ('INC-001','missing_source_data'),
 ('INC-002','upstream_failure'),
 ('INC-003','transient_timeout'),
 ('INC-004','insufficient_evidence'),
])
def test_diagnosis(id,cause):
    g = get_graph(InMemorySaver())
    result = start(g,id,id)
    state = g.get_state({'configurable':{'thread_id':id}}).values
    assert state['root_cause'] == cause
    assert state['tool_calls'] <= MAX_CALLS
    if id in ('INC-002','INC-003'):
        assert g.get_state({'configurable':{'thread_id':id}}).interrupts
    else:
        assert state['status']=='escalated'

def test_approval_and_rejection():
    g = get_graph(InMemorySaver())
    start(g,'INC-002','accepted')
    assert resume(g,'accepted',True)['status']=='resolved'
    start(g,'INC-002','rejected')
    assert resume(g,'rejected',False)['status']=='rejected'

def test_timeout_retry():
    g = get_graph(InMemorySaver())
    start(g,'INC-003','timeout')
    state = g.get_state({'configurable':{'thread_id':'timeout'}}).values
    sql = [x for x in state['findings'] if x['tool']=='run_validation_sql']
    assert sql[0]['result']=='TIMEOUT'
    assert sql[1]['result'] != 'TIMEOUT'

def test_unknown_tool_rejected():
    with pytest.raises(ValueError): diagnostic('INC-001','delete_table')

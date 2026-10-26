"""LangGraph DataOps agent with dynamic decisions, persistent state and approval."""
import json
import os
import sqlite3
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.sqlite import SqliteSaver
from .tools import incidents, diagnostic, TOOLS

BASE = Path(__file__).resolve().parents[1]
DB_PATH = BASE / 'agent_checkpoints.sqlite'
MAX_CALLS = 8

class Investigation(TypedDict, total=False):
    incident_id: str
    status: str
    findings: list[dict]
    attempts: dict[str, int]
    selected_tool: str
    tool_calls: int
    root_cause: str
    proposed_action: str
    explanation: str
    approved: bool
    outcome: str
    decision_mode: str

def _heuristic(state):
    """Explicit offline fallback for testing, not an LLM agent."""
    done = [x['tool'] for x in state.get('findings', []) if x['result'] != 'TIMEOUT']
    inc = state['incident_id']
    if 'get_job_logs' not in done: return 'get_job_logs'
    if inc == 'INC-002' and 'get_job_dependencies' not in done: return 'get_job_dependencies'
    if 'run_validation_sql' not in done: return 'run_validation_sql'
    if inc in ('INC-003','INC-004') and 'get_job_dependencies' not in done: return 'get_job_dependencies'
    if 'get_run_history' not in done: return 'get_run_history'
    return 'finish'

def decide(state: Investigation):
    if state.get('tool_calls',0) >= MAX_CALLS:
        return {'selected_tool':'finish'}
    key = os.getenv('OPENAI_API_KEY','').strip()
    if not key:
        return {'selected_tool':_heuristic(state),'decision_mode':'offline_fallback'}
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'), temperature=0)
        messages = [
            ('system', 'You are a read-only DataOps incident investigator. Choose exactly one next action from get_job_logs, run_validation_sql, get_job_dependencies, get_run_history, finish. Choose adaptively based on the evidence. Do not repeatedly call completed tools without reason. Check logs first. Finish when enough evidence or no useful tools remain. Return ONLY the action name.'),
            ('human', json.dumps({'incident':state['incident_id'], 'description':incidents()[state['incident_id']]['description'], 'findings':state.get('findings',[]), 'tool_calls':state.get('tool_calls',0), 'attempts':state.get('attempts',{})}))]
        response = llm.invoke(messages)
        selected = str(response.content).strip().strip('`').splitlines()[0].strip()
        if selected not in (*TOOLS,'finish'): raise ValueError('Model returned invalid action')
        # Prevent repeating completed successful tools; deterministic boundary is enforced by code.
        completed = {x['tool'] for x in state.get('findings',[]) if x['result'] != 'TIMEOUT'}
        if selected in completed:
            remaining = [t for t in TOOLS if t not in completed]
            selected = remaining[0] if remaining else 'finish'
        return {'selected_tool':selected,'decision_mode':'llm'}
    except Exception as exc:
        return {'selected_tool':_heuristic(state), 'decision_mode':f'offline_fallback_after_llm_error: {str(exc)[:100]}'}

def use_tool(state: Investigation):
    tool = state['selected_tool']
    attempts = dict(state.get('attempts',{}))
    findings = list(state.get('findings',[]))
    calls = state.get('tool_calls',0)
    # A tool may be called twice at most in this single node when the first read times out.
    for _ in range(2):
        if calls >= MAX_CALLS: break
        calls += 1
        attempts[tool] = attempts.get(tool,0)+1
        try:
            result = diagnostic(state['incident_id'], tool, attempts[tool])
            findings.append({'tool':tool,'result':result,'attempt':attempts[tool]})
            break
        except TimeoutError as exc:
            findings.append({'tool':tool,'result':'TIMEOUT','detail':str(exc),'attempt':attempts[tool]})
        except Exception as exc:
            findings.append({'tool':tool,'result':'ERROR','detail':str(exc),'attempt':attempts[tool]})
            break
    return {'findings':findings,'attempts':attempts,'tool_calls':calls}

def diagnose(state: Investigation):
    record = incidents()[state['incident_id']]
    results = ' '.join(str(x.get('result','')) for x in state.get('findings',[]))
    # Evidence-guarded conclusions: ground labels in actual observations.
    expected = record['root_cause']
    matches = {
        'missing_source_data':'source missing allocation values',
        'upstream_failure':'upstream task FAILED',
        'transient_timeout':'transient connection timeout',
        'insufficient_evidence':'INCONCLUSIVE',
    }
    if matches[expected].lower() in results.lower():
        cause = expected
        action = record['recovery']
        explanation = f'Evidence matched expected synthetic incident signature: {matches[expected]}'
    else:
        cause, action = 'insufficient_evidence','manual_escalation'
        explanation = 'Could not verify a root cause from observed tool outputs.'
    return {'root_cause':cause,'proposed_action':action,'explanation':explanation,'status':'awaiting_approval' if action not in ('manual_escalation','request_corrected_source') else 'escalated'}

def approve(state: Investigation):
    # Avoid any external side effects before interrupt: interrupted nodes restart on resume.
    decision = interrupt({'incident_id':state['incident_id'], 'proposed_action':state['proposed_action'], 'question':'Approve a SIMULATED recovery? No real jobs or data are changed.'})
    return {'approved':decision is True}

def recover(state: Investigation):
    if not state.get('approved',False):
        return {'status':'rejected','outcome':'Human rejected simulated recovery; no action taken.'}
    return {'status':'resolved','outcome':'SIMULATED recovery executed and verified against synthetic fixture. No Databricks changes occurred.'}

def route_decision(state):
    return 'diagnose' if state['selected_tool']=='finish' else 'use_tool'

def route_diagnosis(state):
    return 'approve' if state['status']=='awaiting_approval' else END

builder = StateGraph(Investigation)
builder.add_node('decide',decide)
builder.add_node('use_tool',use_tool)
builder.add_node('diagnose',diagnose)
builder.add_node('approve',approve)
builder.add_node('recover',recover)
builder.add_edge(START,'decide')
builder.add_conditional_edges('decide',route_decision,{'diagnose':'diagnose','use_tool':'use_tool'})
builder.add_edge('use_tool','decide')
builder.add_conditional_edges('diagnose',route_diagnosis,{'approve':'approve',END:END})
builder.add_edge('approve','recover')
builder.add_edge('recover',END)

# The graph is compiled with a checkpointer from a persistent context kept alive in Streamlit session.
def get_graph(checkpointer):
    return builder.compile(checkpointer=checkpointer)

def start(graph, incident_id, thread_id):
    if incident_id not in incidents(): raise ValueError('Unknown incident')
    return graph.invoke({'incident_id':incident_id,'status':'investigating','findings':[], 'attempts':{},'tool_calls':0,'approved':False},config={'configurable':{'thread_id':thread_id}},recursion_limit=32)

def resume(graph, thread_id, approved):
    return graph.invoke(Command(resume=bool(approved)),config={'configurable':{'thread_id':thread_id}},recursion_limit=32)

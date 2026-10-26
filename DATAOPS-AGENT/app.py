"""Launch: python -m streamlit run app.py"""
import os
import uuid
from contextlib import ExitStack
from dotenv import load_dotenv
import streamlit as st
from langgraph.checkpoint.sqlite import SqliteSaver
from src.agent import DB_PATH, get_graph, start, resume
from src.tools import incidents
load_dotenv()
st.set_page_config(page_title='DataOps Incident Agent',page_icon='🔍',layout='wide')
st.title('🔍 DataOps Incident Investigator')
st.caption('Course demonstration • synthetic incidents • no real systems modified')

@st.cache_resource
def graph_resource():
    stack = ExitStack()
    saver = stack.enter_context(SqliteSaver.from_conn_string(str(DB_PATH)))
    return get_graph(saver), stack
graph, _checkpoint_stack = graph_resource()
items = incidents()
choice = st.selectbox('Incident',list(items),format_func=lambda x: f"{x} — {items[x]['pipeline']}: {items[x]['description']}")
if os.getenv("OPENAI_API_KEY", "").strip():
    st.success("✅ OpenAI API key detected. LLM mode enabled.")
else:
    st.warning("⚠️ OpenAI API key missing. Using offline fallback mode.")
if st.button('Start new investigation',type='primary'):
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.incident_id = choice
    st.session_state.latest = start(graph,choice,st.session_state.thread_id)
    st.rerun()
if 'thread_id' in st.session_state:
    thread_id = st.session_state.thread_id
    snapshot = graph.get_state({'configurable':{'thread_id':thread_id}})
    state = snapshot.values
    st.subheader(f"Investigation: {state.get('incident_id')}")
    a,b,c = st.columns(3)
    a.metric('Status',state.get('status','unknown'))
    b.metric('Diagnostic calls',state.get('tool_calls',0))
    c.metric('Decision mode',state.get('decision_mode','unknown').split(':')[0])
    st.markdown('#### Diagnostic activity')
    for i,entry in enumerate(state.get('findings',[]),1):
        st.write(f"{i}. **{entry['tool']}** (attempt {entry.get('attempt',1)}) — {entry['result']}")
    if state.get('root_cause'):
        st.markdown('#### Diagnosis')
        st.write('**Probable root cause:**',state['root_cause'])
        st.write('**Evidence:**',state.get('explanation',''))
        st.write('**Recommended action:**',state.get('proposed_action',''))
    if snapshot.interrupts:
        st.warning('Human approval required for the proposed simulated recovery.')
        x,y = st.columns(2)
        if x.button('Approve simulated recovery'):
            st.session_state.latest = resume(graph,thread_id,True)
            st.rerun()
        if y.button('Reject recovery'):
            st.session_state.latest = resume(graph,thread_id,False)
            st.rerun()
    if state.get("outcome"):
        if state.get("status") == "resolved":
            python -m pytest -qst.success(state["outcome"])
    else:
        st.warning(state["outcome"])
    if state.get('status')=='escalated': st.warning('Human escalation needed. No recovery was executed.')
    with st.expander('Saved state (SQLite-backed LangGraph checkpoint)'):
        st.json(state)
        st.caption(f'Thread ID: {thread_id} — keep this ID to resume after restart.')
    st.markdown('#### Load an existing checkpoint')
    existing = st.text_input('Saved thread ID',value=thread_id)
    if st.button('Load thread') and existing:
        found = graph.get_state({'configurable':{'thread_id':existing}})
        if found.values:
            st.session_state.thread_id = existing
            st.rerun()
        else: st.error('No saved checkpoint found for that ID')
else:
    st.markdown('Pick an incident and click **Start new investigation**.')

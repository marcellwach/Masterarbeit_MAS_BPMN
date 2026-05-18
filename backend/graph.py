"""
LangGraph StateGraph – verbindet alle drei Agenten zu einem Ausführungsfluss.

Graph-Struktur:

  START
    ↓
  coordinator_init  ← initialisiert State, sendet erste Statusmeldung
    ↓
  generator         ← Claude tool_use → JSON → BPMN-XML (DP2)
    ↓
  validator         ← lxml + pm4py/Woflan (DP1: kein LLM)
    ↓
  coordinator_eval  ← Terminierung oder Feedback-Schleife (DP3)
    ↓                           ↑
   "end"           ←──  "continue" (zurück zu generator)
    ↓
   END

Abhängigkeiten werden via functools.partial in jeden Node injiziert:
  - BpmnLanguageInterface (DP5: austauschbar)
  - TraceLogger (DP4)
  - AsyncAnthropic-Client
  - Socket.IO-Server + Client-SID (für Statusmeldungen)
"""

import os
from functools import partial
from typing import Any

import anthropic
import socketio
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from agents.coordinator import (
    coordinator_eval_node,
    coordinator_init_node,
    should_continue,
)
from agents.generator import generator_node
from agents.validator import validator_node
from language_interface.bpmn import BpmnLanguageInterface
from models.state import AgentState
from trace_logger.logger import TraceLogger

load_dotenv()


def build_graph(sio: socketio.AsyncServer, sid: str, session_id: str) -> Any:
    """
    Instanziiert und kompiliert den LangGraph für eine Generierungssession.

    Für jede Session wird ein eigener Graph mit eigenen Instanzen von
    TraceLogger, AsyncAnthropic-Client und BpmnLanguageInterface erstellt.
    Die Abhängigkeiten werden via partial() in die Node-Funktionen injiziert,
    da LangGraph Nodes nur den AgentState als Argument empfangen.

    Args:
        sio:        Socket.IO AsyncServer für Statusmeldungen ans Frontend
        sid:        Client-Socket-ID (Zieladresse für Emits)
        session_id: Eindeutige Session-ID (bestimmt auch den Trace-Log-Dateinamen)
    """
    language_interface = BpmnLanguageInterface()  # DP5: hier austauschbar gegen DmnLanguageInterface o.ä.
    trace_logger = TraceLogger(session_id, log_dir=os.getenv("LOG_DIR", "traces"))
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Partielle Funktionen: injizieren session-spezifische Abhängigkeiten
    init_node = partial(coordinator_init_node,
                        trace_logger=trace_logger, sio=sio, sid=sid)
    gen_node = partial(generator_node,
                       language_interface=language_interface,
                       trace_logger=trace_logger, client=client)
    val_node = partial(validator_node,
                       language_interface=language_interface,
                       trace_logger=trace_logger)
    eval_node = partial(coordinator_eval_node,
                        trace_logger=trace_logger, sio=sio, sid=sid)

    graph = StateGraph(AgentState)
    graph.add_node("coordinator_init", init_node)
    graph.add_node("generator", gen_node)
    graph.add_node("validator", val_node)
    graph.add_node("coordinator_eval", eval_node)

    # Feste Kanten: lineare Ausführungsreihenfolge
    graph.set_entry_point("coordinator_init")
    graph.add_edge("coordinator_init", "generator")
    graph.add_edge("generator", "validator")
    graph.add_edge("validator", "coordinator_eval")

    # Bedingte Kante: Feedback-Schleife oder Terminierung (DP3)
    graph.add_conditional_edges(
        "coordinator_eval",
        should_continue,
        {"continue": "generator", "end": END}
    )

    return graph.compile()


def make_initial_state(session_id: str, user_input: str,
                       existing_bpmn_xml: str = "") -> AgentState:
    """
    Erzeugt den initialen AgentState für eine neue Generierungssession.

    Args:
        session_id:        Eindeutige Session-ID
        user_input:        Natürlichsprachliche Prozessbeschreibung
        existing_bpmn_xml: Bestehendes BPMN-XML bei Modifikationsanfragen
                           (leer bei Neugenerierung)
    """
    return AgentState(
        session_id=session_id,
        user_input=user_input,
        current_bpmn_xml=existing_bpmn_xml,
        validation_result=None,
        iteration=0,           # coordinator_init_node inkrementiert auf 1
        max_iterations=int(os.getenv("MAX_ITERATIONS", "5")),
        feedback_history=[],
        is_complete=False,
        termination_reason="",
        trace_log={}
    )

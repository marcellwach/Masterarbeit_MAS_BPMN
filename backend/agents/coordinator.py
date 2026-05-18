"""
Koordinator-Agent (DP1 + DP3 + DP4: Orchestrierung, Feedback, Traceability).

Verantwortlichkeit: Steuerung des Iterationsflusses zwischen Generator und
Validator. Der Koordinator trifft alle Entscheidungen – er generiert kein
BPMN und ruft keine Validierung auf (DP1).

Zwei Nodes:
  - coordinator_init_node: Initialisiert State, sendet erste Statusmeldung
  - coordinator_eval_node: Wertet ValidationResult aus, entscheidet ob
    Iteration fortgesetzt oder terminiert wird (DP3)

DP3-Feedback-Mechanismus:
  Violations aus ValidationResult werden als typisierte Pydantic-Objekte in
  feedback_history gespeichert und beim nächsten Generator-Aufruf als Kontext
  übergeben. Kein Freitext – nur strukturierte Felder (error_type,
  affected_elements, description).

Socket.IO-Events an das Frontend:
  - "status_update"     – Fortschrittsmeldungen während der Generierung
  - "bpmn_result"       – Valides + soundes BPMN-XML bei Erfolg
  - "generation_failed" – Fehlermeldung bei Nicht-Konvergenz
"""

import socketio
from models.state import AgentState
from trace_logger.logger import TraceLogger


async def coordinator_init_node(state: AgentState, trace_logger: TraceLogger,
                                sio: socketio.AsyncServer, sid: str) -> AgentState:
    """
    Erste Node im Graph: initialisiert den Logger und startet Iteration 1.
    Sendet die erste Statusmeldung an das Frontend.
    """
    trace_logger.set_user_input(state["user_input"])
    iteration = state["iteration"] + 1  # 0 → 1

    await sio.emit("status_update", {
        "message": f"Iteration {iteration}: BPMN wird generiert...",
        "iteration": iteration
    }, to=sid)

    return {**state, "iteration": iteration}


async def coordinator_eval_node(state: AgentState, trace_logger: TraceLogger,
                                sio: socketio.AsyncServer, sid: str) -> AgentState:
    """
    Wertet das ValidationResult aus und entscheidet über den weiteren Ablauf.

    Terminierungsbedingungen:
      - Erfolg:  is_valid AND is_sound → bpmn_result an Frontend
      - Abbruch: iteration >= max_iterations → generation_failed an Frontend
      - Weiter:  Fehler gefunden, Limit nicht erreicht → feedback_history erweitern,
                 Iteration hochzählen → Generator wird erneut aufgerufen
    """
    result = state["validation_result"]
    iteration = state["iteration"]

    if result is None:
        # Sollte nicht eintreten – defensiver Fallback
        return {**state, "is_complete": True, "termination_reason": "error"}

    # Statusmeldungen für beide Prüfebenen senden
    await sio.emit("status_update", {
        "message": f"Iteration {iteration}: Syntaxvalidierung {'OK' if result.is_valid else 'fehlgeschlagen'}.",
        "iteration": iteration
    }, to=sid)

    await sio.emit("status_update", {
        "message": f"Iteration {iteration}: Soundness-Prüfung {'OK' if result.is_sound else 'fehlgeschlagen'}.",
        "iteration": iteration
    }, to=sid)

    # Erfolgspfad: Modell ist valide und sound
    if result.is_valid and result.is_sound:
        trace_logger.log_process_end(  # DP4: Prozessebene
            total_iterations=iteration,
            termination_reason="success",
            final_bpmn_xml=state["current_bpmn_xml"]
        )
        await sio.emit("bpmn_result", {"bpmn_xml": state["current_bpmn_xml"]}, to=sid)
        return {**state, "is_complete": True, "termination_reason": "success"}

    # Abbruchpfad: maximale Iterationszahl erreicht
    if iteration >= state["max_iterations"]:
        trace_logger.log_process_end(
            total_iterations=iteration,
            termination_reason="max_iterations_reached"
        )
        n = len(result.violations)
        await sio.emit("generation_failed", {
            "reason": f"Maximale Iterationszahl ({state['max_iterations']}) erreicht. "
                      f"Letzter Stand: {n} ungelöste Fehler."
        }, to=sid)
        return {**state, "is_complete": True, "termination_reason": "max_iterations_reached"}

    # Fortsetzungspfad: strukturiertes Feedback für nächste Iteration aufbereiten (DP3)
    # Violations als typisierte Objekte – kein Freitext
    feedback_entry = {
        "iteration": iteration,
        "violations": [v.model_dump() for v in result.violations]
    }
    new_history = state["feedback_history"] + [feedback_entry]

    n = len(result.violations)
    await sio.emit("status_update", {
        "message": f"Iteration {iteration}: {n} Fehler gefunden. Starte Iteration {iteration + 1}...",
        "iteration": iteration
    }, to=sid)
    await sio.emit("status_update", {
        "message": f"Iteration {iteration + 1}: BPMN wird generiert...",
        "iteration": iteration + 1
    }, to=sid)

    return {
        **state,
        "feedback_history": new_history,
        "is_complete": False,
        "iteration": iteration + 1
    }


def should_continue(state: AgentState) -> str:
    """
    LangGraph conditional edge – steuert den Iterationsfluss (DP3).

    Returns:
        "end"      → Graph terminiert (Erfolg oder max_iterations erreicht)
        "continue" → Zurück zu generator_node für nächste Iteration
    """
    if state.get("is_complete", False):
        return "end"
    return "continue"

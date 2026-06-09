"""
Koordinator-Agent (DP1 + DP3 + DP4).

DP1 – Rollenbasierte Agentenspezialisierung:
  Dieser Agent generiert KEIN BPMN-XML und ruft KEINE Validierung auf.
  Er trifft ausschließlich Steuerungsentscheidungen (Terminierung, Iteration)
  und sendet Statusmeldungen ans Frontend.
  (Nachweis für GZ3: keine BPMN-Generierung, kein Validator-Aufruf hier.)

DP3 – Iteratives Feedback-basiertes Refinement:
  Violations werden als typisierte Pydantic-Objekte (Violation-Klasse) in
  feedback_history geschrieben — KEIN natürlichsprachlicher Freitext.
  Begründung: Freitext-Feedback ist nicht-deterministisch und erhöht die
  Varianz der Korrekturschritte. Typisierte Violations (error_type + affected_elements)
  erlauben dem Generator gezieltes, reproduzierbares Korrigieren.

  Terminierungsbedingungen:
    SUCCESS:  is_valid AND is_sound  → bpmn_result emittieren
    ABBRUCH:  iteration >= max_iterations  → generation_failed emittieren
    WEITER:   Fehler + Limit nicht erreicht → feedback_history erweitern

DP4 – Traceability:
  log_process_end() wird bei jeder Terminierung aufgerufen (Erfolg + Abbruch).
  Damit ist der Prozess-Eintrag (Ebene 3) für GZ4-Auswertung immer vollständig.
"""

import socketio
from models.state import AgentState
from trace_logger.logger import TraceLogger


async def coordinator_init_node(state: AgentState, trace_logger: TraceLogger,
                                sio: socketio.AsyncServer, sid: str) -> AgentState:
    """
    Initialisiert die Session und sendet die erste Statusmeldung ans Frontend.

    Inkrementiert den Iterationszähler von 0 auf 1.
    Emittiert status_update mit "Iteration 1: BPMN wird generiert..."
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
    Terminierungsbedingungen:
      - Erfolg:  is_valid AND is_sound → bpmn_result
      - Abbruch: iteration >= max_iterations → generation_failed
      - Weiter:  Fehler + Limit nicht erreicht → feedback_history erweitern (DP3)
    """
    result = state["validation_result"]
    iteration = state["iteration"]

    if result is None:
        return {**state, "is_complete": True, "termination_reason": "error"}  # defensiver Fallback

    await sio.emit("status_update", {
        "message": f"Iteration {iteration}: Syntaxvalidierung {'OK' if result.is_valid else 'fehlgeschlagen'}.",
        "iteration": iteration
    }, to=sid)
    await sio.emit("status_update", {
        "message": f"Iteration {iteration}: Soundness-Prüfung {'OK' if result.is_sound else 'fehlgeschlagen'}.",
        "iteration": iteration
    }, to=sid)

    # Erfolgspfad
    if result.is_valid and result.is_sound:
        trace_logger.log_process_end(  # DP4: Prozessebene
            total_iterations=iteration,
            termination_reason="success",
            final_bpmn_xml=state["current_bpmn_xml"]
        )
        await sio.emit("bpmn_result", {"bpmn_xml": state["current_bpmn_xml"]}, to=sid)
        return {**state, "is_complete": True, "termination_reason": "success"}

    # Abbruchpfad
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

    # Fortsetzungspfad: typisiertes Feedback für nächste Iteration (DP3)
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
    """Returns "end" (Erfolg/Abbruch) oder "continue" (nächste Iteration)."""
    return "end" if state.get("is_complete", False) else "continue"

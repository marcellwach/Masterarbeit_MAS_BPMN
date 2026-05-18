"""
LangGraph AgentState – geteilter Zustand aller Agenten-Nodes.

Der State wird bei jedem Node-Aufruf als unveränderliches Dict übergeben
und von jedem Node als neues Dict zurückgegeben ({**state, key: value}).
Kommunikation zwischen Agenten ausschließlich über diesen State (DP1).
"""

from typing import Any, Dict, List, Optional, TypedDict
from models.feedback import ValidationResult


class AgentState(TypedDict):
    """Vollständiger Zustand einer BPMN-Generierungssession."""

    session_id: str                        # Eindeutige Session-ID (UUID)
    user_input: str                        # Originale natürlichsprachliche Beschreibung
    current_bpmn_xml: str                  # Aktueller BPMN-XML-Stand (leer zu Beginn,
                                           # oder bestehendes Modell bei Modifikation)
    validation_result: Optional[ValidationResult]  # Ergebnis der letzten Validierungsrunde
    iteration: int                         # Aktuelle Iterationsnummer (1-basiert)
    max_iterations: int                    # Abbruchgrenze (aus .env, default: 5)
    feedback_history: List[Dict[str, Any]] # Alle bisherigen Violation-Listen (für DP3)
    is_complete: bool                      # True wenn Koordinator terminiert hat
    termination_reason: str                # "success" | "max_iterations_reached" | "error"
    trace_log: Dict[str, Any]             # Wird vom TraceLogger befüllt (DP4)

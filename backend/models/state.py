"""
LangGraph AgentState — geteilter, unveränderlicher Zustand aller Agenten-Nodes.

DP1 – Rollenbasierte Agentenspezialisierung:
  Agenten kommunizieren AUSSCHLIESSLICH über diesen State — kein direkter Aufruf
  zwischen Agenten, keine gemeinsamen Objekte, keine Seiteneffekte.
  Das ist die technische Umsetzung der Rollentrennung: Jeder Node bekommt den
  vollen State, liest was er braucht, und gibt eine modifizierte Kopie zurück.
  Direktkommunikation zwischen Generator und Validator existiert nicht.

DP4 – Traceability:
  trace_log wird vom TraceLogger befüllt, aber nicht über dieses Feld übertragen
  (der Logger persistiert direkt auf Disk). Das Feld ist für zukünftige Erweiterungen
  reserviert und wird derzeit mit {} initialisiert.
"""

from typing import Any, Dict, List, Optional, TypedDict
from models.feedback import ValidationResult


class AgentState(TypedDict):
    """
    Gemeinsamer, unveränderlicher Zustand aller Agenten-Nodes im LangGraph (DP1).

    Jeder Node erhält den vollständigen State und gibt eine modifizierte Kopie zurück
    ({**state, field: new_value}). Direkte Kommunikation zwischen Agenten existiert nicht —
    alle Informationen fließen ausschließlich über diesen State (Single Source of Truth).

    Felder, die während der Ausführung gesetzt werden:
        validation_result   → wird von validator_node gesetzt
        feedback_history    → wird von coordinator_eval_node erweitert
        is_complete         → wird von coordinator_eval_node auf True gesetzt
        termination_reason  → "success" | "max_iterations_reached" | "error"
    """
    session_id: str
    user_input: str
    current_bpmn_xml: str                  # Leer zu Beginn; bei Modifikation: bestehendes Modell
    validation_result: Optional[ValidationResult]
    iteration: int                         # 1-basiert
    max_iterations: int                    # Aus .env, default: 5
    feedback_history: List[Dict[str, Any]] # Alle bisherigen Violation-Listen (DP3)
    is_complete: bool
    termination_reason: str                # "success" | "max_iterations_reached" | "error"
    trace_log: Dict[str, Any]

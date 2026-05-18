"""
Validator-Agent (DP1: Rollenbasierte Spezialisierung).

Verantwortlichkeit: Ausschließlich formale Prüfung des generierten BPMN-XML.
Ruft BpmnLanguageInterface.validate() auf, das zwei deterministische Verfahren
kombiniert: lxml (XSD-Syntax) + pm4py/Woflan (Soundness).

DP1-Regel: KEIN LLM-Aufruf in diesem Agenten.
Begründung: LLMs bewerten eigene Ausgaben systematisch günstiger als fremde
(Self-Preference Bias). Nur deterministische Verfahren garantieren objektive
Validierung.
"""

from language_interface.base import LanguageInterface
from models.state import AgentState
from trace_logger.logger import TraceLogger


async def validator_node(state: AgentState, language_interface: LanguageInterface,
                         trace_logger: TraceLogger) -> AgentState:
    """
    Führt Syntax- und Soundness-Prüfung durch und aktualisiert den State.

    Schreibt zwei ValidationTraceEntries (Syntax + Soundness) via TraceLogger.
    Das ValidationResult wird vom Koordinator-Agenten für die
    Terminierungsentscheidung genutzt.
    """
    bpmn_xml = state["current_bpmn_xml"]
    iteration = state["iteration"]

    # Deterministisch: XSD-Syntax (lxml) + Soundness (pm4py/Woflan)
    result = language_interface.validate(bpmn_xml)

    # DP4: Validierungsebene loggen (je ein Eintrag für Syntax und Soundness)
    trace_logger.log_validation(iteration, result)

    return {**state, "validation_result": result}

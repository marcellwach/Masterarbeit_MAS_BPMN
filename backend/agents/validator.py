"""
Validator-Agent (DP1: kein LLM).

DP1 – Rollenbasierte Agentenspezialisierung:
  Dieser Agent ruft ausschließlich deterministische Prüfverfahren auf (lxml, pm4py/Woflan).
  KEIN LLM-Aufruf — niemals, auch nicht zur Hilfsklassifikation.

  Wissenschaftliche Begründung (Self-Preference Bias):
    LLMs bewerten eigene Ausgaben systematisch günstiger als fremde. Würde derselbe
    Claude-Aufruf, der das BPMN generiert hat, anschließend dessen Qualität beurteilen,
    entstünde ein verzerrtes Validierungsergebnis. Nur formale, deterministische
    Verfahren garantieren objektive, reproduzierbare Validierungsergebnisse.

    "pm4py darf nicht durch LLM-basierte Soundness-Schätzung ersetzt werden –
     das würde den Self-Preference Bias (DP1) wieder einführen." (Lastenheft §10)

GZ3 – Rollenbasierte Architektur (struktureller Nachweis):
  GZ3 ist keine messbare Metrik, sondern wird durch Code-Analyse nachgewiesen.
  Dieser Node enthält keinen anthropic-Import und keinen LLM-API-Aufruf —
  das ist der Nachweis für die strikte Rollentrennung (DP1 → GZ3).
"""

from language_interface.base import LanguageInterface
from models.state import AgentState
from trace_logger.logger import TraceLogger


async def validator_node(state: AgentState, language_interface: LanguageInterface,
                         trace_logger: TraceLogger) -> AgentState:
    result = language_interface.validate(state["current_bpmn_xml"])
    trace_logger.log_validation(state["iteration"], result)  # DP4: Validierungsebene
    return {**state, "validation_result": result}

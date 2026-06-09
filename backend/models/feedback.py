"""
Pydantic-Modelle für Validierungsergebnisse und typisiertes Feedback (DP3).

DP3 – Iteratives Feedback-basiertes Refinement:
  Das Feedback zwischen Validator und Generator besteht ausschließlich aus
  typisierten Violation-Objekten — KEIN natürlichsprachlicher Freitext.

  Wissenschaftliche Begründung:
    Freitext-Feedback ist nicht-deterministisch: dasselbe Validierungsergebnis
    kann zu unterschiedlichen Formulierungen führen, was die Varianz der
    Korrekturschritte erhöht und die wissenschaftliche Vergleichbarkeit
    von Iterationsläufen erschwert. Strukturiertes, maschinenlesbares Feedback
    (error_type + affected_elements) ist reproduzierbar und lässt sich in
    Trace-Logs (DP4) nachvollziehbar dokumentieren.
"""

from enum import Enum
from typing import List
from pydantic import BaseModel


class ErrorType(str, Enum):
    """
    Typisierte Fehlerkategorien für das strukturierte Feedback (DP3).

    Syntax-Fehler (SYNTAX_*) werden durch lxml erkannt und müssen vor
    der Soundness-Prüfung behoben werden.
    Semantische Fehler (SEMANTIC_*) werden durch pm4py/Woflan erkannt
    und betreffen die Ausführungskorrektheit des Petri-Netzes.
    """
    SYNTAX_XSD        = "syntax_xsd"           # XSD-Schema-Verletzung (lxml)
    SYNTAX_METAMODEL  = "syntax_metamodel"      # Referenzintegrität (fehlender sourceRef o.ä.)
    SEMANTIC_SOUNDNESS  = "semantic_soundness"
    SEMANTIC_DEADLOCK   = "semantic_deadlock"
    SEMANTIC_UNREACHABLE = "semantic_unreachable"


class Violation(BaseModel):
    """
    Einzelner Regelverstoß im Feedback-Protokoll (DP3).

    Violations werden als typisierte Objekte zwischen Validator und Generator
    übergeben — KEIN natürlichsprachlicher Freitext, damit der Generator
    gezielt und reproduzierbar korrigieren kann (reduziert Nicht-Determinismus).

    affected_elements enthält die konkreten BPMN-Element-IDs, die das Problem
    verursachen — so weiß der Generator exakt, welche Elemente zu korrigieren sind.
    description ist eine formale, maschinenlesbare Fehlerbeschreibung (kein Freitext).
    """
    error_type: ErrorType
    affected_elements: List[str]   # IDs der betroffenen BPMN-Elemente
    description: str               # Formale Beschreibung — kein natürlichsprachlicher Freitext (DP3)


class ValidationResult(BaseModel):
    """is_valid AND is_sound → Erfolg; sonst → nächste Iteration (DP3)."""
    is_valid: bool             # XSD-Syntax + Referenzintegrität
    is_sound: bool             # Woflan-Soundness
    violations: List[Violation]
    validation_timestamp: str  # ISO-8601 UTC

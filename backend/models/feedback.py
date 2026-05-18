"""
Pydantic-Modelle für Validierungsergebnisse.

Diese Modelle transportieren strukturiertes Feedback zwischen Validator-Agent
und Generator-Agent (DP3). Kein Freitext – alle Felder sind typisiert, um
Nicht-Determinismus im Feedback-Signal zu vermeiden.
"""

from enum import Enum
from typing import List
from pydantic import BaseModel


class ErrorType(str, Enum):
    """Klassifiziert Validierungsfehler nach Typ und Prüfebene."""
    SYNTAX_XSD = "syntax_xsd"                      # XSD-Schema-Verletzung (lxml)
    SYNTAX_METAMODEL = "syntax_metamodel"          # Referenzintegrität (z.B. fehlender sourceRef)
    SEMANTIC_SOUNDNESS = "semantic_soundness"      # Woflan: allgemeine Soundness-Verletzung
    SEMANTIC_DEADLOCK = "semantic_deadlock"        # Woflan: Deadlock gefunden
    SEMANTIC_UNREACHABLE = "semantic_unreachable"  # Woflan: Endzustand nicht erreichbar


class Violation(BaseModel):
    """
    Einzelne Regelverletzung – maschinenlesbar, kein Freitext (DP3).

    Wird vom Validator erzeugt und vom Koordinator als Feedback
    an den Generator weitergereicht.
    """
    error_type: ErrorType          # Klassifizierter Fehlertyp
    affected_elements: List[str]   # IDs der betroffenen BPMN-Elemente
    description: str               # Formale Fehlerbeschreibung


class ValidationResult(BaseModel):
    """
    Gesamtergebnis einer Validierungsrunde (Syntax + Soundness).

    Bestimmt die Terminierungsentscheidung des Koordinator-Agenten:
    is_valid AND is_sound → Erfolg, sonst → nächste Iteration.
    """
    is_valid: bool             # True wenn XSD-Syntax und Referenzintegrität korrekt
    is_sound: bool             # True wenn Woflan-Soundness bestätigt
    violations: List[Violation]
    validation_timestamp: str  # ISO-8601 UTC

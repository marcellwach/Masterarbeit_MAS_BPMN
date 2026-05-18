"""
Pydantic-Modelle für das Drei-Ebenen-Logging (DP4).

DP4 schreibt drei Logging-Ebenen vor:
  1. Ausgabeebene   – was jeder Agent ein- und ausgegeben hat
  2. Validierungsebene – Ergebnis jeder Syntax- und Soundness-Prüfung
  3. Prozessebene   – Gesamtstatus der Session (Terminierungsgrund, etc.)

Alle Einträge sind maschinenlesbar (keine Freitexte) für die automatisierte
Evaluation über evaluate.py (GZ4).
"""

from typing import List, Optional
from pydantic import BaseModel


class OutputTraceEntry(BaseModel):
    """Ausgabeebene: dokumentiert einen einzelnen Agenten-Aufruf."""
    agent_id: str          # "generator" | "validator" | "coordinator"
    iteration: int
    timestamp: str         # ISO-8601 UTC
    input_hash: str        # SHA-256 des Inputs – Reproduzierbarkeit ohne Daten zu speichern
    output_summary: str    # Erste 200 Zeichen der Ausgabe


class ValidationTraceEntry(BaseModel):
    """Validierungsebene: dokumentiert eine Syntax- oder Soundness-Prüfung."""
    iteration: int
    timestamp: str         # ISO-8601 UTC
    validation_type: str   # "syntax" | "soundness"
    passed: bool
    violations: List[dict] # Serialisierte Violation-Objekte bei Fehlern


class ProcessTraceEntry(BaseModel):
    """Prozessebene: dokumentiert den Gesamtabschluss der Session."""
    total_iterations: int
    termination_reason: str  # "success" | "max_iterations_reached"
    final_status: str        # "valid_and_sound" | "failed"
    timestamp: str           # ISO-8601 UTC


class TraceLog(BaseModel):
    """Vollständiger Log einer Generierungssession (alle drei Ebenen)."""
    session_id: str
    user_input: str
    output_entries: List[OutputTraceEntry]
    validation_entries: List[ValidationTraceEntry]
    process_entry: Optional[ProcessTraceEntry]  # None solange Session läuft
    final_bpmn_xml: Optional[str]               # Nur bei erfolgreicher Generierung

"""
Pydantic-Modelle für das Drei-Ebenen-Logging (DP4).

DP4 – Traceability:
  Jede Generierungssession wird vollständig in drei Ebenen protokolliert:
  1. Ausgabeebene       – was jeder Agent eingegeben/ausgegeben hat (OutputTraceEntry)
  2. Validierungsebene  – Ergebnis jeder Syntax- und Soundness-Prüfung (ValidationTraceEntry)
  3. Prozessebene       – Gesamtstatus der Session (ProcessTraceEntry)

  "Der Trace-Logger ist nicht optional – er ist Voraussetzung für die
   wissenschaftliche Evaluation (DP4, GZ4)." (Lastenheft §10)

GZ4 – Traceability-Vollständigkeit (Zielwert: 100%):
  Berechnung (evaluate.py): Für jede Session prüfen ob output_entries,
  validation_entries UND process_entry vorhanden sind.
  Vollständigkeit-Rate = complete_sessions / total_sessions → Zielwert: 1.0

GZ1 + GZ2 Messgrundlage:
  GZ1 (Syntaktische Konformität) = validation_entries[type="syntax"].passed / total
  GZ2 (Semantische Korrektheit)  = process_entry.termination_reason == "success" / total
"""

from typing import List, Optional
from pydantic import BaseModel


class OutputTraceEntry(BaseModel):
    """
    Ebene 1: Ausgabe-Protokoll eines Agenten (DP4).

    Protokolliert was jeder Agent in einer Iteration eingegeben und ausgegeben hat.
    Der Eingabe-Prompt wird als SHA-256-Hash gespeichert (kein Klartext), um
    API-Keys und Prompts nicht in Logs zu exponieren.
    """
    agent_id: str
    iteration: int
    timestamp: str        # ISO-8601 UTC
    input_hash: str       # SHA-256 — Reproduzierbarkeit ohne Raw-Text zu speichern
    output_summary: str   # Erste 200 Zeichen


class ValidationTraceEntry(BaseModel):
    """
    Ebene 2: Validierungs-Protokoll einer Prüfung (DP4).

    Syntax und Soundness werden als separate Einträge gespeichert, damit GZ1
    (Syntaktische Konformität) und GZ2 (Semantische Korrektheit) unabhängig
    voneinander ausgewertet werden können.
    """
    iteration: int
    timestamp: str        # ISO-8601 UTC
    validation_type: str  # "syntax" | "soundness"
    passed: bool
    violations: List[dict]


class ProcessTraceEntry(BaseModel):
    """
    Ebene 3: Prozess-Protokoll der gesamten Session (DP4).

    Wird erst am Ende der Session durch log_process_end() gesetzt.
    Enthält die für GZ2 (Konvergenzrate) und GZ4 (Traceability) relevanten Felder.
    """
    total_iterations: int
    termination_reason: str  # "success" | "max_iterations_reached"
    final_status: str        # "valid_and_sound" | "failed"
    timestamp: str           # ISO-8601 UTC


class TraceLog(BaseModel):
    """
    Vollständiger drei-Ebenen-Log einer Generierungssession (DP4).

    Aggregiert alle drei Protokollebenen in einer JSON-Datei (traces/{session_id}.json).
    process_entry ist None solange die Session noch läuft — damit ist der Log
    auch bei laufenden Sessions partiell auslesbar.
    """
    session_id: str
    user_input: str
    output_entries: List[OutputTraceEntry]
    validation_entries: List[ValidationTraceEntry]
    process_entry: Optional[ProcessTraceEntry]  # None solange Session läuft
    final_bpmn_xml: Optional[str]

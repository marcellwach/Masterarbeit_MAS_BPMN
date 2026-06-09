"""
Drei-Ebenen-Logger (DP4): Ausgabe-, Validierungs- und Prozessebene.

DP4 – Traceability:
  Schreibt nach jeder Node-Ausführung in traces/{session_id}.json.
  "Der Trace-Logger ist nicht optional – er ist Voraussetzung für die
   wissenschaftliche Evaluation (DP4, GZ4)." (Lastenheft §10)

  Drei Ebenen (entspricht den Pydantic-Modellen in models/trace.py):
    Ebene 1 – Ausgabeebene (log_output):     Was hat der Generator pro Iteration erzeugt?
    Ebene 2 – Validierungsebene (log_validation): Welche Syntax-/Soundness-Fehler gab es?
    Ebene 3 – Prozessebene (log_process_end): Wie hat die Session geendet?

GZ4 – Traceability-Vollständigkeit (Zielwert: 1.0):
  evaluate.py prüft ob alle drei Ebenen für jede Session vorhanden sind.
  Dieser Logger stellt durch seine Aufrufstruktur sicher, dass Ebene 1 + 2
  nach jeder Iteration vollständig sind und Ebene 3 bei jedem Sessionende gesetzt wird.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models.feedback import ValidationResult
from models.trace import (
    OutputTraceEntry,
    ProcessTraceEntry,
    TraceLog,
    ValidationTraceEntry,
)


class TraceLogger:
    """
    Schreibt alle Ereignisse einer Generierungssession in eine JSON-Datei (DP4).

    Drei Ebenen:
        output_entries     – Ausgaben des Generator-Agenten (Input-Hash + Output-Vorschau)
        validation_entries – Syntax- und Soundness-Prüfungsergebnisse
        process_entry      – Gesamtstatus der Session (wird am Ende gesetzt)

    Die Datei wird nach jeder Änderung vollständig neu geschrieben (_persist).
    Damit ist der Log auch bei Absturz bis zum letzten Checkpoint lesbar.
    """

    def __init__(self, session_id: str, log_dir: str = "traces"):
        self.session_id = session_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / f"{session_id}.json"

        self._output_entries: list[OutputTraceEntry] = []
        self._validation_entries: list[ValidationTraceEntry] = []
        self._process_entry: Optional[ProcessTraceEntry] = None
        self._user_input: str = ""
        self._final_bpmn_xml: Optional[str] = None

    def set_user_input(self, user_input: str) -> None:
        """Setzt die Nutzereingabe – wird vom coordinator_init_node aufgerufen."""
        self._user_input = user_input

    def log_output(self, agent_id: str, iteration: int,
                   input_data: str, output_data: str) -> None:
        """
        Protokolliert eine Agenten-Ausgabe auf der Ausgabeebene (DP4).

        Der Eingabe-Prompt wird als SHA-256-Hash gespeichert, nicht im Klartext.
        Das ermöglicht Reproduzierbarkeitsnachweis ohne API-Keys oder Prompts zu exponieren.
        """
        # Input als SHA-256 gespeichert – Reproduzierbarkeit ohne Raw-Text zu speichern
        entry = OutputTraceEntry(
            agent_id=agent_id,
            iteration=iteration,
            timestamp=_now(),
            input_hash=hashlib.sha256(input_data.encode()).hexdigest(),
            output_summary=output_data[:200]
        )
        self._output_entries.append(entry)
        self._persist()

    def log_validation(self, iteration: int, result: ValidationResult) -> None:
        """
        Protokolliert das Validierungsergebnis auf der Validierungsebene (DP4).

        Erzeugt zwei separate Einträge (Syntax + Soundness), damit GZ1 und GZ2
        unabhängig voneinander ausgewertet werden können.
        """
        # Syntax-Eintrag
        self._validation_entries.append(ValidationTraceEntry(
            iteration=iteration,
            timestamp=_now(),
            validation_type="syntax",
            passed=result.is_valid,
            violations=[v.model_dump() for v in result.violations
                        if v.error_type.value.startswith("syntax")]
        ))
        # Soundness-Eintrag
        self._validation_entries.append(ValidationTraceEntry(
            iteration=iteration,
            timestamp=_now(),
            validation_type="soundness",
            passed=result.is_sound,
            violations=[v.model_dump() for v in result.violations
                        if v.error_type.value.startswith("semantic")]
        ))
        self._persist()

    def log_process_end(self, total_iterations: int,
                        termination_reason: str,
                        final_bpmn_xml: Optional[str] = None) -> None:
        """
        Schließt den Log ab – setzt den Prozess-Eintrag auf der Prozessebene (DP4).

        Wird vom coordinator_eval_node aufgerufen, wenn die Session endet
        (Erfolg oder max_iterations_reached).
        """
        self._final_bpmn_xml = final_bpmn_xml
        self._process_entry = ProcessTraceEntry(
            total_iterations=total_iterations,
            termination_reason=termination_reason,
            final_status="valid_and_sound" if termination_reason == "success" else "failed",
            timestamp=_now()
        )
        self._persist()

    def get_full_log(self) -> TraceLog:
        """Gibt den aktuellen vollständigen TraceLog zurück (für _persist und Tests)."""
        return TraceLog(
            session_id=self.session_id,
            user_input=self._user_input,
            output_entries=self._output_entries,
            validation_entries=self._validation_entries,
            process_entry=self._process_entry,
            final_bpmn_xml=self._final_bpmn_xml
        )

    def _persist(self) -> None:
        log = self.get_full_log()
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(log.model_dump(), f, indent=2, ensure_ascii=False, default=str)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

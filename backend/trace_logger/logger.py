"""
Drei-Ebenen-Logger (DP4: Traceability).

Schreibt nach jeder Node-Ausführung einen Eintrag in eine JSON-Datei unter
traces/{session_id}.json. Die drei Ebenen sind:

  1. Ausgabeebene   (OutputTraceEntry)     – nach jedem Generator-/Validator-Aufruf
  2. Validierungsebene (ValidationTraceEntry) – nach jeder Syntax- und Soundness-Prüfung
  3. Prozessebene   (ProcessTraceEntry)    – nach Abschluss der Session

Die Logs sind maschinenlesbar und dienen der wissenschaftlichen Evaluation (GZ4).
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
    """Verwaltet den vollständigen Trace-Log einer Generierungssession."""

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
        """Setzt den originalen Nutzer-Input für den Log-Header."""
        self._user_input = user_input

    def log_output(self, agent_id: str, iteration: int,
                   input_data: str, output_data: str) -> None:
        """
        Ausgabeebene: dokumentiert einen Agenten-Aufruf.
        Input wird als SHA-256-Hash gespeichert (kein Raw-Text für Datensparsamkeit).
        """
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
        Validierungsebene: schreibt je einen Eintrag für Syntax und Soundness.
        Violations werden nach Typ gefiltert und getrennt gespeichert.
        """
        # Syntax-Eintrag: XSD + Metamodell-Verletzungen
        self._validation_entries.append(ValidationTraceEntry(
            iteration=iteration,
            timestamp=_now(),
            validation_type="syntax",
            passed=result.is_valid,
            violations=[v.model_dump() for v in result.violations
                        if v.error_type.value.startswith("syntax")]
        ))

        # Soundness-Eintrag: Woflan-Ergebnis
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
        """Prozessebene: dokumentiert den Abschluss der Session."""
        self._final_bpmn_xml = final_bpmn_xml
        self._process_entry = ProcessTraceEntry(
            total_iterations=total_iterations,
            termination_reason=termination_reason,
            final_status="valid_and_sound" if termination_reason == "success" else "failed",
            timestamp=_now()
        )
        self._persist()

    def get_full_log(self) -> TraceLog:
        """Gibt den vollständigen Log als Pydantic-Modell zurück."""
        return TraceLog(
            session_id=self.session_id,
            user_input=self._user_input,
            output_entries=self._output_entries,
            validation_entries=self._validation_entries,
            process_entry=self._process_entry,
            final_bpmn_xml=self._final_bpmn_xml
        )

    def _persist(self) -> None:
        """Schreibt den aktuellen Log-Stand atomar in die JSON-Datei."""
        log = self.get_full_log()
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(log.model_dump(), f, indent=2, ensure_ascii=False, default=str)


def _now() -> str:
    """Gibt den aktuellen Zeitstempel als ISO-8601 UTC-String zurück."""
    return datetime.now(timezone.utc).isoformat()

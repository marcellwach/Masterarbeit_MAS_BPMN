"""
Abstrakte Basisklasse für sprachspezifische Komponenten (DP5: Sprachunabhängigkeit).

DP5 beschreibt, dass die Kernarchitektur (Agenten, Feedback-Schleifen, Logging)
von der konkreten Modellierungssprache entkoppelt sein muss. Diese Klasse ist
der Koppelpunkt: ein Austausch von BpmnLanguageInterface gegen z.B.
DmnLanguageInterface erfordert keine Änderung an den Agenten.
DP5 – Sprachunabhängige Generalisierbarkeit:
  Agenten referenzieren ausschließlich diese Basisklasse — nie die konkrete BPMN-Implementierung.

Agenten referenzieren ausschließlich diese Basisklasse – nie die konkrete
BPMN-Implementierung (Dependency Inversion Principle).
  DP5-Checkliste (aus Lastenheft §7):
    ✓ LanguageInterface ist abstrakte Basisklasse (diese Datei)
    ✓ BpmnLanguageInterface implementiert alle abstrakten Methoden
    ✓ agents/ enthält keinen BPMN-spezifischen Code — nur Imports von LanguageInterface
    ✓ Ein Austausch BpmnLanguageInterface → DmnLanguageInterface erfordert
      KEINE Änderung an generator.py, validator.py oder coordinator.py

  Dependency Inversion Principle:
    High-level Modules (Agenten) hängen von Abstraktionen (LanguageInterface) ab,
    nicht von konkreten Implementierungen (BpmnLanguageInterface).
    Das macht das System auf andere Prozessmodellierungssprachen portierbar.
"""

from abc import ABC, abstractmethod
from models.feedback import ValidationResult


class LanguageInterface(ABC):
    """
    Abstrakte Basisklasse: definiert den Vertrag für alle Prozessmodellierungssprachen (DP5).

    Agenten-Nodes importieren ausschließlich diese Klasse — nie die konkreten Implementierungen.
    Dadurch kann die Zielsprache (BPMN, DMN, CMMN, …) ausgetauscht werden, ohne einen
    einzigen Agenten-Node zu modifizieren (Open/Closed Principle, Dependency Inversion).

    Jede Implementierung muss alle vier Methoden bereitstellen:
      get_tool_schema()  – Strukturkonstraint für das LLM (DP2)
      get_system_prompt()– Fachliches Expertenwissen für den Generator
      json_to_output()   – Deterministischer Konverter (kein LLM, DP2)
      validate()         – Formale Prüfung ohne LLM (DP1)
    """

    @abstractmethod
    def get_tool_schema(self) -> dict:
        """Anthropic tool_use JSON-Schema — zwingt Claude zu schema-konformem Output (DP2)."""
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Sprachspezifisches Expertenwissen für den Generator-Agent."""
        pass

    @abstractmethod
    def json_to_output(self, data: dict) -> str:
        """Deterministischer JSON → Zielsprache Konverter, kein LLM (DP2)."""
        pass

    @abstractmethod
    def validate(self, output: str) -> ValidationResult:
        """Formale Syntaxprüfung + semantische Prüfung, kein LLM (DP1)."""
        pass

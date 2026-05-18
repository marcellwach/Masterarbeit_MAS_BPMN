"""
Abstrakte Basisklasse für sprachspezifische Komponenten (DP5: Sprachunabhängigkeit).

DP5 beschreibt, dass die Kernarchitektur (Agenten, Feedback-Schleifen, Logging)
von der konkreten Modellierungssprache entkoppelt sein muss. Diese Klasse ist
der Koppelpunkt: ein Austausch von BpmnLanguageInterface gegen z.B.
DmnLanguageInterface erfordert keine Änderung an den Agenten.

Agenten referenzieren ausschließlich diese Basisklasse – nie die konkrete
BPMN-Implementierung (Dependency Inversion Principle).
"""

from abc import ABC, abstractmethod
from models.feedback import ValidationResult


class LanguageInterface(ABC):
    """
    Abstrakte Schnittstelle für eine Modellierungssprache.

    Implementierungen müssen vier Methoden bereitstellen:
      - get_tool_schema()  → Constraint-Mechanismus für den Generator (DP2)
      - get_system_prompt() → Sprachspezifisches Expertenwissen für Claude
      - json_to_output()   → Deterministischer Konverter JSON → Zielsprache
      - validate()         → Formale Syntaxprüfung + semantische Prüfung (DP1)
    """

    @abstractmethod
    def get_tool_schema(self) -> dict:
        """
        Gibt das Anthropic tool_use JSON-Schema für die Zielsprache zurück.

        Das Schema definiert die Struktur, die Claude per tool_use garantiert
        liefert (DP2: Constraint-gesteuerte Generierung). Claude kann keinen
        Output erzeugen, der nicht diesem Schema entspricht.

        Returns:
            Anthropic-kompatibles Tool-Definition-Dict mit name, description
            und input_schema.
        """
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Gibt den sprachspezifischen System-Prompt für den Generator-Agent zurück.

        Beschreibt Claude die Modellierungskonventionen der Zielsprache,
        häufige Fehler und die Regeln für valide Modelle.
        """
        pass

    @abstractmethod
    def json_to_output(self, data: dict) -> str:
        """
        Konvertiert das tool_use-Ergebnis deterministisch in die Zielsprache.

        Kein LLM-Aufruf – reine Transformation. Dies ist der zweite Teil von
        DP2: auch wenn tool_use das JSON garantiert, muss der JSON→XML-Konverter
        deterministisch und fehlerfrei sein.

        Args:
            data: tool_use input_schema-konformes JSON-Dict
        Returns:
            Vollständiger Ausgabe-String (z.B. BPMN-XML)
        """
        pass

    @abstractmethod
    def validate(self, output: str) -> ValidationResult:
        """
        Führt die vollständige formale Validierung durch (DP1: kein LLM).

        Zwei Prüfungen:
          1. Syntaxprüfung: XML-Wohlgeformtheit + XSD-Konformität (lxml)
          2. Semantische Prüfung: Soundness via Petri-Netz-Mapping (pm4py)

        Kein LLM-Aufruf – ausschließlich deterministische formale Verfahren,
        um Self-Preference Bias zu vermeiden (DP1).

        Args:
            output: Zu prüfender Ausgabe-String
        Returns:
            ValidationResult mit is_valid, is_sound und violations[]
        """
        pass

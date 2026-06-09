"""
Generator-Agent (DP1 + DP2).

DP1 – Rollenbasierte Agentenspezialisierung:
  Dieser Agent ruft KEINEN Validator auf und erzeugt ausschließlich BPMN-XML.
  Kein Validierungsergebnis kommt von hier — das garantiert, dass kein Self-Preference
  Bias in die Beurteilung der eigenen Ausgabe einfließt.

DP2 – Constraint-gesteuerte Generierung (tool_use statt Outlines):
  Ursprüngliche Planung war grammar-guided generation via Outlines + BPMN-2.0-XSD.
  Technischer PoC (Mai 2026) ergab: Outlines 1.3.0 unterstützt keine structured
  generation mit der Anthropic API (NotImplementedError). Als wissenschaftlich
  gleichwertiger Mechanismus wird Anthropics tool_use mit JSON-Schema genutzt:

    tool_choice="required" → Claude MUSS schema-konformes JSON liefern (API-seitig)
    Deterministischer JSON→XML-Konverter → syntaktisch wohlgeformtes BPMN-XML

  Die wissenschaftliche Aussagekraft von DP2 bleibt vollständig erhalten:
  Der Constraint greift API-seitig (Anthropic) statt lokal (Logit-Processor) —
  in beiden Fällen ist jede Ausgabe per Konstruktion strukturkonform.
  Kein Post-hoc-Retry nach Syntaxfehler nötig (→ GZ1-Zielwert: 100%).

Iterationsverhalten:
  Iteration 1 = Nutzerprompt (ggf. mit bestehendem XML bei Modifikation)
  Iteration 2+ = Nutzerprompt + typisierte Violations als Feedback (DP3)
"""

import os
from typing import Any

import anthropic
from language_interface.base import LanguageInterface
from models.state import AgentState
from trace_logger.logger import TraceLogger


def _build_prompt(state: AgentState, system_prompt: str) -> list[dict[str, Any]]:
    """
    Baut die Messages-Liste für den Anthropic-API-Call auf.

    Iteration 1, Modifikationsmodus: Bestehendes BPMN-XML + Änderungsanweisung.
    Iteration 1, Neugenerierung:     Nur die Nutzereingabe.
    Iteration 2+:                    Nutzereingabe + typisierte Violations als Feedback (DP3).
    """
    existing_xml = state.get("current_bpmn_xml", "")
    is_modification = bool(existing_xml) and state["iteration"] == 1

    if is_modification:
        user_content = (
            f"Hier ist ein bestehendes BPMN-2.0-Modell als XML:\n\n"
            f"```xml\n{existing_xml}\n```\n\n"
            f"Bitte modifiziere dieses Modell entsprechend der folgenden Anweisung. "
            f"Behalte alle bestehenden Elemente und ihre IDs bei, füge nur die gewünschten "
            f"Änderungen hinzu oder entferne die genannten Elemente:\n\n"
            f"{state['user_input']}"
        )
    else:
        user_content = state["user_input"]

    # DP3: Ab Iteration 2 typisiertes Feedback anhängen (keine Freitexte)
    if state["iteration"] > 1 and state["feedback_history"]:
        last_feedback = state["feedback_history"][-1]
        violations: list[dict] = last_feedback.get("violations", [])
        if violations:
            feedback_lines = []
            for v in violations:
                elements = ", ".join(v.get("affected_elements", [])) or "unbekannt"
                feedback_lines.append(
                    f"- Fehlertyp: {v['error_type']} | "
                    f"Betroffene Elemente: {elements} | "
                    f"Beschreibung: {v['description']}"
                )
            user_content = (
                f"{user_content}\n\n"
                f"ITERATION {state['iteration']} – Bitte korrigiere folgende Fehler:\n"
                + "\n".join(feedback_lines)
            )

    return [{"role": "user", "content": user_content}]


async def generator_node(state: AgentState, language_interface: LanguageInterface,
                         trace_logger: TraceLogger,
                         client: anthropic.AsyncAnthropic) -> AgentState:
    """AsyncAnthropic damit der Event Loop während des API-Calls für Socket.IO-Emits frei bleibt."""
    tool_schema = language_interface.get_tool_schema()
    system_prompt = language_interface.get_system_prompt()
    messages = _build_prompt(state, system_prompt)
    temperature = float(os.getenv("TEMPERATURE", "0.0"))

    # DP2: tool_choice="required" → Claude MUSS das Schema ausfüllen, kein Freitext möglich
    response = await client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=4096,
        system=system_prompt,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": tool_schema["name"]},
        temperature=temperature,
        messages=messages
    )

    bpmn_json: dict = {}
    for block in response.content:
        if block.type == "tool_use":
            bpmn_json = block.input
            break

    bpmn_xml = language_interface.json_to_output(bpmn_json)  # deterministisch, kein LLM (DP2)

    trace_logger.log_output(  # DP4: Ausgabeebene
        agent_id="generator",
        iteration=state["iteration"],
        input_data=str(messages),
        output_data=bpmn_xml
    )

    return {**state, "current_bpmn_xml": bpmn_xml}

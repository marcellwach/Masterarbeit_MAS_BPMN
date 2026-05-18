"""
Generator-Agent (DP1 + DP2: Spezialisierung + Constraint-gesteuerte Generierung).

Verantwortlichkeit: Generierung von BPMN-XML aus einer natürlichsprachlichen
Prozessbeschreibung via Anthropic Claude.

DP2-Mechanismus: tool_use mit JSON-Schema
  - tool_choice={"type": "tool", "name": "generate_bpmn"} zwingt Claude,
    ausschließlich schema-konformes JSON zu liefern.
  - Ein deterministischer JSON→XML-Konverter (language_interface.json_to_output)
    erzeugt das finale BPMN-XML ohne LLM-Aufruf.
  - Syntaktische Wohlgeformtheit ist per Konstruktion garantiert (kein Post-hoc-Retry).

DP1-Regel: KEIN Validator-Aufruf in diesem Agenten.

Iterationsverhalten:
  - Iteration 1: Prompt = Nutzerbeschreibung (ggf. + bestehendes XML bei Modifikation)
  - Iteration 2+: Prompt erweitert um typisierte Violation-Objekte (DP3, kein Freitext)
"""

import os
from typing import Any

import anthropic
from language_interface.base import LanguageInterface
from models.state import AgentState
from trace_logger.logger import TraceLogger


def _build_prompt(state: AgentState, system_prompt: str) -> list[dict[str, Any]]:
    """
    Baut den Message-Array für den Claude API-Call auf.

    Bei Modifikationen (bestehendes XML vorhanden) wird das XML als Kontext
    in den Prompt eingebettet. Ab Iteration 2 werden Violation-Objekte als
    strukturiertes Feedback angehängt (DP3).
    """
    existing_xml = state.get("current_bpmn_xml", "")
    # Modifikationsmodus: bestehendes Modell als Ausgangspunkt übergeben
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
    """
    Generiert BPMN via Anthropic tool_use (async, DP2).

    Verwendet AsyncAnthropic damit der asyncio Event Loop während des API-Calls
    nicht blockiert wird – Socket.IO kann währenddessen Statusmeldungen senden.
    """
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

    # Extrahiere tool_use-Block (durch tool_choice garantiert vorhanden)
    bpmn_json: dict = {}
    for block in response.content:
        if block.type == "tool_use":
            bpmn_json = block.input
            break

    # Deterministischer JSON → BPMN-XML Konverter (kein LLM, DP2)
    bpmn_xml = language_interface.json_to_output(bpmn_json)

    # DP4: Ausgabeebene loggen
    trace_logger.log_output(
        agent_id="generator",
        iteration=state["iteration"],
        input_data=str(messages),
        output_data=bpmn_xml
    )

    return {**state, "current_bpmn_xml": bpmn_xml}

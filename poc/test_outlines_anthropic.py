"""
PoC: Outlines + Anthropic API – Technische Risikovalidierung für DP2

Ziel: Prüfen welcher Ansatz für Constraint-gesteuerte BPMN-Generierung
      mit der Anthropic API funktioniert.

Ergebnisse werden in poc_results.json gespeichert.

Führe aus mit:
    python poc/test_outlines_anthropic.py

ANTHROPIC_API_KEY muss als Umgebungsvariable gesetzt sein.
"""

import io
import json
import os
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import anthropic
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-4-6"

RESULTS_FILE = Path(__file__).parent / "poc_results.json"

results: dict = {}

SIMPLE_PROMPT = (
    "Beschreibe einen einfachen Urlaubsantrag-Prozess als BPMN 2.0 XML. "
    "Der Prozess: Mitarbeiter stellt Antrag → Manager prüft → Genehmigt oder Abgelehnt → Ende."
)


# ---------------------------------------------------------------------------
# Test 1: Outlines + Anthropic API – Structured Generation
# ---------------------------------------------------------------------------
def test_1_outlines_structured():
    print("\n" + "=" * 60)
    print("TEST 1: Outlines structured generation mit Anthropic API")
    print("=" * 60)
    try:
        import outlines
        client = anthropic.Anthropic(api_key=API_KEY)
        model = outlines.Anthropic(client, model_name=MODEL)

        # Versuche structured generation mit einem einfachen Pydantic-Modell
        from pydantic import BaseModel
        from typing import List

        class BpmnElement(BaseModel):
            id: str
            type: str
            name: str

        class BpmnModel(BaseModel):
            process_id: str
            elements: List[BpmnElement]

        generator = outlines.Generator(model, BpmnModel)
        result = generator(SIMPLE_PROMPT)

        print(f"✓ Structured generation FUNKTIONIERT: {result}")
        results["test_1"] = {"status": "success", "result": str(result), "approach": "outlines_structured"}
        return True

    except Exception as e:
        print(f"✗ Structured generation FEHLGESCHLAGEN: {e}")
        results["test_1"] = {"status": "failed", "error": str(e)}
        return False


# ---------------------------------------------------------------------------
# Test 2: Anthropic tool_use mit BPMN JSON-Schema (DP2-Hauptkandidat)
# ---------------------------------------------------------------------------
def test_2_tool_use_json_schema():
    print("\n" + "=" * 60)
    print("TEST 2: Anthropic tool_use mit BPMN JSON-Schema")
    print("=" * 60)
    try:
        client = anthropic.Anthropic(api_key=API_KEY)

        # JSON-Schema das BPMN-Struktur beschreibt
        bpmn_schema = {
            "name": "generate_bpmn",
            "description": "Generiert ein BPMN 2.0 Prozessmodell als strukturiertes JSON",
            "input_schema": {
                "type": "object",
                "properties": {
                    "process_id": {
                        "type": "string",
                        "description": "Eindeutige ID des Prozesses (z.B. 'Process_1')"
                    },
                    "process_name": {
                        "type": "string",
                        "description": "Name des Prozesses"
                    },
                    "start_events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"}
                            },
                            "required": ["id", "name"]
                        }
                    },
                    "end_events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"}
                            },
                            "required": ["id", "name"]
                        }
                    },
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"}
                            },
                            "required": ["id", "name"]
                        }
                    },
                    "gateways": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["exclusiveGateway", "parallelGateway", "inclusiveGateway"]
                                }
                            },
                            "required": ["id", "name", "type"]
                        }
                    },
                    "sequence_flows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "source_ref": {"type": "string"},
                                "target_ref": {"type": "string"},
                                "name": {"type": "string"}
                            },
                            "required": ["id", "source_ref", "target_ref"]
                        }
                    }
                },
                "required": ["process_id", "process_name", "start_events", "end_events", "tasks", "sequence_flows"]
            }
        }

        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            tools=[bpmn_schema],
            tool_choice={"type": "tool", "name": "generate_bpmn"},
            messages=[{
                "role": "user",
                "content": SIMPLE_PROMPT
            }]
        )

        # Extrahiere tool_use Ergebnis
        tool_result = None
        for block in response.content:
            if block.type == "tool_use":
                tool_result = block.input
                break

        if tool_result:
            print(f"✓ tool_use FUNKTIONIERT")
            print(f"  Prozess: {tool_result.get('process_name')}")
            print(f"  Tasks: {[t['name'] for t in tool_result.get('tasks', [])]}")
            print(f"  Flows: {len(tool_result.get('sequence_flows', []))}")

            # Konvertiere JSON → BPMN XML
            bpmn_xml = json_to_bpmn_xml(tool_result)
            print(f"  XML generiert: {len(bpmn_xml)} Zeichen")

            results["test_2"] = {
                "status": "success",
                "approach": "tool_use_json_schema",
                "json_output": tool_result,
                "xml_length": len(bpmn_xml),
                "xml_preview": bpmn_xml[:300]
            }
            return True, bpmn_xml
        else:
            raise ValueError("Kein tool_use Block in Response")

    except Exception as e:
        print(f"✗ tool_use FEHLGESCHLAGEN: {e}")
        results["test_2"] = {"status": "failed", "error": str(e)}
        return False, None


def json_to_bpmn_xml(data: dict) -> str:
    """Deterministischer JSON → BPMN-XML Konverter."""
    process_id = data.get("process_id", "Process_1")
    process_name = data.get("process_name", "Process")

    elements = []

    for se in data.get("start_events", []):
        outgoing = [f["id"] for f in data.get("sequence_flows", []) if f["source_ref"] == se["id"]]
        out_xml = "".join(f"<outgoing>{fid}</outgoing>" for fid in outgoing)
        elements.append(f'<startEvent id="{se["id"]}" name="{se["name"]}">{out_xml}</startEvent>')

    for task in data.get("tasks", []):
        incoming = [f["id"] for f in data.get("sequence_flows", []) if f["target_ref"] == task["id"]]
        outgoing = [f["id"] for f in data.get("sequence_flows", []) if f["source_ref"] == task["id"]]
        in_xml = "".join(f"<incoming>{fid}</incoming>" for fid in incoming)
        out_xml = "".join(f"<outgoing>{fid}</outgoing>" for fid in outgoing)
        elements.append(f'<task id="{task["id"]}" name="{task["name"]}">{in_xml}{out_xml}</task>')

    for gw in data.get("gateways", []):
        incoming = [f["id"] for f in data.get("sequence_flows", []) if f["target_ref"] == gw["id"]]
        outgoing = [f["id"] for f in data.get("sequence_flows", []) if f["source_ref"] == gw["id"]]
        in_xml = "".join(f"<incoming>{fid}</incoming>" for fid in incoming)
        out_xml = "".join(f"<outgoing>{fid}</outgoing>" for fid in outgoing)
        gw_type = gw.get("type", "exclusiveGateway")
        elements.append(
            f'<{gw_type} id="{gw["id"]}" name="{gw["name"]}" isMarkerVisible="true">'
            f'{in_xml}{out_xml}</{gw_type}>'
        )

    for ee in data.get("end_events", []):
        incoming = [f["id"] for f in data.get("sequence_flows", []) if f["target_ref"] == ee["id"]]
        in_xml = "".join(f"<incoming>{fid}</incoming>" for fid in incoming)
        elements.append(f'<endEvent id="{ee["id"]}" name="{ee["name"]}">{in_xml}</endEvent>')

    for flow in data.get("sequence_flows", []):
        name_attr = f' name="{flow["name"]}"' if flow.get("name") else ""
        elements.append(
            f'<sequenceFlow id="{flow["id"]}" '
            f'sourceRef="{flow["source_ref"]}" '
            f'targetRef="{flow["target_ref"]}"{name_attr}/>'
        )

    elements_xml = "\n    ".join(elements)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             id="Definitions_1"
             targetNamespace="http://bpmn.io/schema/bpmn">
  <process id="{process_id}" name="{process_name}" isExecutable="true">
    {elements_xml}
  </process>
</definitions>"""


# ---------------------------------------------------------------------------
# Test 3: XSD-Validierung mit lxml
# ---------------------------------------------------------------------------
def test_3_lxml_validation(bpmn_xml: str | None):
    print("\n" + "=" * 60)
    print("TEST 3: lxml XSD-Validierung")
    print("=" * 60)
    try:
        from lxml import etree

        if not bpmn_xml:
            print("  Übersprungen – kein XML aus Test 2")
            results["test_3"] = {"status": "skipped"}
            return

        # Prüfe ob lxml XML parsen kann (Wohlgeformtheit)
        root = etree.fromstring(bpmn_xml.encode())
        print(f"✓ XML wohlgeformt, Root-Element: {root.tag}")

        # Versuche XSD-Validierung (falls XSD vorhanden)
        xsd_path = Path(__file__).parent.parent / "backend" / "grammar" / "bpmn20.xsd"
        if xsd_path.exists():
            with open(xsd_path, "rb") as f:
                xsd_doc = etree.parse(f)
            xsd = etree.XMLSchema(xsd_doc)
            is_valid = xsd.validate(root)
            print(f"  XSD-Validierung: {'✓ Valide' if is_valid else '✗ Fehler: ' + str(xsd.error_log)}")
            results["test_3"] = {"status": "success", "well_formed": True, "xsd_valid": is_valid}
        else:
            print("  XSD-Datei noch nicht vorhanden – nur Wohlgeformtheit geprüft")
            results["test_3"] = {"status": "success", "well_formed": True, "xsd_valid": None}

    except Exception as e:
        print(f"✗ lxml FEHLGESCHLAGEN: {e}")
        results["test_3"] = {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------
def main():
    if not API_KEY:
        print("FEHLER: ANTHROPIC_API_KEY nicht gesetzt.")
        print("Setze die Variable in einer .env Datei im Projektroot oder als Umgebungsvariable.")
        sys.exit(1)

    print("=" * 60)
    print("PoC: Outlines + Anthropic API für BPMN-Generierung (DP2)")
    print("=" * 60)
    print(f"Modell: {MODEL}")
    print(f"Outlines-Version: ", end="")
    import outlines
    print(outlines.__version__ if hasattr(outlines, "__version__") else "unbekannt")

    # Tests ausführen
    test_1_outlines_structured()
    time.sleep(1)

    success, bpmn_xml = test_2_tool_use_json_schema()
    time.sleep(1)

    test_3_lxml_validation(bpmn_xml)

    # Empfehlung
    print("\n" + "=" * 60)
    print("FAZIT & EMPFEHLUNG FÜR DP2")
    print("=" * 60)

    t1_ok = results.get("test_1", {}).get("status") == "success"
    t2_ok = results.get("test_2", {}).get("status") == "success"

    if t1_ok:
        recommendation = "Fall A: Outlines structured generation mit Anthropic API funktioniert direkt."
        approach = "outlines_structured"
    elif t2_ok:
        recommendation = (
            "Fall C: Outlines unterstützt keine structured generation mit Anthropic API.\n"
            "  → EMPFEHLUNG: Anthropic tool_use mit JSON-Schema als Constraint-Mechanismus (DP2).\n"
            "  → Der Generator-Agent erzwingt BPMN-Struktur via tool_choice='required'.\n"
            "  → Ein deterministischer JSON→XML-Konverter erzeugt das finale BPMN-XML.\n"
            "  → DP2 bleibt erhalten: Constraint-gesteuerte Generierung via API-seitigem Schema-Enforcement."
        )
        approach = "tool_use_json_schema"
    else:
        recommendation = "Alle Ansätze fehlgeschlagen – manuelle Diagnose erforderlich."
        approach = "none"

    print(recommendation)
    results["recommendation"] = {"approach": approach, "text": recommendation}

    # Ergebnisse speichern
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nErgebnisse gespeichert in: {RESULTS_FILE}")

    if bpmn_xml:
        xml_file = Path(__file__).parent / "poc_bpmn_output.xml"
        with open(xml_file, "w", encoding="utf-8") as f:
            f.write(bpmn_xml)
        print(f"Generiertes BPMN-XML gespeichert in: {xml_file}")


if __name__ == "__main__":
    main()

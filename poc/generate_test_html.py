import sys
sys.path.insert(0, '../backend')
from language_interface.bpmn import BpmnLanguageInterface

li = BpmnLanguageInterface()
data = {
    'process_id': 'Process_1', 'process_name': 'Urlaub',
    'start_events': [{'id': 'StartEvent_1', 'name': 'Antrag eingereicht'}],
    'end_events': [{'id': 'EndEvent_1', 'name': 'Prozess beendet'}],
    'tasks': [
        {'id': 'Task_1', 'name': 'Antrag pruefen'},
        {'id': 'Task_2', 'name': 'Genehmigung mitteilen'}
    ],
    'gateways': [{'id': 'Gateway_1', 'name': 'Genehmigt', 'type': 'exclusiveGateway'}],
    'sequence_flows': [
        {'id': 'Flow_1', 'source_ref': 'StartEvent_1', 'target_ref': 'Task_1'},
        {'id': 'Flow_2', 'source_ref': 'Task_1', 'target_ref': 'Gateway_1'},
        {'id': 'Flow_3', 'source_ref': 'Gateway_1', 'target_ref': 'Task_2', 'name': 'Ja'},
        {'id': 'Flow_4', 'source_ref': 'Gateway_1', 'target_ref': 'EndEvent_1', 'name': 'Nein'},
        {'id': 'Flow_5', 'source_ref': 'Task_2', 'target_ref': 'EndEvent_1'},
    ]
}
xml = li.json_to_output(data)

# Escape backticks and backslashes for JS template literal
xml_js = xml.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')

html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>BPMN Test</title>
  <link rel="stylesheet" href="https://unpkg.com/bpmn-js@17/dist/assets/diagram-js.css">
  <link rel="stylesheet" href="https://unpkg.com/bpmn-js@17/dist/assets/bpmn-js.css">
  <link rel="stylesheet" href="https://unpkg.com/bpmn-js@17/dist/assets/bpmn-font/css/bpmn-embedded.css">
  <style>
    body {{ margin: 0; }}
    #canvas {{ width: 100vw; height: 100vh; background: #f8f9fa; }}
    #status {{ position: fixed; top: 10px; left: 10px; background: #222; color: #0f0;
               padding: 8px 12px; font-family: monospace; font-size: 13px; z-index: 100; border-radius: 4px; }}
  </style>
</head>
<body>
  <div id="canvas"></div>
  <div id="status">Lade bpmn-js...</div>
  <script src="https://unpkg.com/bpmn-js@17/dist/bpmn-viewer.development.js"></script>
  <script>
    const xml = `{xml_js}`;
    const viewer = new BpmnJS({{ container: '#canvas' }});
    document.getElementById('status').textContent = 'XML: ' + xml.length + ' Zeichen – importiere...';

    viewer.importXML(xml)
      .then(function(result) {{
        var warnings = result.warnings;
        document.getElementById('status').style.background = '#060';
        document.getElementById('status').textContent = 'OK – warnings: ' + warnings.length;
        viewer.get('canvas').zoom('fit-viewport');
      }})
      .catch(function(err) {{
        document.getElementById('status').style.background = '#600';
        document.getElementById('status').textContent = 'FEHLER: ' + err.message;
        console.error(err);
      }});
  </script>
</body>
</html>"""

with open('../test_viewer_inline.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Geschrieben: test_viewer_inline.html')
print('XML Laenge:', len(xml))

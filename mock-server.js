const { Server } = require("socket.io");
const http = require("http");

const server = http.createServer();
const io = new Server(server, {
  cors: { origin: "http://localhost:3000" },
});

const MOCK_BPMN = `<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
             xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
             id="Definitions_1"
             targetNamespace="http://bpmn.io/schema/bpmn">
  <process id="Process_1" isExecutable="true">
    <startEvent id="StartEvent_1" name="Urlaubsantrag eingereicht">
      <outgoing>Flow_1</outgoing>
    </startEvent>
    <task id="Task_1" name="Antrag prüfen">
      <incoming>Flow_1</incoming>
      <outgoing>Flow_2</outgoing>
    </task>
    <exclusiveGateway id="Gateway_1" name="Genehmigt?">
      <incoming>Flow_2</incoming>
      <outgoing>Flow_3</outgoing>
      <outgoing>Flow_4</outgoing>
    </exclusiveGateway>
    <task id="Task_2" name="Genehmigung mitteilen">
      <incoming>Flow_3</incoming>
      <outgoing>Flow_5</outgoing>
    </task>
    <task id="Task_3" name="Ablehnung mitteilen">
      <incoming>Flow_4</incoming>
      <outgoing>Flow_6</outgoing>
    </task>
    <endEvent id="EndEvent_1" name="Prozess abgeschlossen">
      <incoming>Flow_5</incoming>
      <incoming>Flow_6</incoming>
    </endEvent>
    <sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_1"/>
    <sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="Gateway_1"/>
    <sequenceFlow id="Flow_3" sourceRef="Gateway_1" targetRef="Task_2" name="Ja"/>
    <sequenceFlow id="Flow_4" sourceRef="Gateway_1" targetRef="Task_3" name="Nein"/>
    <sequenceFlow id="Flow_5" sourceRef="Task_2" targetRef="EndEvent_1"/>
    <sequenceFlow id="Flow_6" sourceRef="Task_3" targetRef="EndEvent_1"/>
  </process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="152" y="82" width="36" height="36"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Task_1_di" bpmnElement="Task_1">
        <dc:Bounds x="240" y="60" width="100" height="80"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Gateway_1_di" bpmnElement="Gateway_1" isMarkerVisible="true">
        <dc:Bounds x="395" y="75" width="50" height="50"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Task_2_di" bpmnElement="Task_2">
        <dc:Bounds x="500" y="20" width="100" height="80"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Task_3_di" bpmnElement="Task_3">
        <dc:Bounds x="500" y="130" width="100" height="80"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="662" y="82" width="36" height="36"/>
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_1_di" bpmnElement="Flow_1">
        <di:waypoint x="188" y="100"/>
        <di:waypoint x="240" y="100"/>
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_2_di" bpmnElement="Flow_2">
        <di:waypoint x="340" y="100"/>
        <di:waypoint x="395" y="100"/>
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_3_di" bpmnElement="Flow_3">
        <di:waypoint x="420" y="75"/>
        <di:waypoint x="420" y="60"/>
        <di:waypoint x="500" y="60"/>
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_4_di" bpmnElement="Flow_4">
        <di:waypoint x="420" y="125"/>
        <di:waypoint x="420" y="170"/>
        <di:waypoint x="500" y="170"/>
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_5_di" bpmnElement="Flow_5">
        <di:waypoint x="600" y="60"/>
        <di:waypoint x="680" y="60"/>
        <di:waypoint x="680" y="100"/>
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_6_di" bpmnElement="Flow_6">
        <di:waypoint x="600" y="170"/>
        <di:waypoint x="680" y="170"/>
        <di:waypoint x="680" y="118"/>
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</definitions>`;

io.on("connection", (socket) => {
  console.log("Client connected:", socket.id);

  socket.on("generate_bpmn", (data) => {
    console.log("Received generate_bpmn:", data.prompt);

    const delay = (ms) => new Promise((r) => setTimeout(r, ms));

    (async () => {
      await delay(500);
      socket.emit("status_update", { message: "Iteration 1: BPMN wird generiert...", iteration: 1 });
      await delay(1200);
      socket.emit("status_update", { message: "Iteration 1: Syntaxvalidierung läuft...", iteration: 1 });
      await delay(800);
      socket.emit("status_update", { message: "Iteration 1: Soundness-Prüfung läuft...", iteration: 1 });
      await delay(600);
      socket.emit("bpmn_result", { bpmn_xml: MOCK_BPMN });
    })();
  });

  socket.on("disconnect", () => {
    console.log("Client disconnected:", socket.id);
  });
});

server.listen(8000, () => {
  console.log("Mock-Backend läuft auf http://localhost:8000");
});

import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root
  property var settings: ({})
  property bool busy: scanProcess.running || actionProcess.running
  property string busyLabel: ""

  readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl(".")).replace(/^file:\/\//, "").replace(/\/$/, ""))
  readonly property string binPath: pluginDir + "/bin"

  property var localIps: []
  property string primaryLocalIp: ""
  property string tailscaleIp: ""
  property int serverCount: 0
  property var servers: []
  property var stacks: []
  property var stoppedStacks: []
  property string errorText: ""

  function refresh() {
    errorText = ""
    busyLabel = ""
    scanProcess.command = ["python3", binPath + "/scan-servers.py"]
    scanProcess.running = true
  }

  function runAction(label, command) {
    errorText = ""
    busyLabel = label
    actionProcess.command = command
    actionProcess.running = true
  }

  function killServer(server) {
    if (!server) return
    var stackId = String(server.stack || "")
    if (stackId !== "") {
      runAction("Stopping " + server.name + "…", ["python3", binPath + "/stack.py", "stop", stackId])
      return
    }
    var unit = String(server.unit || "")
    var p = parseInt(String(server.pid || 0), 10)
    if (unit !== "" && server.stoppable !== false) {
      runAction("Stopping " + (server.name || "service") + "…", ["systemctl", "--user", "stop", unit])
    } else if (p > 0) {
      // start-time token from the scan: kill-tree.py verifies it, so a recycled PID is never killed
      var st = parseInt(String(server.starttime === undefined || server.starttime === null ? "" : server.starttime), 10)
      runAction("Killing " + (server.name || "process") + "…", ["python3", binPath + "/kill-tree.py", String(p), String(isNaN(st) ? -1 : st)])
    }
  }

  function startStack(id, name) {
    runAction("Starting " + (name || "stack") + "…", ["python3", binPath + "/stack.py", "start", String(id)])
  }

  property int refreshSec: {
    var s = settings ? settings.refreshSec : undefined
    return (s !== undefined && s !== null && s > 0) ? s : 30
  }

  Timer {
    id: refreshTimer
    interval: root.refreshSec * 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Process {
    id: scanProcess
    running: false
    command: []
    stdout: StdioCollector { id: scanStdout; waitForEnd: true; onStreamFinished: root.parseScan(String(scanStdout.text || "")) }
    onExited: function(exitCode) {
      if (exitCode !== 0 && root.errorText === "") root.errorText = "Scan failed (exit " + exitCode + ")"
    }
  }

  Process {
    id: actionProcess
    running: false
    command: []
    stdout: StdioCollector { id: actionStdout; waitForEnd: true }
    stderr: StdioCollector { id: actionStderr; waitForEnd: true; onStreamFinished: if (String(actionStderr.text || "").trim() !== "") root.errorText = String(actionStderr.text).trim() }
    onExited: function(exitCode) {
      if (exitCode !== 0 && root.errorText === "") root.errorText = "Action failed (exit " + exitCode + ")"
      root.busyLabel = ""
      Qt.callLater(function() { root.refresh() })
    }
  }

  function parseScan(raw) {
    try {
      var data = JSON.parse(String(raw || "{}"))
      root.localIps = data.local_ips || []
      root.primaryLocalIp = data.primary_local_ip || ""
      root.tailscaleIp = data.tailscale_ip || ""
      root.servers = data.servers || []
      root.serverCount = (data.servers || []).length
      var allStacks = data.stacks || []
      var stopped = []
      for (var i = 0; i < allStacks.length; i++) {
        if (allStacks[i].state === "stopped") stopped.push(allStacks[i])
      }
      root.stacks = allStacks
      root.stoppedStacks = stopped
      root.errorText = ""
    } catch (e) {
      root.errorText = "Parse error"
    }
  }

  Component.onCompleted: Qt.callLater(root.refresh)
}

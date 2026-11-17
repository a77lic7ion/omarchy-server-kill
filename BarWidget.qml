import QtQuick
import Quickshell
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "shaun.server-kill"

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  readonly property bool opened: panelLoader.item ? (panelLoader.item.opened === true) : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? (panelLoader.item.popoutSwitchClosing === true) : false

  function open() { if (panelLoader.item && panelLoader.item.open) panelLoader.item.open() }
  function close() { if (panelLoader.item && panelLoader.item.close) panelLoader.item.close() }
  function toggle() { if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle() }
  function closeForPopoutSwitch() { if (panelLoader.item && panelLoader.item.closeForPopoutSwitch) panelLoader.item.closeForPopoutSwitch() }
  function refresh() { if (service) service.refresh() }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Service {
    id: service
    settings: root.settings
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: { root.injectPanel(); Qt.callLater(root.injectPanel) }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: service.serverCount > 0 ? ("\uf2c2 " + service.serverCount) : "\uf2c2"
    tooltipText: {
      var parts = []
      if (service.localIpsText) parts.push("Local: " + service.localIpsText)
      if (service.tailscaleUrl) parts.push("Tail: " + service.tailscaleUrl)
      if (service.serverCount > 0) parts.push(service.serverCount + " server" + (service.serverCount > 1 ? "s" : ""))
      if (service.errorText) parts.push("Err: " + service.errorText)
      return (parts.length > 0 ? parts.join("  ·  ") : "Server Kill")
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.toggle()
      else if (buttonCode === Qt.RightButton) service.refresh()
    }
  }
}

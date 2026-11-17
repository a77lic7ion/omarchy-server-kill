import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "shaun.server-kill"
  ipcTarget: "shaun.server-kill"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null

  readonly property color foreground: Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.3)
  readonly property color urgent: Color.urgent
  readonly property color accent: Color.accent
  readonly property string fontFamily: Style.font.family
  readonly property color cardBg: Color.popups.background
  readonly property color cardBorder: Color.popups.border

  Service {
    id: service
    settings: root.settings
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { service.refresh(); return "ok" }
  }

  onOpenedChanged: {
    if (opened) {
      service.refresh()
      Qt.callLater(function() { if (keyCatcher) keyCatcher.forceActiveFocus() })
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(600))
    contentHeight: panel.fittedContentHeight(column.implicitHeight + Style.space(24), Style.space(700))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTextKey: function(t) { if (t === "r" || t === "R") service.refresh() }
    }

    Flickable {
      id: panelFlick
      anchors.fill: parent
      contentWidth: width
      contentHeight: column.implicitHeight + Style.space(24)
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      flickableDirection: Flickable.VerticalFlick
      interactive: contentHeight > height
      ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

      Column {
        id: column
        width: panelFlick.width - Style.space(24)
        x: Style.space(12)
        y: Style.space(4)
        spacing: Style.space(14)

        // ---- Header ----
        RowLayout {
          width: parent.width
          spacing: Style.space(12)

          Text {
            text: "Server Kill"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            verticalAlignment: Text.AlignVCenter
          }

          Text {
            Layout.fillWidth: true
            text: service.busy ? (service.busyLabel !== "" ? service.busyLabel : "Scanning…") : (service.serverCount + " running")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter
          }

          Text {
            text: "Refresh"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            verticalAlignment: Text.AlignVCenter
            MouseArea {
              anchors.fill: parent
              anchors.margins: -Style.space(6)
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: service.refresh()
            }
          }
        }

        // ---- Global addresses ----
        RowLayout {
          width: parent.width
          spacing: Style.space(10)

          Text {
            text: "Local " + (service.primaryLocalIp || "—")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
          Text {
            visible: service.tailscaleIp !== ""
            Layout.fillWidth: true
            text: "Tailscale " + service.tailscaleIp
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
        }

        Rectangle {
          width: parent.width
          height: 1
          color: root.cardBorder
        }

        // ---- Empty / error ----
        Text {
          visible: service.errorText !== ""
          width: parent.width
          text: service.errorText
          color: root.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.WordWrap
        }

        Text {
          visible: !service.busy && service.serverCount === 0 && service.errorText === "" && (service.stoppedStacks || []).length === 0
          width: parent.width
          text: "No listening servers found."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          horizontalAlignment: Text.AlignHCenter
          topPadding: Style.space(20)
          bottomPadding: Style.space(20)
        }

        // ---- Stopped stacks ----
        Repeater {
          model: service.stoppedStacks || []
          delegate: Rectangle {
            width: column.width
            height: stoppedContent.implicitHeight + Style.space(28)
            radius: Style.cornerRadius
            color: root.cardBg
            border.color: root.cardBorder
            border.width: 1

            property var stack: modelData

            ColumnLayout {
              id: stoppedContent
              width: parent.width - Style.space(24)
              x: Style.space(12)
              y: Style.space(14)
              spacing: Style.space(6)

              Item {
                width: parent.width
                height: Style.space(26)

                Text {
                  id: stoppedName
                  anchors.left: parent.left
                  anchors.verticalCenter: parent.verticalCenter
                  width: Math.max(0, parent.width - stoppedTrailing.width - Style.space(12))
                  text: stack.name
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: true
                  elide: Text.ElideRight
                }

                Row {
                  id: stoppedTrailing
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  spacing: Style.space(12)

                  Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "stopped"
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }

                  Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: startLabel.implicitWidth + Style.space(20)
                    height: Style.space(26)
                    radius: Style.cornerRadius
                    color: startArea.containsMouse ? root.accent : "transparent"
                    border.color: root.accent
                    border.width: 1

                    Text {
                      id: startLabel
                      anchors.centerIn: parent
                      text: "Start"
                      color: startArea.containsMouse ? Color.background : root.accent
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      font.bold: true
                    }

                    MouseArea {
                      id: startArea
                      anchors.fill: parent
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: service.startStack(stack.id, stack.name)
                    }
                  }
                }
              }

              Text {
                visible: (stack.description || "") !== ""
                Layout.fillWidth: true
                text: stack.description
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
              }
            }
          }
        }

        // ---- Server cards ----
        Repeater {
          model: service.servers || []
          delegate: Rectangle {
            width: column.width
            height: cardContent.implicitHeight + Style.space(28)
            radius: Style.cornerRadius
            color: root.cardBg
            border.color: root.cardBorder
            border.width: 1

            property var server: modelData

            ColumnLayout {
              id: cardContent
              width: parent.width - Style.space(24)
              x: Style.space(12)
              y: Style.space(14)
              spacing: Style.space(6)

              // Title row
              RowLayout {
                width: parent.width
                spacing: Style.space(12)

                Text {
                  Layout.fillWidth: true
                  text: server.name
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  font.bold: true
                  elide: Text.ElideRight
                }

                Text {
                  text: "PID " + String(server.pid || "?")
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }

                Rectangle {
                  width: killLabel.implicitWidth + Style.space(20)
                  height: Style.space(26)
                  radius: Style.cornerRadius
                  color: killArea.containsMouse ? root.urgent : "transparent"
                  border.color: root.urgent
                  border.width: 1

                  Text {
                    id: killLabel
                    anchors.centerIn: parent
                    text: "Kill"
                    color: killArea.containsMouse ? Color.background : root.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.bold: true
                  }

                  MouseArea {
                    id: killArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    enabled: (server.pid || 0) > 0 || String(server.stack || "") !== ""
                    onClicked: service.killServer(server)
                  }
                }
              }

              // URL rows (one per port)
              Repeater {
                model: server.entries || []
                delegate: RowLayout {
                  width: cardContent.width
                  spacing: Style.space(10)

                  Text {
                    text: ":" + String(modelData.port)
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    Layout.minimumWidth: Style.space(46)
                  }

                  Text {
                    Layout.fillWidth: true
                    text: modelData.local_url
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    elide: Text.ElideRight
                    MouseArea {
                      anchors.fill: parent
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: Quickshell.execDetached(["omarchy-launch-browser", modelData.local_url])
                    }
                  }

                  Text {
                    visible: modelData.tail_url !== ""
                    Layout.maximumWidth: Style.space(240)
                    text: modelData.tail_url
                    color: root.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    elide: Text.ElideRight
                    MouseArea {
                      anchors.fill: parent
                      hoverEnabled: true
                      cursorShape: Qt.PointingHandCursor
                      onClicked: Quickshell.execDetached(["omarchy-launch-browser", modelData.tail_url])
                    }
                  }

                  Text {
                    visible: modelData.tail_url === ""
                    text: "localhost"
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}

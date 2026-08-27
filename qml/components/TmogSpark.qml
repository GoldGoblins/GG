import QtQuick

Item {
    id: root
    property var values: []
    property color stroke: "#8db89a"
    property color fill: "#1c2a22"
    property color grid: "#242424"
    property real yMax: 0

    Canvas {
        id: plot
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            var w = width
            var h = height
            ctx.clearRect(0, 0, w, h)
            if (w < 8 || h < 8)
                return
            var gx
            var gy
            ctx.strokeStyle = root.grid
            ctx.lineWidth = 1
            for (gx = 0; gx <= 6; gx++) {
                var x = gx / 6 * w
                ctx.beginPath()
                ctx.moveTo(x, 0)
                ctx.lineTo(x, h)
                ctx.stroke()
            }
            for (gy = 0; gy <= 4; gy++) {
                var y = gy / 4 * h
                ctx.beginPath()
                ctx.moveTo(0, y)
                ctx.lineTo(w, y)
                ctx.stroke()
            }
            var pts = root.values
            if (!pts || pts.length < 1)
                return
            var maxv = Number(root.yMax || 0)
            var i
            for (i = 0; i < pts.length; i++) {
                var v = Number(pts[i] || 0)
                if (v > maxv)
                    maxv = v
            }
            if (maxv <= 0)
                maxv = 1
            var last = pts.length < 2 ? 2 : pts.length
            ctx.beginPath()
            ctx.moveTo(0, h)
            for (i = 0; i < pts.length; i++) {
                var px = (pts.length === 1 ? 1 : i / (last - 1)) * w
                var py = h - (Number(pts[i] || 0) / maxv) * (h - 3) - 1
                ctx.lineTo(px, py)
            }
            ctx.lineTo(w, h)
            ctx.closePath()
            ctx.fillStyle = root.fill
            ctx.fill()
            ctx.beginPath()
            for (i = 0; i < pts.length; i++) {
                var sx = (pts.length === 1 ? 1 : i / (last - 1)) * w
                var sy = h - (Number(pts[i] || 0) / maxv) * (h - 3) - 1
                if (i === 0)
                    ctx.moveTo(sx, sy)
                else
                    ctx.lineTo(sx, sy)
            }
            ctx.strokeStyle = root.stroke
            ctx.lineWidth = 1.4
            ctx.stroke()
        }
    }

    onValuesChanged: plot.requestPaint()
    onYMaxChanged: plot.requestPaint()
    onWidthChanged: plot.requestPaint()
    onHeightChanged: plot.requestPaint()
}

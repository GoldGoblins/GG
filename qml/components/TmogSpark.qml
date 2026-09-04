import QtQuick

Item {
    id: root
    property var values: []
    property var marks: []
    property color stroke: "#8db89a"
    property color fill: "#1c2a22"
    property color grid: "#242424"
    property real yMax: 0
    property bool fromZero: true

    function redraw() {
        if (!root.visible)
            return
        if (width < 8 || height < 8)
            return
        plot.requestPaint()
    }

    Canvas {
        id: plot
        anchors.fill: parent
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Immediate
        antialiasing: true
        onPaint: {
            var ctx = getContext("2d")
            var w = width
            var h = height
            ctx.clearRect(0, 0, w, h)
            if (w < 8 || h < 8)
                return
            var gx
            var gy
            ctx.lineJoin = "round"
            ctx.lineCap = "round"
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
            var minv = root.fromZero ? 0 : Number.POSITIVE_INFINITY
            var i
            for (i = 0; i < pts.length; i++) {
                var v = Number(pts[i] || 0)
                if (v > maxv)
                    maxv = v
                if (!root.fromZero && v < minv)
                    minv = v
            }
            if (minv === Number.POSITIVE_INFINITY)
                minv = 0
            if (maxv <= minv)
                maxv = minv + 1
            if (!root.fromZero) {
                var pad = (maxv - minv) * 0.12
                if (pad <= 0)
                    pad = Math.abs(maxv) * 0.02 || 1
                minv -= pad
                maxv += pad
            }
            function yAt(val) {
                return h - ((Number(val || 0) - minv) / (maxv - minv)) * (h - 8) - 4
            }
            var last = pts.length < 2 ? 2 : pts.length
            ctx.beginPath()
            ctx.moveTo(0, h)
            for (i = 0; i < pts.length; i++) {
                var px = (pts.length === 1 ? 1 : i / (last - 1)) * w
                ctx.lineTo(px, yAt(pts[i]))
            }
            ctx.lineTo(w, h)
            ctx.closePath()
            ctx.fillStyle = root.fill
            ctx.fill()
            ctx.beginPath()
            for (i = 0; i < pts.length; i++) {
                var sx = (pts.length === 1 ? 1 : i / (last - 1)) * w
                var sy = yAt(pts[i])
                if (i === 0)
                    ctx.moveTo(sx, sy)
                else
                    ctx.lineTo(sx, sy)
            }
            ctx.strokeStyle = root.stroke
            ctx.lineWidth = 1.6
            ctx.lineJoin = "round"
            ctx.lineCap = "round"
            ctx.stroke()
            var marks = root.marks || []
            var n = pts.length
            for (i = 0; i < marks.length; i++) {
                var m = marks[i] || {}
                var mi = Number(m.i)
                if (mi < 0)
                    continue
                if (mi > n - 1)
                    mi = n - 1
                var mx = (n <= 1 ? 1 : mi / (last - 1)) * w
                var my = yAt(m.px !== undefined && m.px !== null && Number(m.px) > 0
                    ? m.px
                    : pts[Math.round(mi)])
                var buy = String(m.side || "") === "buy"
                ctx.beginPath()
                if (buy) {
                    ctx.moveTo(mx, my - 6)
                    ctx.lineTo(mx - 4.5, my + 3)
                    ctx.lineTo(mx + 4.5, my + 3)
                } else {
                    ctx.moveTo(mx, my + 6)
                    ctx.lineTo(mx - 4.5, my - 3)
                    ctx.lineTo(mx + 4.5, my - 3)
                }
                ctx.closePath()
                ctx.fillStyle = buy ? "#8db89a" : "#c98989"
                ctx.fill()
            }
        }
    }

    onValuesChanged: root.redraw()
    onMarksChanged: root.redraw()
    onYMaxChanged: root.redraw()
    onFromZeroChanged: root.redraw()
    onWidthChanged: root.redraw()
    onHeightChanged: root.redraw()
    onVisibleChanged: {
        if (visible)
            root.redraw()
    }
}

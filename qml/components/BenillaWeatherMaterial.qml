import QtQuick
import QtQuick3D
CustomMaterial {
    property bool uTrilinear: true
    property int uMipCount: 0
    property TextureInput uMipTable: TextureInput { texture: Texture { source:Qt.resolvedUrl("../game/framexml/white.png");minFilter:Texture.Nearest;magFilter:Texture.Nearest } }
    objectName: "benillaOriginalWeatherMaterial"
    property int uLayer: 0
    property real uFarClip: 0
    property vector3d uCameraAnchor: Qt.vector3d(0,0,0)
    property bool uSceneFog: false
    property real uFogNear: 100000
    property real uFogFar: 100001
    property TextureInput uTexture: TextureInput { texture: Texture { source:Qt.resolvedUrl("../game/framexml/white.png") } }
    shadingMode: CustomMaterial.Unshaded
    cullMode: Material.NoCulling
    depthDrawMode: Material.NeverDepthDraw
    sourceBlend: uLayer<2 ? CustomMaterial.DstColor : CustomMaterial.SrcAlpha
    destinationBlend: uLayer<2 ? CustomMaterial.SrcColor : CustomMaterial.OneMinusSrcAlpha
    vertexShader: Qt.resolvedUrl("../shaders/gg-benilla-weather.vert")
    fragmentShader: Qt.resolvedUrl("../shaders/gg-benilla-weather.frag")
}

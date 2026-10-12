VARYING vec3 vBenillaNormal;
VARYING vec3 vBenillaPosition;
VARYING vec4 vBenillaColor;
VARYING vec2 vBenillaUv;
VARYING vec3 vBenillaPointLight;
VARYING float vBenillaEyeDepth;
vec3 benillaNormal(vec3 value) {
    return dot(value,value) > 1e-12 ? normalize(value) : vec3(0.0);
}
void MAIN() {
    vBenillaNormal = uModelSpaceLight ? benillaNormal(NORMAL) : benillaNormal(NORMAL_MATRIX * NORMAL);
    vBenillaPosition = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    vBenillaEyeDepth = -(VIEW_MATRIX * vec4(vBenillaPosition,1.0)).z;
    POSITION = VIEWPROJECTION_MATRIX * vec4(vBenillaPosition, 1.0);
    vBenillaColor = uVertexColors ? COLOR : vec4(1.0);
    vBenillaUv = UV0;
    if (uEnvironmentMap) {
        vec3 p = (VIEW_MATRIX * vec4(vBenillaPosition,1.0)).xyz;
        vec3 n = benillaNormal((VIEW_MATRIX * vec4(benillaNormal(NORMAL_MATRIX * NORMAL),0.0)).xyz);
        vec3 reflection = p - 2.0*dot(p,n)*n;
        reflection /= max(length(reflection),0.000001);
        vBenillaUv = reflection.xy*0.5 + vec2(0.5);
    }
    vec3 lightVector = uLightPosition - (uModelSpaceLight ? VERTEX : vBenillaPosition);
    float d = length(lightVector);
    float falloff = 1.0 / max(0.000001,0.7*d + 0.03*d*d);
    vBenillaPointLight = uPointLight ? uDiffuse * falloff * max(0.0,dot(vBenillaNormal,lightVector/max(d,0.000001))) : vec3(0.0);
}

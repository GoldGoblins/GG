// Authored positions stay in model units; only depth is moved to the sky slice.
VARYING vec3 vBenillaNormal;
VARYING vec3 vBenillaPosition;
VARYING vec4 vBenillaColor;
VARYING vec2 vBenillaUv;
VARYING vec3 vBenillaPointLight;
VARYING float vBenillaEyeDepth;
void MAIN() {
    vec3 local = mat3(MODEL_MATRIX)*VERTEX + MODEL_MATRIX[3].xyz-uCameraPosition;
    vBenillaNormal = normalize(NORMAL_MATRIX*NORMAL);
    vBenillaPosition = uCameraPosition+local;
    vBenillaEyeDepth = -(mat3(VIEW_MATRIX)*local).z;
    POSITION = PROJECTION_MATRIX*vec4(mat3(VIEW_MATRIX)*local,1.0);
    POSITION.z = POSITION.w;
    vBenillaColor = vec4(1.0);
    vBenillaPointLight = vec3(0.0);
    vBenillaUv = UV0;
    if (uEnvironmentMap) {
        vec3 p=mat3(VIEW_MATRIX)*local;
        vec3 n=normalize(mat3(VIEW_MATRIX)*vBenillaNormal);
        vec3 reflection=p-2.0*dot(p,n)*n;
        vBenillaUv=reflection.xy/max(length(reflection),0.000001)*0.5+vec2(0.5);
    }
}

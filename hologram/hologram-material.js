import * as THREE from 'three';

// Muted cyan: reads as "hologram" without blowing out under bloom. Start colour of every room.
export const NEUTRAL = new THREE.Color(0x3a8fb0);

const vertexShader = /* glsl */ `
  varying vec3 vWorldPos;
  varying vec3 vWorldNormal;
  void main() {
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vWorldPos = wp.xyz;
    vWorldNormal = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 uColor;
  uniform float uTime;
  uniform float uSeed;
  uniform float uHighlight;
  uniform float uDim;       // 1 = normal, lower = faded (room on a floor that is not selected)
  varying vec3 vWorldPos;
  varying vec3 vWorldNormal;
  void main() {
    vec3 n = normalize(vWorldNormal);
    if (!gl_FrontFacing) n = -n;
    vec3 viewDir = normalize(cameraPosition - vWorldPos);
    float fresnel = pow(1.0 - clamp(abs(dot(n, viewDir)), 0.0, 1.0), 2.0);

    float scan = smoothstep(0.88, 1.0, sin(vWorldPos.y * 7.0 - uTime * 1.5));
    float flicker = 0.97 + 0.03 * sin(uTime * 23.0 + uSeed * 10.0);

    float intensity = 0.22 + fresnel * 0.35 + scan * 0.10 + uHighlight * 0.35;
    float alpha = 0.16 + fresnel * 0.22 + scan * 0.05 + uHighlight * 0.18;
    gl_FragColor = vec4(uColor * intensity * flicker, alpha * uDim);
  }
`;

export function createHologramMaterial(seed = 0) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: NEUTRAL.clone() },
      uTime: { value: 0 },
      uSeed: { value: seed },
      uHighlight: { value: 0 },
      uDim: { value: 1 },
    },
    vertexShader,
    fragmentShader,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });
}

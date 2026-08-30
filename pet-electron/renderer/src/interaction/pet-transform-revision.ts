export type PetTransformSnapshot = {
  revision: number;
  anchor: { x: number; y: number };
  zoomScale: number;
};

export type PetTransformResolution = {
  accepted: boolean;
  state: PetTransformSnapshot;
};

function isValidTransform(transform: PetTransformSnapshot): boolean {
  return (
    Number.isSafeInteger(transform?.revision) &&
    transform.revision >= 1 &&
    Number.isFinite(transform?.anchor?.x) &&
    Number.isFinite(transform?.anchor?.y) &&
    Number.isFinite(transform?.zoomScale) &&
    transform.zoomScale > 0
  );
}

export function resolveAuthoritativePetTransform(
  current: PetTransformSnapshot,
  incoming: PetTransformSnapshot
): PetTransformResolution {
  if (!isValidTransform(incoming) || incoming.revision <= current.revision) {
    return { accepted: false, state: current };
  }

  return {
    accepted: true,
    state: {
      revision: incoming.revision,
      anchor: { ...incoming.anchor },
      zoomScale: incoming.zoomScale
    }
  };
}

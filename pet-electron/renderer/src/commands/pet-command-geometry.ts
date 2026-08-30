export type PetGeometryRenderer = {
  applyAuthoritativeTransform: (transform: {
    revision: number;
    anchor: { x: number; y: number };
    zoomScale: number;
  }) => boolean;
  getTransformRevision: () => number;
  setExpectedHostBounds: (bounds?: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
  } | null) => void;
};

export function applyPetGeometryCommand(
  renderer: PetGeometryRenderer,
  payload: Record<string, any>
): { handled: boolean; transformAccepted: boolean; hostAccepted: boolean } {
  if (
    payload.type === "pet-transform-set" &&
    payload.petAnchor &&
    Number.isSafeInteger(Number(payload.transformRevision))
  ) {
    const transformAccepted = renderer.applyAuthoritativeTransform({
      revision: Number(payload.transformRevision),
      anchor: {
        x: Number(payload.petAnchor.x),
        y: Number(payload.petAnchor.y)
      },
      zoomScale: Number(payload.zoomScale)
    });
    return { handled: true, transformAccepted, hostAccepted: false };
  }

  if (payload.type === "pet-host-set") {
    const hostRevision = Number(payload.transformRevision);
    if (
      !Number.isSafeInteger(hostRevision) ||
      hostRevision !== renderer.getTransformRevision()
    ) {
      return { handled: true, transformAccepted: false, hostAccepted: false };
    }
    renderer.setExpectedHostBounds(payload.petHostBounds);
    return { handled: true, transformAccepted: false, hostAccepted: true };
  }

  return { handled: false, transformAccepted: false, hostAccepted: false };
}

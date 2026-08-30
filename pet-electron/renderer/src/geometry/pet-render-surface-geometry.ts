export type PetScreenPoint = {
  x: number;
  y: number;
};

export type PetScreenRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PetModelScreenBounds = {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width?: number;
  height?: number;
};

export type PetRenderSurfaceState = {
  screenBounds: PetScreenRect;
  localBounds: PetScreenRect;
  anchorScreenPoint: PetScreenPoint;
  transformRevision: number;
};

export type PetRenderSurfaceOptions = {
  initialWidth?: number;
  initialHeight?: number;
  bottomInset?: number;
  horizontalPadding?: number;
  verticalPadding?: number;
  minWidth?: number;
  minHeight?: number;
  expandTolerance?: number;
  shrinkMargin?: number;
};

export const DEFAULT_RENDER_SURFACE_OPTIONS = Object.freeze({
  initialWidth: 760,
  initialHeight: 1280,
  bottomInset: 24,
  horizontalPadding: 96,
  verticalPadding: 96,
  minWidth: 280,
  minHeight: 420,
  expandTolerance: 24,
  shrinkMargin: 48
});

function finiteNumber(value: number | undefined, fallback = 0): number {
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

export function normalizePetScreenRect(rect: PetScreenRect | null | undefined): PetScreenRect | null {
  if (!rect) return null;
  const x = finiteNumber(rect.x, Number.NaN);
  const y = finiteNumber(rect.y, Number.NaN);
  const width = finiteNumber(rect.width, Number.NaN);
  const height = finiteNumber(rect.height, Number.NaN);
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
    return null;
  }
  return { x, y, width, height };
}

function normalizeModelBounds(
  bounds: PetModelScreenBounds | null | undefined
): Required<PetModelScreenBounds> | null {
  if (!bounds) return null;
  const left = finiteNumber(bounds.left, Number.NaN);
  const top = finiteNumber(bounds.top, Number.NaN);
  const right = finiteNumber(bounds.right, Number.NaN);
  const bottom = finiteNumber(bounds.bottom, Number.NaN);
  if (![left, top, right, bottom].every(Number.isFinite) || right <= left || bottom <= top) {
    return null;
  }
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function resolveOptions(options: PetRenderSurfaceOptions = {}) {
  return { ...DEFAULT_RENDER_SURFACE_OPTIONS, ...(options || {}) };
}

export function screenRectToShellLocal(
  screenBounds: PetScreenRect,
  shellBounds: PetScreenRect
): PetScreenRect | null {
  const screen = normalizePetScreenRect(screenBounds);
  const shell = normalizePetScreenRect(shellBounds);
  if (!screen || !shell) return null;
  return {
    x: screen.x - shell.x,
    y: screen.y - shell.y,
    width: screen.width,
    height: screen.height
  };
}

export function createInitialPetRenderSurface(
  shellBounds: PetScreenRect,
  anchorScreenPoint: PetScreenPoint,
  transformRevision: number,
  options: PetRenderSurfaceOptions = {}
): PetRenderSurfaceState | null {
  const shell = normalizePetScreenRect(shellBounds);
  const anchor = {
    x: finiteNumber(anchorScreenPoint?.x, Number.NaN),
    y: finiteNumber(anchorScreenPoint?.y, Number.NaN)
  };
  if (!shell || !Number.isFinite(anchor.x) || !Number.isFinite(anchor.y)) return null;
  const config = resolveOptions(options);
  const width = Math.max(1, finiteNumber(config.initialWidth, 760));
  const height = Math.max(1, finiteNumber(config.initialHeight, 1280));
  const bottomInset = Math.max(0, Math.min(height - 1, finiteNumber(config.bottomInset, 24)));
  const screenBounds = {
    x: anchor.x - width / 2,
    y: anchor.y - (height - bottomInset),
    width,
    height
  };
  const localBounds = screenRectToShellLocal(screenBounds, shell);
  return localBounds
    ? {
        screenBounds,
        localBounds,
        anchorScreenPoint: anchor,
        transformRevision: Math.max(0, Math.trunc(finiteNumber(transformRevision)))
      }
    : null;
}

export function translatePetRenderSurfaceToAnchor(
  state: PetRenderSurfaceState,
  shellBounds: PetScreenRect,
  anchorScreenPoint: PetScreenPoint,
  transformRevision: number
): PetRenderSurfaceState | null {
  const shell = normalizePetScreenRect(shellBounds);
  const current = normalizePetScreenRect(state?.screenBounds);
  const anchor = {
    x: finiteNumber(anchorScreenPoint?.x, Number.NaN),
    y: finiteNumber(anchorScreenPoint?.y, Number.NaN)
  };
  if (!shell || !current || !Number.isFinite(anchor.x) || !Number.isFinite(anchor.y)) return null;
  const deltaX = anchor.x - state.anchorScreenPoint.x;
  const deltaY = anchor.y - state.anchorScreenPoint.y;
  const screenBounds = {
    ...current,
    x: current.x + deltaX,
    y: current.y + deltaY
  };
  const localBounds = screenRectToShellLocal(screenBounds, shell);
  return localBounds
    ? {
        screenBounds,
        localBounds,
        anchorScreenPoint: anchor,
        transformRevision: Math.max(0, Math.trunc(finiteNumber(transformRevision)))
      }
    : null;
}

export function resolvePetRenderSurfaceEnvelope(
  modelBounds: PetModelScreenBounds,
  shellBounds: PetScreenRect,
  anchorScreenPoint: PetScreenPoint,
  transformRevision: number,
  options: PetRenderSurfaceOptions = {}
): PetRenderSurfaceState | null {
  const shell = normalizePetScreenRect(shellBounds);
  const model = normalizeModelBounds(modelBounds);
  if (!shell || !model) return null;
  const config = resolveOptions(options);
  const paddedLeft = model.left - Math.max(0, finiteNumber(config.horizontalPadding));
  const paddedTop = model.top - Math.max(0, finiteNumber(config.verticalPadding));
  const paddedRight = model.right + Math.max(0, finiteNumber(config.horizontalPadding));
  const paddedBottom = model.bottom + Math.max(0, finiteNumber(config.verticalPadding));
  const width = Math.max(
    1,
    finiteNumber(config.minWidth, 1),
    paddedRight - paddedLeft
  );
  const height = Math.max(
    1,
    finiteNumber(config.minHeight, 1),
    paddedBottom - paddedTop
  );
  const centerX = (paddedLeft + paddedRight) / 2;
  const centerY = (paddedTop + paddedBottom) / 2;
  const screenBounds = {
    x: centerX - width / 2,
    y: centerY - height / 2,
    width,
    height
  };
  const localBounds = screenRectToShellLocal(screenBounds, shell);
  return localBounds
    ? {
        screenBounds,
        localBounds,
        anchorScreenPoint: {
          x: finiteNumber(anchorScreenPoint?.x, centerX),
          y: finiteNumber(anchorScreenPoint?.y, paddedBottom)
        },
        transformRevision: Math.max(0, Math.trunc(finiteNumber(transformRevision)))
      }
    : null;
}

export function surfaceContainsModelBounds(
  surfaceBounds: PetScreenRect,
  modelBounds: PetModelScreenBounds,
  tolerance = 0
): boolean {
  const surface = normalizePetScreenRect(surfaceBounds);
  const model = normalizeModelBounds(modelBounds);
  if (!surface || !model) return false;
  const allowed = Math.max(0, finiteNumber(tolerance));
  return (
    model.left >= surface.x - allowed &&
    model.top >= surface.y - allowed &&
    model.right <= surface.x + surface.width + allowed &&
    model.bottom <= surface.y + surface.height + allowed
  );
}

export function resolvePetRenderSurfaceAction(
  currentBounds: PetScreenRect | null,
  desiredBounds: PetScreenRect,
  options: PetRenderSurfaceOptions = {}
): "apply" | "shrink" | "keep" {
  const current = normalizePetScreenRect(currentBounds);
  const desired = normalizePetScreenRect(desiredBounds);
  if (!desired || !current) return "apply";
  const config = resolveOptions(options);
  const tolerance = Math.max(0, finiteNumber(config.expandTolerance));
  const containsDesired =
    desired.x >= current.x - tolerance &&
    desired.y >= current.y - tolerance &&
    desired.x + desired.width <= current.x + current.width + tolerance &&
    desired.y + desired.height <= current.y + current.height + tolerance;
  if (!containsDesired) return "apply";
  const margin = Math.max(0, finiteNumber(config.shrinkMargin));
  if (current.width - desired.width >= margin * 2 || current.height - desired.height >= margin * 2) {
    return "shrink";
  }
  return "keep";
}

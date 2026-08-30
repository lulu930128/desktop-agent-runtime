import {
  createInitialPetRenderSurface,
  normalizePetScreenRect,
  resolvePetRenderSurfaceAction,
  resolvePetRenderSurfaceEnvelope,
  screenRectToShellLocal,
  surfaceContainsModelBounds,
  translatePetRenderSurfaceToAnchor,
  type PetModelScreenBounds,
  type PetRenderSurfaceState,
  type PetScreenPoint,
  type PetScreenRect
} from "../geometry/pet-render-surface-geometry";

const SURFACE_SHRINK_DELAY_MS = 360;

export type PetRenderSurfaceSnapshot = {
  enabled: boolean;
  shellBounds: PetScreenRect | null;
  applied: PetRenderSurfaceState | null;
  pending: PetRenderSurfaceState | null;
  lastAction: string;
  modelContained: boolean | null;
};

type ControllerOptions = {
  enabled: boolean;
  shellBounds?: PetScreenRect | null;
  anchorScreenPoint?: PetScreenPoint | null;
  transformRevision?: number;
};

function cloneState(state: PetRenderSurfaceState | null): PetRenderSurfaceState | null {
  return state
    ? {
        screenBounds: { ...state.screenBounds },
        localBounds: { ...state.localBounds },
        anchorScreenPoint: { ...state.anchorScreenPoint },
        transformRevision: state.transformRevision
      }
    : null;
}

function cssDip(value: number): string {
  return `${Math.round(value * 1000) / 1000}px`;
}

export class PetRenderSurfaceController {
  private readonly element: HTMLElement;
  private readonly enabled: boolean;
  private shellBounds: PetScreenRect | null;
  private applied: PetRenderSurfaceState | null;
  private pending: PetRenderSurfaceState | null;
  private latestModelBounds: PetModelScreenBounds | null;
  private shrinkTimer: number | null;
  private lastAction: string;

  public constructor(element: HTMLElement, options: ControllerOptions) {
    this.element = element;
    this.enabled = options.enabled === true;
    this.shellBounds = normalizePetScreenRect(options.shellBounds || null);
    this.pending = null;
    this.latestModelBounds = null;
    this.shrinkTimer = null;
    this.lastAction = this.enabled ? "bootstrap" : "legacy-window-surface";
    this.applied =
      this.enabled && this.shellBounds && options.anchorScreenPoint
        ? createInitialPetRenderSurface(
            this.shellBounds,
            options.anchorScreenPoint,
            Number(options.transformRevision) || 0
          )
        : null;

    if (this.enabled) {
      this.element.parentElement?.classList.add("fixed-shell-enabled");
      if (this.applied) this.applyDomState(this.applied);
    }
  }

  public isEnabled(): boolean {
    return this.enabled;
  }

  public scheduleTransform(
    anchorScreenPoint: PetScreenPoint,
    transformRevision: number
  ): boolean {
    if (!this.enabled || !this.shellBounds) return false;
    const base = this.pending || this.applied;
    if (!base || transformRevision < base.transformRevision) return false;
    this.clearShrinkTimer();
    const next = translatePetRenderSurfaceToAnchor(
      base,
      this.shellBounds,
      anchorScreenPoint,
      transformRevision
    );
    if (!next) return false;
    this.pending = next;
    this.lastAction = "transform-translate";
    return true;
  }

  public scheduleShellBounds(shellBounds: PetScreenRect): boolean {
    if (!this.enabled) return false;
    const normalized = normalizePetScreenRect(shellBounds);
    const base = this.pending || this.applied;
    if (!normalized || !base) return false;
    const localBounds = screenRectToShellLocal(base.screenBounds, normalized);
    if (!localBounds) return false;
    this.clearShrinkTimer();
    this.shellBounds = normalized;
    this.pending = { ...base, localBounds };
    this.lastAction = "shell-topology";
    return true;
  }

  public scheduleModelEnvelope(
    modelBounds: PetModelScreenBounds,
    transformRevision: number
  ): boolean {
    if (!this.enabled || !this.shellBounds) return false;
    const base = this.pending || this.applied;
    if (!base || transformRevision !== base.transformRevision) return false;
    const desired = resolvePetRenderSurfaceEnvelope(
      modelBounds,
      this.shellBounds,
      base.anchorScreenPoint,
      transformRevision
    );
    if (!desired) return false;
    this.latestModelBounds = { ...modelBounds };
    const action = resolvePetRenderSurfaceAction(base.screenBounds, desired.screenBounds);
    if (action === "apply") {
      this.clearShrinkTimer();
      this.pending = desired;
      this.lastAction = "envelope-expand";
      return true;
    }
    if (action === "shrink") {
      this.scheduleShrink(desired);
      this.lastAction = "envelope-shrink-pending";
      return true;
    }
    this.clearShrinkTimer();
    this.lastAction = "envelope-keep";
    return false;
  }

  public flushPending(): boolean {
    if (!this.enabled || !this.pending) return false;
    const next = this.pending;
    this.pending = null;
    this.applied = next;
    this.applyDomState(next);
    return true;
  }

  public getSnapshot(): PetRenderSurfaceSnapshot {
    const effective = this.pending || this.applied;
    return {
      enabled: this.enabled,
      shellBounds: this.shellBounds ? { ...this.shellBounds } : null,
      applied: cloneState(this.applied),
      pending: cloneState(this.pending),
      lastAction: this.lastAction,
      modelContained:
        effective && this.latestModelBounds
          ? surfaceContainsModelBounds(effective.screenBounds, this.latestModelBounds)
          : null
    };
  }

  public dispose(): void {
    this.clearShrinkTimer();
    this.pending = null;
  }

  private applyDomState(state: PetRenderSurfaceState): void {
    const bounds = state.localBounds;
    this.element.style.width = cssDip(bounds.width);
    this.element.style.height = cssDip(bounds.height);
    this.element.style.transform = `translate3d(${cssDip(bounds.x)}, ${cssDip(bounds.y)}, 0)`;
  }

  private scheduleShrink(desired: PetRenderSurfaceState): void {
    this.clearShrinkTimer();
    this.shrinkTimer = window.setTimeout(() => {
      this.shrinkTimer = null;
      const base = this.pending || this.applied;
      if (!base || base.transformRevision !== desired.transformRevision) return;
      this.pending = desired;
      this.lastAction = "envelope-shrink";
    }, SURFACE_SHRINK_DELAY_MS);
  }

  private clearShrinkTimer(): void {
    if (this.shrinkTimer !== null) {
      window.clearTimeout(this.shrinkTimer);
      this.shrinkTimer = null;
    }
  }
}

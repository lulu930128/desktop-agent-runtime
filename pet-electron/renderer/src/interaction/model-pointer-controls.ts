import {
  PetLive2DRenderer,
  type DragFinishReason
} from "../live2d/pet-live2d-renderer";
import { resolveWheelZoomFactor } from "./pet-zoom-geometry";

export function bindModelPointerControls(
  canvas: HTMLCanvasElement,
  renderer: PetLive2DRenderer
): () => void {
  let hoverOnModel = false;
  let draggingModel = false;
  let activePointerId: number | null = null;
  let hoverRefreshRafId: number | null = null;
  let pendingHoverPoint: { clientX: number; clientY: number } | null = null;
  let anchorUpdateRafId: number | null = null;
  let pendingAnchor: { x: number; y: number } | null = null;
  let transformRequestId = 0;

  const setModelHoverState = (nextHover: boolean): void => {
    if (hoverOnModel === nextHover) {
      if (nextHover) {
        window.kuroPetElectron.updateComponentHover("live2d-model", true);
      }
      return;
    }
    hoverOnModel = nextHover;
    canvas.style.cursor = draggingModel ? "grabbing" : hoverOnModel ? "grab" : "default";
    renderer.setPointerActive(draggingModel);
    window.kuroPetElectron.updateComponentHover("live2d-model", hoverOnModel);
  };

  const refreshModelHover = (clientX: number, clientY: number): boolean => {
    const nextHover = renderer.hitTestCanvasPoint(clientX, clientY);
    setModelHoverState(nextHover);
    return nextHover;
  };

  const refreshModelHoverFromScreen = (screenX: number, screenY: number): boolean => {
    const nextHover = renderer.hitTestScreenPoint(screenX, screenY);
    setModelHoverState(nextHover);
    return nextHover;
  };

  const scheduleModelHoverRefresh = (clientX: number, clientY: number): void => {
    pendingHoverPoint = { clientX, clientY };
    if (hoverRefreshRafId !== null) {
      return;
    }

    hoverRefreshRafId = window.requestAnimationFrame(() => {
      hoverRefreshRafId = null;
      const point = pendingHoverPoint;
      pendingHoverPoint = null;
      if (!point || draggingModel) {
        return;
      }

      refreshModelHover(point.clientX, point.clientY);
    });
  };

  const cancelModelHoverRefresh = (): void => {
    pendingHoverPoint = null;
    if (hoverRefreshRafId !== null) {
      window.cancelAnimationFrame(hoverRefreshRafId);
      hoverRefreshRafId = null;
    }
  };

  const flushPetAnchorUpdate = (): void => {
    if (anchorUpdateRafId !== null) {
      window.cancelAnimationFrame(anchorUpdateRafId);
      anchorUpdateRafId = null;
    }
    const nextAnchor = pendingAnchor;
    pendingAnchor = null;
    if (nextAnchor) {
      transformRequestId += 1;
      window.kuroPetElectron.requestPetTransform({
        kind: "anchor",
        requestId: transformRequestId,
        requestedAnchor: nextAnchor
      });
    }
  };

  const schedulePetAnchorUpdate = (x: number, y: number): void => {
    pendingAnchor = { x, y };
    if (anchorUpdateRafId !== null) {
      return;
    }
    anchorUpdateRafId = window.requestAnimationFrame(() => {
      anchorUpdateRafId = null;
      const nextAnchor = pendingAnchor;
      pendingAnchor = null;
      if (nextAnchor) {
        transformRequestId += 1;
        window.kuroPetElectron.requestPetTransform({
          kind: "anchor",
          requestId: transformRequestId,
          requestedAnchor: nextAnchor
        });
      }
    });
  };

  const handlePointerDown = (event: PointerEvent): void => {
    if (event.button !== 0) {
      return;
    }

    cancelModelHoverRefresh();
    if (!refreshModelHover(event.clientX, event.clientY)) {
      return;
    }

    draggingModel = true;
    activePointerId = event.pointerId;
    canvas.style.cursor = "grabbing";
    renderer.setPointerActive(true);
    renderer.setPointerScreenPoint(event.screenX, event.screenY);
    renderer.beginAnchorDrag(event.screenX, event.screenY);
    window.kuroPetElectron.startWindowDrag(event.screenX, event.screenY);
    try {
      canvas.setPointerCapture(event.pointerId);
    } catch {
      // Electron may move the native window before capture is established.
      // Window-level listeners below remain the recovery path.
    }
    event.preventDefault();
  };

  const handleWheel = (event: WheelEvent): void => {
    cancelModelHoverRefresh();
    if (!refreshModelHover(event.clientX, event.clientY)) {
      return;
    }

    event.preventDefault();
    const scaleFactor = resolveWheelZoomFactor(event.deltaY);
    if (!scaleFactor) {
      return;
    }
    transformRequestId += 1;
    window.kuroPetElectron.requestPetTransform({
      kind: "zoom",
      requestId: transformRequestId,
      scaleFactor,
      pivotScreenPoint: { x: event.screenX, y: event.screenY }
    });
  };

  const handlePointerMove = (event: PointerEvent): void => {
    if (draggingModel) {
      renderer.setPointerScreenPoint(event.screenX, event.screenY);
      const anchor = renderer.updateAnchorDrag(event.screenX, event.screenY);
      schedulePetAnchorUpdate(anchor.x, anchor.y);
      return;
    }

    scheduleModelHoverRefresh(event.clientX, event.clientY);
  };

  const finishPointerDrag = (reason: DragFinishReason): void => {
    if (!draggingModel && activePointerId === null) {
      return;
    }
    draggingModel = false;
    const pointerId = activePointerId;
    activePointerId = null;
    flushPetAnchorUpdate();
    renderer.endAnchorDrag(reason);
    renderer.resetDragPoint();
    window.kuroPetElectron.endWindowDrag();
    if (pointerId !== null && canvas.hasPointerCapture(pointerId)) {
      try {
        canvas.releasePointerCapture(pointerId);
      } catch {
        // Capture may already have been released by the native window move.
      }
    }
    setModelHoverState(false);
    renderer.setPointerActive(false);
    canvas.style.cursor = "default";
  };

  const handlePointerUp = (_event: PointerEvent): void => {
    finishPointerDrag("pointerup");
  };

  const handlePointerCancel = (): void => {
    finishPointerDrag("pointercancel");
  };

  const handleLostPointerCapture = (): void => {
    finishPointerDrag("lostpointercapture");
  };

  const handlePointerLeave = (): void => {
    if (draggingModel) {
      return;
    }
    cancelModelHoverRefresh();
    setModelHoverState(false);
    renderer.setPointerActive(false);
  };

  const handleBlur = (): void => {
    finishPointerDrag("blur");
    cancelModelHoverRefresh();
    flushPetAnchorUpdate();
    setModelHoverState(false);
    renderer.setPointerActive(false);
  };

  canvas.addEventListener("pointerdown", handlePointerDown);
  canvas.addEventListener("wheel", handleWheel, { passive: false });
  window.addEventListener("pointermove", handlePointerMove);
  window.addEventListener("pointerup", handlePointerUp);
  window.addEventListener("pointercancel", handlePointerCancel);
  canvas.addEventListener("lostpointercapture", handleLostPointerCapture);
  canvas.addEventListener("pointerleave", handlePointerLeave);
  window.addEventListener("blur", handleBlur);
  const unbindGlobalPointer = window.kuroPetElectron.onCommand((payload) => {
    if (payload.type !== "pet-pointer-set" || !payload.screenPoint) {
      return;
    }
    if (draggingModel) {
      window.kuroPetElectron.updateComponentHover("live2d-model", true);
      renderer.setPointerScreenPoint(payload.screenPoint.x, payload.screenPoint.y);
      return;
    }
    refreshModelHoverFromScreen(payload.screenPoint.x, payload.screenPoint.y);
  });

  return () => {
    canvas.removeEventListener("pointerdown", handlePointerDown);
    canvas.removeEventListener("wheel", handleWheel);
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", handlePointerUp);
    window.removeEventListener("pointercancel", handlePointerCancel);
    canvas.removeEventListener("lostpointercapture", handleLostPointerCapture);
    canvas.removeEventListener("pointerleave", handlePointerLeave);
    window.removeEventListener("blur", handleBlur);
    unbindGlobalPointer();

    finishPointerDrag("dispose");
    cancelModelHoverRefresh();
    setModelHoverState(false);
    renderer.setPointerActive(false);
    renderer.resetDragPoint();
  };
}

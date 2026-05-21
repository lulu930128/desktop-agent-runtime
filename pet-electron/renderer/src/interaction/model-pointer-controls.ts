import { PetLive2DRenderer } from "../live2d/pet-live2d-renderer";
import { storeModelZoomScale } from "../model-zoom";

export function bindModelPointerControls(
  canvas: HTMLCanvasElement,
  renderer: PetLive2DRenderer
): () => void {
  let hoverOnModel = false;
  let draggingModel = false;
  let hoverRefreshRafId: number | null = null;
  let pendingHoverPoint: { clientX: number; clientY: number } | null = null;
  let zoomUpdateRafId: number | null = null;
  let pendingModelZoomScale: number | null = null;

  const setModelHoverState = (nextHover: boolean): void => {
    if (hoverOnModel === nextHover) {
      return;
    }
    hoverOnModel = nextHover;
    canvas.style.cursor = draggingModel ? "grabbing" : hoverOnModel ? "grab" : "default";
    renderer.setPointerActive(hoverOnModel || draggingModel);
    window.kuroPetElectron.updateComponentHover("live2d-model", hoverOnModel);
  };

  const refreshModelHover = (clientX: number, clientY: number): boolean => {
    const nextHover = renderer.hitTestCanvasPoint(clientX, clientY);
    setModelHoverState(nextHover);
    if (nextHover) {
      renderer.setDragPointFromCanvas(clientX, clientY);
    } else if (!draggingModel) {
      renderer.resetDragPoint();
    }
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

  const schedulePetModelZoom = (zoomScale: number): void => {
    pendingModelZoomScale = zoomScale;
    if (zoomUpdateRafId !== null) {
      return;
    }

    zoomUpdateRafId = window.requestAnimationFrame(() => {
      zoomUpdateRafId = null;
      const nextZoomScale = pendingModelZoomScale;
      pendingModelZoomScale = null;
      if (nextZoomScale !== null) {
        window.kuroPetElectron.setPetModelZoom(nextZoomScale);
      }
    });
  };

  const cancelPetModelZoom = (): void => {
    pendingModelZoomScale = null;
    if (zoomUpdateRafId !== null) {
      window.cancelAnimationFrame(zoomUpdateRafId);
      zoomUpdateRafId = null;
    }
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
    canvas.style.cursor = "grabbing";
    renderer.setPointerActive(true);
    renderer.setDragPointFromCanvas(event.clientX, event.clientY);
    renderer.beginAnchorDrag(event.clientX, event.clientY);
    event.preventDefault();
  };

  const handleWheel = (event: WheelEvent): void => {
    cancelModelHoverRefresh();
    if (!refreshModelHover(event.clientX, event.clientY)) {
      return;
    }

    event.preventDefault();
    const zoomScale = renderer.adjustZoomByWheel(event.deltaY);
    storeModelZoomScale(zoomScale);
    schedulePetModelZoom(zoomScale);
  };

  const handlePointerMove = (event: PointerEvent): void => {
    if (draggingModel) {
      renderer.setDragPointFromCanvas(event.clientX, event.clientY);
      const anchor = renderer.updateAnchorDrag(event.clientX, event.clientY);
      window.kuroPetElectron.setPetAnchor(anchor.x, anchor.y);
      return;
    }

    scheduleModelHoverRefresh(event.clientX, event.clientY);
  };

  const handlePointerUp = (): void => {
    draggingModel = false;
    renderer.endAnchorDrag();
    renderer.resetDragPoint();
    renderer.setPointerActive(hoverOnModel);
    canvas.style.cursor = hoverOnModel ? "grab" : "default";
  };

  const handlePointerLeave = (): void => {
    if (draggingModel) {
      return;
    }
    cancelModelHoverRefresh();
    setModelHoverState(false);
    renderer.setPointerActive(false);
    renderer.resetDragPoint();
  };

  const handleBlur = (): void => {
    draggingModel = false;
    renderer.endAnchorDrag();
    cancelModelHoverRefresh();
    cancelPetModelZoom();
    setModelHoverState(false);
    renderer.setPointerActive(false);
    renderer.resetDragPoint();
  };

  canvas.addEventListener("pointerdown", handlePointerDown);
  canvas.addEventListener("wheel", handleWheel, { passive: false });
  window.addEventListener("pointermove", handlePointerMove);
  window.addEventListener("pointerup", handlePointerUp);
  canvas.addEventListener("pointerleave", handlePointerLeave);
  window.addEventListener("blur", handleBlur);

  return () => {
    canvas.removeEventListener("pointerdown", handlePointerDown);
    canvas.removeEventListener("wheel", handleWheel);
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", handlePointerUp);
    canvas.removeEventListener("pointerleave", handlePointerLeave);
    window.removeEventListener("blur", handleBlur);

    draggingModel = false;
    renderer.endAnchorDrag();
    cancelModelHoverRefresh();
    cancelPetModelZoom();
    setModelHoverState(false);
    renderer.setPointerActive(false);
    renderer.resetDragPoint();
  };
}

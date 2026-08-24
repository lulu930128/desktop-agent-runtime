function resolvePetMousePolicy({
  mode,
  petGameMode,
  forceIgnoreMouse,
  interactiveHover
}) {
  if (mode !== "pet") {
    return {
      ignoreMouseEvents: false,
      forwardMouseMoves: true,
      mode: "window-interactive"
    };
  }

  if (petGameMode) {
    return {
      ignoreMouseEvents: true,
      forwardMouseMoves: true,
      mode: "game-passthrough"
    };
  }

  if (forceIgnoreMouse) {
    return {
      ignoreMouseEvents: true,
      forwardMouseMoves: true,
      mode: "full-passthrough"
    };
  }

  if (interactiveHover) {
    return {
      ignoreMouseEvents: false,
      forwardMouseMoves: true,
      mode: "model-interactive"
    };
  }

  return {
    ignoreMouseEvents: true,
    forwardMouseMoves: true,
    mode: "transparent-passthrough"
  };
}

module.exports = { resolvePetMousePolicy };

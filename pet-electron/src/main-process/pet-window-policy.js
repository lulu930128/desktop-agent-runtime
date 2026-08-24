const PET_ALWAYS_ON_TOP_LEVEL = "screen-saver";

function resolvePetWindowPolicy({ mode }) {
  if (mode === "pet") {
    return {
      mode: "pet-topmost",
      focusable: false,
      alwaysOnTop: true,
      alwaysOnTopLevel: PET_ALWAYS_ON_TOP_LEVEL,
      visibleOnAllWorkspaces: true,
      visibleOnFullScreen: true,
      skipTaskbar: true,
      moveTopOnShow: true
    };
  }

  return {
    mode: "window-normal",
    focusable: true,
    alwaysOnTop: false,
    alwaysOnTopLevel: "normal",
    visibleOnAllWorkspaces: false,
    visibleOnFullScreen: false,
    skipTaskbar: true,
    moveTopOnShow: false
  };
}

module.exports = {
  PET_ALWAYS_ON_TOP_LEVEL,
  resolvePetWindowPolicy
};

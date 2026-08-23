const { Menu } = require("electron");

function buildCommonMenuItems(state, actions) {
  return [
    {
      label: "顯示 Kuro 工作面板",
      click: actions.showBriefing
    },
    {
      label: "停止目前輸出",
      click: actions.interruptOutput
    },
    { type: "separator" },
    {
      label: state.forceIgnoreMouse ? "關閉滑鼠穿透" : "開啟滑鼠穿透",
      click: actions.toggleIgnoreMouse
    },
    {
      label: "遊戲模式",
      type: "checkbox",
      checked: Boolean(state.petGameMode),
      click: actions.toggleGameMode
    },
    {
      label: "移到下一個螢幕",
      click: actions.moveNextDisplay
    },
    {
      label: "重新載入前端",
      click: actions.reloadFrontend
    },
    { type: "separator" },
    {
      label: "結束",
      click: actions.quit
    }
  ];
}

function createTrayMenu(state, actions) {
  return Menu.buildFromTemplate([
    {
      label: "顯示桌寵",
      click: actions.showPet
    },
    { type: "separator" },
    ...buildCommonMenuItems(state, actions)
  ]);
}

function createPetContextMenu(state, actions) {
  return Menu.buildFromTemplate(buildCommonMenuItems(state, actions));
}

module.exports = {
  createPetContextMenu,
  createTrayMenu
};

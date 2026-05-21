const { Menu } = require("electron");

function buildCommonMenuItems(state, actions) {
  return [
    {
      label: state.forceIgnoreMouse ? "關閉滑鼠穿透" : "開啟滑鼠穿透",
      click: actions.toggleIgnoreMouse
    },
    {
      label: state.readerVisible ? "隱藏閱讀框" : "顯示閱讀框",
      click: actions.toggleReader
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

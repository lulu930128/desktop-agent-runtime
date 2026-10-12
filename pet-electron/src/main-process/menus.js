const { Menu } = require("electron");

function createPetContextMenu(state, actions) {
  return Menu.buildFromTemplate([
    { label: "停止桌寵音效", click: actions.interruptOutput },
    { type: "separator" },
    { label: state.forceIgnoreMouse ? "關閉滑鼠穿透" : "開啟滑鼠穿透", click: actions.toggleIgnoreMouse },
    { label: "遊戲模式", type: "checkbox", checked: Boolean(state.petGameMode), click: actions.toggleGameMode },
    { label: "移到下一個螢幕", click: actions.moveNextDisplay },
    { label: "重置桌寵位置", click: actions.resetPosition },
    { label: "重新載入桌寵", click: actions.reloadFrontend },
    { type: "separator" },
    { label: "隱藏桌寵", click: actions.hidePet }
  ]);
}
module.exports = { createPetContextMenu };

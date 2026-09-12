# 第三方來源與授權範圍

## Kuro 自有內容

Kuro 自行撰寫、未另標示授權的程式碼與文字文件採用 [Apache License 2.0](LICENSE)。此宣告不取代下列元件、檔頭或素材的既有授權，也不宣稱維護者擁有所有第三方權利。[NOTICE](NOTICE) 提供專案歸屬聲明。

## 已確認的第三方邊界

| 元件／位置 | 授權與來源 |
| --- | --- |
| `Open-LLM-VTuber/` 上游程式及其 fork 修改 | 保留該子專案 [MIT License](Open-LLM-VTuber/LICENSE)，含原始 copyright；Live2D 素材另計。 |
| `vendor/CubismWebFramework/` | [原始授權文件](vendor/CubismWebFramework/LICENSE.md)；Live2D Open Software License 與適用的 SDK 發布條件。 |
| `pet-electron/vendor/CubismWebFramework/` | [隨附授權文件](pet-electron/vendor/CubismWebFramework/LICENSE.md)，不因複製位置改變授權。 |
| `vendor/CubismWebSamples/` | [License](vendor/CubismWebSamples/LICENSE.md) 與 [Notice](vendor/CubismWebSamples/NOTICE.md)，樣本素材另有條件。 |
| Cubism Core，包含 frontend／renderer 中的複本 | [Core 授權入口](vendor/CubismWebSamples/Core/LICENSE.md) 指向 Live2D Proprietary Software License；不是 Apache 或 MIT。 |
| `Open-LLM-VTuber/live2d-models/` 樣本角色 | [Live2D 樣本素材條款](Open-LLM-VTuber/LICENSE-Live2D.md)，依個別角色與使用情境適用。 |

官方條款入口：[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)、[Live2D Open Software License](https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html)、[Live2D Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html)。實際使用與發布時應查閱適用版本及個別協議，不以本表取代原文。

## 尚需逐項確認的資產

`kuro_launcher/NaikaiFont-Regular.ttf`、角色圖示、README 圖片、其他字型／音訊／模型與預先打包的前端 library，不能僅由根目錄 LICENSE 推定可再散布。未完成來源與授權清單核對前，不將這些資產宣稱為 Apache-2.0，也不以本次文件整理宣稱完成整包授權稽核。

Python／npm dependencies 依各套件授權；lockfile 記錄版本，不等於完整 license inventory。發布 binary 或搬運 vendor 檔案時，須保留對應 notices，另核對 bundled dependencies、字型與模型的分發條件。

中央語音引擎、模型權重與私人 voice references 由獨立工作區管理，不由此 repo 的 LICENSE 授權。沒有明確權利的資產不要加入新提交或發行包。

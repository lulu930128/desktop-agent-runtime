# Kuro Original Git Renderer → Qt Web Host — Source-Pinned Implementation Plan

Date: 2026-10-10 (+08:00)
Status: APPROVED FOR IMPLEMENTATION; **NO RELEASE ACCEPTANCE YET**
Owner: Kuro desktop; Qt is the sole application UI, tray, runtime lifecycle and qt-primary conversation owner. Electron remains Live2D Pet-only.

## 0. Decision / Source of Truth
User selected the **existing Git Work Companion source itself**, not a Qt Widgets re-creation from screenshots. Target = the older dark work-companion layout with narrow icon rail, compact chrome, Chat character/model/thinking controls and Settings with six category groups (user-supplied older screenshots, 2026-10-10 conversation). Preserve original DOM/CSS, not visual approximations. Wiring may be stubbed during the **isolated preview gate**, but disabled actions must say unavailable, not fake success.

**Authoritative local source revision to verify before writing any code:**
- Repository: `C:\project\desktop-agent-runtime`
- Local recorded HEAD: `995c23c7c8d1be62000229d58610d2214f3bb745`
- Source history location: `git show 995c23c7c8d1be62000229d58610d2214f3bb745:<path>`; check `git rev-parse HEAD` / `git cat-file -e` first.
- GitHub cross-reference (older remote snapshot only, **not authoritative over local HEAD**): `94065af5cfbaa3b5acbd5e7e19417a803cdaa122`. Historical initial Work Panel commit `3baf05728921607d71306c98d43eaad155b0dbc1`.
- Existing ground-truth inventory: `devtools/git-work-companion-parity-20261010/GitSourceInventory.json` and `GitWorkCompanionParityMatrix.md`.
- Do not assume Git HEAD's files are same as remote `94065af`. Verify bytes, versions and hashes before copying.

### Immutable source paths and recorded HEAD raw SHA-256
Paths are relative to repository root; **these are existing Git-tree paths, currently deleted in working tree**. Read via `git show`; do NOT restore them into their old production path.

| Original immutable Git path | Required source / responsibility | Recorded HEAD SHA-256 |
| --- | --- | --- |
| `pet-electron/renderer/src/work-panel/main.ts` | `renderShell`, `renderChat`, `renderSettings`, history drawer, event handlers | `9f0b8eb99c7f1e0435b0b85eaf46222edce1215c6cf89dce91be1105d9cdbbc5` |
| `pet-electron/renderer/src/work-panel/styles.css` | Entire original CSS palette, geometry, breakpoints, Chat/Settings UI | `d6c5bbf9bd49609300f8675061b4acbf4639d3dd08940cf70b79b4054715020f` |
| `pet-electron/renderer/src/work-panel/model.ts` | Today source/priority display helpers | `25b91217df1a805160b92f6215878b16f9ee49af7ed10d9a128b7f15093d0792` |
| `pet-electron/renderer/src/work-panel/types.ts` | `WorkPanelBridge`, UI data types, event contracts | `c06528df69736b5338911b793e6c0fc83ba702e61c6505742ff12b60b1949e52` |
| `pet-electron/renderer/src/work-panel/schedule.ts` | Schedule panel | `695bf308ecc1ba010839a3d50703c6696f6e154457c1346874f8fd3a57f66e99` |
| `pet-electron/renderer/work-panel.html` | Original `#app` mounting document | `35f01f7e3f8cd449e81a7ec6d119cfe88d996f96c72415537fa0f1385dc74acb` |

The 5 hashes above are from the pre-existing `GitSourceInventory.json` under `HEAD` and need independent git-tree verification before acceptance. Historic screenshot repo asset `docs/assets/readme/kuro-v1-work-panel-settings.jpg` is an Electron runtime historical reference; user screenshots of earlier Chat and Settings are the visual target.

### Original UI methods to retain (not re-create in Python)
`main.ts`: `renderShell()`, `renderChrome()`, `renderChat()`, `renderHistoryDrawer()`, `renderChatTranscript()`, `renderSettings()`, `settingsAssistantGroup()`, `settingsConversationGroup()`, `settingsPerceptionGroup()`, `settingsToolsGroup()`, `settingsPetGroup()`, `settingsRuntimeGroup()`, Today and Schedule rendering. DOM and CSS remain the single visual source of truth.
`styles.css`: `--rail-width: 78px`, `--chrome-height: 50px`, `--iris: #65b3a6`, `.rail`, `.chrome`, `.chat-header`, `.message-list`, `.composer`, `.settings-shell`, `.settings-nav`, `.settings-content` and responsive breakpoints. These are from the Git version, **not** the newer 180px/gold/73px QSS recreation.

## 1. Target implementation (do not write another Qt Widgets replica)
Proposed new location:
`kuro_launcher/work_companion_web/`: byte-identical Git source copies in `src/work-panel/` + a narrow HTML/bootstrap entry + `qt-bridge.ts` adapter and build config. Use the already existing Vite/TypeScript toolchain without adding another UI framework. Built static assets stay generated/ignored, not checked in.

Proposed Qt host: `kuro_launcher/qt_web_surface.py`, containing `QWebEngineView` + `QWebChannel` and a minimal allowlisted QObject port. Existing `launcher_qt.py`, `kuro_launcher/qt_app.py`, `qt_controller.py`, `qt_chat_client.py`, `qt_core_pages.py`, and Core stay authoritative; Qt owns window/tray/activation, conversation identity & permissions. Pet stays presentation only.

Old `main.ts` currently does `const bridge = window.kuroWorkPanel || fallbackBridge`. Initialize the new adapter **before importing main.ts** (e.g., separate bootstrap with dynamic import after QWebChannel ready), rather than changing original UI rendering. Preserve old source pristine and record any intentional source changes with rationale and minimal diff. Adapter must map each UI intent to existing Qt/Core/Conversation endpoints, not resurrect old Electron IPC, legacy ports (:23568), mail provider calls or duplicate source-of-truth. Fail closed for unsupported mutating operations. Render a truthful `unavailable/disabled` status for an unwired capability.

## 2. Required gates (stop on real failure)
1. **GIT PIN / WIP GUARD**: Independently confirm local HEAD, all six `git show` sources, SHA-256 & filenames, preserve baseline of existing dirty tracked/untracked files. No `git checkout`, `reset`, `clean`, `git restore` or broad file overwrites. No commit/push. Save actual Git hash/filename proof in this task's checkpoint.
2. **ISOLATED ORIGINAL VIEW**: Create a new, non-production static preview with the original source, original CSS, original markup. Use synthetic anonymous payloads only; never access private history/state or real providers. Typecheck/build it, confirm Chat/Settings/Today navigation, controls, responsive/keyboard states.
3. **WEBENGINE CAPABILITY**: Check whether `QWebEngineView` and `QWebChannel` can truly import and render, not just `.pyi`. Existing `requirements-qt.txt` currently lists `PySide6-Essentials`; the previous reviewer observed no WebEngine `.pyd`. Test compatible addons in an isolated writable env first. **Do not install/change production Python environment or force-disable sandbox/GPU security to hide startup failures**. If unavailable, mark `BLOCKED` and keep the current Qt launcher functional.
4. **Qt HOST / BRIDGE**: Use Qt WebEngine as the sole application UI host only after isolated preview and host capability pass. Allowlist commands and payloads, async result/error and context/revision fences, prevent arbitrary file/network/navigation exposure, maintain existing explicit confirmation for write/delete/send; no repeat/silent fallback; preserve all Pet-only ownership. Do not create a second production app surface.
5. **PARITY + RELEASE GATE**: Compare screenshots from the **same Git UI commit, same view state and synthetic inputs** rendered as (a) original baseline preview, (b) new Qt host, at 1280×720 and 1380×860; inspect optional 125%/200% DPI. Save paths, image dimensions, DOM/layout measurements, computed design tokens and measurable pixel-diff statistics with a clearly documented crop/window-chrome boundary. Pixel diff is evidence, not an invented perfect equality threshold. Require explicit human review of user-provided two target screenshots (older Settings/Chat). Original DOM/CSS and geometric equality are blockers; if rendering cannot be compared, status stays `UNVERIFIED`. Test keyboard/IME, history open/close, model/thinking/role layout, settings six categories, composer, Today/Schedule, accessibility, loading/error/disabled. Confirm G7 removed files remain absent at their *old* paths.
6. **Regression + adoption**: targeted Qt/source tests, frontend TypeScript check/build, existing relevant G3/G5/G6/G8 lifecycle tests and renderer/pet-only tests; capture exact commands and exit codes. Do not claim actual Windows visible desktop, hardware, mic/camera, real memory/history and TTS acceptance without explicit live user verification.

## 3. Mandatory stop conditions / rollback
- Do not restore Electron application windows/business services, Pet tray or old WorkPanelControlServer; existing architecture remains Qt-primary.
- Do not touch running Qt/Core/Conversation/Pet/TTS processes, private chat/history/memory/OAuth/models, official DB or provider refresh as part of isolated screenshot work.
- Do not add hidden production fallback or dual frontend.
- If source hashes, dependency runtime or security isolation differs from this document, stop and report actual evidence; retain existing running launcher/Qt UI untouched.
- Keep source snapshot + scoped diff with pre-image hashes. Rollback only new files and task-owned changes after verifying hashes; never reset the entire dirty worktree.
- Record PASS / FAIL / BLOCKED / UNVERIFIED per gate; product acceptance = **NOT ACCEPTED** until old and new render parity plus production smoke are demonstrated.

## 4. Frontend skill review rubric
Use user's enabled `frontend-design`, `design-taste-frontend` and `ui-ux-pro-max` skills for exact DOM/CSS fidelity, effective viewport, typography, focus outlines, narrow navigation, keyboard behavior, responsive breakpoints, and screenshot alignment. They must **audit fidelity to the Git source**, not propose a third redesign.

## 5. 2026-10-10 實作 checkpoint：原始碼隔離完成、Qt WebEngine 阻塞

本節是現行進度；上方第 1 節 `kuro_launcher/work_companion_web/` 為早期**提議位置，已被本節取代**。因該路徑會被現有 G8 production consumer scan 視為重新加入舊 Work Panel，為避免退回正式版的安全／ownership 收斂，所有本輪原始碼只放在：

`devtools/original-git-web-host-20261010/frontend/`

Git 歷史基準（本機）：`995c23c7c8d1be62000229d58610d2214f3bb745`。以 `git cat-file`／`git show` 取得原版原始碼後，逐檔核對來源、目的地 SHA-256 完全一致；不是根據圖片重畫，不恢復 Electron 舊的正式執行路徑。

| 原始 Git source path | Source SHA-256（本機 Git） | 實際隔離目的地（相對上述 frontend 目錄） | 結果 |
| --- | --- | --- | --- |
| `pet-electron/renderer/src/work-panel/main.ts` | `9f0b8eb99c7f1e0435b0b85eaf46222edce1215c6cf89dce91be1105d9cdbbc5` | `src/work-panel/main.ts` | PASS，91835 bytes |
| `pet-electron/renderer/src/work-panel/styles.css` | `d6c5bbf9bd49609300f8675061b4acbf4639d3dd08940cf70b79b4054715020f` | `src/work-panel/styles.css` | PASS，39429 bytes |
| `pet-electron/renderer/src/work-panel/model.ts` | `25b91217df1a805160b92f6215878b16f9ee49af7ed10d9a128b7f15093d0792` | `src/work-panel/model.ts` | PASS，6874 bytes |
| `pet-electron/renderer/src/work-panel/types.ts` | `c06528df69736b5338911b793e6c0fc83ba702e61c6505742ff12b60b1949e52` | `src/work-panel/types.ts` | PASS，7049 bytes |
| `pet-electron/renderer/src/work-panel/schedule.ts` | `695bf308ecc1ba010839a3d50703c6696f6e154457c1346874f8fd3a57f66e99` | `src/work-panel/schedule.ts` | PASS，20274 bytes |
| `pet-electron/renderer/work-panel.html` | `35f01f7e3f8cd449e81a7ec6d119cfe88d996f96c72415537fa0f1385dc74acb` | `work-panel.html` | PASS，367 bytes |

詳細證據：`devtools/original-git-web-host-20261010/SourceVerification.json`；包含 blob、不同 commit（`94065af` 與 `3baf057`）比較、目的地 SHA 與 G7 35 個原路徑維持不存在。

### Gate 與真實可驗證狀態

| Gate | 狀態 | 本輪證據或尚未完成項目 |
| --- | --- | --- |
| Git pin／WIP baseline | PASS | 六個 Git 檔案原位元相同，既有 1202 個 WIP source/資料檔沒有意外修改；35 個 G7 原 legacy 路徑仍不存在 |
| Isolated Web source/build | SOURCE PASS、UI interaction UNVERIFIED | 原版 HTML/CSS/TS 保存；Vite 8.0.13、TS 6.0.3 check/build 成功；合成 bridge preview 可短暫由 localhost 提供 |
| Qt WebEngine 執行環境 | BLOCKED | 正式 Python 3.10.12 裡 `QtWebChannel`／`QtWebEngineWidgets` 不存在，隔離 Python venv 因 Windows socket 權限 error 10013 無法下載套件；不可把 `.pyi` 當執行套件 |
| Qt Host／Bridge | 隔離候選程式已建立，runtime BLOCKED | `qt_preview_host.py`、`preview_protocol.py` 只接 synthetic/read-only；沒有正式 Qt Controller／Core／Conversation 接線；4 Python 和 3 Node bridge tests PASS |
| 原版 ↔ 新版畫面高度一致 | UNVERIFIED／NOT ACCEPTED | Chrome Headless GPU process 故障，內建 browser sandbox 無法啟動，**0 張**成功基準／Qt Host 截圖；沒有 DOM 座標、DPI、像素差異測量可作為 PASS |
| Regression／正式 adoption | Source targeted PASS；正式採用 BLOCKED | G3/G4/G5/G6/G8 相關 73 Python tests PASS；Pet owner 20 Node PASS，原 Pet renderer check/build PASS；正式 `launcher_qt.py` 未接新 Host，不重啟、無 commit/push |

**正式版仍未切換**：這一輪不得聲稱圖二／圖三已經在 Qt Host 真正顯示。不得恢復原 Electron Work Panel 的 business/IPC/Window/Tray 或把 synthetic 測試說成真實服務驗收。待正常 Windows 權限環境可啟動 Chrome 與 PySide6 WebEngine，依 `devtools/original-git-web-host-20261010/README.md` 重新執行隔離 capture，在 **同 commit、同 fixture、同 viewport** 下比對 Chat/Settings（主要）、Today/Schedule（次要）的截圖、DOM/CSS 幾何、字型、DPI、pixel MAE/RMS/changed fraction，以及原版操作。比對 PASS 後，另行設計正式 Qt Bridge 與 acceptance，不以技術預覽繞過 Core/Conversation ownership 和確認政策。

細節與安全接力：`devtools/original-git-web-host-20261010/README.md`；`Validation.json` 為第一次原路徑造成 G8 FAIL 的歷史證據；**`ValidationFollowup.json`** 是隔離路徑修正後 G8 PASS 的後續證據。正式發布仍 **NOT ACCEPTED**。


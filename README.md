# Kuro Desktop Agent Runtime

這份 repo 把 `launcher`、`Open-LLM-VTuber`、`gpt_sovits`、`bridge`、角色 prompt、專案 prompt 放在同一個工作區，方便直接當成一份完整專案維護。

目前的路徑原則是：

1. 進 git 的設定檔盡量使用 **repo 相對路徑**
2. `launcher` 在執行時再把需要的路徑轉成 **絕對路徑**
3. 本機秘密、log、模型權重、音檔、runtime 暫存檔維持在 `.gitignore`

## 啟動

```powershell
cd <repo-root>
.\envs\kuro-llm310\python.exe .\launcher.py
```

也可以直接使用根目錄的 `桌寵啟動器.vbs`。

## 路徑規則

- `kuro_launcher.settings.yaml` 使用 `${HERE}` 當 repo root
- 角色 YAML 內的 `ref_audio_path` 使用 `voices/<角色ID>/...`
- `compose.yaml` 的 bind mount 使用相對路徑
- `launcher` 會在產生 runtime 設定時，把需要的音檔路徑轉成絕對路徑
- `gpt_sovits_tts.py` 的 debug dump 不再綁死某一台機器的目錄

## 重要檔案

- `kuro_launcher.settings.yaml`
- `launcher.py`
- `kuro_launcher/runtime_conf.py`
- `kuro_launcher/services.py`
- `Open-LLM-VTuber/characters/*.yaml`
- `Open-LLM-VTuber/model_dict.json`
- `Open-LLM-VTuber/prompts/persona/*.txt`
- `Open-LLM-VTuber/prompts/utils/response_contract_prompt.txt`
- `projects/<project_id>/project.yaml`
- `projects/<project_id>/prompts/project_prompt.txt`
- `projects/<project_id>/prompts/tool_prompt.txt`
- `voices/<角色ID>/ref.wav`
- `voices/<角色ID>/ref6s.wav`
- `gpt_sovits/GPT_SoVITS/configs/tts_infer_<角色ID>.yaml`

## Prompt 分層

目前 system prompt 會依序組成：

1. `System Contract`
2. `Character Persona`
3. `Project Context`
4. `Tool Use Policy`
5. `Expression Contract`

其中：

- 角色人格放在 `Open-LLM-VTuber/prompts/persona/*.txt`
- 專案 prompt 放在 `projects/<project_id>/prompts/project_prompt.txt`
- tool prompt 放在 `projects/<project_id>/prompts/tool_prompt.txt`
- 系統輸出格式放在 `Open-LLM-VTuber/prompts/utils/response_contract_prompt.txt`

## 角色與專案

### 角色

角色設定檔位於：

- `Open-LLM-VTuber/characters/`

每個角色至少會關聯到：

- `conf_name`
- `conf_uid`
- `live2d_model_name`
- `persona_prompt_path`
- `default_project_id`
- `agent_config`
- `tts_config`

### 專案

專案設定位於：

- `projects/`

目前範例專案：

- `projects/desktop-agent-runtime/project.yaml`

## 記憶規則

目前記憶維持 **一個角色一份**，不因切換專案分離。  
也就是說，同一角色在不同專案下會延續同一份角色記憶。

## Launcher

目前 `launcher` 已改成 `CustomTkinter`，主要負責：

- 選角色
- 選專案
- 預覽 prompt
- 啟動 / 停止 / 重啟各服務
- 查看 log

## Git 注意事項

建議提交的內容：

- 角色 YAML
- persona / project / tool prompt
- `model_dict.json`
- `tts_infer_<角色ID>.yaml`
- 專案設定
- 程式碼與文件

不要提交的內容：

- `.env`
- API key
- `launcher_logs/`
- `Open-LLM-VTuber/conf.launcher_runtime.yaml`
- `voices/**/*.wav`
- `*.ckpt`
- `*.pth`
- `gpt_sovits/GPT_weights*/`
- `gpt_sovits/SoVITS_weights*/`
- `gpt_sovits/GPT_SoVITS/pretrained_models/`
- 本機暫存資料夾

## 目前方向

這份專案現在的設計目標是：

- repo 可以被 clone 到任意路徑
- 角色 prompt、專案 prompt、tool prompt 可獨立調整
- `launcher` 負責把相對路徑整理成執行時需要的配置
- 使用者後續可以直接把這份 repo 當模板延伸自己的角色與專案

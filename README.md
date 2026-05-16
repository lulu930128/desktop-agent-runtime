# Kuro Desktop Agent Runtime

這份專案把 `launcher`、`Open-LLM-VTuber`、`gpt_sovits`、`bridge`、角色設定和專案 prompt 放在同一個 repo，目標是讓別人 clone 下來後，只要補本機模型、音檔和金鑰，就能直接套模板啟動。

## 啟動

```powershell
cd C:\your-folder\desktop-agent-runtime
.\envs\kuro-llm310\python.exe .\launcher.py
```

## 路徑規則

現在這份專案採用兩層規則：

1. **repo 內儲存的設定盡量用相對路徑**
2. **launcher 在執行時再把需要的資源轉成絕對路徑**

這樣做的好處是：

- repo 可以搬到別的磁碟或別的資料夾
- 角色 YAML 可以當模板重複使用
- 啟動器仍然能穩定把音檔、prompt 與 runtime config 指到正確位置

### 目前已改成相對路徑的重點

- [C:\kuro\kuro_launcher.settings.yaml](C:/kuro/kuro_launcher.settings.yaml)  
  `ROOT` 改成 `${HERE}`，不再綁死 `C:\kuro`

- 角色 YAML 的 `ref_audio_path` 改成 repo 相對路徑  
  例如：
  - [C:\kuro\Open-LLM-VTuber\characters\kuro.yaml](C:/kuro/Open-LLM-VTuber/characters/kuro.yaml)
  - [C:\kuro\Open-LLM-VTuber\characters\mao_pro.yaml](C:/kuro/Open-LLM-VTuber/characters/mao_pro.yaml)
  - [C:\kuro\Open-LLM-VTuber\characters\shizuku.yaml](C:/kuro/Open-LLM-VTuber/characters/shizuku.yaml)
  - [C:\kuro\Open-LLM-VTuber\characters\yumi.yaml](C:/kuro/Open-LLM-VTuber/characters/yumi.yaml)

- [C:\kuro\compose.yaml](C:/kuro/compose.yaml) 的 bind mount 改成相對路徑

### 執行時的轉換

- [C:\kuro\kuro_launcher\runtime_conf.py](C:/kuro/kuro_launcher/runtime_conf.py)  
  會把角色 YAML 裡的 `ref_audio_path` 轉成 runtime 用的絕對路徑，再寫進 `conf.launcher_runtime.yaml`

- [C:\kuro\kuro_launcher\services.py](C:/kuro/kuro_launcher/services.py)  
  啟動 LLM 時會把 launcher log 目錄用環境變數傳給子程序

- [C:\kuro\Open-LLM-VTuber\src\open_llm_vtuber\tts\gpt_sovits_tts.py](C:/kuro/Open-LLM-VTuber/src/open_llm_vtuber/tts/gpt_sovits_tts.py)  
  不再把 debug dump 寫死到 `C:\kuro\launcher_logs`

## Prompt 分層

system prompt 目前會依序組成：

1. `System Contract`
2. `Character Persona`
3. `Project Context`
4. `Tool Use Policy`
5. `Expression Contract`

對應位置如下：

- 系統輸出格式：
  [C:\kuro\Open-LLM-VTuber\prompts\utils\response_contract_prompt.txt](C:/kuro/Open-LLM-VTuber/prompts/utils/response_contract_prompt.txt)
- 角色 persona：
  [C:\kuro\Open-LLM-VTuber\prompts\persona](C:/kuro/Open-LLM-VTuber/prompts/persona)
- 專案 prompt：
  [C:\kuro\projects\desktop-agent-runtime\prompts\project_prompt.txt](C:/kuro/projects/desktop-agent-runtime/prompts/project_prompt.txt)
- tool prompt：
  [C:\kuro\projects\desktop-agent-runtime\prompts\tool_prompt.txt](C:/kuro/projects/desktop-agent-runtime/prompts/tool_prompt.txt)

## 角色與專案

### 角色設定

角色 YAML 放在：

- [C:\kuro\Open-LLM-VTuber\characters](C:/kuro/Open-LLM-VTuber/characters)

每個角色目前至少包含：

- `conf_name`
- `conf_uid`
- `live2d_model_name`
- `persona_prompt_path`
- `default_project_id`
- `agent_config`
- `tts_config`

### 專案設定

專案設定放在：

- [C:\kuro\projects](C:/kuro/projects)

目前範例專案：

- [C:\kuro\projects\desktop-agent-runtime\project.yaml](C:/kuro/projects/desktop-agent-runtime/project.yaml)

## 記憶規則

目前仍然是 **一角色一份記憶**。

也就是說：

- 切換專案不會切記憶
- 同一角色在不同專案下仍會保留同一份角色歷程

這符合目前的目標：角色像同一個人，只是工作上下文不同。

## Launcher 目前做的事

新的 launcher 已改成 `CustomTkinter`，可以：

- 選角色
- 選專案
- 看目前 prompt 指向
- 啟動 / 停止 Bridge、TTS、LLM
- 看 log

## 目前保留空白給你重寫的地方

以下 prompt 目前預設留空，方便你自己設計：

- [C:\kuro\Open-LLM-VTuber\prompts\persona\kuro.txt](C:/kuro/Open-LLM-VTuber/prompts/persona/kuro.txt)
- [C:\kuro\Open-LLM-VTuber\prompts\persona\mao_pro.txt](C:/kuro/Open-LLM-VTuber/prompts/persona/mao_pro.txt)
- [C:\kuro\Open-LLM-VTuber\prompts\persona\shizuku.txt](C:/kuro/Open-LLM-VTuber/prompts/persona/shizuku.txt)
- [C:\kuro\Open-LLM-VTuber\prompts\persona\yumi.txt](C:/kuro/Open-LLM-VTuber/prompts/persona/yumi.txt)
- [C:\kuro\projects\desktop-agent-runtime\prompts\project_prompt.txt](C:/kuro/projects/desktop-agent-runtime/prompts/project_prompt.txt)
- [C:\kuro\projects\desktop-agent-runtime\prompts\tool_prompt.txt](C:/kuro/projects/desktop-agent-runtime/prompts/tool_prompt.txt)

只有系統輸出格式 prompt 目前是預先填好的。

# === 0. 乾淨骨架（固定 ASCII 路徑） ===
New-Item -ItemType Directory `
  C:\kuro, C:\kuro\gpt_sovits, C:\kuro\datasets, C:\kuro\models\gpt_sovits `
  -Force | Out-Null

# === 1. 安裝 uv（官方推薦方式之一） ===
try { uv --version | Out-Null } catch {
  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

# === 2. 安裝 FFmpeg（winget） ===
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  winget install -e --id Gyan.FFmpeg
}

# === 3. 取得 GPT-SoVITS 官方 repo（不要用 fork） ===
Set-Location C:\kuro\gpt_sovits
if (-not (Test-Path .git)) { git clone https://github.com/RVC-Boss/GPT-SoVITS . }

# === 4. 建獨立 venv 並安裝依賴（遵循官方順序） ===
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -r extra-req.txt --no-deps
uv pip install -r requirements.txt

Write-Host "`n==> 下一步：到 https://pytorch.org/get-started/locally/ 生成 Windows/pip/CUDA 的安裝指令，貼回終端來裝 GPU 版 torch。"
Write-Host "==> 然後把 BERT/HuBERT/ERes2Net 權重放到 GPT_SoVITS\pretrained_models\*（見 README）。"

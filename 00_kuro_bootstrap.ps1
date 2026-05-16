# === 0. Resolve repo root ===
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$GptSovitsDir = Join-Path $RepoRoot "gpt_sovits"
$DatasetsDir = Join-Path $RepoRoot "datasets"
$ModelsDir = Join-Path $RepoRoot "models\gpt_sovits"

New-Item -ItemType Directory `
  -Path $RepoRoot, $GptSovitsDir, $DatasetsDir, $ModelsDir `
  -Force | Out-Null

# === 1. Install uv if missing ===
try { uv --version | Out-Null } catch {
  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

# === 2. Install FFmpeg if missing ===
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  winget install -e --id Gyan.FFmpeg
}

# === 3. Clone GPT-SoVITS if needed ===
Set-Location $GptSovitsDir
if (-not (Test-Path .git)) { git clone https://github.com/RVC-Boss/GPT-SoVITS . }

# === 4. Create venv and install Python deps ===
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -r extra-req.txt --no-deps
uv pip install -r requirements.txt

Write-Host "`n==> Next: open https://pytorch.org/get-started/locally/ and generate the Windows/pip/CUDA command for your machine."
Write-Host "==> Then install the correct GPU build of torch into this environment."
Write-Host "==> Pretrained BERT/HuBERT/ERes2Net files still need to be placed under GPT_SoVITS\pretrained_models\*."

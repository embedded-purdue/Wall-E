#!/bin/bash
# One-time setup on a Gilbreth LOGIN node (not inside a job).
# Builds the venv and pre-downloads model weights, so the compute node never
# needs the network. Run:  bash gilbreth_setup.sh
set -euo pipefail

# Home has a small quota; weights and the venv go to scratch.
export HF_HOME="$RCAC_SCRATCH/hf"
VENV="$RCAC_SCRATCH/btbench-venv"

# Models to pull. Keep this list identical to the one in gilbreth_sweep.sbatch.
MODELS=(
  "meta-llama/Llama-3.2-1B-Instruct"        # Akshat's baseline: 36.3%, below the 54.9% majority line
  "Qwen/Qwen3-1.7B"                         # hybrid reasoning: thinking forced off in walle_bt.encode
  "Qwen/Qwen2.5-Coder-1.5B-Instruct"
  "deepseek-ai/deepseek-coder-1.3b-instruct"
  "meta-llama/Llama-3.2-3B-Instruct"        # gated
  "google/gemma-3n-E2B-it"                  # gated; needs recent transformers
  "HuggingFaceTB/SmolLM3-3B"                # hybrid reasoning: /no_think injected into system
  "microsoft/Phi-4-mini-instruct"
  "Qwen/Qwen3-4B-Instruct-2507"             # the non-thinking Qwen3 variant
)

module purge

# Module names differ per cluster and change between maintenances, so try the usual
# candidates rather than hard-coding one. `module spider python` lists what's really here.
# Gilbreth (Nov 2026) has only versioned anaconda/conda modules; the bare name fails.
# py312 first: torch wheels for 3.13 are patchier than for 3.12.
for m in anaconda/2024.10-py312 anaconda/2025.06-py313 conda/2025.09 conda/2026.03 anaconda conda; do
  if module load "$m" 2>/dev/null; then
    echo "loaded module: $m"
    break
  fi
done
command -v python3 >/dev/null || { echo "No python3 after module load; run 'module spider python'"; exit 1; }
PY_BIN="$(command -v python3)"
echo "python: $PY_BIN ($($PY_BIN --version 2>&1))"

if [ ! -d "$VENV" ]; then
  "$PY_BIN" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
# Gemma 3n and Phi-4-mini need a recent transformers; pin one version for the whole sweep
pip install --quiet torch "transformers>=4.53" accelerate pyyaml python-dotenv sentencepiece protobuf

mkdir -p "$HF_HOME"

# Gated repos (meta-llama) need a token: accept the license on huggingface.co,
# then `huggingface-cli login` once, or export HF_TOKEN before running this.
for m in "${MODELS[@]}"; do
  echo "=== fetching $m"
  python - "$m" <<'PY'
import sys
from huggingface_hub import snapshot_download
model = sys.argv[1]
try:
    snapshot_download(model, allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt"])
    print(f"  ok: {model}")
except Exception as exc:
    print(f"  FAILED {model}: {exc}")   # keep going; a gated repo shouldn't stop the rest
PY
done

echo
echo "venv:    $VENV"
echo "weights: $HF_HOME"
echo "Now submit the sweep:  sbatch gilbreth_sweep.sbatch"

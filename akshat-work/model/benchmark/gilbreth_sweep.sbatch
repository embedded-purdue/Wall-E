#!/bin/bash
# Classifier sweep on Gilbreth: does a bigger model beat Llama-3.2-1B's 36.3%?
#
# Baseline to beat (meta-llama/Llama-3.2-1B-Instruct, 91 requests):
#   overall 33/91 = 36.3%   task 9/50   cannot_do 16/16   conversation 8/12   unclear 0/13
#
# Run gilbreth_setup.sh on a login node FIRST, then:  sbatch gilbreth_sweep.sbatch
# Check your queue name and limits with `slist` before submitting.

#SBATCH --job-name=walle-clf-sweep
#SBATCH --account=csso                # from `slist`; csso has the free A10s
#SBATCH --partition=a10               # Gilbreth requires an explicit partition.
                                      # A10 = 24GB, plenty for <=4B in fp16, and no queue.
                                      # For A100s instead: --account=dkihara --partition=a100-80gb
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.out

set -euo pipefail

export HF_HOME="$RCAC_SCRATCH/hf"
export HF_HUB_OFFLINE=1               # weights were pre-fetched; fail loudly instead of hanging
export TOKENIZERS_PARALLELISM=false

module purge
# Same module probing as gilbreth_setup.sh: the venv's interpreter is a symlink into
# whichever python module was loaded, so it has to be on PATH here too.
for m in anaconda/2024.10-py312 anaconda/2025.06-py313 conda/2025.09 conda/2026.03 anaconda conda; do
  module load "$m" 2>/dev/null && { echo "loaded module: $m"; break; }
done
# shellcheck disable=SC1091
source "$RCAC_SCRATCH/btbench-venv/bin/activate"

cd "$SLURM_SUBMIT_DIR"
mkdir -p results/sweep

nvidia-smi
python -c "import torch; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0))"

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

for m in "${MODELS[@]}"; do
  slug="${m##*/}"                     # Qwen/Qwen2.5-7B-Instruct -> Qwen2.5-7B-Instruct
  out="results/sweep/clf_${slug}.csv"
  if [ -s "$out" ]; then
    echo "=== skip $m (already have $out)"
    continue
  fi
  echo "=== $m -> $out"
  # --device cuda so a silent CPU fallback can't make this take hours
  python run_classifier.py --model "$m" --device cuda --out "$out" || {
    echo "    FAILED $m, continuing"   # one bad model shouldn't kill the sweep
    continue
  }
done

echo
python report_classifier.py "results/sweep/clf_*.csv" --csv results/sweep/summary.csv

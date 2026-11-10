#!/bin/bash
# Tree-generation sweep on Gilbreth: can a bigger model actually build the trees?
#
# The classifier sweep answered its own question (Qwen3-4B 83.5% vs a 54.9% baseline),
# but that says nothing about tree generation: both 1B models manage 1-5 action matches
# out of 49 there. Classification and generation are different difficulties.
#
# Grading is automatic -- report_tree.py compares against expected_steps -- so no
# hand-grading is needed for these numbers.
#
# Run gilbreth_setup.sh on a login node first, then:  sbatch gilbreth_tree.sbatch

#SBATCH --job-name=walle-tree-sweep
#SBATCH --account=csso
#SBATCH --partition=a10
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00          # 6 models x 49 tasks x 2 conditions, up to 1024 new
                                 # tokens each -- far longer than the classifier's JSON
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.out

set -euo pipefail

export HF_HOME="$RCAC_SCRATCH/hf"
export HF_HUB_OFFLINE=1
export TOKENIZERS_PARALLELISM=false

module purge
for m in anaconda/2024.10-py312 anaconda/2025.06-py313 conda/2025.09 conda/2026.03 anaconda conda; do
  module load "$m" 2>/dev/null && { echo "loaded module: $m"; break; }
done
# shellcheck disable=SC1091
source "$RCAC_SCRATCH/btbench-venv/bin/activate"

cd "$SLURM_SUBMIT_DIR"
mkdir -p results/tree_sweep

nvidia-smi
python -c "import torch; print('torch', torch.__version__, '| cuda', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0))"

# Deployment candidates only. Gemma 3n is excluded: AutoTokenizer reports no chat
# template for it, so it would run unformatted while every other model gets its own.
MODELS=(
  "meta-llama/Llama-3.2-1B-Instruct"        # anchor: comparable to the week-3 chart
  "Qwen/Qwen3-1.7B"                         # the likely Jetson Orin Nano pick
  "microsoft/Phi-4-mini-instruct"           # best `unclear` recall in the classifier sweep
  "Qwen/Qwen3-4B-Instruct-2507"             # classifier leader; ceiling if generation is offloaded
  "Qwen/Qwen2.5-Coder-1.5B-Instruct"        # flopped at classification, but BT XML is structured
  "deepseek-ai/deepseek-coder-1.3b-instruct"#   output -- worth testing where coder tuning helps
)

for m in "${MODELS[@]}"; do
  slug="${m##*/}"
  out="results/tree_sweep/tree_${slug}.csv"
  echo "=== $m -> $out"
  # --resume keys on (model, id, condition): a walltime kill costs nothing.
  python run_tree_baseline.py --models "$m" --device cuda --out "$out" --resume || {
    echo "    FAILED $m, continuing"
    continue
  }
done

echo
python report_tree.py "results/tree_sweep/tree_*.csv" --by-difficulty --csv results/tree_sweep/summary.csv

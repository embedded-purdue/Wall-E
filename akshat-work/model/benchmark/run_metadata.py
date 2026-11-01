"""Record inputs/settings; refuse to resume results from a different experiment."""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def config_for(args, inputs):
    settings = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()
                if k not in {"resume", "out", "dry_run", "print_prompt"}}
    packages = {}
    for name in ["PyYAML", "torch", "transformers", "peft", "sentence-transformers"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    code = list(Path(__file__).parent.glob("*.py"))
    code.append(Path(__file__).parent.parent / "bt_validator.py")
    try:
        git = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        git = "unknown"
    return {"settings": settings, "inputs": {str(p): fingerprint(p) for p in inputs},
            "code": {p.name: fingerprint(p) for p in code}, "git_head": git,
            "python": platform.python_version(), "platform": platform.platform(),
            "packages": packages}


def prepare_run(out, config, resume=False):
    path = Path(str(out) + ".meta.json")
    if out.exists():
        if not resume:
            raise ValueError(f"Refusing to overwrite {out}; choose a new --out path.")
        if not path.exists():
            raise ValueError("Cannot resume a CSV without its .meta.json provenance.")
        metadata = json.loads(path.read_text())
        if metadata["config"] != config:
            raise ValueError("Resume settings, inputs, code or environment changed; use a new --out.")
        return path, metadata
    metadata = {"config": config, "models": {}}
    path.write_text(json.dumps(metadata, indent=2) + "\n")
    return path, metadata

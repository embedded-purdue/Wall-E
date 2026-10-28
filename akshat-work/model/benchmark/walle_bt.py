"""Shared helpers for the Wall-E baseline: prompts, cleanup, readable steps, example retrieval."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

HERE = Path(__file__).parent

# BTGenBot-2's system prompt, copied exactly from their dataset (bt_dataset.json "instruction").
SYSTEM_PROMPT = """
You are a helpful assistant that can assist with creating behavior trees.
Your task:
- Convert the provided summary of a behavior into an XML-formatted behavior tree.
- Ensure the behavior tree matches the description in the summary.
- The behavior tree must be compatible with the BehaviorTree.CPP library.
- Only use the actions and parameters provided in the action list below the summary.

Output Requirements:
- Output only the XML representation of the behavior tree. Do not include explanations, comments, or any additional text.
- Ensure all actions and parameters strictly match the provided list.
- If possible limit the use of SubTrees.

Please generate the behavior tree based on the summary and action list provided.
"""

# Our wrapper that turns a raw request into something shaped like their training summaries,
# which all start with "The behavior tree ...".
REQUEST_TEMPLATE = (
    "The behavior tree controls Wall-E, a small robot with treads, a head camera, one arm "
    'and a can crusher. The user said: "{request}". The tree makes Wall-E carry out exactly '
    "this request, using only the actions below."
)


# ---------- skills from the shared YAML ----------
def action_list(yaml_path: str | Path) -> str:
    """Build BTGenBot-2's 'Actions: [...]' line from the YAML.

    Their training data lists only leaf nodes, in this exact format, and never lists control or
    decorator nodes, so we do the same. Conditions go in the same list because the model has
    never seen a separate 'Conditions:' line.
    """
    vocab = yaml.safe_load(Path(yaml_path).read_text())
    parts = []
    for section in ("actions", "conditions"):
        for name, spec in (vocab.get(section) or {}).items():
            spec = spec or {}
            params = list(spec.get("required", [])) + list(spec.get("optional", []))
            parts.append(
                f"{name} (parameters: {', '.join(params)})" if params else name
            )
    return "Actions: [" + ", ".join(parts) + "]"


def user_message(request: str, actions: str) -> str:
    return REQUEST_TEMPLATE.format(request=request) + "\n\n" + actions


def build_messages(
    request: str, actions: str, example: dict | None = None
) -> list[dict]:
    """Zero-shot, or one-shot with the example as an earlier user/assistant turn.

    The paper doesn't say how it formatted the one-shot example. A prior chat turn matches the
    training format exactly (system / user / assistant), so the model sees a solved task first.
    """
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if example:
        msgs.append(
            {"role": "user", "content": user_message(example["request"], actions)}
        )
        msgs.append({"role": "assistant", "content": example["tree_xml"].strip()})
    msgs.append({"role": "user", "content": user_message(request, actions)})
    return msgs


# ---------- output cleanup ----------
def clean_output(text: str) -> tuple[str, bool]:
    """Keep only <root ...>...</root>. Returns (xml, had_extra_text).

    Only strips code fences and text outside the root element; never edits the tree itself.
    """
    raw = text.strip()
    start, end = raw.find("<root"), raw.find("</root>")
    if start == -1 or end == -1:
        return raw, False
    xml = raw[start : end + len("</root>")]
    return xml, xml != raw


# ---------- readable steps (same notation as the test set) ----------
def _snake(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()


def shorthand(node: ET.Element, top: bool = True) -> str:
    tag, kids = node.tag, list(node)
    if tag in ("Action", "Condition"):  # explicit <Action ID="..."> form
        tag = node.attrib.get("ID", tag)
    attrs = {k: v for k, v in node.attrib.items() if k not in ("ID", "name")}
    if tag == "Sequence":
        s = " -> ".join(shorthand(k, False) for k in kids)
        return s if top else f"({s})"
    if tag == "Fallback":
        return "[" + " | ".join(shorthand(k, False) for k in kids) + "]"
    if kids:
        params = ", ".join(f"{k}={v}" for k, v in attrs.items())
        return f"{tag}({params}){{ " + " ; ".join(shorthand(k) for k in kids) + " }"
    args = [f'"{v}"' if k in ("text", "hint") else v for k, v in attrs.items()]
    return f"{_snake(tag)}({', '.join(args)})"


def steps_from_xml(xml: str) -> str:
    """Readable steps for a tree, or '' if it doesn't parse."""
    try:
        root = ET.fromstring(xml)
        bt = root.find("BehaviorTree")
        return shorthand(list(bt)[0]) if bt is not None and len(bt) else ""
    except ET.ParseError:
        return ""


# ---------- example library + retrieval ----------
_STOP = set(
    "a an the to and it my me you your of on in at for is are then that this please".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z']+", text.lower()) if t not in _STOP]


class ExampleLibrary:
    """Picks the closest example tree for a request.

    retriever="embed": sentence-transformers embeddings of request + description (what week 4 builds).
    retriever="tfidf": word overlap, no extra dependencies, but weaker.
    retriever="auto":  embed if sentence-transformers is installed, else tfidf.
    """

    EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self, path: str | Path = HERE / "example_library.json", retriever: str = "tfidf"
    ):
        self.items = json.loads(Path(path).read_text())
        if retriever in ("auto", "embed"):
            try:
                from sentence_transformers import SentenceTransformer

                self._st = SentenceTransformer(self.EMBED_MODEL)
                self._emb = self._st.encode(
                    [i["request"] + ". " + i["description"] for i in self.items],
                    normalize_embeddings=True,
                )
                self.retriever = "embed"
                return
            except ImportError:
                if retriever == "embed":
                    raise
        self.retriever = "tfidf"
        docs = [_tokens(i["request"] + " " + i["description"]) for i in self.items]
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        v = {t: c * self.idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def retrieve(self, request: str) -> tuple[dict, float]:
        if self.retriever == "embed":
            q = self._st.encode([request], normalize_embeddings=True)[0]
            scores = [float(x) for x in self._emb @ q]
            best = max(range(len(scores)), key=scores.__getitem__)
            return self.items[best], scores[best]
        q = self._vec(_tokens(request))
        scores = [sum(q.get(t, 0) * w for t, w in v.items()) for v in self.vecs]
        best = max(range(len(scores)), key=scores.__getitem__)
        return self.items[best], scores[best]


def near_duplicates(
    test_requests: list[str], library: ExampleLibrary, threshold: float = 0.6
):
    """Test requests whose words overlap a library request too much (Jaccard), i.e. leakage."""
    hits = []
    for r in test_requests:
        a = set(_tokens(r))
        for item in library.items:
            b = set(_tokens(item["request"]))
            if a and b and len(a & b) / len(a | b) >= threshold:
                hits.append((r, item["request"]))
    return hits


# ---------- local Hugging Face models (shared by both scripts) ----------
DEFAULT_MAIN_LLM = "meta-llama/Llama-3.2-1B-Instruct"
BTGENBOT2 = "AIRLab-POLIMI/llama-3.2-1b-it-ft-lora-bt"


def load_env():
    """HF_TOKEN from a .env file, as in the team notebook."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def load_chat_model(model_id: str, device: str = "auto"):
    """Load a model with transformers. Returns generate(messages, max_new_tokens, sample, stop) -> (text, n_tokens).

    Instruct/chat models use their chat template. A base model (no template) gets a plain
    "System/User/Assistant" transcript instead, and `stop` strings keep it from rambling.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if device == "auto":
        device = (
            "cuda"
            if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available() else "cpu"
        )
    if device == "cuda":
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    else:
        dtype = torch.float16 if device == "mps" else torch.float32

    tok = AutoTokenizer.from_pretrained(model_id)
    try:
        model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
    except TypeError:  # older transformers
        model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype)
    model.to(device).eval()
    has_template = bool(getattr(tok, "chat_template", None))
    print(
        f"Loaded {model_id} on {device} ({dtype}){'' if has_template else ' [no chat template: plain-text prompt]'}"
    )

    def encode(messages):
        if has_template:
            return tok.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            ).to(device)
        text = (
            "".join(
                f"{m['role'].capitalize()}: {m['content'].strip()}\n\n"
                for m in messages
            )
            + "Assistant:"
        )
        return tok(text, return_tensors="pt").to(device)

    def generate(messages, max_new_tokens=1024, sample=False, stop=None):
        inputs = encode(messages)
        kwargs = dict(
            max_new_tokens=max_new_tokens,
            pad_token_id=(
                tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
            ),
        )
        kwargs.update(
            dict(do_sample=True, temperature=0.7, top_p=0.95)
            if sample
            else dict(do_sample=False)
        )
        if stop:
            kwargs.update(stop_strings=stop, tokenizer=tok)
        with torch.no_grad():
            try:
                out = model.generate(**inputs, **kwargs)
            except (TypeError, ValueError):  # transformers too old for stop_strings
                kwargs.pop("stop_strings", None), kwargs.pop("tokenizer", None)
                out = model.generate(**inputs, **kwargs)
        new = out[0][inputs["input_ids"].shape[1] :]
        return tok.decode(new, skip_special_tokens=True), int(new.shape[0])

    def unload():
        nonlocal model
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        elif device == "mps":
            torch.mps.empty_cache()

    generate.unload = unload
    return generate

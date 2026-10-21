from clearvoice import ClearVoice
import torch
import numpy as np
from scipy.io.wavfile import write
import soundfile as sf
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from openai_whisper import record_from_mic

device = "mps" if torch.backends.mps.is_available() else "cpu"
torch_dtype = torch.float32
model_id = "distil-whisper/distil-small.en"

myClearVoice = ClearVoice(task="speech_enhancement", model_names=["MossFormer2_SE_48K"])
print("ClearVoice loaded")

model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
).to(device)
processor = AutoProcessor.from_pretrained(model_id)
pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    max_new_tokens=128,
    torch_dtype=torch_dtype,
    device=device,
)
print("STT pipeline ready")


"""
UNCOMMENT THIS CODE IF YOU WANT TO USE MIC
source = record_from_mic(3)
if np.issubdtype(source.dtype, np.floating):
    source = (np.clip(source, -1, 1) * 32767).astype(np.int16)
write("instructions.wav", 16000, source)
"""


# change to instructions.wav for microphone
enhanced = myClearVoice(input_path="noise.MP3", online_write=False)
myClearVoice.write(enhanced, output_path="clear.wav")

audio, sr = sf.read("noise.MP3", dtype="float32")  # float in [-1, 1]
if audio.ndim > 1:
    audio = audio.mean(axis=1)  # stereo -> mono

result = pipe({"raw": audio, "sampling_rate": sr})
print(result["text"])

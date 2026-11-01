import base64
import mimetypes
import re
from pathlib import Path


def audio_request(provider: str, model: str | None, name: str, audio: bytes) -> dict:
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if Path(name).suffix.lower() == ".wav":
        content_type = "audio/wav"
    if provider != "qwen":
        return {"data": {"model": model}, "files": {"file": (name, audio, content_type)}}
    if not re.fullmatch(r"(?:qwen3-asr-flash|qwen-audio-3\.[01]-asr-flash)(?:-\d{4}-\d{2}-\d{2})?", model or ""):
        raise ValueError("Qwen Audio supports synchronous qwen3-asr-flash and qwen-audio-3.0/3.1-asr-flash models, not realtime, filetrans or speech synthesis models")
    if not audio or len(audio) > 10_000_000:
        raise ValueError("Qwen audio file must be between 1 byte and 10 MB")
    if not content_type.startswith(("audio/", "video/")):
        raise ValueError("Qwen requires a supported audio file extension, such as .wav or .mp3")
    data_uri = f"data:{content_type};base64,{base64.b64encode(audio).decode('ascii')}"
    content = {"audio": data_uri}
    parameters = {"asr_options": {"enable_itn": False}}
    if (model or "").startswith(("qwen-audio-3.0-asr-flash", "qwen-audio-3.1-asr-flash")):
        content = {"type": "input_audio", "input_audio": {"data": data_uri}}
        parameters = {}
    return {"json": {"model": model, "input": {"messages": [{"role": "user", "content": [content]}]}, "parameters": parameters}}

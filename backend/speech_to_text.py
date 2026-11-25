"""
backend/speech_to_text.py - Reliable Speech Recognition using Faster-Whisper
Decodes WAV (PCM 8/16/24/32-bit, mono/stereo, any sample rate) via stdlib wave,
decodes MP3/M4A/OGG/WebM/float-WAV via PyAV (without the broken metadata_errors kwarg)
or FFmpeg CLI fallback, converts to mono 16 kHz float32 PCM, and passes the numpy array
directly to Faster-Whisper.
"""
import importlib.util
import io
import logging
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

import config

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
_whisper_models: Dict[str, Any] = {}


def _get_whisper_model(model_size: Optional[str] = None) -> Tuple[Optional[Any], str, str]:
    """
    Lazy-load and cache Faster-Whisper model on CPU by model_size.
    Tries local cache first to avoid unnecessary HuggingFace Hub network calls.
    Returns (model, error_code, error_message).
    """
    if not is_whisper_available():
        return (
            None,
            "missing_dependency",
            "Speech recognition library (faster-whisper) is not installed. Please use text input.",
        )

    target_model = (model_size or config.WHISPER_MODEL or "base").strip()
    if target_model in _whisper_models:
        return _whisper_models[target_model], "", ""

    download_root = str(Path.home() / ".cache" / "whisper")
    try:
        from faster_whisper import WhisperModel

        logger.info(f"Loading Whisper model '{target_model}' (local cache check)...")
        try:
            model = WhisperModel(
                target_model,
                device="cpu",
                compute_type="int8",
                download_root=download_root,
                local_files_only=True,
            )
        except Exception:
            logger.info(f"Whisper model '{target_model}' not in local cache; downloading...")
            model = WhisperModel(
                target_model,
                device="cpu",
                compute_type="int8",
                download_root=download_root,
                local_files_only=False,
            )

        _whisper_models[target_model] = model
        logger.info(f"Whisper model '{target_model}' loaded successfully.")
        return model, "", ""

    except Exception as e:
        err_str = str(e)
        logger.error(f"Failed to load Whisper model '{target_model}': {type(e).__name__}: {err_str}")
        lower = err_str.lower()
        if any(k in lower for k in ("connecterror", "getaddrinfo", "network", "timeout", "localentrynotfound")):
            return (
                None,
                "network_download_failed",
                f"Speech model '{target_model}' could not be downloaded (check internet connection) or switch to text input.",
            )
        return (
            None,
            "model_load_failed",
            f"Could not initialize speech recognition model '{target_model}'. Please retry or use text input.",
        )


def _resample_to_16k(samples: np.ndarray, orig_rate: int) -> np.ndarray:
    """Resample 1D float32 audio array to 16,000 Hz cleanly."""
    if orig_rate == TARGET_SAMPLE_RATE or len(samples) == 0:
        return samples.astype(np.float32, copy=False)

    try:
        from math import gcd
        from scipy.signal import resample_poly

        divisor = gcd(TARGET_SAMPLE_RATE, int(orig_rate))
        up = TARGET_SAMPLE_RATE // divisor
        down = int(orig_rate) // divisor
        resampled = resample_poly(samples, up, down)
        return np.clip(resampled, -1.0, 1.0).astype(np.float32)
    except Exception:
        duration = len(samples) / float(orig_rate)
        target_len = max(1, int(round(duration * TARGET_SAMPLE_RATE)))
        old_idx = np.linspace(0.0, len(samples) - 1, num=len(samples))
        new_idx = np.linspace(0.0, len(samples) - 1, num=target_len)
        return np.interp(new_idx, old_idx, samples).astype(np.float32)


def _decode_pcm_wav(audio_bytes: bytes) -> Tuple[np.ndarray, int, int, str]:
    """
    Decode standard PCM WAV bytes using Python stdlib `wave`.
    Returns (mono_16k_float32, orig_rate, orig_channels, format_label).
    """
    with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        comptype = wf.getcomptype()

        if comptype != "NONE":
            raise wave.Error(f"Unsupported compressed WAV type: {comptype}")
        if framerate <= 0 or channels <= 0:
            raise wave.Error("Invalid WAV header metadata.")

        raw = wf.readframes(nframes)

    if not raw:
        return np.zeros(0, dtype=np.float32), framerate, channels, "WAV"

    if sampwidth == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sampwidth == 3:
        raw_u8 = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        padded = np.zeros((raw_u8.shape[0], 4), dtype=np.uint8)
        padded[:, :3] = raw_u8
        # Sign-extend 24-bit little-endian into 32-bit signed integer
        padded[:, 3] = np.where((raw_u8[:, 2] & 0x80) != 0, 0xFF, 0x00)
        arr = padded.view("<i4").reshape(-1).astype(np.float32) / 8388608.0
    elif sampwidth == 4:
        arr = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise wave.Error(f"Unsupported WAV sample width: {sampwidth} bytes")

    if channels > 1:
        usable = (len(arr) // channels) * channels
        arr = arr[:usable].reshape(-1, channels).mean(axis=1)

    mono_16k = _resample_to_16k(arr, framerate)
    return mono_16k, framerate, channels, f"WAV ({sampwidth * 8}-bit)"


def _decode_with_pyav(audio_bytes: bytes) -> Tuple[np.ndarray, int, int, str]:
    """
    Decode WAV/MP3/M4A/OGG/WebM/FLAC using PyAV WITHOUT `metadata_errors` kwarg
    (compatible with PyAV 16-19+).
    """
    import av

    resampler = av.audio.resampler.AudioResampler(
        format="s16",
        layout="mono",
        rate=TARGET_SAMPLE_RATE,
    )
    chunks = []
    orig_rate = TARGET_SAMPLE_RATE
    orig_channels = 1
    codec_name = "Audio"

    with av.open(io.BytesIO(audio_bytes), mode="r") as container:
        if not container.streams.audio:
            raise ValueError("File contains no audio stream.")
        stream = container.streams.audio[0]
        orig_rate = int(stream.rate or TARGET_SAMPLE_RATE)
        orig_channels = int(stream.channels or 1)
        codec_name = (container.format.name or "Audio").split(",")[0].upper()

        for frame in container.decode(audio=0):
            for rframe in resampler.resample(frame):
                chunks.append(rframe.to_ndarray().reshape(-1))
        for rframe in resampler.resample(None):
            chunks.append(rframe.to_ndarray().reshape(-1))

    if not chunks:
        return np.zeros(0, dtype=np.float32), orig_rate, orig_channels, codec_name

    pcm_s16 = np.concatenate(chunks)
    audio_f32 = np.clip(pcm_s16.astype(np.float32) / 32768.0, -1.0, 1.0)
    return audio_f32, orig_rate, orig_channels, codec_name


def _decode_with_ffmpeg(audio_bytes: bytes, ext_hint: str = ".audio") -> Tuple[np.ndarray, int, int, str]:
    """Fallback conversion using external FFmpeg binary if installed."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise FileNotFoundError("FFmpeg binary not found on PATH.")

    in_path = None
    out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext_hint, delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            in_path = tmp_in.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_out:
            out_path = tmp_out.name

        proc = subprocess.run(
            [
                ffmpeg_bin, "-y", "-i", in_path,
                "-ac", "1", "-ar", str(TARGET_SAMPLE_RATE),
                "-sample_fmt", "s16", out_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore")[:300])
        wav_bytes = Path(out_path).read_bytes()
        return _decode_pcm_wav(wav_bytes)
    finally:
        for p in (in_path, out_path):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass


def decode_audio_to_pcm16k(
    audio_bytes: bytes,
    filename: Optional[str] = None,
) -> Tuple[Optional[np.ndarray], Dict[str, Any], str, str]:
    """
    Decode raw audio bytes into a 1D float32 mono 16 kHz numpy array.
    Returns (audio_array, metadata_dict, error_code, error_message).
    """
    if not audio_bytes or len(audio_bytes) < 64:
        return (
            None,
            {"duration": 0.0},
            "empty_audio",
            "The recording is empty. Please click the microphone, speak clearly, and stop recording.",
        )

    ext_hint = Path(filename).suffix.lower() if filename else ".audio"
    is_wav = audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE"

    # Fast stdlib path for standard PCM WAV recordings (including browser st.audio_input)
    if is_wav:
        try:
            audio, rate, channels, fmt = _decode_pcm_wav(audio_bytes)
            duration = len(audio) / float(TARGET_SAMPLE_RATE)
            return audio, {"duration": duration, "sample_rate": rate, "channels": channels, "format": fmt}, "", ""
        except Exception as wav_err:
            logger.debug(f"Stdlib wave decoder fallback to PyAV: {wav_err}")

    # PyAV path (MP3, M4A, OGG, WebM, IEEE-float WAV, etc.)
    if importlib.util.find_spec("av") is not None:
        try:
            audio, rate, channels, fmt = _decode_with_pyav(audio_bytes)
            duration = len(audio) / float(TARGET_SAMPLE_RATE)
            return audio, {"duration": duration, "sample_rate": rate, "channels": channels, "format": fmt}, "", ""
        except Exception as av_err:
            logger.warning(f"PyAV decode failed ({type(av_err).__name__}): {av_err}")

    # FFmpeg CLI fallback
    if shutil.which("ffmpeg"):
        try:
            audio, rate, channels, fmt = _decode_with_ffmpeg(audio_bytes, ext_hint=ext_hint)
            duration = len(audio) / float(TARGET_SAMPLE_RATE)
            return audio, {"duration": duration, "sample_rate": rate, "channels": channels, "format": fmt}, "", ""
        except Exception as ff_err:
            logger.error(f"FFmpeg decode failed: {ff_err}")
            return (
                None,
                {"duration": 0.0},
                "conversion_failed",
                "Could not read or convert this audio file. Please try recording again or upload a valid WAV/MP3 file.",
            )

    ffmpeg_hint = (
        " If uploading MP3/M4A files, ensure PyAV or FFmpeg (`winget install Gyan.FFmpeg`) is installed, "
        "or upload a standard WAV file."
    )
    return (
        None,
        {"duration": 0.0},
        "invalid_format",
        "Unsupported or corrupted audio format." + ffmpeg_hint,
    )


def get_audio_info(audio_bytes: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
    """Inspect audio bytes for duration, sample rate, channels, and silence status."""
    audio, meta, err_code, err_msg = decode_audio_to_pcm16k(audio_bytes, filename=filename)
    if audio is None:
        return {
            "valid": False,
            "duration": 0.0,
            "sample_rate": 0,
            "channels": 0,
            "format": "Unknown",
            "is_silent": True,
            "error_code": err_code,
            "error_message": err_msg,
        }

    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    is_silent = len(audio) == 0 or (rms < 1e-4 and peak < 1e-3)
    return {
        "valid": True,
        "duration": round(float(meta.get("duration", 0.0)), 2),
        "sample_rate": int(meta.get("sample_rate", TARGET_SAMPLE_RATE)),
        "channels": int(meta.get("channels", 1)),
        "format": meta.get("format", "Audio"),
        "rms": rms,
        "is_silent": is_silent,
        "error_code": "",
        "error_message": "",
    }


def transcribe_audio_detailed(
    audio_bytes: bytes,
    language: Optional[str] = None,
    model_size: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Decode, validate, and transcribe audio bytes with Faster-Whisper.
    Returns structured dict with `success`, `text`, `language`, `confidence`,
    `duration`, `error_code`, and user-friendly `error_message`.
    """
    audio, meta, err_code, err_msg = decode_audio_to_pcm16k(audio_bytes, filename=filename)
    if audio is None:
        return {
            "success": False,
            "text": "",
            "language": config.DEFAULT_LANGUAGE,
            "confidence": 0.0,
            "duration": 0.0,
            "error_code": err_code,
            "error_message": err_msg,
        }

    duration = float(meta.get("duration", 0.0))
    if duration < 0.25:
        return {
            "success": False,
            "text": "",
            "language": config.DEFAULT_LANGUAGE,
            "confidence": 0.0,
            "duration": round(duration, 2),
            "error_code": "empty_audio",
            "error_message": "Recording was too short (under 0.3s). Please hold your speech a bit longer and retry.",
        }

    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    if rms < 1e-4 and peak < 1e-3:
        return {
            "success": False,
            "text": "",
            "language": config.DEFAULT_LANGUAGE,
            "confidence": 0.0,
            "duration": round(duration, 2),
            "error_code": "silent_audio",
            "error_message": "No sound detected in the recording. Please check your microphone permissions and input device.",
        }

    model, model_err_code, model_err_msg = _get_whisper_model(model_size)
    if model is None:
        return {
            "success": False,
            "text": "",
            "language": config.DEFAULT_LANGUAGE,
            "confidence": 0.0,
            "duration": round(duration, 2),
            "error_code": model_err_code,
            "error_message": model_err_msg,
        }

    lang_param = language if language in ("en", "hi") else None
    domain_prompt = (
        "DreamHome Realty, Phagwara, Jalandhar, Ludhiana, Nawanshahr, Adampur, "
        "1 BHK, 2 BHK, 3 BHK, 4 BHK, apartment, villa, independent house, lakh, crore."
        if lang_param != "hi"
        else "ड्रीमहोम रियल्टी, फगवाड़ा, जालंधर, लुधियाना, नवांशहर, 2 बीएचके, फ्लैट, लाख, करोड़।"
    )
    try:
        segments, info = model.transcribe(
            audio,
            language=lang_param,
            task="transcribe",
            beam_size=5,
            best_of=5,
            initial_prompt=domain_prompt,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()

        # If VAD trimmed a quiet or short real utterance, retry once without VAD
        if not text and rms >= 0.002:
            logger.debug("VAD produced empty transcript on audible audio; retrying with vad_filter=False.")
            segments, info = model.transcribe(
                audio,
                language=lang_param,
                task="transcribe",
                beam_size=5,
                best_of=5,
                initial_prompt=domain_prompt,
                vad_filter=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()

        detected_lang = (
            lang_param
            or (info.language if info and info.language in ("en", "hi") else "en")
        )
        confidence = float(info.language_probability) if info else 0.0

        if not text:
            return {
                "success": False,
                "text": "",
                "language": detected_lang,
                "confidence": confidence,
                "duration": round(duration, 2),
                "error_code": "no_speech_detected",
                "error_message": "Could not hear clear speech in the recording. Try speaking closer to the mic or use text input.",
            }

        return {
            "success": True,
            "text": text,
            "language": detected_lang,
            "confidence": confidence,
            "duration": round(duration, 2),
            "error_code": "",
            "error_message": "",
        }

    except Exception as e:
        logger.error(f"Whisper transcription error: {type(e).__name__}: {e}", exc_info=True)
        return {
            "success": False,
            "text": "",
            "language": lang_param or "en",
            "confidence": 0.0,
            "duration": round(duration, 2),
            "error_code": "transcription_failed",
            "error_message": "We could not transcribe that recording. Please try recording again or type your message below.",
        }


def transcribe_audio_bytes(
    audio_bytes: bytes,
    language: str = None,
    model_size: str = None,
    filename: str = None,
) -> Tuple[str, str, float, str]:
    """
    Backward-compatible wrapper returning:
        (transcribed_text, detected_language, confidence, error_message)
    """
    res = transcribe_audio_detailed(
        audio_bytes,
        language=language,
        model_size=model_size,
        filename=filename,
    )
    return res["text"], res["language"], res["confidence"], res["error_message"]


def is_whisper_available() -> bool:
    """Check if Faster-Whisper is installed without loading weights."""
    return importlib.util.find_spec("faster_whisper") is not None


def is_ffmpeg_available() -> bool:
    """Check whether external FFmpeg binary is available on PATH."""
    return shutil.which("ffmpeg") is not None


def get_stt_status() -> dict:
    """Get speech-to-text system status."""
    return {
        "whisper_available": is_whisper_available(),
        "pyav_available": importlib.util.find_spec("av") is not None,
        "ffmpeg_available": is_ffmpeg_available(),
        "model_size": config.WHISPER_MODEL,
        "device": "cpu",
        "languages_supported": ["en", "hi", "auto-detect"],
    }

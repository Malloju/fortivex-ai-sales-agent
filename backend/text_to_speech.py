"""
backend/text_to_speech.py - Text-to-speech using Edge TTS with local Windows SAPI fallback
Converts AI responses to spoken audio (MP3 via Edge TTS, WAV via Windows SAPI when offline),
with clean markdown stripping, generous timeout + retry, and zero UI blocking.
"""
import asyncio
import concurrent.futures
import importlib.util
import logging
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import config

logger = logging.getLogger(__name__)

EDGE_TTS_TIMEOUT_SECONDS = 22.0


def _get_voice(language: str = "en", voice_override: str = None) -> str:
    """Select appropriate Edge TTS voice for language."""
    if voice_override:
        return voice_override
    if language in ("hi", "hindi"):
        return config.TTS_VOICE_HI
    return config.TTS_VOICE_EN


def _clean_text_for_speech(text: str) -> str:
    """Strip markdown formatting, URLs, property IDs, and symbols for natural speech."""
    cleaned = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    cleaned = re.sub(r"\(P\d{3}\)", "", cleaned)
    cleaned = re.sub(r"[#*`_~>]", "", cleaned)
    cleaned = re.sub(r"[🏠📅📞👥⭐📈🔵🟢🟡🔴⚠️💡🎙️✅❌•📊🔍⚙️🗣️💬📋]", "", cleaned)
    cleaned = cleaned.replace("₹", "Rupees ")
    cleaned = cleaned.replace(" | ", ", ").replace("|", ", ").replace(" — ", ", ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def cleanup_old_temp_audio(max_age_seconds: int = 3600) -> int:
    """Remove stale temporary audio files older than max_age_seconds."""
    if not config.AUDIO_DIR.exists():
        return 0
    removed = 0
    cutoff = time.time() - max_age_seconds
    for pattern in ("*.mp3", "*.wav"):
        for f in config.AUDIO_DIR.glob(pattern):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                pass
    return removed


def _can_reach_tts_host(timeout_seconds: float = 2.0) -> bool:
    """Fast non-blocking check in a daemon thread so offline runs fail cleanly."""
    reachable = [False]

    def _probe():
        try:
            with socket.create_connection(("speech.platform.bing.com", 443), timeout=timeout_seconds):
                reachable[0] = True
        except Exception:
            reachable[0] = False

    t = threading.Thread(target=_probe, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)
    return reachable[0]


async def _synthesize_async(text: str, voice: str) -> Optional[bytes]:
    """Async Edge TTS synthesis with 22s timeout."""
    try:
        import edge_tts

        async def _stream() -> bytes:
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data

        audio_data = await asyncio.wait_for(_stream(), timeout=EDGE_TTS_TIMEOUT_SECONDS)
        return audio_data if audio_data else None
    except ImportError:
        logger.error("edge-tts not installed.")
        return None
    except asyncio.TimeoutError:
        logger.warning(f"Edge TTS timed out after {EDGE_TTS_TIMEOUT_SECONDS:.0f}s.")
        return None
    except Exception as e:
        logger.error(f"Edge TTS synthesis error: {type(e).__name__}: {e}")
        return None


def _synthesize_edge_tts(spoken_text: str, voice: str) -> Optional[bytes]:
    """Run Edge TTS synchronously (safe inside Streamlit's active event loop) with 1 retry."""
    for attempt in range(2):
        try:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, _synthesize_async(spoken_text, voice))
                        audio = future.result(timeout=EDGE_TTS_TIMEOUT_SECONDS + 3.0)
                else:
                    audio = loop.run_until_complete(_synthesize_async(spoken_text, voice))
            except RuntimeError:
                audio = asyncio.run(_synthesize_async(spoken_text, voice))

            if audio and len(audio) >= 128:
                return audio
        except Exception as e:
            logger.warning(f"Edge TTS attempt {attempt + 1} failed: {type(e).__name__}: {e}")
    return None


def _synthesize_windows_sapi(spoken_text: str) -> Optional[bytes]:
    """
    Offline local Windows SAPI fallback using System.Speech.Synthesis.
    Produces valid PCM WAV bytes without network access.
    """
    if sys.platform != "win32":
        return None

    tmp_wav = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = Path(tmp.name)

        safe_text = spoken_text.replace("'", "''")
        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{str(tmp_wav)}'); "
            f"$s.Speak('{safe_text}'); "
            "$s.Dispose()"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=15,
        )
        if proc.returncode == 0 and tmp_wav.exists():
            wav_bytes = tmp_wav.read_bytes()
            if len(wav_bytes) > 128:
                return wav_bytes
    except Exception as e:
        logger.warning(f"Windows SAPI fallback failed: {type(e).__name__}: {e}")
    finally:
        if tmp_wav:
            try:
                tmp_wav.unlink(missing_ok=True)
            except Exception:
                pass
    return None


def synthesize_speech_full(
    text: str,
    language: str = "en",
    voice_override: str = None,
) -> Dict[str, Any]:
    """
    Generate spoken audio for text.
    Tries Edge TTS first (MP3), then falls back to local Windows SAPI (WAV) if Edge TTS is offline/unavailable.
    Returns structured dict:
        {success, audio_bytes, mime_type, provider, voice, error_message}
    """
    if not text or not text.strip():
        return {
            "success": False,
            "audio_bytes": None,
            "mime_type": "audio/mpeg",
            "provider": "none",
            "voice": "",
            "error_message": "",
        }

    spoken_text = _clean_text_for_speech(text)
    if len(spoken_text) > 950:
        spoken_text = spoken_text[:950].rsplit(".", 1)[0] + ". Check the chat for full details."

    voice = _get_voice(language, voice_override)
    cleanup_old_temp_audio()

    # Primary: Edge TTS
    if is_tts_available() and _can_reach_tts_host():
        audio = _synthesize_edge_tts(spoken_text, voice)
        if audio:
            return {
                "success": True,
                "audio_bytes": audio,
                "mime_type": "audio/mpeg",
                "provider": "edge-tts",
                "voice": voice,
                "error_message": "",
            }

    # Local fallback (English / ASCII-safe offline synthesis via Windows SAPI)
    if language != "hi":
        sapi_audio = _synthesize_windows_sapi(spoken_text)
        if sapi_audio:
            logger.info("Synthesized speech via local Windows SAPI fallback.")
            return {
                "success": True,
                "audio_bytes": sapi_audio,
                "mime_type": "audio/wav",
                "provider": "windows-sapi",
                "voice": "Microsoft SAPI",
                "error_message": "",
            }

    return {
        "success": False,
        "audio_bytes": None,
        "mime_type": "audio/mpeg",
        "provider": "none",
        "voice": voice,
        "error_message": "Could not synthesize voice audio (Edge TTS unavailable or timed out). Click Retry Voice to try again.",
    }


def synthesize_speech_with_status(
    text: str,
    language: str = "en",
    voice_override: str = None,
) -> Tuple[Optional[bytes], str]:
    """Backward-compatible wrapper returning (audio_bytes, error_message)."""
    res = synthesize_speech_full(text, language=language, voice_override=voice_override)
    return res["audio_bytes"], res["error_message"]


def synthesize_speech(
    text: str,
    language: str = "en",
    voice_override: str = None,
) -> Optional[bytes]:
    """Convert text to speech audio bytes or None on failure."""
    res = synthesize_speech_full(text, language=language, voice_override=voice_override)
    return res["audio_bytes"]


def save_audio_file(audio_bytes: bytes, filename: str = None) -> Optional[str]:
    """Save audio bytes to a temporary file and return the path."""
    if not audio_bytes:
        return None
    try:
        config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        if filename:
            path = config.AUDIO_DIR / filename
        else:
            with tempfile.NamedTemporaryFile(
                suffix=".mp3", dir=config.AUDIO_DIR, delete=False
            ) as tmp:
                path = Path(tmp.name)

        path.write_bytes(audio_bytes)
        return str(path)
    except Exception as e:
        logger.error(f"Error saving audio: {e}")
        return None


def is_tts_available() -> bool:
    """Check if Edge TTS is available."""
    return importlib.util.find_spec("edge_tts") is not None


def get_tts_status() -> dict:
    """Get TTS system status."""
    return {
        "edge_tts_available": is_tts_available(),
        "sapi_fallback_available": sys.platform == "win32",
        "voice_english": config.TTS_VOICE_EN,
        "voice_hindi": config.TTS_VOICE_HI,
        "default_language": config.DEFAULT_LANGUAGE,
    }

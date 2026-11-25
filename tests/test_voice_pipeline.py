"""
tests/test_voice_pipeline.py - Comprehensive tests for audio decoding,
Faster-Whisper STT error handling, TTS voice selection, and multi-turn context preservation.
"""
import io
import sys
import wave
from pathlib import Path

import av
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_wav_bytes(samples: np.ndarray, rate: int = 16000, channels: int = 1, sampwidth: int = 2) -> bytes:
    """Create PCM WAV bytes in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        if sampwidth == 1:
            data = np.clip((samples * 127.0) + 128.0, 0, 255).astype(np.uint8)
        elif sampwidth == 2:
            data = np.clip(samples * 32767.0, -32768, 32767).astype("<i2")
        else:
            data = np.clip(samples * 2147483647.0, -2147483648, 2147483647).astype("<i4")
        wf.writeframes(data.tobytes())
    return buf.getvalue()


def _make_mp3_bytes(samples: np.ndarray, rate: int = 16000) -> bytes:
    """Encode float32 mono samples into real MP3 bytes using PyAV."""
    buf = io.BytesIO()
    pcm_s16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
    with av.open(buf, mode="w", format="mp3") as container:
        stream = container.add_stream("mp3", rate=rate)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(pcm_s16.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = rate
        for pkt in stream.encode(frame):
            container.mux(pkt)
        for pkt in stream.encode(None):
            container.mux(pkt)
    return buf.getvalue()


def test_decode_stereo_48khz_wav_to_mono_16khz():
    """Verify stereo 48 kHz WAV decodes and resamples cleanly to 16 kHz mono float32."""
    from backend import speech_to_text as stt

    t = np.linspace(0, 1.5, 48000 + 24000, endpoint=False)
    left = 0.25 * np.sin(2 * np.pi * 440 * t)
    right = 0.25 * np.sin(2 * np.pi * 880 * t)
    stereo = np.column_stack([left, right]).reshape(-1)
    wav_bytes = _make_wav_bytes(stereo, rate=48000, channels=2, sampwidth=2)

    audio, meta, err_code, err_msg = stt.decode_audio_to_pcm16k(wav_bytes, filename="stereo.wav")
    assert err_code == ""
    assert err_msg == ""
    assert audio is not None
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert abs(len(audio) - 24000) <= 50
    assert meta["channels"] == 2
    assert meta["sample_rate"] == 48000


def test_decode_mp3_via_pyav_without_metadata_errors():
    """Verify MP3 decoding works via PyAV 19+ without metadata_errors bug."""
    from backend import speech_to_text as stt

    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    mp3_bytes = _make_mp3_bytes(tone, rate=16000)

    audio, meta, err_code, err_msg = stt.decode_audio_to_pcm16k(mp3_bytes, filename="clip.mp3")
    assert err_code == ""
    assert err_msg == ""
    assert audio is not None
    assert len(audio) >= 15000


def test_stt_empty_silent_and_invalid_audio():
    """Test cases 6, 7, 8: silent recording, empty recording, invalid audio file."""
    from backend import speech_to_text as stt

    # Empty bytes
    res_empty = stt.transcribe_audio_detailed(b"")
    assert res_empty["success"] is False
    assert res_empty["error_code"] == "empty_audio"

    # Too short (<0.25s)
    short_wav = _make_wav_bytes(np.ones(1600, dtype=np.float32) * 0.1, rate=16000)
    res_short = stt.transcribe_audio_detailed(short_wav)
    assert res_short["success"] is False
    assert res_short["error_code"] == "empty_audio"

    # Silent 2-second WAV
    silent_wav = _make_wav_bytes(np.zeros(32000, dtype=np.float32), rate=16000)
    res_silent = stt.transcribe_audio_detailed(silent_wav)
    assert res_silent["success"] is False
    assert res_silent["error_code"] == "silent_audio"

    # Corrupted / non-audio bytes
    res_invalid = stt.transcribe_audio_detailed(b"not-an-audio-file-at-all-random-bytes-1234567890" * 5, filename="bad.mp3")
    assert res_invalid["success"] is False
    assert res_invalid["error_code"] in ("invalid_format", "conversion_failed")


def test_stt_background_noise_no_crash():
    """Test case 9: noisy audio without real speech returns clean friendly feedback, not a crash."""
    from backend import speech_to_text as stt

    rng = np.random.default_rng(42)
    noise = (0.02 * rng.standard_normal(32000)).astype(np.float32)
    noisy_wav = _make_wav_bytes(noise, rate=16000)

    res = stt.transcribe_audio_detailed(noisy_wav, language="en", model_size="base")
    assert isinstance(res, dict)
    assert "error_code" in res
    assert res["error_code"] in ("", "no_speech_detected")


def test_context_preservation_across_turns(tmp_path, monkeypatch):
    """
    Verify Section 4 requirement:
    Customer: 'I am looking for a 2 BHK apartment in Phagwara.'
    AI asks budget -> Customer: 'Around 50 lakh.'
    AI remembers Phagwara + 2 BHK + Apartment and recommends matching properties.
    """
    import config
    from backend import database as db
    from backend import ai_agent, conversation as conv_manager

    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "ctx_test.db")
    monkeypatch.setattr(config, "IS_DEMO_MODE", True)
    ai_agent._agent_instance = None
    db.init_database()

    ctx = conv_manager.create_session()
    r1, ctx = ai_agent.process_customer_message(
        "I am looking for a 2 BHK apartment in Phagwara.", ctx
    )
    assert "budget" in r1.lower()
    assert ctx.customer_profile.preferred_location == "Phagwara"
    assert ctx.customer_profile.bedrooms == 2
    assert ctx.customer_profile.property_type == "Apartment"

    r2, ctx = ai_agent.process_customer_message("Around 50 lakh.", ctx)
    assert ctx.customer_profile.budget_max == 5_000_000
    assert "Sunrise Apartments" in r2 or "Phagwara" in r2
    assert "50" in r2

    # Turn 3: Topic question after criteria must answer the topic, not repeat properties
    r3, ctx = ai_agent.process_customer_message("What home loan options do you support?", ctx)
    assert "loan" in r3.lower() or "bank" in r3.lower()


def test_windows_sapi_offline_tts_produces_valid_wav():
    """Verify local Windows SAPI fallback produces valid RIFF WAVE speech offline."""
    import sys
    from backend import text_to_speech as tts

    if sys.platform != "win32":
        pytest.skip("Windows-only SAPI test")

    wav_bytes = tts._synthesize_windows_sapi("Here are some properties in Phagwara.")
    assert wav_bytes is not None
    assert len(wav_bytes) > 2000
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"


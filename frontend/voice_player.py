"""
frontend/voice_player.py - Slim conversational audio playback component
Handles single-play-per-turn automatic voice playback inside chat bubbles,
live "Speaking..." status, Stop/Replay controls, and explicit browser autoplay-blocked fallback.
"""
import base64
import html
import json
import streamlit.components.v1 as components


def render_voice_player(
    audio_bytes: bytes,
    mime_type: str,
    turn_id: str,
    auto_play: bool = True,
    provider: str = "edge-tts",
) -> None:
    """Render a minimal inline audio bar inside an AI assistant message bubble."""
    if not audio_bytes:
        return

    b64_audio = base64.b64encode(audio_bytes).decode("ascii")
    safe_mime = html.escape(mime_type or "audio/mpeg")
    safe_provider = html.escape(provider or "edge-tts")
    turn_js = json.dumps(turn_id)
    auto_js = "true" if auto_play else "false"

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * {{ box-sizing: border-box; font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
        body {{ margin: 0; padding: 0; background: transparent; }}
        .dh-voice-bar {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 7px 10px;
        }}
        .dh-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .dh-left {{
            display: flex;
            align-items: center;
            gap: 7px;
        }}
        .dh-pill {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 2px 9px;
            border-radius: 9999px;
            font-size: 11.5px;
            font-weight: 600;
            background: #EEF2FF;
            color: #4338CA;
        }}
        .dh-pill.speaking {{ background: #DBEAFE; color: #1D4ED8; }}
        .dh-pill.done {{ background: #DCFCE7; color: #15803D; }}
        .dh-pill.blocked {{ background: #FEF3C7; color: #B45309; }}
        .dh-btn {{
            border: 1px solid #CBD5E1;
            background: #FFFFFF;
            color: #0F172A;
            border-radius: 6px;
            padding: 3px 9px;
            font-size: 11.5px;
            font-weight: 600;
            cursor: pointer;
        }}
        .dh-btn:hover {{ background: #F1F5F9; }}
        .dh-btn-primary {{
            background: #4F46E5;
            border-color: #4F46E5;
            color: #FFFFFF;
        }}
        .dh-btn-primary:hover {{ background: #4338CA; }}
        .dh-notice {{
            display: none;
            font-size: 11.5px;
            color: #92400E;
            background: #FFFBEB;
            border: 1px solid #FDE68A;
            border-radius: 6px;
            padding: 5px 8px;
        }}
        .dh-meta {{ font-size: 11px; color: #64748B; }}
        audio {{ width: 100%; height: 28px; }}
    </style>
    </head>
    <body>
    <div class="dh-voice-bar">
        <div class="dh-row">
            <div class="dh-left">
                <span id="statusBadge" class="dh-pill">🔊 Voice ready</span>
                <span id="timeText" class="dh-meta">0:00</span>
                <span class="dh-meta">· {safe_provider}</span>
            </div>
            <div style="display:flex; gap:5px;">
                <button id="playBtn" class="dh-btn dh-btn-primary" type="button">▶ Play</button>
                <button id="stopBtn" class="dh-btn" type="button">⏹ Stop</button>
            </div>
        </div>
        <div id="autoplayNotice" class="dh-notice">
            Browser blocked autoplay. Click <strong>▶ Play</strong> above (or enable audio autoplay for this site).
        </div>
        <audio id="audioEl" controls preload="auto" src="data:{safe_mime};base64,{b64_audio}"></audio>
    </div>

    <script>
    (function() {{
        const turnId = {turn_js};
        const shouldAuto = {auto_js};
        const audio = document.getElementById("audioEl");
        const statusBadge = document.getElementById("statusBadge");
        const timeText = document.getElementById("timeText");
        const playBtn = document.getElementById("playBtn");
        const stopBtn = document.getElementById("stopBtn");
        const notice = document.getElementById("autoplayNotice");
        const storageKey = "dh_played_" + turnId;

        function fmt(sec) {{
            if (!isFinite(sec) || sec < 0) return "0:00";
            const m = Math.floor(sec / 60);
            const s = Math.floor(sec % 60);
            return m + ":" + (s < 10 ? "0" : "") + s;
        }}

        function setStatus(cls, text) {{
            statusBadge.className = "dh-pill " + cls;
            statusBadge.textContent = text;
        }}

        audio.addEventListener("loadedmetadata", function() {{
            timeText.textContent = "0:00 / " + fmt(audio.duration);
        }});
        audio.addEventListener("timeupdate", function() {{
            timeText.textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration);
        }});
        audio.addEventListener("playing", function() {{
            notice.style.display = "none";
            setStatus("speaking", "🔊 Speaking...");
        }});
        audio.addEventListener("pause", function() {{
            if (!audio.ended && audio.currentTime > 0) {{
                setStatus("", "⏸ Paused");
            }}
        }});
        audio.addEventListener("ended", function() {{
            setStatus("done", "✓ Spoken");
        }});

        function startPlay(isUserGesture) {{
            if (isUserGesture) {{
                audio.currentTime = 0;
            }}
            const promise = audio.play();
            if (promise !== undefined) {{
                promise.then(function() {{
                    notice.style.display = "none";
                    setStatus("speaking", "🔊 Speaking...");
                }}).catch(function() {{
                    setStatus("blocked", "🔇 Click Play");
                    notice.style.display = "block";
                }});
            }}
        }}

        playBtn.addEventListener("click", function() {{ startPlay(true); }});
        stopBtn.addEventListener("click", function() {{
            audio.pause();
            audio.currentTime = 0;
            setStatus("", "⏹ Stopped");
        }});

        let alreadyPlayed = false;
        try {{ alreadyPlayed = sessionStorage.getItem(storageKey) === "1"; }} catch (e) {{}}

        if (shouldAuto && !alreadyPlayed) {{
            try {{ sessionStorage.setItem(storageKey, "1"); }} catch (e) {{}}
            startPlay(false);
        }} else if (alreadyPlayed) {{
            setStatus("done", "✓ Spoken");
        }}
    }})();
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=118)

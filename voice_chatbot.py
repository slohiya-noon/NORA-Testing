import streamlit as st
import time
import os
import tempfile
import pandas as pd

# ── Page config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Voice Chatbot",
    page_icon="🎤",
    layout="wide"
)

# ── Custom CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
    .chat-user {
        background: #313244;
        border-radius: 12px;
        padding: 12px 16px;
        margin: 8px 0;
    }
    .chat-assistant {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 12px 16px;
        margin: 8px 0;
        border-left: 3px solid #89b4fa;
    }
    .chat-label { font-size: 11px; color: #6c7086; margin-bottom: 4px; }
    .chat-text  { color: #cdd6f4; font-size: 15px; }
    .latency-bar {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 6px 0;
        font-size: 13px;
    }
    .status-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .pill-green  { background: #a6e3a1; color: #1e1e2e; }
    .pill-yellow { background: #f9e2af; color: #1e1e2e; }
    .pill-red    { background: #f38ba8; color: #1e1e2e; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────
if "conversation"    not in st.session_state: st.session_state.conversation    = []
if "latency_history" not in st.session_state: st.session_state.latency_history = []
if "transcript"      not in st.session_state: st.session_state.transcript      = ""
if "last_audio_id"   not in st.session_state: st.session_state.last_audio_id   = None
if "tts_audio"       not in st.session_state: st.session_state.tts_audio       = None
if "stt_time"        not in st.session_state: st.session_state.stt_time        = 0.0
if "input_counter" not in st.session_state: st.session_state.input_counter = 0

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuration")

    with st.expander("🔑 API Keys", expanded=True):
        openai_key     = st.text_input("OpenAI API Key",     type="password", placeholder="sk-...")
        azure_key      = st.text_input("Azure Speech Key",   type="password")
        azure_region   = st.text_input("Azure Region",       value="westeurope")
        google_key     = st.text_input("Google TTS API Key", type="password")
        elevenlabs_key = st.text_input("ElevenLabs API Key", type="password")

    st.divider()

    st.subheader("🌐 Language")
    language = st.selectbox("Language", ["English", "Arabic"])

    st.divider()

    st.subheader("🎙️ Speech-to-Text")
    stt_model = st.selectbox("STT Model", [
        "On-Device (Browser)",
        "OpenAI Whisper (API)",
        "Manual Input",
    ])
    if stt_model == "On-Device (Browser)":
        st.caption("🟢 Free · Runs in browser · No audio sent to server · Chrome required")
    elif stt_model == "OpenAI Whisper (API)":
        st.caption("🔵 Best accuracy · $0.006/min · Supports Arabic + English")

    st.divider()

    st.subheader("🔊 Text-to-Speech")
    tts_model = st.selectbox("TTS Model", [
        "OpenAI TTS-1",
        "OpenAI TTS-1-HD",
        "Azure Neural",
        "Google Neural2",
        "ElevenLabs",
    ])

    tts_style = tts_rate = tts_pitch = tts_styledegree = tts_stability = tts_similarity = None

    if tts_model in ["OpenAI TTS-1", "OpenAI TTS-1-HD"]:
        tts_voice = st.selectbox("Voice", ["nova", "alloy", "echo", "fable", "onyx", "shimmer"])
        if language == "Arabic":
            st.caption("⚠️ OpenAI TTS has limited Arabic support")

    elif tts_model == "Azure Neural":
        if language == "Arabic":
            tts_voice = st.selectbox("Voice", [
                "ar-SA-ZariyahNeural", "ar-EG-SalmaNeural",
                "ar-AE-FatimaNeural",  "ar-JO-SanaNeural",
                "ar-LB-LaylaNeural",   "ar-KW-NouraNeural",
            ])
        else:
            tts_voice = st.selectbox("Voice", [
                "en-US-JennyNeural", "en-US-AriaNeural",
                "en-US-SaraNeural",  "en-GB-SoniaNeural",
                "en-AU-NatashaNeural",
            ])
        tts_style       = st.selectbox("Style", ["customerservice", "cheerful", "friendly", "newscast"])
        tts_rate        = st.slider("Speaking Rate", 0.5,  1.5,  0.9,  0.05)
        tts_pitch       = st.slider("Pitch (%)",    -10,   10,   2)
        tts_styledegree = st.slider("Style Degree",  0.1,  2.0,  1.5,  0.1)

    elif tts_model == "Google Neural2":
        if language == "Arabic":
            tts_voice = st.selectbox("Voice", [
                "ar-XA-Neural2-A", "ar-XA-Neural2-B",
                "ar-XA-Neural2-C", "ar-XA-Neural2-D",
            ])
        else:
            tts_voice = st.selectbox("Voice", [
                "en-US-Neural2-F", "en-US-Neural2-H",
                "en-US-Neural2-G", "en-GB-Neural2-C",
                "en-AU-Neural2-A",
            ])
        tts_rate  = st.slider("Speaking Rate", 0.5,  1.5,  0.9, 0.05)
        tts_pitch = st.slider("Pitch",        -10.0, 10.0, 2.0, 0.5)

    elif tts_model == "ElevenLabs":
        tts_voice      = st.selectbox("Voice", [
            "Rachel", "Bella", "Antoni",
            "Farah","Sana", "Abrar Sabah"
        ])
        tts_stability  = st.slider("Stability",        0.0, 1.0, 0.5,  0.05)
        tts_similarity = st.slider("Similarity Boost", 0.0, 1.0, 0.75, 0.05)

    st.divider()

    st.subheader("🤖 Agent")
    system_prompt = st.text_area(
        "System Prompt",
        value="You are a helpful customer service assistant. Keep responses concise and friendly.",
        height=100
    )
    agent_model = st.selectbox("LLM Model", ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"])

    st.divider()
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.conversation    = []
        st.session_state.latency_history = []
        st.session_state.transcript      = ""
        st.session_state.last_audio_id   = None
        st.session_state.tts_audio       = None
        st.session_state.stt_time        = 0.0
        # Before st.rerun() in pipeline:
        st.session_state.transcript    = ""
        st.session_state.stt_time      = 0.0
        st.session_state.last_audio_id = None
        if "whisper_edit"  in st.session_state: del st.session_state["whisper_edit"]
        if "ondevice_edit" in st.session_state: del st.session_state["ondevice_edit"]
        st.rerun()

# ── TTS Functions ─────────────────────────────────────────────────
def tts_openai(text, model, voice):
    from openai import OpenAI
    client   = OpenAI(api_key=openai_key)
    response = client.audio.speech.create(
        model=model, voice=voice, input=text, response_format="wav"
    )
    return response.content

def tts_azure(text, voice, style, rate, pitch, styledegree):
    import azure.cognitiveservices.speech as speechsdk
    xml_lang = "en-US"
    for prefix, lang in [
        ("ar-EG","ar-EG"),("ar-AE","ar-AE"),("ar-JO","ar-JO"),
        ("ar-LB","ar-LB"),("ar-KW","ar-KW"),("ar-SA","ar-SA"),
        ("en-GB","en-GB"),("en-AU","en-AU"),("en-US","en-US"),
    ]:
        if voice.startswith(prefix):
            xml_lang = lang
            break

    ssml = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
        xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='{xml_lang}'>
        <voice name='{voice}'>
            <mstts:express-as style='{style}' styledegree='{styledegree}'>
                <prosody rate='{rate}' pitch='+{pitch}%'>{text}</prosody>
            </mstts:express-as>
        </voice>
    </speak>"""

    cfg = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
    )
    synth  = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
    result = synth.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise Exception(result.cancellation_details.error_details)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    speechsdk.AudioDataStream(result).save_to_wav_file(path)
    with open(path, "rb") as f:
        data = f.read()
    os.unlink(path)
    return data

def tts_google(text, voice_name, rate, pitch):
    from google.cloud import texttospeech as gtts
    client   = gtts.TextToSpeechClient(client_options={"api_key": google_key})
    response = client.synthesize_speech(
        input        = gtts.SynthesisInput(text=text),
        voice        = gtts.VoiceSelectionParams(language_code=voice_name[:5], name=voice_name),
        audio_config = gtts.AudioConfig(
            audio_encoding=gtts.AudioEncoding.LINEAR16,
            speaking_rate=rate,
            pitch=pitch
        )
    )
    return response.audio_content

def tts_elevenlabs(text, voice_name, stability, similarity):
    import requests
    st.write(f"DEBUG: key={elevenlabs_key[:8] if elevenlabs_key else 'EMPTY'}")
    voice_ids = {
        "Rachel":      "21m00Tcm4TlvDq8ikWAM",
        "Bella":       "EXAVITQu4vr4xnSDxMaL",
        "Antoni":      "ErXwobaYiN019PkySvjV",
        "Farah":       "4wf10lgibMnboGJGCLrP",
        "Sana":        "mRdG9GYEjJmIzqbYTidv",
        "Abrar Sabah": "VwC51uc4PUblWEJSPzeo",
    }
    
    voice_id = voice_ids.get(voice_name, voice_ids["Rachel"])
    
    # ← Add these debug prints
    print(f"DEBUG key: '{elevenlabs_key[:5]}...{elevenlabs_key[-4:]}'")
    print(f"DEBUG voice: {voice_name} → {voice_id}")
    print(f"DEBUG text length: {len(text)}")
    
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": elevenlabs_key,
            "Content-Type": "application/json"
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity
            }
        }
    )
    st.write(f"DEBUG status: {response.status_code}")
    st.write(f"DEBUG response: {response.text[:300]}")
    print(f"DEBUG status: {response.status_code}")
    print(f"DEBUG response: {response.text[:200]}")
    
    if response.status_code != 200:
        raise Exception(f"ElevenLabs error {response.status_code}: {response.text}")
    
    return response.content

def run_tts(text):
    if tts_model == "OpenAI TTS-1":
        return tts_openai(text, "tts-1", tts_voice)
    elif tts_model == "OpenAI TTS-1-HD":
        return tts_openai(text, "tts-1-hd", tts_voice)
    elif tts_model == "Azure Neural":
        return tts_azure(text, tts_voice, tts_style, tts_rate, tts_pitch, tts_styledegree)
    elif tts_model == "Google Neural2":
        return tts_google(text, tts_voice, tts_rate, tts_pitch)
    elif tts_model == "ElevenLabs":
        return tts_elevenlabs(text, tts_voice, tts_stability, tts_similarity)

# ── STT ───────────────────────────────────────────────────────────
def run_stt_whisper(audio_bytes):
    from openai import OpenAI
    client = OpenAI(api_key=openai_key)
    result = client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.wav", audio_bytes, "audio/wav"),
        language="ar" if language == "Arabic" else "en"
    )
    return result.text

# ── Agent ─────────────────────────────────────────────────────────
def run_agent(user_text):
    from openai import OpenAI
    client   = OpenAI(api_key=openai_key)
    messages = [{"role": "system", "content": system_prompt}]
    for turn in st.session_state.conversation:
        messages.append({"role": "user",      "content": turn["user"]})
        messages.append({"role": "assistant", "content": turn["assistant"]})
    messages.append({"role": "user", "content": user_text})
    resp = client.chat.completions.create(
        model=agent_model, messages=messages, temperature=0.7
    )
    return resp.choices[0].message.content

# ── Helpers ───────────────────────────────────────────────────────
def latency_bar(label, value, total, color):
    pct = min(int((value / total) * 100), 100) if total > 0 else 0
    return f"""
    <div class='latency-bar'>
        <span style='width:55px;color:#cdd6f4;'>{label}</span>
        <div style='flex:1;background:#313244;border-radius:4px;height:8px;'>
            <div style='width:{pct}%;background:{color};height:8px;border-radius:4px;'></div>
        </div>
        <span style='width:50px;text-align:right;color:#89b4fa;font-weight:bold;'>{value:.2f}s</span>
    </div>"""

def rtf_pill(rtf):
    if rtf < 0.2:
        return f"<span class='status-pill pill-green'>⚡ RTF {rtf:.2f} — Outstanding</span>"
    elif rtf < 0.5:
        return f"<span class='status-pill pill-yellow'>✅ RTF {rtf:.2f} — Good</span>"
    else:
        return f"<span class='status-pill pill-red'>⚠️ RTF {rtf:.2f} — Slow</span>"

# ── Main layout ───────────────────────────────────────────────────
st.title("🎤 Voice Chatbot")
st.caption(
    f"STT: **{stt_model}** &nbsp;|&nbsp; "
    f"TTS: **{tts_model}** — {tts_voice} &nbsp;|&nbsp; "
    f"LLM: **{agent_model}** &nbsp;|&nbsp; "
    f"Lang: **{language}**"
)

left_col, right_col = st.columns([3, 2])

# ── Left column ───────────────────────────────────────────────────
with left_col:

    # ── Conversation history ──────────────────────────────────────
    st.subheader("💬 Conversation")
    conv_container = st.container(height=300)
    with conv_container:
        if not st.session_state.conversation:
            st.markdown(
                "<p style='color:#6c7086;text-align:center;margin-top:60px;'>"
                "Start speaking to begin...</p>",
                unsafe_allow_html=True
            )
        for turn in st.session_state.conversation:
            st.markdown(f"""
            <div class='chat-user'>
                <div class='chat-label'>🧑 You</div>
                <div class='chat-text'>{turn['user']}</div>
            </div>
            <div class='chat-assistant'>
                <div class='chat-label'>🤖 Assistant</div>
                <div class='chat-text'>{turn['assistant']}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Persistent audio player ───────────────────────────────────
    if st.session_state.tts_audio:
        st.markdown("**🔊 Last Response:**")
        st.audio(st.session_state.tts_audio, format="audio/wav", autoplay=True)

    st.divider()

    # ── STT Section ───────────────────────────────────────────────
    st.subheader("🎙️ Input")
    user_text_input = ""
    stt_time        = 0.0

    # ── On-Device STT via streamlit-mic-recorder ──────────────────
    if stt_model == "On-Device (Browser)":
        st.caption("🟢 Free · Runs in browser · No audio sent to server · Chrome required")
        try:
            from streamlit_mic_recorder import speech_to_text

            lang_code = "ar-SA" if language == "Arabic" else "en-US"

            # speech_to_text returns transcribed text directly
            text = speech_to_text(
                language=lang_code,
                start_prompt="🎤 Click to speak",
                stop_prompt="⏹️ Stop recording",
                just_once=True,
                use_container_width=True,
                key="mic_stt"
            )

            if text:
                st.session_state.transcript = text
                st.session_state.stt_time   = 0.0  # on-device = no server latency

            if st.session_state.transcript:
                st.markdown("**📝 Transcribed — edit if needed:**")
                user_text_input = st.text_area(
                    label="t", label_visibility="collapsed",
                    value=st.session_state.transcript,
                    height=80, 
                    key="ondevice_edit",
                    # key=f"whisper_edit_{st.session_state.input_counter}"
                )

        except ImportError:
            st.error("Install: `pip3 install streamlit-mic-recorder`")
            user_text_input = st.text_area(
                label="fallback", label_visibility="collapsed",
                placeholder="streamlit-mic-recorder not installed. Type manually here...",
                height=80
            )

    # ── Whisper API STT ───────────────────────────────────────────
    elif stt_model == "OpenAI Whisper (API)":
        st.caption("🔵 Best accuracy · $0.006/min · Arabic + English")
        audio_data = st.audio_input("🎤 Click mic to record")

        if audio_data:
            audio_bytes  = audio_data.read()
            audio_hash   = hash(audio_bytes)

            if audio_hash != st.session_state.last_audio_id:
                st.session_state.last_audio_id = audio_hash
                st.session_state.input_counter += 1
                if not openai_key:
                    st.error("Enter OpenAI API Key in sidebar")
                else:
                    with st.spinner("🎙️ Transcribing..."):
                        stt_start = time.time()
                        try:
                            st.session_state.transcript = run_stt_whisper(audio_bytes)
                            st.session_state.stt_time   = time.time() - stt_start
                        except Exception as e:
                            st.error(f"STT Error: {e}")

                    # st.rerun()

        if st.session_state.transcript:
            st.markdown("**📝 Transcribed — edit if needed:**")
            st.session_state[f"whisper_edit_{st.session_state.input_counter}"] = st.session_state.transcript
            user_text_input = st.text_area(
                label="w", label_visibility="collapsed",
                value=st.session_state.transcript,
                height=80,
                key=f"whisper_edit_{st.session_state.input_counter}" 
            )

    # ── Manual Input ──────────────────────────────────────────────
    else:
        st.caption("✏️ Type your message manually")
        user_text_input = st.text_area(
            label="m", label_visibility="collapsed",
            placeholder="Type your message here...",
            height=80, key="manual_input"
        )

    # ── Send button ───────────────────────────────────────────────
    send_btn = st.button(
        "▶️ Send",
        use_container_width=True,
        type="primary",
        disabled=not (isinstance(user_text_input, str) and user_text_input.strip())
    )

    # ── Pipeline ──────────────────────────────────────────────────
    if send_btn and isinstance(user_text_input, str) and user_text_input.strip():
        if not openai_key:
            st.error("Please enter your OpenAI API Key in the sidebar")
        else:
            user_text = user_text_input.strip()
            print(f"DEBUG pipeline started: '{user_text[:30]}'")
            print(f"DEBUG tts_model: {tts_model}")
            print(f"DEBUG tts_voice: {tts_voice}")
            print(f"DEBUG elevenlabs_key empty: {elevenlabs_key == ''}")

            # Agent
            with st.spinner("🤖 Agent thinking..."):
                agent_start    = time.time()
                agent_response = run_agent(user_text)
                agent_time     = time.time() - agent_start
                print(f"DEBUG agent response: '{agent_response[:30]}'")

            # TTS
            print(f"DEBUG calling TTS...")
            with st.spinner(f"🔊 Generating speech ({tts_model})..."):
                tts_start = time.time()
                try:
                    tts_audio = run_tts(agent_response)
                    tts_time  = time.time() - tts_start
                    tts_ok    = True
                    print(f"DEBUG TTS success, audio size: {len(tts_audio)}")
                except Exception as e:
                    tts_time  = time.time() - tts_start
                    tts_ok    = False
                    tts_audio = None
                    print(f"DEBUG TTS error: {e}")
                    st.error(f"TTS Error: {e}")

            total_time = stt_time + agent_time + (tts_time if tts_ok else 0)

            # Save to session state
            st.session_state.conversation.append({
                "user":      user_text,
                "assistant": agent_response,
            })
            st.session_state.latency_history.append({
                "stt":   round(stt_time, 3),
                "agent": round(agent_time, 3),
                "tts":   round(tts_time, 3) if tts_ok else 0.0,
                "total": round(total_time, 3),
            })

            # Store audio in session state → survives rerun
            if tts_ok and tts_audio:
                st.session_state.tts_audio = tts_audio

            # Reset transcript
            st.session_state.transcript    = ""
            st.session_state.stt_time      = 0.0
            st.session_state.last_audio_id = None
            # st.session_state.input_counter += 1

            st.rerun()

# ── Right column ──────────────────────────────────────────────────
with right_col:
    st.subheader("📊 Latency Monitor")

    if st.session_state.latency_history:
        last  = st.session_state.latency_history[-1]
        total = last["total"]

        # Metrics
        if stt_model == "OpenAI Whisper (API)":
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("STT",   f"{last['stt']:.2f}s")
            c2.metric("Agent", f"{last['agent']:.2f}s")
            c3.metric("TTS",   f"{last['tts']:.2f}s")
            c4.metric("Total", f"{last['total']:.2f}s")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Agent", f"{last['agent']:.2f}s")
            c2.metric("TTS",   f"{last['tts']:.2f}s")
            c3.metric("Total", f"{last['total']:.2f}s")
            st.markdown(
                "<p style='font-size:12px;color:#6c7086;margin:2px 0 10px;'>"
                "🟢 STT: On-device — 0ms server latency</p>",
                unsafe_allow_html=True
            )

        # Breakdown bars
        bars = ""
        if stt_model == "OpenAI Whisper (API)" and last["stt"] > 0:
            bars += latency_bar("STT",   last["stt"],   total, "#f38ba8")
        bars += latency_bar("Agent", last["agent"], total, "#a6e3a1")
        bars += latency_bar("TTS",   last["tts"],   total, "#89b4fa")
        st.markdown(bars, unsafe_allow_html=True)

        # RTF
        if last["tts"] > 0 and st.session_state.conversation:
            reply        = st.session_state.conversation[-1]["assistant"]
            est_duration = (len(reply) / 5) / 2.5
            rtf          = last["tts"] / max(est_duration, 0.1)
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(rtf_pill(rtf), unsafe_allow_html=True)

        st.divider()

        # History chart
        if len(st.session_state.latency_history) > 1:
            st.subheader("📈 History")
            hdf = pd.DataFrame(st.session_state.latency_history)
            hdf.index = [f"T{i+1}" for i in range(len(hdf))]
            cols = ["stt", "agent", "tts"] if stt_model == "OpenAI Whisper (API)" else ["agent", "tts"]
            st.bar_chart(hdf[cols])

        # Averages
        st.subheader("📋 Averages")
        hdf = pd.DataFrame(st.session_state.latency_history)
        if stt_model == "OpenAI Whisper (API)":
            avg_data = {
                "Component": ["STT", "Agent", "TTS", "Total"],
                "Avg (s)": [f"{hdf['stt'].mean():.3f}",  f"{hdf['agent'].mean():.3f}", f"{hdf['tts'].mean():.3f}", f"{hdf['total'].mean():.3f}"],
                "Min (s)": [f"{hdf['stt'].min():.3f}",   f"{hdf['agent'].min():.3f}",  f"{hdf['tts'].min():.3f}",  f"{hdf['total'].min():.3f}"],
                "Max (s)": [f"{hdf['stt'].max():.3f}",   f"{hdf['agent'].max():.3f}",  f"{hdf['tts'].max():.3f}",  f"{hdf['total'].max():.3f}"],
            }
        else:
            avg_data = {
                "Component": ["On-Device STT", "Agent", "TTS", "Total"],
                "Avg (s)": ["0.000 (free)", f"{hdf['agent'].mean():.3f}", f"{hdf['tts'].mean():.3f}", f"{hdf['total'].mean():.3f}"],
                "Min (s)": ["—",            f"{hdf['agent'].min():.3f}",  f"{hdf['tts'].min():.3f}",  f"{hdf['total'].min():.3f}"],
                "Max (s)": ["—",            f"{hdf['agent'].max():.3f}",  f"{hdf['tts'].max():.3f}",  f"{hdf['total'].max():.3f}"],
            }
        st.dataframe(avg_data, hide_index=True, use_container_width=True)

        st.divider()
        st.markdown(f"""
        <div style='font-size:12px;color:#6c7086;line-height:2.0;'>
            <b style='color:#cdd6f4;'>Current Config</b><br>
            🎙️ STT &nbsp;: {stt_model}<br>
            🔊 TTS &nbsp;: {tts_model} — {tts_voice}<br>
            🤖 LLM &nbsp;: {agent_model}<br>
            🌐 Lang: {language}
        </div>
        """, unsafe_allow_html=True)

    else:
        st.markdown("""
        <div style='text-align:center;color:#6c7086;margin-top:100px;'>
            <p style='font-size:48px;'>📊</p>
            <p>Latency metrics appear here<br>after your first message</p>
        </div>
        """, unsafe_allow_html=True)
# SAM Roadmap

Approved by Sachin Verma on 2026-11-24. Every phase was tested (`python -m tests.sam_tests`, plus a real launch) before the next one started.

**Decisions:** Gemini Live stays the online brain · every user-visible name becomes SAM · internal code names (`SamLive`, `SamUI`, browser profile folder, phone pairing token) stay, so browser logins and pairing keep working.

**Hardware target:** Intel i5-8250U (4 cores), 8 GB RAM, Intel UHD 620 (no CUDA). Local AI runs on the CPU.

| # | Phase | Status | Result |
|---|---|---|---|
| 0 | Safety: atomic memory writes, dashboard off by default, error-classification fixes, quiet routine defaults | ✅ Done | Corrupt memory is set aside, not wiped; dashboard port 8765, starts only on REMOTE |
| 1 | Rebrand to SAM, owner Sachin Verma | ✅ Done | Every name changed to SAM / Sachin Verma; attribution kept in LICENSE + NOTICE |
| 2 | Hindi / English / Hinglish behaviour | ✅ Done | `preferred_language` setting; voice tool `sam_settings` |
| 3 | Offline stack: Ollama + llama3.2:3b, Whisper small, Piper hi/en | ✅ Done | ~45–70 s warm-up once, then 5–17 s per reply; tool calls verified |
| 4 | Automatic online/offline switching | ✅ Done | Engine mode `auto`; switches when the internet drops or returns |
| 5 | Confirmation before sensitive actions | ✅ Done | Delete, overwrite, move, send message, package install wait for CONFIRM |
| 6 | Memory upgrade: edit, conversation history, better recall | ✅ Done | ✎ edit and + add in the memory panel; `conversation_history` tool |
| 7 | Wake word "Hey Sam" | ✅ Done | Vosk keyword spotting; 8/8 on synthetic tests; needs a real-mic check |
| 8 | Hand-gesture control (MediaPipe) | ✅ Done | 7 poses + swipes; off by default; 34 ms/frame |
| 9 | HUD status chips and lite mode | ✅ Done | AI / NET / MIC / CAM / WAKE chips; `ui_lite` |
| 10 | Cleanup: dead code, requirements, docs | ✅ Done | 5 dead files and 4 unused packages removed |

## Still to check by hand (needs your voice, face and room)
- "Hey Sam" on your real microphone: turn WAKE WORD on and say it from your normal distance. If it wakes by itself, raise `wake_threshold` (default 0.85); if it misses you, lower it.
- Gestures: open the camera privacy shutter and test each pose in your usual lighting. The camera read nearly black in testing (brightness 7/255).
- Offline voice end to end: switch the Wi-Fi off and talk.

## Ideas for later
- Verified WhatsApp sending (the original `_whatsapp_core` plugin is missing from the upstream repo).
- A real weather tool (the current one only opens a browser search).
- A Hinglish-capable local model if a better small one appears (llama3.2:3b sometimes answers English questions in Hinglish).

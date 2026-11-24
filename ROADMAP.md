# SAM Roadmap

Approved by Sachin Verma on 2026-11-24. Base: MARK LVII. Every phase is tested (`python -m tests.sam_tests`, plus a real launch) before the next one starts.

**Decisions:** Gemini Live stays the online brain · every user-visible name becomes SAM · internal code names (`JarvisLive`, `JarvisUI`, browser profile folder, phone pairing token) stay, so browser logins and pairing keep working.

**Hardware target:** Intel i5-8250U (4 cores), 8 GB RAM, Intel UHD 620 (no CUDA). Local AI runs on the CPU.

| # | Phase | Status |
|---|---|---|
| 0 | Safety: atomic memory writes, dashboard off by default, error-classification fixes, quiet routine defaults | ✅ Done |
| 1 | Rebrand to SAM, owner Sachin Verma | ✅ Done |
| 2 | Hindi / English / Hinglish behaviour | ⏳ |
| 3 | Offline stack: Ollama + llama3.2:3b, Whisper small, Piper hi/en | ⏳ |
| 4 | Automatic online/offline switching | ⏳ |
| 5 | Confirmation before sensitive actions | ⏳ |
| 6 | Memory upgrade: edit, conversation history, better recall | ⏳ |
| 7 | Wake word "Hey Sam" | ⏳ |
| 8 | Hand-gesture control (MediaPipe) | ⏳ |
| 9 | HUD status chips and lite mode | ⏳ |
| 10 | Cleanup: dead code, requirements, docs | ⏳ |

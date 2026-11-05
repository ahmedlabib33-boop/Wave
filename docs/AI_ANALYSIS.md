# Optional Groq AI analysis

Wave can ask Groq for a short operator-facing analysis of records already stored in the sensor hub. It is available in **Sensor Hub → AI analysis brief** and through the authenticated `POST /api/ai/brief` endpoint.

Set these values in the private `.env` file on the laptop or server:

```dotenv
GROQ_API_KEY=your-server-only-key
GROQ_MODEL=openai/gpt-oss-20b
GROQ_MAX_TOKENS=350
```

The browser never receives the Groq key. The server sends only the configured WGS84 search area, source-health metadata, and at most 100 recent normalized observations. It excludes provider raw payloads, camera stream URLs, credentials, frame images, and data-download paths.

The result is an AI-generated text summary, not a measurement. It cannot create observations, validate camera coverage, identify an object, establish source availability, or add map positions. The original records, timestamps, measurement methods, and source diagnostics remain the evidence to inspect. The Source Diagnostics page records Groq configuration and the last successful analysis request.

If the key is absent, the UI and API report that the optional integration is unconfigured. A rate-limit response is recorded separately and retried only when the operator sends a later request.

# OpenAI migration validation

Active provider: openai. Model: gpt-6-astra. Responses API with image input, strict JSON schema, reasoning high, store=false, truncation disabled. Existing CAD recognition and exclusion code unchanged.

Live synthetic request returned HTTP 401 on 2026-10-08. The configured OpenAI credential was rejected. No production CAD was sent to OpenAI, and no production revision or DWG was generated. Replace OPENAI_API_KEY in the server .env and restart the project before a live CAD test.

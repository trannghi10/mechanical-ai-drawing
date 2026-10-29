# Free local mode validation

2026-10-08: active native Qwen3-VL 4B; AI_OFFLINE=1, CAD_FREE_MODE=1, CAD_DWG_ENABLED=1. Runtime vision health and app readiness verified on loopback. Cloud calls remain disabled. The user explicitly selected the installed free ODA File Converter for local DWG input/output. Both DWG and DXF uploads are enabled.

Added preview and approved DXF export endpoints. Full test suite: 97 passed, including geometry/DIM/BOM/dependency propagation, preview export before approval, final export blocked before approval, byte-preserving approved DXF download, original immutability, and tampered revision rejection. Frontend JavaScript syntax passed.

No production LEG6949 revision was created by this migration. Qwen4B previously failed fit reasoning and the full related scope exceeded the 32768-token local budget. Large products need further context retrieval and checked rules; the app must reject incomplete plans rather than create an incorrect backup.

DWG roundtrip verification succeeded on the full 17.7 MB LEG6949 test output: 17 edited properties, native table data, layout entity inventories and DWG signature checked after DWG-to-DXF reopen. This fixture keeps bas unchanged and is a test, not an approved full engineering revision. See `storage/validation-fixtures/dwg-backup-roundtrip-test.json`.

General rectangular-profile recipes and source-measured linear equations are now connected to AI planning and revision validation. Holes keep their diameter and nearest-end offset; omitted geometry and hole collisions block execution. Arbitrary profiles, 3D solids, unverified ownership and unknown design intent remain unsupported.


2026-10-08 runtime repair: the previously pinned combined Qwen GGUF was no longer present. The installed migrated Qwen3-VL 4B GGUF (`9a575165…`) and projector (`84a6711c…`) were found in the local Ollama manifest and their SHA256 hashes verified. The launcher now supports this exact pair and the older combined file. `start-project.ps1` starts the model in the background; `/ai/start` provides a local recovery button. Readiness still requires vision support and the pinned model. Checked CAD compilers remain accessible when the model is down, without claiming model readiness. The UI restores the saved selection instead of displaying an unrelated first frame.

The exact request “thay đổi chi tiết số 6 hộp 30x60 dày 2 mm thành dày 1.2 mm” was submitted through the UI on the saved LEG6949 BOM frame `43C372`. The checked compiler recognized the request and the fit note. After the user chose preserving the snug fit, companion bas geometry and the original cut grid were implemented and a DWG preview was exported and reopened successfully. The original file remains unchanged and the revision remains unapproved. See `docs/tube-fit-backup-validation.md`.

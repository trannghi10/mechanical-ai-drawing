# Parametric editing and DWG backup validation — 2026-10-08

The user selected the already installed free ODA File Converter. AI remains on localhost. `CAD_DWG_ENABLED=1` permits local DWG input/output while `CAD_FREE_MODE=1` and `AI_OFFLINE=1` remain active.

Implemented reusable editing of measured rectangular profiles (closed straight four-vertex polyline or four LINE edges), circular holes and bound dimensions. The engine computes coordinates from the requested real measurement and source DIMLFAC, keeps hole diameter and nearest-end offset, checks profile closure and omitted geometry, rejects hole overlap/out-of-bounds and protects other instances through clone-on-write.

Source-measured linear equations support chains and cycles with a unique solution. For example, A=100, B=60 and C=40 with preserved differences become 76, 36 and 16 when A changes to 76. Conflicting or underdetermined equations are rejected. This solves supplied constraints; it does not discover design intent or certify a mechanical connection from a note alone.

The compiler handles an explicit old-to-new dimension command with a specified anchor on a uniquely identified supported profile. For model-driven requests, small local scopes now contain full raw geometry rather than indexed columns and omitted block children, with focused planning instructions. The first local model test with the previous context asked redundant questions and did not execute; that failure is retained in `parametric-live/plan-response.json`.

End-to-end API test on the separately authored PART-X sample: request 100→76 mm, preserve left end and circular holes, synchronize dimension and specification. Four edited properties were validated, the other shared instance remained unchanged, preview was rendered, and a real DWG preview backup (13,408 bytes) was downloaded. The preview remains unapproved; no production revision was approved by this test. Report: `storage/validation-fixtures/parametric-live/end-to-end.json`.

DWG reopen checks also passed for the full 17,724,390-byte LEG6949 test output, including native table data, edited geometry/text, true scaled dimensions, layer visibility and layout entity inventory. That fixture uses the earlier test policy of keeping bas unchanged and is not an approved full engineering change. Report: `storage/validation-fixtures/dwg-backup-roundtrip-test.json`.

UI verified: after-preview drawing, download success, “Tải DWG xem trước” and “Duyệt bản sửa và xuất DWG backup”. Original CAD files are preserved. Sheet recognition/red-cross exclusions were not changed.

Final natural-language test: “rút ngắn ... còn 76 mm, giữ cố định đầu trái ...” reads the original dimension from the source, compiles four property changes and downloads a validated 13,408-byte DWG without requiring the old length in the command. This uses the source-checked rectangular compiler, not invented model coordinates. Report: `storage/validation-fixtures/parametric-live/natural-end-to-end.json`; file: `TEST-natural-request-backup.dwg`.

Native-model limitations remain observable: the raw-geometry test initially found the correct outline/hole/dimension refs but used an instance handle as part code and omitted ownership evidence. Source-backed normalization was added for native block membership and labelled text. A subsequent model call omitted the structured recipe and produced no executable operations; its result remains blocked and preserved in `native-final-plan-response.json`. Do not describe unrestricted model-driven CAD editing as completed. Current full regression suite: 130 passed.

Limits: arbitrary curved profiles, 3D solids, general cut nesting, unverified geometry ownership, all BOM templates, and automatic recovery of every assembly relationship are not complete. The old 724→700 / all laser-sheet thickness request is not marked completed by these tests. A working DWG exporter cannot turn an incomplete engineering plan into a complete backup.

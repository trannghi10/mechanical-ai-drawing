# DWG preview progress — 09/10/2026

Historical snapshot. See [the 10/10/2026 report](backup-progress-2026-10-10.md) for the newer DWG, assembly mappings and remaining work.

The current artifact is a **preview**, not a complete synchronized assembly backup. This report supersedes the earlier tube + bas 4 preview for the same request. Original drawing recognition and red-cross exclusions are unchanged.

Request: part 6, tube 30×60×571.5, wall 2 → 1.2 mm; retain outside dimensions, drilling and snug fits. Check the entire `(Cắt laser)` stage and modify only affected parts.

## Actual artifact

- Document: `baf461e9c2764a5ba9000a48772f846c`.
- Plan: `a679e1061b4647fa98397e4617b73084`, 39,348 bound operations.
- Revision: `6f71190b8f894a28a7e0a6ce5cd9bea5`, unapproved.
- DWG: `storage/backups/LEG6949-PREVIEW-hop1.2-bas1-2-3-4-R3.8.dwg`, 17,679,028 bytes, DWG 2018.
- Original DXF SHA-256: `3f1c8d90be4d3e8d858b15abfd017f17ae20c2dd323863e2af63fe983685662b`, unchanged.
- Open: `http://127.0.0.1:8765/explorer?document=baf461e9c2764a5ba9000a48772f846c&revision=6f71190b8f894a28a7e0a6ce5cd9bea5&target=43C372`.

## Changes actually written

| Part | Before | After |
| --- | --- | --- |
| 1 — 8.1.06759.002 | 2×25.6×45 | 2×27.2×45 |
| 2 — 8.1.07007.002 | 2×10.6×25.6 | 2×11.4×27.2 |
| 3 — 8.1.07008.002 | 2×25.6×55.6 | 2×27.2×57.2 |
| 4 — 8.1.07009.002 | 2×25.6×444.5 | 2×27.2×444.5 |
| 6 — 8.1.07011.002 | 2×30×60×571.5 | 1.2×30×60×571.5 |

All dimensions are millimeters. Bound detail profiles, side projections, true DIMENSION measurements and descriptions update together. Plate thickness and holes stay fixed. Bas 1, 2 and 3 corner radii change R3 → R3.8 to follow the verified tube inner corner radius; native radial dimensions and every retained cut template change together. Four native BOM tables (`43BF4A`, `43C373`, `440824`, `440825`) and their geometry mirrors contain all five revised specifications. Assembly BOM quantities remain unchanged. The packaging BOM is a separate material/numbering context.

## Corner-fit correction and additional CAD tool

The installed FreeCAD 1.1.1 bundled Python now runs OpenCASCADE BRep validation offline. It constructs faces directly from the checked CAD LINE/ARC/LWP profiles and real holes, extrudes the measured side-view gauge and checks validity. For the full cap (bas 3), it also checks centered containment in the source-bound tube inner section before and after the edit. Bas 1/2 checks prove valid individual solids, not complete assembly placement.

The previous R3 preview had **0.592487883 mm³** corner interference after the tube wall change. Linear clearance equations did not catch it. The corrected R3.8 cap has **0 mm³** interference in this section check. The old revision `12a92caab83e49aeb152acccac98da9a` is marked `needs_revalidation` and failed solid validation; new exports from it are blocked. Existing old DWG files are retained for traceability and must not be used as completed backups.

`FREECAD_PYTHON` can select the installed bundled interpreter; the application auto-detects `C:/Program Files/FreeCAD */bin/python.exe`. No additional model, paid SDK or cloud CAD transmission was introduced. Missing or failed solid checks block this adapter before applying changes. Final approval recompiles saved source bindings so legacy plans cannot bypass new radius rules.

Small detail frames `43800A`, `43807D`, `4380F3` are recovered only as dependency targets using exact known BOM codes, title-block labels, fit notes and closed frames. They do not change the sheet gallery recognition thresholds.

The full-width fits preserve `outside − 2×wall − plate = 0.4 mm`. Part 2's short axis is a single-wall fit: the measured 15 mm notch offset, tube wall, measured 2 mm closing plate and 0.4 mm gap give 10.6 → 11.4 mm. The compiler verifies the tube's closed six-edge L silhouette and source dimensions; it does not copy the 1.6 mm change onto every axis.

## Cutting layouts

| Part | Source pieces/sheet | Revised pieces/sheet |
| --- | ---: | ---: |
| 1 | 2735 | 2465 |
| 2 | 10363 | 8240 |
| 3 | 2171 | 1960 |
| 4 | 306 | 286 |

Stock remains 1250×3000 mm. The rounded-profile packer keeps source used bounds/margins, rotations and mirrors, and conservatively uses the largest adjacent source clearance (3 mm). Part 4 retains its verified 0.5 mm source gap. Every retained profile is bound to its matching detail geometry, and bounds and collisions are checked. This is conservative repacking, not global or interlocking nesting optimization.

Identical local geometry changes share a newly cloned static block within the selected instances. Original definitions and unselected instances retain their original geometry. This avoids creating over 10,000 duplicate block definitions and keeps the modified DXF near 95 MB.

## Verification

ODA converts the separate DXF to DWG and reopens the DWG as DXF. Export verification checks real changed properties and DIM measurements, all native table values, cloned geometry/holes, layout inventories, layer visibility and native dimension links. Supported copied LWP DIMASSOC references are rebound to the uniquely measured vertex on an incident straight edge; adjacent endpoint intersections are normalized, while unproven intersections and topology changes are blocked. Code reference: [Autodesk DIMASSOC](https://help.autodesk.com/cloudhelp/2024/ENU/AutoCAD-DXF/files/GUID-C0B96256-A911-4B4D-85E6-EB4AF2C91E27.htm).

Evidence:

- `storage/validation-fixtures/rounded-companion-backup-check.json`
- `storage/validation-fixtures/current-preview-measurements.json`
- Revision `revision.json` contains full operations, isolation and roundtrip reports.
- `storage/validation-fixtures/backup-bas3-R3.8-after.jpg` shows the actual 57.2×27.2/R3.8 detail with its unchanged Ø10.5 hole.
- `storage/validation-fixtures/companion-source/solid-validation.json` records the source-bound FreeCAD checks.

220 Python tests passed, including a real FreeCAD regression which detects the old R3 interference and accepts R3.8. The independent DWG roundtrip audit measured all three native radial dimensions at 3.8, preserved all 1,373 original circles and all 41 native tables, and checked cut counts/stock sizes. JavaScript syntax, fit-to-view and proposal deduplication checks passed.

The UI keeps one selected drawing visible, opens related frames one at a time, and explicitly distinguishes the available preview from final approval. Repeated downloads reuse a DWG only when the current DXF and exported DWG hashes still match the verified roundtrip. Slow preview rendering preserves newer export/review metadata.

## Work still required for a complete backup

The detached orthographic/isometric assembly drawings in `43C372`, `43BC13`, `43BD0D`, `43BF49` do not yet have verified ownership and projection transforms for every changed part. Their BOM cells update; their assembly geometry does not yet fully update. Old assembly references `434BBD` and `434C87` remain review references, not validated current dimensions.

Final approval and final DWG/DXF export are blocked for this revision. A production-capable next stage needs to bind each assembly projection/section/detail to source parts, solve their assembly placement and wall/clearance effects, regenerate every affected view and validate cross-view consistency. The assembly map must include enlarged details and welding boundaries, not just the exploded part outlines. Model visual guesses do not constitute this proof. Strength, welding suitability and manufacturing approval are not established by the current geometric checks.

The implemented adapters cover verified axial rounded rectangles, rectangular tubes and the source-bounded static cutting patterns above. They do not implement arbitrary CAD topology, general 3D reconstruction or every future product's assembly constraints.

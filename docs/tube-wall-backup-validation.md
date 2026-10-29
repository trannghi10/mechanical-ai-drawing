# Checked tube-wall planner

2026-10-08. Added a checked compiler for a single numbered rectangular steel tube thickness reduction. It identifies the verified BOM row, matching detail sheet, four concentric arc pairs, four inner section lines, four hidden wall projection lines and the true wall dimension. Numeric intent is parsed locally; actual CAD coordinates and BOM binding are obtained from the parser, not invented by the language model. Unsupported shapes/units/combined requests fall back to the existing planner.

Production LEG6949 test: 17 operations applied to TEST-tube-wall-not-approved.dxf; source hash unchanged. Actual wall measurement after readback: 1.199999999999818 mm. Inner arcs radius 3 to 3.8; outside 30x60 and length 571.5 retained. Detail title, stock specification and native BOM description/mirror synchronized. Rendered PNG visually inspected.

Fixed dimension rendering canonicalizing defpoint and causing post-edit validation failure. Added regression coverage for requested DIM position, measured value and original immutability. Full suite passed 102 tests before the final additional BOM-policy test; targeted tube suite passed 6 tests afterward.

The test DXF deliberately keeps the bas unchanged; this is a test policy, not user approval. It is NOT a complete approved product backup. A live app plan with no fit policy returns a specific question. The human choice is pending: retain bas and accept larger clearance, or preserve clearance and change bas/cut-layout. The second path is not yet implemented. No ODA or cloud API used. No claim of arbitrary-detail editing or structural strength validation.

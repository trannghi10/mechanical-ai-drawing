# Tube and bas fit backup validation

The LEG6949 request changes tube part 6 from 2 mm to 1.2 mm. The user selected preserving the snug fit. The checked compiler updates the companion bas part 4 and its existing cut sheet using source geometry, exact BOM codes and the fit note. No model-generated CAD coordinates or cloud requests are used for these operations.

- Tube 8.1.07011.002: wall 2 → 1.2 mm, outside 30×60 and length 571.5 mm preserved. Inner arcs/lines, longitudinal wall projections and the real thickness DIMENSION change together.
- Bas 8.1.07009.002: width 25.6 → 27.2 mm, thickness 2 mm and length 444.5 mm preserved. Symmetric widening leaves all three drilling centers and radii unchanged. The real width/half-width dimensions and specification text update together.
- Fit equation: outside 30 − 2×wall − bas width = 0.4 mm, before and after. The fit note and three measured dimensions are the evidence.
- Both native BOM description cells and their display mirrors update. BOM assembly quantities remain unchanged.
- Cut sheet: original 1250×3000 mm stock, source 0.5 mm cutting gap and margins retained. Repacking the existing two-zone 0/90 grid gives 286 parts instead of 306. Twenty static layout INSERTs are removed from the revision only; retained instances are isolated from shared definitions. The count text, bas specification and edge-margin dimensions update together. The layout is validated for bounds and collisions; it is not globally optimized nesting.
- Equal template geometry and drilling remain recognizable even after previous edits assigned different isolated block names.
- Supported native DIMASSOC endpoint links are refreshed to the real changed LINE endpoints. Source cached points were stale. Unknown snaps, opaque reactors on changed dimensions and other association classes remain blocked. Unchanged drilling/longitudinal dimensions keep their native constraints.

## Actual artifact

Document `baf461e9c2764a5ba9000a48772f846c`, plan `57e76d496b384400855f7a2d5d699ad2`, revision `bfbe287cac3f41ce84249fe1a1256a1a`.

`storage/backups/LEG6949-PREVIEW-hop1.2-bas27.2.dwg` is a real 17,780,763-byte DWG 2018 preview. The revision is unapproved. The original source DXF hash is unchanged. DWG-to-DXF reopening verified edited properties, real DIM measurements, all native tables, layout inventories, layer visibility, cloned geometry/drilling and native DIMASSOC anchors. The reopened wall measures 1.2 mm, bas width 27.2 mm and fit gap 0.4 mm within numerical tolerance.

Evidence: `storage/validation-fixtures/tube-keep-fit-end-to-end.json`. The application's existing before/after previews and dependency confirmation precede final approval/export. The engine supports the checked geometry patterns above; arbitrary 3D, dynamic blocks, complex profiles and unproven links remain outside this validation.

## Expanded four-BOM backup

The latest live UI check starts from the tube detail sheet alone (`43BAB5`). Code-based scope expansion finds the bas detail, cut sheet and four assembly BOM sheets. Plan `ee2543b0997b4a749f13f0bc295cd80c` compiles 1492 operations across seven targets. Revision `db786ddc9bc14b9492f30164c05eb5e3` updates the description cells and their mirrors in tables `43BF4A`, `43C373`, `440824`, `440825`.

`storage/backups/LEG6949-PREVIEW-hop1.2-bas27.2-4BOM.dwg` is the new 17,792,491-byte DWG preview. DWG-to-DXF reopening confirms both new descriptions in all four native tables; the original source hash is unchanged. Full exporter roundtrip checks pass. It remains unapproved, for technical review before production. Evidence: `storage/validation-fixtures/four-bom-backup-check.json`.

The UI displays six grouped proposal rows, showing synchronization at nine tube-description locations and ten bas-description locations. The primary drawing remains selected; the other six targets are available through a collapsed review selector. Source recognition and red-cross exclusions were not modified.

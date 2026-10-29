# Experimental direct point-reference bridge

The bounded adapter is now integrated into proposal schema 2 and revision/undo
with a fresh repair and all 12 challenges required before ready. PostgreSQL
recovery is resolved. See `docs/native-revision-release-2026-10-22.md` for the
HTTP and restart receipts; notes below retain the earlier standalone experiment.

Status: built with MSVC 14.44.35207 and tested in AutoCAD 2027. Synthetic save/reopen
and the bounded customer-copy repair passed independent DXF verification. All
eight A/B ±10 mm challenges passed after save/reopen. The DLL is not included in
the production bundle and revision workers never invoke it.

Verified evidence: `storage/validation-fixtures/native-point-reference-validated-edafbefa/verification.json`.
Final cumulative evidence: `storage/validation-fixtures/native-point-reference-validated-613ecb2c/verification.json`.
The cumulative DWG retains all four existing complete legacy DIM bindings. Eight
A/B challenges passed again, plus four native-B-only challenges after removing
the redundant new legacy B reference on disposable copies. See
`native-b-isolation.json` in the cumulative evidence directory.
This adapter adds an `AcDbDimAssoc` with explicit A/B references while retaining
the original native B action; it does not add an A parameter to the private
`AcDbAssocRotatedDimActionBody` implementation.

`NativePointReference.cpp` uses the SDK's `AcDbDimAssoc` / `AcDbOsnapPointRef`
API and a database transaction. It supplies explicit polyline segment-start
references for both DIM endpoints, checks evaluated coordinates before posting,
and makes no call to remove an existing native action. This does **not** prove
that a DIMASSOC can coexist with the existing native B action.

The synthetic-only `MECHANICALPOINTREFSMOKE` command is compiled into the managed
local plugin. Its Python runner separately checks the saved/reopened DXF binding.
It intentionally does not report native B preservation or customer repair success.

Prerequisites: ObjectARX 2027, MSVC 14.44 x64, Windows SDK.

```powershell
powershell -NoProfile -File scripts/build_native_point_reference.ps1
python scripts/setup_autocad.py build
python scripts/setup_autocad.py check
python scripts/probe_native_point_references.py
```

Run local AutoCAD commands with the existing workspace execution permissions.
SDK currently extracted to `storage/tools/objectarx2027/CDROM1`.
Compiler installation target: `storage/tools/vsbuild2026`.

The system installer did not finish. Workspace-local Microsoft packages were
used instead; build with `python scripts/build_native_point_reference.py`.
Compiler payload hashes were checked against the Microsoft catalog. The bridge
DLL SHA-256 is `536117f27842c6199bdb8f019965a86e042f49f864d43b94a6363ad1fb1b2d41`.
The later build with the challenge-only B-removal export has SHA-256
`2e542e39ffe40a642eda53bec72f0b4b4de6566ea8dbc6694394c66febc7c4ca`.

The customer-copy experiment captures native B action/dependency/parameter
identities, verifies them after posting and reopening, and challenges A and B
independently via DIMREGEN without assigning DIM endpoints. Any failure discards
the private database and leaves the current revision intact. Production revision
integration is still pending; PostgreSQL currently reports recovery mode and
the latest standard setup check stops before its CAD stage for that reason.

On 22 October the Microsoft installer reached catalog download but stopped making
progress. A local catalog was downloaded successfully. Restarting the installer
was refused by Windows with `Access is denied` for setup PID 18260 (started 08:30).
The process was not killed and no duplicate installer was started. Administrative
completion/cancellation of that installer is required before the local-catalog
retry. This is an OS privilege error, not an automatic approval-review rejection.

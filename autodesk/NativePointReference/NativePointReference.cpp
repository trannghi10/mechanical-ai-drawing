// Experimental bridge: supported ObjectARX point-reference API only.
// The caller must use a disposable database and independently verify save/reopen.
#include "dbapserv.h"
#include "dbdim.h"
#include "dbpl.h"
#include "dbsubeid.h"
#include "dbdimassoc.h"
#include "dbdimptref.h"
#include "dbtrans.h"
#include <memory>

namespace {
void check(Acad::ErrorStatus status) { if (status != Acad::eOk) throw status; }
AcDbObjectId resolve(AcDbDatabase* db, const wchar_t* handle) {
    AcDbObjectId id;
    check(db->getAcDbObjectId(id, false, AcDbHandle(handle)));
    return id;
}
}

// Challenge-only: remove the redundant new legacy B reference on a disposable
// copy so that movement of B must be supplied by the original native action.
extern "C" __declspec(dllexport) int __cdecl MechanicalDisableSecondPointReference(
    AcDbDatabase* db, const wchar_t* dimHandle) noexcept {
    if (!db || !dimHandle) return -1;
    auto manager=db->transactionManager();manager->startTransaction();
    try {
        auto dimId=resolve(db,dimHandle);AcDbObjectId assocId;
        check(acdbGetDimAssocId(dimId,assocId));
        AcDbDimAssoc* assoc=nullptr;check(manager->getObject(assoc,assocId,AcDb::kForWrite));
        if (!assoc || !assoc->pointRef(0) || !assoc->pointRef(1)) throw Acad::eInvalidInput;
        check(assoc->removePointRef(1));check(assoc->setAssocFlag(1,false));
        if (assoc->pointRef(1) || assoc->assocFlag(1) || !assoc->pointRef(0)) throw Acad::eInvalidInput;
        check(manager->endTransaction());return 0;
    } catch (Acad::ErrorStatus status) {manager->abortTransaction();return int(status);}
    catch (...) {manager->abortTransaction();return -2;}
}

// No command emulation, no native action deletion, no raw DWG/DXF field patching.
// Both references are explicit. Whether DIMASSOC and the existing native action
// coexist correctly must be proven by the managed experiment, not assumed here.
extern "C" __declspec(dllexport) int __cdecl MechanicalAddPointReferences(
    AcDbDatabase* db, const wchar_t* dimHandle, const wchar_t* polyHandle,
    int firstVertex, int secondVertex, int* stage) noexcept {
    if (!db || !dimHandle || !polyHandle || !stage) return -1;
    auto manager = db->transactionManager();
    *stage = 0;
    manager->startTransaction();
    try {
        auto dimId = resolve(db, dimHandle), polyId = resolve(db, polyHandle);
        AcDbRotatedDimension* dim = nullptr;
        AcDbPolyline* poly = nullptr;
        check(manager->getObject(dim, dimId, AcDb::kForWrite));
        check(manager->getObject(poly, polyId, AcDb::kForRead));
        *stage = 1;
        if (!dim || !poly || !poly->isClosed() || firstVertex < 0 || secondVertex < 0
            || firstVertex >= int(poly->numVerts()) || secondVertex >= int(poly->numVerts())
            || firstVertex == secondVertex) throw Acad::eInvalidInput;
        for (unsigned i = 0; i < poly->numVerts(); ++i) {
            double bulge = 0; check(poly->getBulgeAt(i, bulge));
            if (bulge != 0.0) throw Acad::eInvalidInput;
        }
        AcGePoint3d a, b;
        check(poly->getPointAt(firstVertex, a)); check(poly->getPointAt(secondVertex, b));
        if (dim->xLine1Point().distanceTo(a) > 1e-6 || dim->xLine2Point().distanceTo(b) > 1e-6)
            throw Acad::eInvalidInput;
        AcDbObjectId existing;
        auto existingStatus = acdbGetDimAssocId(dimId, existing);
        if (existingStatus != Acad::eKeyNotFound && existingStatus != Acad::eNullObjectId)
            check(existingStatus);
        if (!existing.isNull()) throw Acad::eDuplicateKey;
        *stage = 2;
        auto assoc = std::make_unique<AcDbDimAssoc>();
        check(assoc->setDimObjId(dimId));
        int vertices[] = {firstVertex, secondVertex};
        AcGePoint3d points[] = {a, b};
        for (int endpoint = 0; endpoint < 2; ++endpoint) {
            // LWPOLYLINE segment markers are 1 based; start snap selects its start.
            AcDbFullSubentPath path(polyId, AcDb::kEdgeSubentType, vertices[endpoint] + 1);
            auto ref = std::make_unique<AcDbOsnapPointRef>(AcDbPointRef::kOsnapStart, &path,
                                                        nullptr, &points[endpoint]);
            AcGePoint3d evaluated;
            check(ref->evalPoint(evaluated));
            if (evaluated.distanceTo(points[endpoint]) > 1e-6) throw Acad::eInvalidInput;
            check(assoc->setPointRef(endpoint, ref.get())); ref.release();
            check(assoc->setAssocFlag(endpoint, true));
        }
        *stage = 3;
        AcDbObjectId assocId;
        check(assoc->post(dimId, assocId, true));
        auto posted = assoc.release();
        check(manager->addNewlyCreatedDBRObject(posted, true));
        check(posted->addToPointRefReactor());
        *stage = 4;
        if (posted->dimObjId() != dimId) throw Acad::eNullObjectId;
        check(posted->updateDimension(true, false));
        if (dim->xLine1Point().distanceTo(a) > 1e-6 || dim->xLine2Point().distanceTo(b) > 1e-6)
            throw Acad::eInvalidInput;
        check(manager->endTransaction());
        *stage = 5;
        return 0;
    } catch (Acad::ErrorStatus status) {
        manager->abortTransaction(); return int(status);
    } catch (...) {
        manager->abortTransaction(); return -2;
    }
}

using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.EditorInput;
using CoreApplication=Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace MechanicalCad;

public partial class Commands
{
    static bool RepairObjectRemoved(Database db,string handle)
    {
        try {return Id(db,handle).IsErased;}
        catch(Autodesk.AutoCAD.Runtime.Exception e) when(e.ErrorStatus.ToString() is "UnknownHandle" or "KeyNotFound") {return true;}
    }
    [CommandMethod("MECHANICALCHALLENGEREPAIREDDIM")]
    public void ChallengeRepairedDimension()
    {
        try {ChallengeRepairedDimensionChecked();}
        catch(System.Exception e) {Write("relationship-challenge-error.json",new {type=e.GetType().FullName,message=e.Message,stack=e.StackTrace});}
    }
    static void ChallengeRepairedDimensionChecked()
    {
        using var input=JsonDocument.Parse(File.ReadAllBytes("relationship-challenge.json"));var cfg=input.RootElement;
        Require(RepairInputHash()==S(cfg,"source_sha256"),"Challenge source hash mismatch");
        var db=CoreApplication.DocumentManager.MdiActiveDocument.Database;var editor=CoreApplication.DocumentManager.MdiActiveDocument.Editor;
        Require(Path.GetFullPath(db.Filename)==Path.GetFullPath("input.dwg"),"Challenge requires private input document");
        var root=S(cfg,"polyline_handle");var dimHandle=S(cfg,"dimension_handle");var vertex=cfg.GetProperty("vertex_index").GetInt32();
        var delta=StretchPoint(cfg.GetProperty("delta"))-Point3d.Origin;
        bool nativeHead=cfg.TryGetProperty("native_head_observation",out var nativeHeadJson) && nativeHeadJson.GetBoolean();
        bool firstEndpoint=nativeHead || (cfg.TryGetProperty("challenge_first_endpoint",out var firstJson) && firstJson.GetBoolean());
        bool pointReferences=cfg.TryGetProperty("native_point_reference_challenge",out var refsJson) && refsJson.GetBoolean();
        bool nativeBOnly=cfg.TryGetProperty("native_b_only",out var onlyJson) && onlyJson.GetBoolean();
        Require(!nativeBOnly || (pointReferences && !firstEndpoint),"Native B isolation requires B challenge");
        var nativeTarget=pointReferences?cfg.GetProperty("native_target"):default;
        bool bounded=pointReferences?S(nativeTarget,"dimension_handle")==dimHandle && vertex==nativeTarget.GetProperty(firstEndpoint?"a_vertex":"b_vertex").GetInt32() && vertex>=0 && vertex<8:
            firstEndpoint?((dimHandle=="3DFA24" && vertex==1)||(dimHandle=="3DFA29" && vertex==0)):(vertex==3 || vertex==6);
        Require(bounded && delta.Length>1e-6 && delta.Length<=20 && Math.Abs(delta.Z)<1e-10,"Challenge needs bounded vertex move");
        ProbeDimension beforeDim;Point3d[] points;Dictionary<string,string> before;HashSet<string> beforeVisuals;
        using(var tr=db.TransactionManager.StartTransaction())
        {
            var poly=(Polyline)tr.GetObject(Id(db,root),OpenMode.ForRead);var dim=(RotatedDimension)tr.GetObject(Id(db,dimHandle),OpenMode.ForRead);
            Require(poly.Closed && poly.NumberOfVertices==8 && poly.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-8,1e-8)),"Unsupported challenge profile");
            Require((firstEndpoint?dim.XLine1Point:dim.XLine2Point).DistanceTo(poly.GetPoint3dAt(vertex))<1e-6 && (nativeHead?dim.ExtensionDictionary.IsNull:!dim.ExtensionDictionary.IsNull),"Challenge endpoint mismatch");
            if(nativeHead)
            {
                var refs=dim.GetPersistentReactorIds().Cast<ObjectId>().ToArray();Require(refs.Length==1,"Native head observation requires one DIM dependency");
                var dependency=tr.GetObject(refs[0],OpenMode.ForRead) as AssocDependency;Require(dependency!=null && dependency.DependentOnObject==dim.ObjectId,"Native DIM dependency mismatch");
                var action=(AssocAction)tr.GetObject(dependency!.OwningAction,OpenMode.ForRead);
                var geometries=action.GetDependencies(true,true).Cast<ObjectId>().Select(id=>tr.GetObject(id,OpenMode.ForRead)).OfType<AssocGeomDependency>().ToArray();
                Require(geometries.Length==1 && geometries[0].DependentOnObject==poly.ObjectId,"Native DIM source mismatch");
            }
            points=Enumerable.Range(0,8).Select(poly.GetPoint3dAt).ToArray();beforeDim=ProbeDim(dim);
            before=CenterState(db,tr);beforeVisuals=ProbeVisuals(db,tr,new[]{dimHandle});tr.Commit();
        }
        if(nativeBOnly)
        {
            var library=System.Runtime.InteropServices.NativeLibrary.Load(Path.GetFullPath("MechanicalPointReference.dll"));
            try
            {
                var disable=System.Runtime.InteropServices.Marshal.GetDelegateForFunctionPointer<DisableSecondPointReference>(System.Runtime.InteropServices.NativeLibrary.GetExport(library,"MechanicalDisableSecondPointReference"));
                Require(disable(db.UnmanagedObject,dimHandle)==0,"Could not isolate native B from new legacy B reference");
            }
            finally {System.Runtime.InteropServices.NativeLibrary.Free(library);}
        }
        using(var tr=db.TransactionManager.StartTransaction())
        {
            var poly=(Polyline)tr.GetObject(Id(db,root),OpenMode.ForWrite);var target=points[vertex]+delta;
            poly.SetPointAt(vertex,new Point2d(target.X,target.Y));tr.Commit();
        }
        // No DIM endpoint assignment. Trigger associative updates through the editor.
        editor.Command("_.DIMREGEN");editor.Regen();
        if(nativeHead)
        {
            using var tr=db.TransactionManager.StartTransaction();var dim=(RotatedDimension)tr.GetObject(Id(db,dimHandle),OpenMode.ForRead);
            var poly=(Polyline)tr.GetObject(Id(db,root),OpenMode.ForRead);var observedExpectedA=beforeDim.A+delta;
            for(int i=0;i<8;i++)Require(poly.GetPoint3dAt(i).DistanceTo(points[i]+(i==vertex?delta:new Vector3d(0,0,0)))<1e-6,"Native head observation changed unexpected vertex");
            var axisHead=new Vector3d(Math.Cos(beforeDim.Angle),Math.Sin(beforeDim.Angle),0);
            var expected=Math.Abs((beforeDim.B-observedExpectedA).DotProduct(axisHead));
            Write("relationship-native-head.json",new {status="observed_native_head_response",source_sha256=S(cfg,"source_sha256"),polyline_handle=root,dimension_handle=dimHandle,vertex_index=vertex,
                delta=V(delta),before=ProbeDimJson(beforeDim),after=ProbeDimJson(ProbeDim(dim)),expected_a=P(observedExpectedA),expected_measurement_if_bound=expected,
                follows_candidate_vertex=dim.XLine1Point.DistanceTo(observedExpectedA)<1e-6 && Math.Abs(dim.Measurement-expected)<1e-6,
                original_head_unchanged=dim.XLine1Point.DistanceTo(beforeDim.A)<1e-6,original_other_endpoint_unchanged=dim.XLine2Point.DistanceTo(beforeDim.B)<1e-6,
                dim_endpoint_writer_assigned=false,output_dwg_created=false,customer_revision_created=false,
                policy="Observation on a disposable copy after DIMREGEN. Failure to follow is not permission to attach an inferred vertex."});
            return;
        }
        var expectedA=beforeDim.A+(firstEndpoint?delta:new Vector3d(0,0,0));var expectedB=beforeDim.B+(firstEndpoint?new Vector3d(0,0,0):delta);var axis=new Vector3d(Math.Cos(beforeDim.Angle),Math.Sin(beforeDim.Angle),0);
        var expectedMeasure=Math.Abs((expectedB-expectedA).DotProduct(axis));
        void Check(Database database,Transaction tr)
        {
            var poly=(Polyline)tr.GetObject(Id(database,root),OpenMode.ForRead);var dim=(RotatedDimension)tr.GetObject(Id(database,dimHandle),OpenMode.ForRead);
            Write("relationship-challenge-current.json",new {before=ProbeDimJson(beforeDim),after=ProbeDimJson(ProbeDim(dim)),expected_b=P(expectedB),expected_measurement=expectedMeasure});
            Require(dim.XLine1Point.DistanceTo(expectedA)<1e-6 && dim.XLine2Point.DistanceTo(expectedB)<1e-6 && Math.Abs(dim.Measurement-expectedMeasure)<1e-6,"Repaired DIM did not follow geometry automatically");
            for(int i=0;i<8;i++)Require(poly.GetPoint3dAt(i).DistanceTo(points[i]+(i==vertex?delta:new Vector3d(0,0,0)))<1e-6,"Challenge changed unexpected vertex");
            Require(dim.DimensionStyle.Handle.ToString()==beforeDim.Style && dim.DimensionText==beforeDim.Value && Math.Abs(dim.Rotation-beforeDim.Angle)<1e-10,"Challenge DIM style changed");
            if(pointReferences)
            {
                string dependency=S(nativeTarget,"dimension_dependency"),geometry=S(nativeTarget,"geometry_dependency"),actionHandle=S(nativeTarget,"action_handle");
                var dep=(AssocDependency)tr.GetObject(Id(database,dependency),OpenMode.ForRead);
                var geom=(AssocGeomDependency)tr.GetObject(Id(database,geometry),OpenMode.ForRead);
                var action=(AssocAction)tr.GetObject(Id(database,actionHandle),OpenMode.ForRead);
                Require(action.ActionBody==Id(database,S(nativeTarget,"body_handle")) && tr.GetObject(action.ActionBody,OpenMode.ForRead).GetRXClass().Name=="AcDbAssocRotatedDimActionBody","Native B action body changed");
                Require(dep.OwningAction==action.ObjectId && dep.DependentOnObject==dim.ObjectId && geom.OwningAction==action.ObjectId && geom.DependentOnObject==poly.ObjectId,"Native B challenge ownership changed");
                Require(dim.GetPersistentReactorIds().Cast<ObjectId>().Contains(dep.ObjectId) && poly.GetPersistentReactorIds().Cast<ObjectId>().Contains(geom.ObjectId),"Native B challenge reactors removed");
                var nativeB=((System.Collections.IEnumerable)geom.VertexSubentityGeometry).Cast<Point3d>().ToArray();
                Require(nativeB.Length==1 && nativeB[0].DistanceTo(dim.XLine2Point)<1e-6,"Native B challenge vertex no longer matches DIM");
            }
        }
        using(var tr=db.TransactionManager.StartTransaction()){Check(db,tr);tr.Commit();}
        db.SaveAs(Path.GetFullPath("relationship-challenge.dwg"),DwgVersion.AC1032);
        using var reopened=new Database(false,true);reopened.ReadDwgFile(Path.GetFullPath("relationship-challenge.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);reopened.CloseInput(true);
        var previous=HostApplicationServices.WorkingDatabase;HostApplicationServices.WorkingDatabase=reopened;
        try
        {
            using var tr=reopened.TransactionManager.StartTransaction();Check(reopened,tr);
            var after=CenterState(reopened,tr);var afterVisuals=ProbeVisuals(reopened,tr,new[]{dimHandle});
            // A neighboring DIM may legitimately update from the changed polyline.
            // Report all differences; caller must inspect them rather than claim isolation.
            var changed=before.Keys.Intersect(after.Keys).Where(h=>h!=root && !beforeVisuals.Contains(h) && !afterVisuals.Contains(h) && !SameNativeSnapshot(before[h],after[h])).Select(h=>new {handle=h,before=JsonSerializer.Deserialize<JsonElement>(before[h]),after=JsonSerializer.Deserialize<JsonElement>(after[h])}).ToArray();
            Write("relationship-challenge-native.json",new {status="native_repaired_dim_followed_geometry",source_sha256=S(cfg,"source_sha256"),output_sha256=Hash("relationship-challenge.dwg"),polyline_handle=root,dimension_handle=dimHandle,vertex_index=vertex,delta=V(delta),before_measurement=beforeDim.Measure,after_measurement=expectedMeasure,dim_endpoint_writer_assigned=false,save_reopen_verified=true,native_b_isolated_from_legacy_b=nativeBOnly,other_changed_inventory_entries=changed,customer_revision_created=false,mechanical_group_complete=false});
            tr.Commit();reopened.DxfOut(Path.GetFullPath("relationship-challenge.dxf"),16,DwgVersion.AC1032);
        }
        finally {HostApplicationServices.WorkingDatabase=previous;}
    }
    static string RepairInputHash()
    {
        using var stream=new FileStream("input.dwg",FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(stream)).ToLowerInvariant();
    }
    [CommandMethod("MECHANICALREPAIRRELATIONSHIPS")]
    public void RepairDimensionRelationships()
    {
        try {RepairDimensionRelationshipsChecked();}
        catch(System.Exception e) {Write("relationship-repair-error.json",new {type=e.GetType().FullName,message=e.Message,stack=e.StackTrace});}
    }

    static void RepairDimensionRelationshipsChecked()
    {
        using var input=JsonDocument.Parse(File.ReadAllBytes("relationship-repair.json"));var cfg=input.RootElement;
        Require(RepairInputHash()==S(cfg,"source_sha256"),"Relationship repair source hash mismatch");
        var document=CoreApplication.DocumentManager.MdiActiveDocument;var db=document.Database;var editor=document.Editor;
        Require(Path.GetFullPath(db.Filename)==Path.GetFullPath("input.dwg"),"Relationship repair requires private input document");
        var root=S(cfg,"polyline_handle");var dims=cfg.GetProperty("dimension_handles").EnumerateArray().Select(e=>e.GetString()!).ToHashSet();
        var repairs=cfg.GetProperty("repairs").EnumerateArray().ToArray();
        bool control=cfg.TryGetProperty("control_only",out var controlJson) && controlJson.GetBoolean();
        bool nativeHeads=cfg.TryGetProperty("repair_native_heads",out var headsJson) && headsJson.GetBoolean();
        bool migrateNative=cfg.TryGetProperty("migrate_native_to_dimassoc",out var migrateJson) && migrateJson.GetBoolean();
        bool restoreNativeB=cfg.TryGetProperty("restore_native_b",out var restoreJson) && restoreJson.GetBoolean();
        Require(!nativeHeads && !migrateNative && !restoreNativeB,"Native head mutation disabled: no validated save/reopen adapter yet");
        Require(!migrateNative || nativeHeads,"Native migration requires explicit native-head repair mode");
        Require(dims.Count==6 && repairs.Length==2 && repairs.Select(r=>S(r,"dimension_handle")).Distinct().Count()==2,"Relationship repair needs bounded two-DIM proposal");
        Dictionary<string,string> before;Dictionary<string,ProbeDimension> beforeDims;HashSet<string> beforeVisuals;
        using(var tr=db.TransactionManager.StartTransaction())
        {
            var poly=tr.GetObject(Id(db,root),OpenMode.ForRead) as Polyline;
            Require(poly!=null && poly.Closed && poly.NumberOfVertices==8 && poly.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-8,1e-8)) && poly.ExtensionDictionary.IsNull,"Unsupported repair source profile");
            foreach(var repair in repairs)
            {
                var handle=S(repair,"dimension_handle");Require(dims.Contains(handle),"Repair outside selected group");
                var dim=(RotatedDimension)tr.GetObject(Id(db,handle),OpenMode.ForRead);
                Require(dim.OwnerId==poly!.OwnerId,"Repair DIM owner mismatch");
                if(nativeHeads)
                {
                    Require(dim.ExtensionDictionary.IsNull,"Native head repair requires original native DIM without DIMASSOC");
                    var dependency=(AssocDependency)tr.GetObject(Id(db,S(repair,"dimension_dependency")),OpenMode.ForRead);
                    var action=(AssocAction)tr.GetObject(Id(db,S(repair,"action_handle")),OpenMode.ForRead);
                    var geometry=(AssocGeomDependency)tr.GetObject(Id(db,S(repair,"geometry_dependency")),OpenMode.ForRead);
                    Require(dim.GetPersistentReactorIds().Cast<ObjectId>().ToHashSet().SetEquals(new[]{dependency.ObjectId}) && dependency.DependentOnObject==dim.ObjectId
                        && dependency.OwningAction==action.ObjectId && geometry.OwningAction==action.ObjectId && geometry.DependentOnObject==poly.ObjectId
                        && action.GetDependencies(true,true).Cast<ObjectId>().ToHashSet().SetEquals(new[]{dependency.ObjectId,geometry.ObjectId}),"Native head repair topology mismatch");
                    Require(geometry.SubentityType==(uint)SubentityType.Vertex && !geometry.IsCachingSubentityGeometry,"Native head repair needs live vertex B reference");
                    var vertices=((System.Collections.IEnumerable)geometry.VertexSubentityGeometry).Cast<Point3d>().ToArray();
                    Require(vertices.Length==1 && vertices[0].DistanceTo(dim.XLine2Point)<1e-6 && vertices[0].DistanceTo(dim.XLine1Point)>1e-6,"Native B reference mismatch");
                }
                else
                {
                Require(!dim.ExtensionDictionary.IsNull,"Repair DIM dictionary missing");
                var dictionary=(DBDictionary)tr.GetObject(dim.ExtensionDictionary,OpenMode.ForRead);
                Require(ProbeDictionaryKeys(dictionary).SetEquals(new[]{"ACAD_DIMASSOC"}),"Unsupported repair DIM dictionary");
                var assoc=dictionary.GetAt("ACAD_DIMASSOC");
                Require(assoc.Handle.ToString()==S(repair,"association_ref") && tr.GetObject(assoc,OpenMode.ForRead).GetRXClass().Name=="AcDbDimAssoc"
                    && dim.GetPersistentReactorIds().Cast<ObjectId>().ToHashSet().SetEquals(new[]{assoc}) && poly.GetPersistentReactorIds().Contains(assoc),"Repair source association mismatch");
                }
                for(int i=0;i<2;i++)
                {
                    var index=repair.GetProperty(i==0?"a_vertex":"b_vertex").GetInt32();Require(index>=0 && index<8,"Invalid repair vertex");
                    var target=StretchPoint(repair.GetProperty(i==0?"a":"b"));
                    Require(poly.GetPoint3dAt(index).DistanceTo(target)<1e-6 && (i==0?dim.XLine1Point:dim.XLine2Point).DistanceTo(target)<1e-6,"Repair endpoint not at proposed source vertex");
                }
            }
            before=CenterState(db,tr);beforeVisuals=ProbeVisuals(db,tr,dims);
            var visualBlocks=dims.Select(h=>((Dimension)tr.GetObject(Id(db,h),OpenMode.ForRead)).DimBlockId).Where(id=>!id.IsNull).Select(id=>id.Handle.ToString()).ToHashSet();
            foreach(var entry in before.Where(p=>!dims.Contains(p.Key)))
            {
                using var row=JsonDocument.Parse(entry.Value);
                foreach(var key in new[]{"dimension_block_handle","block_handle"})
                    if(row.RootElement.TryGetProperty(key,out var value) && value.ValueKind==JsonValueKind.String)
                        Require(!visualBlocks.Contains(value.GetString()!),"Repair DIM visual block has users outside group");
            }
            beforeDims=dims.ToDictionary(h=>h,h=>ProbeDim((RotatedDimension)tr.GetObject(Id(db,h),OpenMode.ForRead)));tr.Commit();
        }
        using var originalView=editor.GetCurrentView();
        using(var sourceSelection=SelectionSet.FromObjectIds(new[]{Id(db,root)}))
            editor.Command("_.ZOOM","_Object",sourceSelection,"");
        editor.Command("_.ZOOM","0.8x");editor.Regen();
        int originalDimAssoc=db.DimAssoc;
        if(migrateNative)db.DimAssoc=2;
        foreach(var repair in control?Array.Empty<JsonElement>():repairs)
        {
            var handle=S(repair,"dimension_handle");var a=StretchPoint(repair.GetProperty("a"));var b=StretchPoint(repair.GetProperty("b"));
            Write("relationship-repair-stage.json",new {dimension_handle=handle,stage="before_dimreassociate"});
            using var selection=SelectionSet.FromObjectIds(new[]{Id(db,handle)});
            var inverse=editor.CurrentUserCoordinateSystem.Inverse();
            if(migrateNative)
            {
                editor.Command("_.DIMDISASSOCIATE",selection,"");
                using var detach=db.TransactionManager.StartTransaction();
                CheckProbeDim((RotatedDimension)detach.GetObject(Id(db,handle),OpenMode.ForRead),beforeDims[handle],new Vector3d(0,0,0));
                detach.Commit();
            }
            var temporarilyHidden=new List<ObjectId>();
            if(migrateNative)
            {
                using var tr=db.TransactionManager.StartTransaction();
                foreach(var h in dims)
                {
                    var dim=(Dimension)tr.GetObject(Id(db,h),OpenMode.ForWrite);
                    if(dim.Visible){dim.Visible=false;temporarilyHidden.Add(dim.ObjectId);}
                }
                tr.Commit();editor.Regen();
            }
            var pickA=a;
            var pickB=b;
            editor.Command("_.DIMREASSOCIATE",selection,"","_end",pickA.TransformBy(inverse),"_end",pickB.TransformBy(inverse));
            if(temporarilyHidden.Count>0)
            {
                using var tr=db.TransactionManager.StartTransaction();foreach(var id in temporarilyHidden)((Entity)tr.GetObject(id,OpenMode.ForWrite)).Visible=true;tr.Commit();editor.Regen();
            }
            Write("relationship-repair-stage.json",new {dimension_handle=handle,stage="after_dimreassociate"});
        }
        editor.SetCurrentView(originalView);
        if(migrateNative)db.DimAssoc=originalDimAssoc;
        if(restoreNativeB)
        {
            Require(migrateNative && nativeHeads,"Native B restoration requires bounded migration preflight");
            using var tr=db.TransactionManager.StartTransaction();
            foreach(var value in cfg.GetProperty("native_restore_handles").EnumerateArray())
            {
                var id=Id(db,value.GetString()!);if(id.IsErased)tr.GetObject(id,OpenMode.ForWrite,true).Erase(false);
            }
            tr.Commit();
        }
        using(var tr=db.TransactionManager.StartTransaction())
        {
            if(nativeHeads)
                Write("relationship-native-head-state.json",new {migrate_native_to_dimassoc=migrateNative,original_ids=repairs.Select(r=>new {dimension_handle=S(r,"dimension_handle"),action_erased=Id(db,S(r,"action_handle")).IsErased,geometry_dependency_erased=Id(db,S(r,"geometry_dependency")).IsErased,dimension_dependency_erased=Id(db,S(r,"dimension_dependency")).IsErased}).ToArray()});
            foreach(var handle in dims)CheckProbeDim((RotatedDimension)tr.GetObject(Id(db,handle),OpenMode.ForRead),beforeDims[handle],new Vector3d(0,0,0));
            tr.Commit();
        }
        db.SaveAs(Path.GetFullPath("relationship-repair.dwg"),DwgVersion.AC1032);
        using var reopened=new Database(false,true);reopened.ReadDwgFile(Path.GetFullPath("relationship-repair.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);reopened.CloseInput(true);
        var previous=HostApplicationServices.WorkingDatabase;HostApplicationServices.WorkingDatabase=reopened;
        try
        {
            using var tr=reopened.TransactionManager.StartTransaction();
            foreach(var handle in dims)CheckProbeDim((RotatedDimension)tr.GetObject(Id(reopened,handle),OpenMode.ForRead),beforeDims[handle],new Vector3d(0,0,0));
            if(nativeHeads)
                foreach(var repair in repairs)
                {
                    if(migrateNative && !restoreNativeB)
                    {
                        Require(RepairObjectRemoved(reopened,S(repair,"action_handle")) && RepairObjectRemoved(reopened,S(repair,"geometry_dependency")) && RepairObjectRemoved(reopened,S(repair,"dimension_dependency")),"Native migration left original action/dependencies live");
                        var migrated=(RotatedDimension)tr.GetObject(Id(reopened,S(repair,"dimension_handle")),OpenMode.ForRead);
                        Require(!migrated.ExtensionDictionary.IsNull,"Migrated DIM has no association dictionary");
                        var dictionary=(DBDictionary)tr.GetObject(migrated.ExtensionDictionary,OpenMode.ForRead);
                        Require(ProbeDictionaryKeys(dictionary).SetEquals(new[]{"ACAD_DIMASSOC"}),"Unexpected migrated DIM dictionary");
                        Require(migrated.GetPersistentReactorIds().Cast<ObjectId>().ToHashSet().SetEquals(new[]{dictionary.GetAt("ACAD_DIMASSOC")}),"Migrated DIM has dangling native reactor");
                        continue;
                    }
                    var action=(AssocAction)tr.GetObject(Id(reopened,S(repair,"action_handle")),OpenMode.ForRead);
                    var geometry=(AssocGeomDependency)tr.GetObject(Id(reopened,S(repair,"geometry_dependency")),OpenMode.ForRead);
                    var dependency=(AssocDependency)tr.GetObject(Id(reopened,S(repair,"dimension_dependency")),OpenMode.ForRead);
                    Require(!action.IsErased && geometry.DependentOnObject==Id(reopened,root) && dependency.DependentOnObject==Id(reopened,S(repair,"dimension_handle"))
                        && geometry.OwningAction==action.ObjectId && dependency.OwningAction==action.ObjectId,"Native head repair lost original action/dependency");
                    Require(action.GetDependencies(true,true).Cast<ObjectId>().ToHashSet().SetEquals(new[]{dependency.ObjectId,geometry.ObjectId}),"Native head repair changed original action dependencies");
                    Require(geometry.SubentityType==(uint)SubentityType.Vertex && !geometry.IsCachingSubentityGeometry,"Repaired native B no longer has live vertex reference");
                    var vertices=((System.Collections.IEnumerable)geometry.VertexSubentityGeometry).Cast<Point3d>().ToArray();
                    Require(vertices.Length==1 && vertices[0].DistanceTo(StretchPoint(repair.GetProperty("b")))<1e-6,"Repair rebound native B to a different vertex");
                }
            // Export diagnostic DXF even when the proposal is rejected below.
            // This file is not a validated result or customer revision.
            reopened.DxfOut(Path.GetFullPath("relationship-repair-diagnostic.dxf"),16,DwgVersion.AC1032);
            var after=CenterState(reopened,tr);var afterVisuals=ProbeVisuals(reopened,tr,dims);var selected=dims.Append(root).ToHashSet();
            Require(SameNativeSnapshot(before[root],after[root],new HashSet<string>{"persistent_reactor_handles"}),"Repair changed source geometry/properties");
            var beforeRest=before.Where(p=>!selected.Contains(p.Key) && !beforeVisuals.Contains(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);
            var afterRest=after.Where(p=>!selected.Contains(p.Key) && !afterVisuals.Contains(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);
            Write("relationship-repair-outside-diff.json",new {removed=beforeRest.Keys.Except(afterRest.Keys).ToArray(),added=afterRest.Keys.Except(beforeRest.Keys).ToArray(),changed=beforeRest.Keys.Intersect(afterRest.Keys).Where(h=>!SameNativeSnapshot(beforeRest[h],afterRest[h])).Select(h=>new {handle=h,before=JsonSerializer.Deserialize<JsonElement>(beforeRest[h]),after=JsonSerializer.Deserialize<JsonElement>(afterRest[h])}).ToArray()});
            bool outsideEqual=beforeRest.Keys.ToHashSet().SetEquals(afterRest.Keys) && beforeRest.All(p=>SameNativeSnapshot(p.Value,afterRest[p.Key]));
            if(!outsideEqual && cfg.TryGetProperty("control_outside_diff",out var controlDiff))
            {
                Require(controlDiff.GetProperty("removed").GetArrayLength()==0 && controlDiff.GetProperty("added").GetArrayLength()==0,"Control changed entity set");
                var changes=controlDiff.GetProperty("changed").EnumerateArray().ToDictionary(e=>S(e,"handle"),e=>e);
                Require(beforeRest.Keys.ToHashSet().SetEquals(afterRest.Keys),"Repair changed entity set");
                foreach(var entry in beforeRest)
                {
                    if(changes.TryGetValue(entry.Key,out var change))
                        Require(SameNativeSnapshot(entry.Value,change.GetProperty("before").GetRawText()) && SameNativeSnapshot(afterRest[entry.Key],change.GetProperty("after").GetRawText()),"Repair differs from no-op control: "+entry.Key);
                    else Require(SameNativeSnapshot(entry.Value,afterRest[entry.Key]),"Repair changed object absent from no-op control: "+entry.Key);
                }
                outsideEqual=true;
            }
            Require(control || outsideEqual,"Repair changed objects outside group");
            Write("relationship-repair-dim-properties.json",dims.Select(handle=>new {handle,before=JsonSerializer.Deserialize<JsonElement>(before[handle]),after=JsonSerializer.Deserialize<JsonElement>(after[handle])}).ToArray());
            foreach(var handle in dims)
            {
                var ignored=new HashSet<string>{"persistent_reactor_handles","extension_dictionary_handle","dimension_block_handle"};
                // The new dictionary is already required to contain exactly ACAD_DIMASSOC.
                if(migrateNative && repairs.Any(r=>S(r,"dimension_handle")==handle))ignored.Add("extension_records");
                Require(SameNativeSnapshot(before[handle],after[handle],ignored),"Repair changed DIM properties: "+handle);
            }
            Write("relationship-repair-native.json",new {status=control?"native_noop_control_saved_reopened":"native_reassociation_saved_reopened",control_only=control,native_action_storage_migrated=migrateNative && !restoreNativeB,native_b_restored=restoreNativeB,outside_matches_control=outsideEqual,source_sha256=RepairInputHash(),output_sha256=Hash("relationship-repair.dwg"),polyline_handle=root,
                dimension_handles=dims.OrderBy(h=>h).ToArray(),unselected_inventory_entries_verified=beforeRest.Count,native_dependencies=NativeDependencies(reopened,tr,selected),
                customer_revision_created=false,mechanical_group_complete=false,policy="Candidate repair only; independent DIMASSOC/source binding verification required."});
            tr.Commit();reopened.DxfOut(Path.GetFullPath("relationship-repair.dxf"),16,DwgVersion.AC1032);
        }
        finally {HostApplicationServices.WorkingDatabase=previous;}
    }
}

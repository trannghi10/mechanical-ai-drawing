using System.Runtime.InteropServices;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

namespace MechanicalCad;

public partial class Commands
{
    [UnmanagedFunctionPointer(CallingConvention.Cdecl,CharSet=CharSet.Unicode)]
    delegate int DisableSecondPointReference(IntPtr database,[MarshalAs(UnmanagedType.LPWStr)] string dimension);
    [CommandMethod("MECHANICALPOINTREFCUSTOMERPROBE")]
    public void NativePointReferenceCustomerProbe()
    {
        try {NativePointReferenceCustomerProbeChecked();}
        catch(System.Exception e) {Write("native-point-reference-error.json",new {type=e.GetType().FullName,message=e.Message,stack=e.StackTrace});}
    }
    static void NativePointReferenceCustomerProbeChecked()
    {
        using var config=JsonDocument.Parse(File.ReadAllBytes("native-point-reference.json"));
        string sourceHash=S(config.RootElement,"source_sha256");
        Require(Hash("input.cad")==sourceHash,"Native reference probe source mismatch");
        var scope=config.RootElement.GetProperty("scope");string root=S(scope,"polyline_handle");
        Require(scope.GetProperty("schema_version").GetInt32()==1,"Unsupported native reference scope");
        var targets=scope.GetProperty("repairs").EnumerateArray().Select(t=>(dim:S(t,"dimension_handle"),a:t.GetProperty("a_vertex").GetInt32(),b:t.GetProperty("b_vertex").GetInt32(),
            action:S(t,"action_handle"),body:S(t,"body_handle"),geom:S(t,"geometry_dependency"),dependency:S(t,"dimension_dependency"),pointA:StretchPoint(t.GetProperty("a")),pointB:StretchPoint(t.GetProperty("b")))).ToArray();
        Require(targets.Length==2 && targets.Select(t=>t.dim).Distinct().Count()==2 && targets.All(t=>t.a>=0 && t.a<8 && t.b>=0 && t.b<8 && t.a!=t.b),"Invalid native reference targets");
        var trees=new Dictionary<string,string>();var points=new Dictionary<string,(Point3d a,Point3d b)>();
        void Verify(Database db)
        {
            using var tr=db.TransactionManager.StartTransaction();
            var poly=(Polyline)tr.GetObject(Id(db,root),OpenMode.ForRead);
            Require(poly.NumberOfVertices==8 && poly.Closed && poly.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-8,1e-8)) && poly.ExtensionDictionary.IsNull,"Unsupported native reference probe polyline");
            foreach(var target in targets)
            {
                var dim=(RotatedDimension)tr.GetObject(Id(db,target.dim),OpenMode.ForRead);
                var dep=(AssocDependency)tr.GetObject(Id(db,target.dependency),OpenMode.ForRead);
                var geom=(AssocGeomDependency)tr.GetObject(Id(db,target.geom),OpenMode.ForRead);
                var action=(AssocAction)tr.GetObject(Id(db,target.action),OpenMode.ForRead);
                Require(dim.OwnerId==poly.OwnerId && action.ActionBody==Id(db,target.body) && tr.GetObject(action.ActionBody,OpenMode.ForRead).GetRXClass().Name=="AcDbAssocRotatedDimActionBody","Native DIM/body scope mismatch");
                Require(poly.GetPoint3dAt(target.a).DistanceTo(target.pointA)<1e-6 && poly.GetPoint3dAt(target.b).DistanceTo(target.pointB)<1e-6,"Native scope source coordinates changed");
                Require(dep.DependentOnObject==dim.ObjectId && dep.OwningAction==action.ObjectId && geom.OwningAction==action.ObjectId && geom.DependentOnObject==poly.ObjectId,"Native B dependency ownership changed");
                Require(dim.GetPersistentReactorIds().Cast<ObjectId>().Contains(dep.ObjectId),"Native B DIM reactor removed");
                Require(poly.GetPersistentReactorIds().Cast<ObjectId>().Contains(geom.ObjectId),"Native B geometry reactor removed");
                Require(action.GetDependencies(true,true).Cast<ObjectId>().ToHashSet().SetEquals(new[]{dep.ObjectId,geom.ObjectId}),"Native B action dependencies changed");
                var vertices=((System.Collections.IEnumerable)geom.VertexSubentityGeometry).Cast<Point3d>().ToArray();
                Require(vertices.Length==1 && vertices[0].DistanceTo(poly.GetPoint3dAt(target.b))<1e-6 && dim.XLine2Point.DistanceTo(vertices[0])<1e-6,"Native B vertex changed");
                string tree=JsonSerializer.Serialize(ProbeActionParameters(db,tr,target.action));
                if(trees.TryGetValue(target.dim,out string? old))
                {
                    Require(old==tree,"Native B parameter tree changed");
                    Require(dim.XLine1Point.DistanceTo(points[target.dim].a)<1e-6 && dim.XLine2Point.DistanceTo(points[target.dim].b)<1e-6,"Probe changed DIM measurement points");
                }
                else
                {
                    Require(dim.ExtensionDictionary.IsNull && dim.XLine1Point.DistanceTo(poly.GetPoint3dAt(target.a))<1e-6,"Probe source already associated or A candidate changed");
                    trees[target.dim]=tree;points[target.dim]=(dim.XLine1Point,dim.XLine2Point);
                }
            }
            tr.Commit();
        }
        var library=NativeLibrary.Load(Path.GetFullPath("MechanicalPointReference.dll"));
        var previous=HostApplicationServices.WorkingDatabase;
        try
        {
            var add=Marshal.GetDelegateForFunctionPointer<AddPointReferences>(NativeLibrary.GetExport(library,"MechanicalAddPointReferences"));
            using(var db=new Database(false,true))
            {
                db.ReadDwgFile(Path.GetFullPath("input.cad"),FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
                HostApplicationServices.WorkingDatabase=db;Verify(db);
                using(var tr=db.TransactionManager.StartTransaction()){Write("native-point-reference-before.json",Inventory(db,tr));tr.Commit();}
                foreach(var target in targets)
                {
                    int status=add(db.UnmanagedObject,target.dim,root,target.a,target.b,out int stage);
                    Require(status==0 && stage==5,"Native point repair failed for "+target.dim+": status="+status+", stage="+stage);
                    Verify(db);
                }
                db.SaveAs(Path.GetFullPath("native-point-reference-repair.dwg"),DwgVersion.AC1032);
            }
            using(var reopened=new Database(false,true))
            {
                reopened.ReadDwgFile(Path.GetFullPath("native-point-reference-repair.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);reopened.CloseInput(true);
                HostApplicationServices.WorkingDatabase=reopened;Verify(reopened);
                using(var tr=reopened.TransactionManager.StartTransaction()){Write("native-point-reference-after.json",Inventory(reopened,tr));tr.Commit();}
                reopened.DxfOut(Path.GetFullPath("native-point-reference-repair.dxf"),16,DwgVersion.AC1032);
            }
            Write("native-point-reference-customer.json",new {status="native_b_preserved_saved_reopened_pending_independent_validation",source_sha256=sourceHash,
                output_sha256=Hash("native-point-reference-repair.dwg"),native_b_parameters_preserved=true,customer_revision_created=false,design_intent_confirmed=false});
        }
        finally {HostApplicationServices.WorkingDatabase=previous;NativeLibrary.Free(library);}
    }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl, CharSet=CharSet.Unicode)]
    delegate int AddPointReferences(IntPtr database, [MarshalAs(UnmanagedType.LPWStr)] string dimension,
        [MarshalAs(UnmanagedType.LPWStr)] string polyline, int a, int b, out int stage);

    // Synthetic-only, never invoked by customer revision APIs.
    [CommandMethod("MECHANICALPOINTREFSMOKE")]
    public void NativePointReferenceSmoke()
    {
        try {NativePointReferenceSmokeChecked();}
        catch(System.Exception e) {Write("native-point-reference-error.json",new {type=e.GetType().FullName,message=e.Message,stack=e.StackTrace});}
    }
    static void NativePointReferenceSmokeChecked()
    {
        string libraryPath=Path.GetFullPath("MechanicalPointReference.dll");
        var library=NativeLibrary.Load(libraryPath);
        try
        {
            var add=Marshal.GetDelegateForFunctionPointer<AddPointReferences>(NativeLibrary.GetExport(library,"MechanicalAddPointReferences"));
            string polyHandle,dimHandle;
            using(var db=new Database(true,true))
            {
                var previous=HostApplicationServices.WorkingDatabase;
                HostApplicationServices.WorkingDatabase=db;
                try
                {
                using(var tr=db.TransactionManager.StartTransaction())
                {
                    var model=(BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db),OpenMode.ForWrite);
                    var poly=new Polyline();
                    poly.AddVertexAt(0,new Point2d(0,0),0,0,0);poly.AddVertexAt(1,new Point2d(100,0),0,0,0);
                    poly.AddVertexAt(2,new Point2d(100,50),0,0,0);poly.AddVertexAt(3,new Point2d(0,50),0,0,0);poly.Closed=true;
                    model.AppendEntity(poly);tr.AddNewlyCreatedDBObject(poly,true);polyHandle=poly.Handle.ToString();
                    var dim=new RotatedDimension(0,new Point3d(0,0,0),new Point3d(100,0,0),new Point3d(0,-15,0),"<>",db.Dimstyle);
                    model.AppendEntity(dim);tr.AddNewlyCreatedDBObject(dim,true);dim.RecomputeDimensionBlock(true);dimHandle=dim.Handle.ToString();tr.Commit();
                }
                int status=add(db.UnmanagedObject,dimHandle,polyHandle,0,1,out int stage);
                Require(status==0 && stage==5,"ObjectARX point-reference smoke failed: status="+status+", stage="+stage);
                db.SaveAs(Path.GetFullPath("native-point-reference-smoke.dwg"),DwgVersion.AC1032);
                }
                finally {HostApplicationServices.WorkingDatabase=previous;}
            }
            using(var reopened=new Database(false,true))
            {
                reopened.ReadDwgFile(Path.GetFullPath("native-point-reference-smoke.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);
                reopened.CloseInput(true);
                using(var tr=reopened.TransactionManager.StartTransaction())
                {
                    var dim=(RotatedDimension)tr.GetObject(Id(reopened,dimHandle),OpenMode.ForRead);
                    Require(dim.XLine1Point.DistanceTo(Point3d.Origin)<1e-8 && dim.XLine2Point.DistanceTo(new Point3d(100,0,0))<1e-8,"Smoke endpoints changed after reopen");
                    Require(!dim.ExtensionDictionary.IsNull,"Smoke DIMASSOC dictionary missing after reopen");
                    var ext=(DBDictionary)tr.GetObject(dim.ExtensionDictionary,OpenMode.ForRead);
                    Require(ext.Contains("ACAD_DIMASSOC"),"Smoke point association missing after reopen");
                    Require(tr.GetObject(ext.GetAt("ACAD_DIMASSOC"),OpenMode.ForRead).GetRXClass().Name=="AcDbDimAssoc","Unexpected smoke association type");
                    tr.Commit();
                }
                reopened.DxfOut(Path.GetFullPath("native-point-reference-smoke.dxf"),16,DwgVersion.AC1032);
            }
            Write("native-point-reference-smoke.json",new {status="saved_reopened_pending_independent_binding_validation",polyline_handle=polyHandle,dimension_handle=dimHandle,customer_revision_created=false,native_b_preservation_tested=false});
        }
        finally {NativeLibrary.Free(library);}
    }
}

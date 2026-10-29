using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

namespace MechanicalCad;

public partial class Commands
{

    static void RunRectangleContract(JsonElement contract,JsonElement[] ops,HashSet<string> scopes)
    {
        Require(S(contract,"mode")=="edit" && ops.Length==1 && S(contract,"input_name").EndsWith(".dwg",StringComparison.OrdinalIgnoreCase),"Rectangle requires isolated DWG edit");
        var op=ops[0];var poly=S(op,"handle");var dim=S(op,"dimension_handle");
        Require(S(op,"expected_type")=="LWPOLYLINE" && PathOf(op).Length==1 && scopes.SetEquals(new[]{poly,dim}),"Rectangle selection scope mismatch");
        Write("point-request.json",new {polyline_handle=poly,dimension_handle=dim});
        new Commands().AicadExportPoints();
        Require(!File.Exists("aicad-error.json") && File.Exists("point-binding.json"),"Rectangle native export failed");
        using var bindingJson=JsonDocument.Parse(File.ReadAllBytes("point-binding.json"));var binding=bindingJson.RootElement;
        Require(S(binding,"owner_handle")==S(op,"owner_handle") && S(binding,"association_handle")==S(op,"association_handle"),"Rectangle contract owner/association mismatch");
        using var fromJson=JsonDocument.Parse(S(op,"before"));using var toJson=JsonDocument.Parse(S(op,"after"));
        var from=fromJson.RootElement.EnumerateArray().ToArray();var to=toJson.RootElement.EnumerateArray().Select(p=>p.EnumerateArray().Select(v=>v.GetDouble()).ToArray()).ToArray();
        var vertices=binding.GetProperty("vertices").EnumerateArray().ToArray();Require(from.Length==4 && to.Length==4,"Rectangle needs four bound vertices");
        for(int i=0;i<4;i++)Require(SameNativeSnapshot(from[i].GetRawText(),vertices[i].GetProperty("xyz").GetRawText()),"Rectangle source vertices changed");
        Require(to.All(p=>p.Length==3 && p.All(double.IsFinite)),"Invalid target vertices");
        var width=to[1][0]-to[0][0];
        Write("point-solution.json",new {source_sha256=Hash("input.cad"),binding_sha256=Hash("point-binding.json"),polyline_handle=poly,dimension_handle=dim,target_width_mm=width,points=to});
        AicadApplyPointsChecked();
        Directory.CreateDirectory("out");File.Copy("point-result.dwg","out/modified.dwg");File.Copy("point-result.dxf","out/roundtrip.dxf");
        using var effects=JsonDocument.Parse(File.ReadAllBytes("point-receipt.json"));
        using(var db=new Database(false,true))
        {
            db.ReadDwgFile(Path.GetFullPath("out/modified.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
            var previous=HostApplicationServices.WorkingDatabase;HostApplicationServices.WorkingDatabase=db;
            try
            {
                using var tr=db.TransactionManager.StartTransaction();var inventory=(Dictionary<string,object>)Inventory(db,tr,false,new HashSet<string>{poly,dim});
                inventory["rectangle_stretch_effects"]=effects.RootElement.Clone();Write("out/inventory.json",inventory);tr.Commit();
            }
            finally{HostApplicationServices.WorkingDatabase=previous;}
        }
        var hashes=new Dictionary<string,string>();foreach(var name in new[]{"modified.dwg","roundtrip.dxf","inventory.json"})hashes[name]=Hash("out/"+name);
        Write("out/receipt.json",new {schema_version=1,status="validated",mode="edit",source_sha256=Hash("input.cad"),commands_sha256=Hash("commands.json"),applied_operations=1,hashes,complete_product_backup=false});
        System.IO.Compression.ZipFile.CreateFromDirectory("out",Path.GetFullPath("result.zip"));Stage("complete");
    }

    [CommandMethod("AICAD_BUILD_FIXTURE",CommandFlags.Session)]
    public void AicadBuildFixture()
    {
        try
        {
            Require(!File.Exists("input.cad"),"Fixture source already exists");
            using var db=new Database(false,true);db.DxfIn(Path.GetFullPath("fixture.dxf"),"fixture-import.log");
            Require(db.Insunits==UnitsValue.Millimeters,"Fixture must use millimeters");
            db.SaveAs(Path.GetFullPath("input.cad"),DwgVersion.AC1032);
        }
        catch(System.Exception error){Write("aicad-error.json",new {message=error.Message,stack=error.StackTrace});}
    }

    static (Polyline,RotatedDimension,string) AicadGroup(Database db,Transaction tr,JsonElement cfg)
    {
        Require(db.Insunits==UnitsValue.Millimeters,"Point binding requires millimeters");
        var poly=tr.GetObject(Id(db,S(cfg,"polyline_handle")),OpenMode.ForRead) as Polyline;
        var dim=tr.GetObject(Id(db,S(cfg,"dimension_handle")),OpenMode.ForWrite) as RotatedDimension;
        Require(poly!=null && dim!=null,"Expected LWPOLYLINE and rotated DIM");
        Require(poly!.Closed && poly.NumberOfVertices==4 && poly.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-10,1e-10)) && poly.ExtensionDictionary.IsNull,"Expected plain closed four-vertex XY polyline");
        Require(Enumerable.Range(0,4).All(i=>poly.GetBulgeAt(i)==0 && poly.GetStartWidthAt(i)==0 && poly.GetEndWidthAt(i)==0),"Bulge or segment width unsupported");
        Require(tr.GetObject(poly.OwnerId,OpenMode.ForRead) is BlockTableRecord owner && owner.IsLayout && dim!.OwnerId==poly.OwnerId,"Group must share a layout");
        Require(!dim!.ExtensionDictionary.IsNull,"DIM has no association dictionary");
        var dict=(DBDictionary)tr.GetObject(dim.ExtensionDictionary,OpenMode.ForRead);
        Require(ProbeDictionaryKeys(dict).SetEquals(new[]{"ACAD_DIMASSOC"}),"Unsupported DIM dictionary");
        var assoc=dict.GetAt("ACAD_DIMASSOC");
        Require(tr.GetObject(assoc,OpenMode.ForRead).GetRXClass().Name=="AcDbDimAssoc" && tr.GetObject(assoc,OpenMode.ForRead).OwnerId==dict.ObjectId,"DIMASSOC ownership mismatch");
        Require(dim.GetPersistentReactorIds().Cast<ObjectId>().ToHashSet().SetEquals(new[]{assoc}) && poly.GetPersistentReactorIds().Cast<ObjectId>().ToHashSet().SetEquals(new[]{assoc}),"Unexpected source reactors");
        Require(Math.Abs(dim.Rotation)<1e-10 && dim.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-10,1e-10)) && (string.IsNullOrEmpty(dim.DimensionText) || dim.DimensionText=="<>"),"Expected unoverridden horizontal DIM");
        var pts=Enumerable.Range(0,4).Select(poly.GetPoint3dAt).ToArray();AicadRectangle(pts);
        Require(dim.XLine1Point.DistanceTo(pts[0])<1e-7 && dim.XLine2Point.DistanceTo(pts[1])<1e-7 && Math.Abs(dim.Measurement-(pts[1].X-pts[0].X))<1e-7,"DIM does not measure vertices 0 and 1");
        return(poly,dim,assoc.Handle.ToString());
    }

    static void AicadRectangle(Point3d[] p)
    {
        Require(p.Length==4 && p.All(v=>double.IsFinite(v.X)&&double.IsFinite(v.Y)&&double.IsFinite(v.Z)),"Invalid rectangle points");
        Require(p[1].X-p[0].X>1e-6 && p[3].Y-p[0].Y>1e-6 && Math.Abs(p[0].Y-p[1].Y)<1e-7 && Math.Abs(p[2].Y-p[3].Y)<1e-7 && Math.Abs(p[0].X-p[3].X)<1e-7 && Math.Abs(p[1].X-p[2].X)<1e-7 && p.All(v=>Math.Abs(v.Z-p[0].Z)<1e-7),"Expected positively oriented axis-aligned rectangle");
    }

    [CommandMethod("AICAD_EXPORT_POINTS",CommandFlags.Session)]
    public void AicadExportPoints()
    {
        try
        {
            using var cfg=JsonDocument.Parse(File.ReadAllBytes("point-request.json"));
            using var db=new Database(false,true);db.ReadDwgFile(Path.GetFullPath("input.cad"),FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
            var previous=HostApplicationServices.WorkingDatabase;HostApplicationServices.WorkingDatabase=db;
            try
            {
                using var tr=db.TransactionManager.StartTransaction();var (poly,dim,assoc)=AicadGroup(db,tr,cfg.RootElement);
                Write("point-binding.json",new {schema_version=1,units="mm",source_sha256=Hash("input.cad"),polyline_handle=poly.Handle.ToString(),dimension_handle=dim.Handle.ToString(),association_handle=assoc,owner_handle=poly.OwnerId.Handle.ToString(),
                    vertices=Enumerable.Range(0,4).Select(i=>new {index=i,point_id="v"+i,xyz=P(poly.GetPoint3dAt(i))}).ToArray(),
                    dimension=new {vertex_indices=new[]{0,1},measurement_mm=dim.Measurement,defpoint2=P(dim.XLine1Point),defpoint3=P(dim.XLine2Point)},
                    fixed_vertex_indices=new[]{0,3},moving_vertex_indices=new[]{1,2},intent="Explicit MVP intent: keep left edge, move right edge along +X",edit_authorization=false});
                tr.Commit();db.DxfOut(Path.GetFullPath("source-readback.dxf"),16,DwgVersion.AC1032);
            }
            finally {HostApplicationServices.WorkingDatabase=previous;}
        }
        catch(System.Exception error){Write("aicad-error.json",new {message=error.Message,stack=error.StackTrace});}
    }

    [CommandMethod("AICAD_APPLY_POINTS",CommandFlags.Session)]
    public void AicadApplyPoints()
    {
        try {AicadApplyPointsChecked();}
        catch(System.Exception error){Write("aicad-error.json",new {message=error.Message,stack=error.StackTrace});}
    }

    static void AicadApplyPointsChecked()
    {
        using var config=JsonDocument.Parse(File.ReadAllBytes("point-solution.json"));var cfg=config.RootElement;
        Require(Hash("input.cad")==S(cfg,"source_sha256") && Hash("point-binding.json")==S(cfg,"binding_sha256"),"Point solution source/binding hash mismatch");
        using var bound=JsonDocument.Parse(File.ReadAllBytes("point-binding.json"));var binding=bound.RootElement;
        Require(S(binding,"source_sha256")==Hash("input.cad") && S(binding,"polyline_handle")==S(cfg,"polyline_handle") && S(binding,"dimension_handle")==S(cfg,"dimension_handle"),"Point solution handle mismatch");
        Require(!File.Exists("point-result.dwg") && !File.Exists("point-candidate.dwg"),"Separate output already exists");
        var pts=cfg.GetProperty("points").EnumerateArray().Select(p=>{var a=p.EnumerateArray().Select(v=>v.GetDouble()).ToArray();Require(a.Length==3,"Expected XYZ point");return new Point3d(a[0],a[1],a[2]);}).ToArray();AicadRectangle(pts);
        double target=cfg.GetProperty("target_width_mm").GetDouble();Require(double.IsFinite(target) && Math.Abs(pts[1].X-pts[0].X-target)<1e-7,"Point solution target mismatch");
        using var db=new Database(false,true);db.ReadDwgFile(Path.GetFullPath("input.cad"),FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
        var previous=HostApplicationServices.WorkingDatabase;HostApplicationServices.WorkingDatabase=db;
        try
        {
            Dictionary<string,string> before;HashSet<string> beforeVisuals;string assoc;string style;Point3d line;Point3d[] old;
            using(var tr=db.TransactionManager.StartTransaction())
            {
                var (poly,dim,association)=AicadGroup(db,tr,cfg);assoc=association;style=dim.DimensionStyle.Handle.ToString();line=dim.DimLinePoint;
                old=Enumerable.Range(0,4).Select(poly.GetPoint3dAt).ToArray();
                var expected=binding.GetProperty("vertices").EnumerateArray().ToArray();Require(expected.Length==4,"Incomplete binding vertices");
                for(int i=0;i<4;i++){var a=expected[i].GetProperty("xyz").EnumerateArray().Select(v=>v.GetDouble()).ToArray();Require(expected[i].GetProperty("index").GetInt32()==i && old[i].DistanceTo(new Point3d(a[0],a[1],a[2]))<1e-7,"Stale vertex binding");}
                Require(assoc==S(binding,"association_handle") && poly.OwnerId.Handle.ToString()==S(binding,"owner_handle"),"Stale association or owner binding");
                Require(pts[0].DistanceTo(old[0])<1e-7 && pts[3].DistanceTo(old[3])<1e-7 && Math.Abs(pts[1].Y-old[1].Y)<1e-7 && Math.Abs(pts[2].Y-old[2].Y)<1e-7 && pts.All(p=>Math.Abs(p.Z-old[0].Z)<1e-7),"Point solution changed fixed edge or height");
                before=CenterState(db,tr);beforeVisuals=ProbeVisuals(db,tr,new[]{dim.Handle.ToString()});
                string visualBlock=dim.DimBlockId.Handle.ToString();
                foreach(var entry in before.Where(p=>p.Key!=dim.Handle.ToString()))
                {
                    using var row=JsonDocument.Parse(entry.Value);
                    Require(!(row.RootElement.TryGetProperty("dimension_block_handle",out var dimBlock)&&dimBlock.GetString()==visualBlock) && !(row.RootElement.TryGetProperty("block_handle",out var insertBlock)&&insertBlock.GetString()==visualBlock),"Rectangle DIM visual block has another user");
                }

                poly.UpgradeOpen();for(int i=0;i<4;i++)poly.SetPointAt(i,new Point2d(pts[i].X,pts[i].Y));
                if(!dim.IsWriteEnabled)dim.UpgradeOpen();dim.XLine1Point=pts[0];dim.XLine2Point=pts[1];dim.RecomputeDimensionBlock(true);
                Require(Math.Abs(dim.Measurement-target)<1e-7,"Updated DIM measurement mismatch");tr.Commit();
            }
            db.SaveAs(Path.GetFullPath("point-candidate.dwg"),DwgVersion.AC1032);
            using var reopened=new Database(false,true);reopened.ReadDwgFile(Path.GetFullPath("point-candidate.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);reopened.CloseInput(true);HostApplicationServices.WorkingDatabase=reopened;
            try
            {
                using var tr=reopened.TransactionManager.StartTransaction();var(poly,dim,association)=AicadGroup(reopened,tr,cfg);
                Require(association==assoc && Enumerable.Range(0,4).All(i=>poly.GetPoint3dAt(i).DistanceTo(pts[i])<1e-7),"Reopened geometry/binding mismatch");
                Write("point-dim-diagnostics.json",new {before_dimline=P(line),after_dimline=P(dim.DimLinePoint),before_style=style,after_style=dim.DimensionStyle.Handle.ToString(),measurement=dim.Measurement});
                Require(Math.Abs(dim.Measurement-target)<1e-7 && dim.DimensionStyle.Handle.ToString()==style && Math.Abs(dim.DimLinePoint.Y-line.Y)<1e-7 && Math.Abs(dim.DimLinePoint.Z-line.Z)<1e-7,"Reopened DIM mismatch");
                var after=CenterState(reopened,tr);var visuals=ProbeVisuals(reopened,tr,new[]{dim.Handle.ToString()});var selected=new HashSet<string>{poly.Handle.ToString(),dim.Handle.ToString()};
                var restBefore=before.Where(p=>!selected.Contains(p.Key)&&!beforeVisuals.Contains(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);
                var restAfter=after.Where(p=>!selected.Contains(p.Key)&&!visuals.Contains(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);
                Require(restBefore.Keys.ToHashSet().SetEquals(restAfter.Keys)&&restBefore.All(p=>SameNativeSnapshot(p.Value,restAfter[p.Key])),"Unselected geometry changed");
                tr.Commit();reopened.DxfOut(Path.GetFullPath("point-result.dxf"),16,DwgVersion.AC1032);
                File.Move("point-candidate.dwg","point-result.dwg");
                Write("point-receipt.json",new {status="native_point_stretch_reopened",source_sha256=Hash("input.cad"),output_sha256=Hash("point-result.dwg"),target_width_mm=target,polyline_handle=S(cfg,"polyline_handle"),dimension_handle=S(cfg,"dimension_handle"),association_handle=assoc,fixed_edge_verified=true,unselected_inventory_entries_verified=restBefore.Count,customer_revision_created=false});
            }
            finally{HostApplicationServices.WorkingDatabase=db;}
        }
        finally{HostApplicationServices.WorkingDatabase=previous;}
    }
}

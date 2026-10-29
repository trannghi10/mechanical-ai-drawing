using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace MechanicalCad;

public partial class Commands
{
    record CenterMove(string Circle, string Mark, string Action, string GeometryDependency,
        string MarkDependency, Point3d Center, Point3d MarkPosition, double Radius, Vector3d Delta);

    static Dictionary<string,string> CenterState(Database db,Transaction tr)
    {
        var entities=(List<Dictionary<string,object?>>)Inventory(db,tr)["entities"];
        foreach(var entity in entities)
            if(entity.TryGetValue("block",out var name) && name is string text && System.Text.RegularExpressions.Regex.IsMatch(text,@"^\*D[0-9]+$"))
                entity.Remove("block"); // DIM names may be renumbered; owner and BTR handles remain mandatory.
        return entities.ToDictionary(e=>(string)e["handle"]!,e=>JsonSerializer.Serialize(e));
    }

    static CenterMove ReadCenterMove(Database db,Transaction tr,JsonElement cfg)
    {
        var values=cfg.GetProperty("delta").EnumerateArray().Select(x=>x.GetDouble()).ToArray();
        Require(values.Length==3 && values.All(double.IsFinite) && Math.Abs(values[2])<1e-10,"Probe needs a finite planar translation");
        var delta=new Vector3d(values[0],values[1],values[2]);
        var circle=tr.GetObject(Id(db,S(cfg,"circle_handle")),OpenMode.ForRead) as Circle;Require(circle!=null,"Probe target must be CIRCLE");
        Require(tr.GetObject(circle!.OwnerId,OpenMode.ForRead) is BlockTableRecord layout && layout.IsLayout,"Probe only supports a layout circle");
        Require(circle.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-8,1e-8)) && circle.ExtensionDictionary.IsNull,"Probe circle must be plain XY geometry");
        var reactors=circle.GetPersistentReactorIds();Require(reactors.Count==1,"Probe requires one circle dependency");
        var dependency=tr.GetObject(reactors[0],OpenMode.ForRead) as AssocGeomDependency;
        Require(dependency!=null && dependency.DependentOnObject==circle.ObjectId,"Probe needs native geometric dependency");
        var action=(AssocAction)tr.GetObject(dependency!.OwningAction,OpenMode.ForRead);
        Require(tr.GetObject(action.ActionBody,OpenMode.ForRead).GetRXClass().Name=="AcDbCenterMarkActionBody","Probe only supports CenterMark action");
        var dependencies=action.GetDependencies(true,true).Cast<ObjectId>().Select(id=>(AssocDependency)tr.GetObject(id,OpenMode.ForRead)).ToArray();
        Require(dependencies.Length==2 && dependencies.Any(d=>d.ObjectId==dependency.ObjectId) && dependencies.Count(d=>d.DependentOnObject==circle.ObjectId)==1,"Ambiguous CenterMark dependency group");
        Require(dependencies.All(d=>d.OwningAction==action.ObjectId),"CenterMark dependency ownership mismatch");
        var markDependency=dependencies.Single(d=>d.DependentOnObject!=circle.ObjectId);
        var mark=tr.GetObject(markDependency.DependentOnObject,OpenMode.ForRead) as BlockReference;
        Require(mark!=null && mark.OwnerId==circle.OwnerId && !mark.IsDynamicBlock && mark.ExtensionDictionary.IsNull,"Probe needs static mark in same layout");
        Require(mark!.GetPersistentReactorIds().Cast<ObjectId>().SequenceEqual(new[] {markDependency.ObjectId}),"CenterMark has extra dependencies");
        Require(circle.Center.DistanceTo(mark.Position)<1e-6,"Source center mark does not match circle");
        if(cfg.TryGetProperty("expected_mark_handle",out var expectedMark))
        {
            Require(mark.Handle.ToString()==expectedMark.GetString() && action.Handle.ToString()==S(cfg,"expected_action_handle") && circle.OwnerId.Handle.ToString()==S(cfg,"expected_owner_handle"),"CenterMark contract dependency/owner mismatch");
            var expected=cfg.GetProperty("expected_center").EnumerateArray().Select(x=>x.GetDouble()).ToArray();
            Require(expected.Length==3 && expected.All(double.IsFinite) && circle.Center.DistanceTo(new Point3d(expected[0],expected[1],expected[2]))<1e-6,"CenterMark contract source center mismatch");
        }
        return new CenterMove(circle.Handle.ToString(),mark.Handle.ToString(),action.Handle.ToString(),dependency.Handle.ToString(),markDependency.Handle.ToString(),circle.Center,mark.Position,circle.Radius,delta);
    }

    static void CheckCenterMove(Database db,Transaction tr,CenterMove move)
    {
        var circle=(Circle)tr.GetObject(Id(db,move.Circle),OpenMode.ForRead);
        var mark=(BlockReference)tr.GetObject(Id(db,move.Mark),OpenMode.ForRead);
        var action=(AssocAction)tr.GetObject(Id(db,move.Action),OpenMode.ForRead);
        Require(tr.GetObject(action.ActionBody,OpenMode.ForRead).GetRXClass().Name=="AcDbCenterMarkActionBody","CenterMark action body lost on readback");
        var dependencies=action.GetDependencies(true,true).Cast<ObjectId>().Select(id=>(AssocDependency)tr.GetObject(id,OpenMode.ForRead)).ToArray();
        Require(dependencies.Length==2 && dependencies.Select(d=>d.Handle.ToString()).ToHashSet().SetEquals(new[] {move.GeometryDependency,move.MarkDependency}) && dependencies.Select(d=>d.DependentOnObject.Handle.ToString()).ToHashSet().SetEquals(new[] {move.Circle,move.Mark}),"CenterMark dependency pair changed on readback");
        Require(action.Status==AssocStatus.IsUpToDateAssocStatus,"Saved CenterMark action is not up to date before evaluation");
        Require(circle.Center.DistanceTo(move.Center+move.Delta)<1e-6 && Math.Abs(circle.Radius-move.Radius)<1e-8 && mark.Position.DistanceTo(move.MarkPosition+move.Delta)<1e-6,"Saved CenterMark geometry mismatch before evaluation");
    }

    static List<Dictionary<string,object?>> TranslateCenterMoves(JsonElement[] configs)
    {
        Require(configs.Length>=1 && configs.Length<=16,"CenterMark supports at most 16 independent pairs");
        using var db=new Database(false,true);db.ReadDwgFile(Path.GetFullPath("input.cad"),FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
        var previous=HostApplicationServices.WorkingDatabase;HostApplicationServices.WorkingDatabase=db;
        try
        {
            CenterMove[] moves;Dictionary<string,string> before;
            using(var tr=db.TransactionManager.StartTransaction())
            {
                // Every group is validated against the original database before any mutation.
                moves=configs.Select(cfg=>ReadCenterMove(db,tr,cfg)).ToArray();
                Require(moves.SelectMany(m=>new[] {m.Circle,m.Mark,m.Action}).Distinct().Count()==moves.Length*3,"CenterMark groups overlap");
                before=CenterState(db,tr);tr.Commit();
            }
            using(var tr=db.TransactionManager.StartTransaction())
            {
                foreach(var move in moves)((Circle)tr.GetObject(Id(db,move.Circle),OpenMode.ForWrite)).TransformBy(Matrix3d.Displacement(move.Delta));
                tr.Commit();
            }
            using(var tr=db.TransactionManager.StartTransaction())
            {
                foreach(var move in moves)
                {
                    ((AssocGeomDependency)tr.GetObject(Id(db,move.GeometryDependency),OpenMode.ForWrite)).SetStatus(AssocStatus.ChangedDirectlyAssocStatus,true);
                    var action=(AssocAction)tr.GetObject(Id(db,move.Action),OpenMode.ForWrite);
                    action.SetStatus(AssocStatus.ChangedDirectlyAssocStatus,false,false);action.Evaluate(AssocManager.GlobalEvaluationMultiCallback());
                }
                foreach(var move in moves)CheckCenterMove(db,tr,move);
                tr.Commit();
            }
            db.SaveAs(Path.GetFullPath("center-probe.dwg"),DwgVersion.AC1032);
            using var reopened=new Database(false,true);reopened.ReadDwgFile(Path.GetFullPath("center-probe.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);reopened.CloseInput(true);
            HostApplicationServices.WorkingDatabase=reopened;
            try
            {
            var effects=new List<Dictionary<string,object?>>();
            using(var tr=reopened.TransactionManager.StartTransaction())
            {
                // Check all persisted pairs before evaluating any action can repair them.
                foreach(var move in moves)CheckCenterMove(reopened,tr,move);
                foreach(var move in moves)
                {
                    var action=(AssocAction)tr.GetObject(Id(reopened,move.Action),OpenMode.ForWrite);
                    action.SetStatus(AssocStatus.ChangedDirectlyAssocStatus,false,false);action.Evaluate(AssocManager.GlobalEvaluationMultiCallback());
                }
                // Recheck every pair after all actions, including effects on earlier pairs.
                foreach(var move in moves)CheckCenterMove(reopened,tr,move);
                var after=CenterState(reopened,tr);Require(before.Keys.ToHashSet().SetEquals(after.Keys),"Probe changed entity inventory");
                var selected=moves.SelectMany(m=>new[] {m.Circle,m.Mark}).ToHashSet();
                foreach(var move in moves)
                {
                    Require(SameNativeSnapshot(before[move.Circle],after[move.Circle],new HashSet<string> {"bbox","center"}),"Circle properties changed beyond translation");
                    Require(SameNativeSnapshot(before[move.Mark],after[move.Mark],new HashSet<string> {"bbox","position"}),"CenterMark properties changed beyond translation");
                }
                var differences=before.Where(p=>!selected.Contains(p.Key) && p.Value!=after[p.Key]).Select(p=>new {handle=p.Key,before=p.Value,after=after[p.Key],within_numeric_tolerance=SameNativeSnapshot(p.Value,after[p.Key])}).ToArray();
                Write("center-probe-differences.json",differences.Take(30).ToArray());
                Require(differences.All(p=>p.within_numeric_tolerance),"Probe changed unselected inventory beyond numeric tolerance");
                var native=NativeDependencies(reopened,tr,selected);
                foreach(var move in moves)effects.Add(new Dictionary<string,object?> {
                    ["status"]="validated_native_translation_probe",["source_sha256"]=Hash("input.cad"),["output_sha256"]=Hash("center-probe.dwg"),
                    ["circle_handle"]=move.Circle,["mark_handle"]=move.Mark,["action_handle"]=move.Action,["delta"]=V(move.Delta),
                    ["source_circle_center"]=P(move.Center),["source_mark_position"]=P(move.MarkPosition),["circle_center"]=P(move.Center+move.Delta),["mark_position"]=P(move.MarkPosition+move.Delta),["radius"]=move.Radius,
                    ["reopened_evaluation_stable"]=true,["persisted_state_verified_before_evaluation"]=true,["selected_pair_count"]=moves.Length,
                    ["unselected_inventory_entries_verified"]=before.Count-selected.Count,["numeric_tolerance"]=1e-7,["roundtrip_rounding_entries"]=differences.Length,
                    ["native_dependencies"]=native,["customer_revision_created"]=false,["edit_authorization"]=false });
                tr.Commit();
            }
            reopened.DxfOut(Path.GetFullPath("center-probe.dxf"),16,DwgVersion.AC1032);
            return effects;
            }
            finally {HostApplicationServices.WorkingDatabase=db;}
        }
        finally {HostApplicationServices.WorkingDatabase=previous;}
    }
}

// No UI API, shell, user Lisp, dynamic compilation, or arbitrary executable code.
using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(MechanicalCad.Commands))]

namespace MechanicalCad;

public partial class Commands
{
    static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = false };
    static string Hash(string file) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file))).ToLowerInvariant();
    static double[] P(Point3d p) => new[] { p.X, p.Y, p.Z };
    static double[] V(Vector3d p) => new[] { p.X, p.Y, p.Z };
    static void Require(bool ok, string message) { if (!ok) throw new InvalidOperationException(message); }
    static string S(JsonElement e, string key) => e.GetProperty(key).GetString()!;
    static void Write(string path, object value) => File.WriteAllText(path, JsonSerializer.Serialize(value, JsonOptions));
    static void Stage(string stage) => Write("plugin-progress.json", new { stage, utc = DateTime.UtcNow });

    static bool SameNativeSnapshot(string before,string after,HashSet<string>? ignoredTopLevel=null)
    {
        using var a=JsonDocument.Parse(before);using var b=JsonDocument.Parse(after);
        bool Same(JsonElement x,JsonElement y,bool top=false)
        {
            if(x.ValueKind!=y.ValueKind)return false;
            if(x.ValueKind==JsonValueKind.Number)return Math.Abs(x.GetDouble()-y.GetDouble())<=1e-7;
            if(x.ValueKind==JsonValueKind.Array)return x.GetArrayLength()==y.GetArrayLength() && x.EnumerateArray().Zip(y.EnumerateArray()).All(p=>Same(p.First,p.Second));
            if(x.ValueKind==JsonValueKind.Object)
            {
                var left=x.EnumerateObject().Where(p=>!top || ignoredTopLevel==null || !ignoredTopLevel.Contains(p.Name)).ToArray();
                var right=y.EnumerateObject().Where(p=>!top || ignoredTopLevel==null || !ignoredTopLevel.Contains(p.Name)).ToDictionary(p=>p.Name,p=>p.Value);
                return left.Length==right.Count && left.All(p=>right.TryGetValue(p.Name,out var value) && Same(p.Value,value));
            }
            return x.GetRawText()==y.GetRawText();
        }
        return Same(a.RootElement,b.RootElement,true);
    }

    [CommandMethod("MECHANICALCENTERPROBE", CommandFlags.Session)]
    public void CenterProbe()
    {
        try { CenterProbeChecked(); }
        catch(System.Exception error) { Write("center-probe-error.json",new { type=error.GetType().FullName,message=error.Message,stack=error.StackTrace }); }
    }

    static void CenterProbeChecked()
    {
        using var input=JsonDocument.Parse(File.ReadAllBytes("center-probe.json"));var cfg=input.RootElement;
        Require(Hash("input.cad")==S(cfg,"source_sha256"),"Probe source hash mismatch");
        var configs=cfg.TryGetProperty("pairs",out var pairs) ? pairs.EnumerateArray().ToArray() : new[] {cfg};
        var effects=TranslateCenterMoves(configs);
        Write("center-probe-effects.json",effects);
        if(effects.Count==1)Write("center-probe-receipt.json",effects[0]);
        else Write("center-probe-receipt.json",new {selected_pair_count=effects.Count,effects});
    }

    [CommandMethod("MECHANICALCAD", CommandFlags.Session)]
    public void Run()
    {
        try { RunChecked(); }
        catch (System.Exception error)
        {
            Write("plugin-error.json", new { type = error.GetType().FullName, message = error.Message, stack = error.StackTrace });
            // No result.zip is produced on failure; the host rejects the job.
            // Do not throw across the native command boundary: Core Console
            // must continue to the fixed QUIT script and release its databases.
            return;
        }
    }

    static void RunChecked()
    {
        Stage("contract");
        // Fixed names prevent command JSON from escaping the APS work directory.
        var commandPath = Path.GetFullPath("commands.json");
        var inputPath = Path.GetFullPath("input.cad");
        using var json = JsonDocument.Parse(File.ReadAllBytes(commandPath));
        var contract = json.RootElement;
        Require(contract.GetProperty("schema_version").GetInt32() == 1, "Unsupported contract");
        Require(Hash(inputPath) == S(contract, "source_sha256"), "Source hash mismatch");
        var mode = S(contract, "mode");
        Require(new[] { "inspect", "convert", "edit", "recover" }.Contains(mode), "Unsupported mode");
        var ops = contract.GetProperty("operations").EnumerateArray().ToArray();
        Require(mode == "edit" || ops.Length == 0, "Unexpected edit operations");
        var scopes = contract.GetProperty("scope_handles").EnumerateArray().Select(e => e.GetString()!).ToHashSet();
        if(ops.Any(op=>S(op,"action")=="stretch_rectangle"))
        {RunRectangleContract(contract,ops,scopes);return;}
        if(ops.Any(op=>S(op,"action")=="translate_centermark"))
        {
            Require(mode=="edit" && ops.Length<=16 && ops.All(op=>S(op,"action")=="translate_centermark") && S(contract,"input_name").EndsWith(".dwg",StringComparison.OrdinalIgnoreCase),"CenterMark needs an isolated DWG edit of at most 16 pairs");
            var configs=new List<object>();var selected=new HashSet<string>();
            foreach(var op in ops)
            {
            var circleHandle=S(op,"handle");var markHandle=S(op,"mark_handle");
            Require(scopes.Contains(circleHandle) && scopes.Contains(markHandle) && S(op,"expected_type")=="CIRCLE" && PathOf(op).Length==1,"CenterMark pair outside layout scope");
            using var beforeJson=JsonDocument.Parse(S(op,"before"));using var afterJson=JsonDocument.Parse(S(op,"after"));
            var from=beforeJson.RootElement.EnumerateArray().Select(x=>x.GetDouble()).ToArray();var to=afterJson.RootElement.EnumerateArray().Select(x=>x.GetDouble()).ToArray();
            Require(from.Length==3 && to.Length==3 && from.Concat(to).All(double.IsFinite),"Invalid CenterMark center vectors");
            var delta=from.Zip(to).Select(p=>p.Second-p.First).ToArray();
            Require(Math.Abs(delta[2])<1e-10 && delta.Any(x=>Math.Abs(x)>1e-10),"CenterMark requires nonzero planar translation");
            configs.Add(new {circle_handle=circleHandle,delta,expected_mark_handle=markHandle,expected_action_handle=S(op,"action_handle"),expected_owner_handle=S(op,"owner_handle"),expected_center=from});
            Require(selected.Add(circleHandle) && selected.Add(markHandle),"CenterMark groups overlap");
            }
            Write("center-probe.json",new {source_sha256=Hash(inputPath),pairs=configs});
            CenterProbeChecked();
            Directory.CreateDirectory("out");File.Copy("center-probe.dwg","out/modified.dwg",false);File.Copy("center-probe.dxf","out/roundtrip.dxf",false);
            using var effectJson=JsonDocument.Parse(File.ReadAllBytes("center-probe-effects.json"));
            using(var resultDb=new Database(false,true))
            {
                resultDb.ReadDwgFile(Path.GetFullPath("out/modified.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);resultDb.CloseInput(true);
                var old=HostApplicationServices.WorkingDatabase;
                try
                {
                    HostApplicationServices.WorkingDatabase=resultDb;
                    using var tr=resultDb.TransactionManager.StartTransaction();
                    var inventory=(Dictionary<string,object>)Inventory(resultDb,tr,false,selected);
                    inventory["centermark_effects"]=effectJson.RootElement.Clone();Write("out/inventory.json",inventory);tr.Commit();
                }
                finally {HostApplicationServices.WorkingDatabase=old;}
            }
            var hashes=new Dictionary<string,string>();foreach(var name in new[] {"modified.dwg","roundtrip.dxf","inventory.json"})hashes[name]=Hash("out/"+name);
            Write("out/receipt.json",new {schema_version=1,status="validated",mode,source_sha256=Hash(inputPath),commands_sha256=Hash(commandPath),applied_operations=ops.Length,hashes,complete_product_backup=false});
            ZipFile.CreateFromDirectory("out",Path.GetFullPath("result.zip"));Stage("complete");return;
        }
        using var db = new Database(false, true);
        Stage("read_source");
        if (mode == "recover")
        {
            Require(S(contract, "input_name").EndsWith(".dwg", StringComparison.OrdinalIgnoreCase), "Recovery requires DWG");
            Stage("recover_copy");
            var copy = Path.GetFullPath("recovery-source.dwg");
            File.Copy(inputPath, copy, false);
            var documents = Autodesk.AutoCAD.ApplicationServices.Core.Application.DocumentManager;
            documents.AppContextRecoverDocument(copy);
            var recoveredDocument = documents.MdiActiveDocument;
            Require(string.Equals(Path.GetFullPath(recoveredDocument.Name), copy, StringComparison.OrdinalIgnoreCase), "Recovery did not open the requested copy");
            var recovered = Path.GetFullPath("recovered-source.dwg");
            using (recoveredDocument.LockDocument()) recoveredDocument.Database.SaveAs(recovered, DwgVersion.AC1032);
            db.ReadDwgFile(recovered, FileOpenMode.OpenForReadAndAllShare, true, null);
        }
        else if (S(contract, "input_name").EndsWith(".dxf", StringComparison.OrdinalIgnoreCase)) db.DxfIn(inputPath, "dxf-import.log");
        else db.ReadDwgFile(inputPath, FileOpenMode.OpenForReadAndAllShare, true, null);
        db.CloseInput(true);
        var previous = HostApplicationServices.WorkingDatabase;
        try
        {
            HostApplicationServices.WorkingDatabase = db;
            Dictionary<string, object> beforeDynamic;
            using (var initial = db.TransactionManager.StartTransaction())
                beforeDynamic = DynamicSnapshots(db, initial);
            Stage("apply");
            var targets = new Dictionary<string, string>();
            var targetOwners = new Dictionary<string, string>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                // Validate every ORIGINAL owner chain before cloning any branch.
                foreach (var op in ops) Target(db, tr, op, false);
                var isolated = new HashSet<string>();
                var clones = new Dictionary<string, ObjectId>();
                foreach (var op in ops)
                {
                    var entity = IsolateTarget(db, tr, op, isolated, clones);
                    targets[Ref(op)] = entity.Handle.ToString();
                    targetOwners[Ref(op)] = entity.OwnerId.Handle.ToString();
                    Apply(db, tr, op, scopes, entity);
                }
                tr.Commit();
            }
            // Save and reopen native DWG before extracting proof and DXF readback.
            Directory.CreateDirectory("out");
            var output = Path.GetFullPath("out/modified.dwg");
            Stage("save_dwg");
            db.SaveAs(output, DwgVersion.AC1032);
            Stage("reopen_dwg");
            using (var reopened = new Database(false, true))
            {
            reopened.ReadDwgFile(output, FileOpenMode.OpenForReadAndAllShare, true, null);
            reopened.CloseInput(true);
            try
            {
            HostApplicationServices.WorkingDatabase = reopened;
            using (var tr = reopened.TransactionManager.StartTransaction())
            {
                foreach (var op in ops) Verify(reopened, tr, op, targets[Ref(op)], targetOwners[Ref(op)]);
                Stage("inventory");
                var afterDynamic = DynamicSnapshots(reopened, tr);
                var changedHandles = ops.Where(o => S(o, "action") == "set_dynamic_property").Select(o => targets[Ref(o)]).ToHashSet();
                if (changedHandles.Count > 0)
                    foreach (var entry in beforeDynamic.Where(entry => !changedHandles.Contains(entry.Key)))
                        Require(afterDynamic.ContainsKey(entry.Key) && JsonSerializer.Serialize(entry.Value) == JsonSerializer.Serialize(afterDynamic[entry.Key]), "Unselected dynamic block changed: " + entry.Key);
                var effects = ops.Where(o => S(o,"action")=="set_dynamic_property").GroupBy(Ref).Select(group => group.First()).Select(o => new {
                    handle=targets[Ref(o)], source_ref=Ref(o), source_handle=S(o,"handle"),
                    before=beforeDynamic[S(o,"handle")],after=afterDynamic[targets[Ref(o)]] }).ToArray();
                var inventory = (Dictionary<string, object>)Inventory(reopened, tr, mode == "recover", scopes);
                inventory["dynamic_effects"] = effects;
                Write("out/inventory.json", inventory);
                tr.Commit();
            }
            Stage("save_dxf");
            reopened.DxfOut(Path.GetFullPath("out/roundtrip.dxf"), 16, DwgVersion.AC1032);
            var hashes = new Dictionary<string, string>();
            foreach (var name in new[] { "modified.dwg", "roundtrip.dxf", "inventory.json" }) hashes[name] = Hash("out/" + name);
            Write("out/receipt.json", new { schema_version = 1, status = "validated", mode,
                source_sha256 = Hash(inputPath), commands_sha256 = Hash(commandPath),
                applied_operations = ops.Length, hashes, source_recovered = mode == "recover", recovery_review_required = mode == "recover", complete_product_backup = false });
            ZipFile.CreateFromDirectory("out", Path.GetFullPath("result.zip"));
            Stage("complete");
            }
            // A database must not be disposed while it is WorkingDatabase;
            // association reactors can access it during teardown.
            finally { HostApplicationServices.WorkingDatabase = db; }
            }
        }
        finally { HostApplicationServices.WorkingDatabase = previous; }
    }

    static Entity Target(Database db, Transaction tr, JsonElement op, bool write)
    {
        var path = PathOf(op);
        Require(path.Length <= 8 && path.Length > 0 && path.Distinct().Count()==path.Length && path[^1]==S(op,"handle"), "Invalid instance path");
        var id = Id(db,path[0]);
        var root=(Entity)tr.GetObject(id,OpenMode.ForRead);
        Require(tr.GetObject(root.OwnerId,OpenMode.ForRead) is BlockTableRecord layout && layout.IsLayout,"Instance path must start in layout");
        for(int i=1;i<path.Length;i++)
        {
            var parent=tr.GetObject(id,OpenMode.ForRead) as BlockReference;
            Require(parent!=null,"Instance path parent is not INSERT");
            Require(!parent!.IsDynamicBlock,"Nested dynamic parent needs a separate native association adapter");
            var definition=(BlockTableRecord)tr.GetObject(parent.BlockTableRecord,OpenMode.ForRead);
            Require(!definition.IsFromExternalReference && !definition.IsFromOverlayReference,"Cannot isolate an XREF");
            var child=Id(db,path[i]);
            Require(((Entity)tr.GetObject(child,OpenMode.ForRead)).OwnerId==parent.BlockTableRecord,"Nested owner path mismatch");
            id=child;
        }
        var entity = (Entity)tr.GetObject(id, write ? OpenMode.ForWrite : OpenMode.ForRead);
        Require(entity.OwnerId.Handle.ToString() == S(op, "owner_handle"), "Owner mismatch");
        Require(entity.GetRXClass().DxfName == S(op, "expected_type"), "Entity type mismatch");
        var owner = tr.GetObject(entity.OwnerId, OpenMode.ForRead);
        // Editing a shared definition changes all instances. Require an isolated
        // layout entity; dynamic parameters act on the chosen block instance.
        Require(path.Length>1 ? S(op,"action")=="set_dynamic_property" : owner is BlockTableRecord record && record.IsLayout, "Shared/nested definition needs isolation first");
        return entity;
    }

    static ObjectId Id(Database db,string handle) => db.GetObjectId(false,new Handle(long.Parse(handle,NumberStyles.HexNumber)),0);
    static string[] PathOf(JsonElement op) => op.TryGetProperty("instance_path",out var p) && p.GetArrayLength()>0
        ? p.EnumerateArray().Select(h=>h.GetString()!).ToArray() : new[]{S(op,"handle")};
    static string Ref(JsonElement op) => string.Join("/",PathOf(op));

    static Entity IsolateTarget(Database db,Transaction tr,JsonElement op,HashSet<string> isolated,Dictionary<string,ObjectId> clones)
    {
        var path=PathOf(op);
        for(int i=0;i<path.Length-1;i++)
        {
            var prefix=string.Join("/",path.Take(i+1));
            if(!isolated.Add(prefix))continue;
            var id=clones.TryGetValue(prefix,out var mapped)?mapped:Id(db,path[i]);
            var parent=(BlockReference)tr.GetObject(id,OpenMode.ForWrite);
            Require(!parent.IsDynamicBlock && parent.AttributeCollection.Count==0,"Nested parent with dynamic properties or attributes needs a separate adapter");
            var source=(BlockTableRecord)tr.GetObject(parent.BlockTableRecord,OpenMode.ForRead);
            Require(source.ExtensionDictionary.IsNull,"Nested parent definition has associations requiring a separate adapter");
            // Clone complete simple static containers. Never flatten, explode
            // or detach an associative/proxy/unknown object to make it editable.
            var members=source.Cast<ObjectId>().ToArray();
            foreach(var member in members)
            {
                var e=tr.GetObject(member,OpenMode.ForRead) as Entity;
                Require(e is Line or Circle or Arc or Polyline or Ellipse or Spline or Dimension or Table or Hatch or DBText or MText or BlockReference,"Unsupported object in nested container");
                Require(e is not Hatch hatch || !hatch.Associative,"Associative hatch in nested container needs native adapter");
                Require(e is BlockReference br && br.IsDynamicBlock || e!.ExtensionDictionary.IsNull,"Associative object in nested container needs native adapter");
            }
            var table=(BlockTable)tr.GetObject(db.BlockTableId,OpenMode.ForWrite);
            var copy=new BlockTableRecord { Name="*U",Origin=source.Origin,Units=source.Units,Explodable=source.Explodable,BlockScaling=source.BlockScaling };
            table.Add(copy);tr.AddNewlyCreatedDBObject(copy,true);
            var mapping=new IdMapping();
            db.DeepCloneObjects(new ObjectIdCollection(members),copy.ObjectId,mapping,false);
            foreach(var member in members)
            {
                Require(mapping.Contains(member) && mapping[member].IsCloned,"Nested clone mapping incomplete");
                clones[prefix+"/"+member.Handle.ToString()]=mapping[member].Value;
            }
            parent.BlockTableRecord=copy.ObjectId;parent.RecordGraphicsModified(true);
        }
        var target=clones.TryGetValue(Ref(op),out var actual)?actual:Id(db,S(op,"handle"));
        return (Entity)tr.GetObject(target,OpenMode.ForWrite);
    }

    static DynamicBlockReferenceProperty Dynamic(Entity entity, string name)
    {
        Require(entity is BlockReference br && br.IsDynamicBlock, "Not a dynamic block instance");
        var matches = ((BlockReference)entity).DynamicBlockReferencePropertyCollection
            .Cast<DynamicBlockReferenceProperty>().Where(p => p.PropertyName == name).ToArray();
        Require(matches.Length == 1 && !matches[0].ReadOnly, "Missing/ambiguous/read-only parameter");
        Require(matches[0].Value is double or short or int or string, "Unsupported native parameter type");
        return matches[0];
    }

    static bool EqualValue(object a, object b) => a is string || b is string
        ? a is string && b is string && (string)a == (string)b
        : Math.Abs(Convert.ToDouble(a, CultureInfo.InvariantCulture) - Convert.ToDouble(b, CultureInfo.InvariantCulture)) < 1e-8;

    static object ParameterValue(DynamicBlockReferenceProperty property, JsonElement value)
    {
        if (property.Value is string)
        {
            Require(value.ValueKind == JsonValueKind.String, "Parameter requires a string");
            return value.GetString()!;
        }
        Require(value.ValueKind == JsonValueKind.Number, "Parameter requires a number");
        var number = value.GetDouble();
        Require(double.IsFinite(number), "Nonfinite parameter");
        if (property.Value is short) { Require(number == Math.Truncate(number) && number >= short.MinValue && number <= short.MaxValue, "Invalid Int16 parameter"); return (short)number; }
        if (property.Value is int) { Require(number == Math.Truncate(number) && number >= int.MinValue && number <= int.MaxValue, "Invalid Int32 parameter"); return (int)number; }
        return number;
    }

    static Dictionary<string, object> DynamicSnapshots(Database db, Transaction tr)
    {
        var result = new Dictionary<string, object>();
        foreach (ObjectId id in (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead))
        {
            var block = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
            foreach (ObjectId member in block)
            {
                if (tr.GetObject(member, OpenMode.ForRead) is not BlockReference br || !br.IsDynamicBlock) continue;
                double[][]? bbox = null;
                try { var box = br.GeometricExtents; bbox = new[] { P(box.MinPoint), P(box.MaxPoint) }; }
                catch (Autodesk.AutoCAD.Runtime.Exception) { }
                result[br.Handle.ToString()] = new {
                    bbox,
                    parameters = br.DynamicBlockReferencePropertyCollection.Cast<DynamicBlockReferenceProperty>()
                        .Select(p => new { name = p.PropertyName, value = Convert.ToString(p.Value, CultureInfo.InvariantCulture), value_type = p.Value?.GetType().Name }).ToArray()
                };
            }
        }
        return result;
    }

    static string Text(Entity e) => e switch {
        DBText t => t.TextString, MText t => t.Contents,
        _ => throw new InvalidOperationException("Unsupported text entity") };

    static void Apply(Database db, Transaction tr, JsonElement op, HashSet<string> scope, Entity e)
    {
        Require(scope.Contains(Ref(op)), "Operation outside scope");
        switch (S(op, "action"))
        {
            case "replace_text":
                Require(Text(e) == S(op, "before"), "Text precondition failed");
                if (e is DBText text) text.TextString = S(op, "after");
                else ((MText)e).Contents = S(op, "after");
                break;
            case "table_cell":
                Require(e is Table, "Not a native table");
                var table = (Table)e;
                int row = op.GetProperty("row").GetInt32(), column = op.GetProperty("column").GetInt32();
                Require(row >= 0 && row < table.Rows.Count && column >= 0 && column < table.Columns.Count, "Invalid table cell");
                Require(table.Cells[row, column].TextString == S(op, "before"), "Cell precondition failed");
                table.Cells[row, column].TextString = S(op, "after");
                table.GenerateLayout();
                break;
            case "set_dynamic_property":
                var prop = Dynamic(e, S(op, "property"));
                Require(EqualValue(prop.Value, ParameterValue(prop, op.GetProperty("before"))), "Parameter precondition failed");
                var value = ParameterValue(prop, op.GetProperty("after"));
                var allowed = prop.GetAllowedValues();
                Require(!(value is string) || allowed.Length > 0, "String parameter needs authored allowed values");
                Require(allowed.Length == 0 || allowed.Any(a => EqualValue(a, value)), "Parameter outside allowed values");
                prop.Value = value;
                Require(EqualValue(prop.Value, value), "AutoCAD did not accept parameter " + prop.PropertyName + "; requested=" + Convert.ToString(value, CultureInfo.InvariantCulture) + "; actual=" + Convert.ToString(prop.Value, CultureInfo.InvariantCulture));
                ((BlockReference)e).RecordGraphicsModified(true);
                break;
            default: throw new InvalidOperationException("Operation not allowlisted");
        }
    }

    static void Verify(Database db, Transaction tr, JsonElement op, string handle, string owner)
    {
        var e=(Entity)tr.GetObject(Id(db,handle),OpenMode.ForRead);
        Require(e.OwnerId.Handle.ToString()==owner && e.GetRXClass().DxfName==S(op,"expected_type"),"Isolated target readback mismatch");
        switch (S(op, "action"))
        {
            case "replace_text": Require(Text(e) == S(op, "after"), "Text readback mismatch"); break;
            case "table_cell":
                Require(((Table)e).Cells[op.GetProperty("row").GetInt32(), op.GetProperty("column").GetInt32()].TextString == S(op, "after"), "Table readback mismatch"); break;
            case "set_dynamic_property":
                var prop = Dynamic(e, S(op, "property"));
                Require(EqualValue(prop.Value, ParameterValue(prop, op.GetProperty("after"))), "Parameter readback mismatch: " + prop.PropertyName + "; requested=" + op.GetProperty("after").ToString() + "; actual=" + Convert.ToString(prop.Value, CultureInfo.InvariantCulture)); break;
            default: throw new InvalidOperationException("Unknown readback operation");
        }
    }

    static object NativeDependencies(Database db, Transaction tr, HashSet<string> scopes)
    {
        const int limit=256, depthLimit=6;
        var nodes=new List<object>();var edges=new List<object>();var errors=new List<object>();
        var queue=new Queue<(ObjectId id,int depth)>();var seen=new HashSet<ObjectId>();bool truncated=false;
        foreach(var scope in scopes.OrderBy(x=>x))
        {
            try
            {
                var path=scope.Split('/');Require(path.Length<=8 && path.Distinct().Count()==path.Length,"Invalid inspection instance path");
                var target=Id(db,path[0]);
                for(int i=1;i<path.Length;i++)
                {
                    var parent=tr.GetObject(target,OpenMode.ForRead) as BlockReference;
                    var child=Id(db,path[i]);
                    Require(parent!=null && tr.GetObject(child,OpenMode.ForRead).OwnerId==parent.BlockTableRecord,"Inspection instance owner mismatch");
                    target=child;
                }
                queue.Enqueue((target,0));
            }
            catch(System.Exception error) { errors.Add(new { root=scope, error=error.GetType().Name }); }
        }
        while(queue.Count>0)
        {
            var (id,depth)=queue.Dequeue();if(id.IsNull || id.IsErased || !seen.Add(id))continue;
            if(nodes.Count>=limit) { truncated=true;break; }
            try
            {
                var obj=tr.GetObject(id,OpenMode.ForRead);var handle=obj.Handle.ToString();
                nodes.Add(new { handle, type=obj.GetRXClass().DxfName, native_class=obj.GetRXClass().Name,
                    managed_class=obj.GetType().FullName, owner_handle=obj.OwnerId.IsNull ? null : obj.OwnerId.Handle.ToString(), depth });
                void Link(ObjectId target,string relation)
                {
                    if(target.IsNull)return;
                    edges.Add(new { source=handle,target=target.Handle.ToString(),relation });
                    if(depth<depthLimit)queue.Enqueue((target,depth+1));else if(!seen.Contains(target))truncated=true;
                }
                foreach(ObjectId reactor in obj.GetPersistentReactorIds())Link(reactor,"persistent_reactor");
                if(!obj.ExtensionDictionary.IsNull)Link(obj.ExtensionDictionary,"extension_dictionary");
                // Entity ownership is reported above, but structural block and
                // layout resources are not expanded as design dependencies.
                if(obj is not Entity && obj is not BlockTableRecord && !obj.OwnerId.IsNull)Link(obj.OwnerId,"owner");
                if(obj is DBDictionary dictionary)
                {
                    using var entries=dictionary.GetEnumerator();int count=0;
                    while(entries.MoveNext()) { if(count++>=128) { truncated=true;break; } Link(entries.Value,"dictionary:"+entries.Key); }
                }
                // Enumerate the owning action's actual dependencies so a mark
                // selected without its source geometry can be explained.
                // Never expand every action in a shared associative network.
                if(obj is AssocAction action && obj is not AssocNetwork)
                {
                    try
                    {
                        int count=0;
                        foreach(ObjectId dependency in action.GetDependencies(true,true))
                        {
                            if(count++>=128) {truncated=true;break;}
                            Link(dependency,"native:Dependency");
                        }
                    }
                    catch(System.Exception error) {errors.Add(new {handle,property="GetDependencies",error=error.GetType().Name});}
                }
                // Fixed read-only native properties only; no supplied member
                // names, evaluation commands, or binary proxy interpretation.
                foreach(var name in new[] { "DependentOnObject","OwningAction","ActionBody","ParentAction" })
                {
                    var property=obj.GetType().GetProperty(name);
                    if(property==null || property.PropertyType!=typeof(ObjectId) || property.GetIndexParameters().Length!=0)continue;
                    try { if(property.GetValue(obj) is ObjectId target)Link(target,"native:"+name); }
                    catch(System.Exception error) { errors.Add(new { handle,property=name,error=error.GetType().Name }); }
                }
            }
            catch(System.Exception error) { errors.Add(new { handle=id.Handle.ToString(),error=error.GetType().Name }); }
        }
        return new { requested_roots=scopes.OrderBy(x=>x).ToArray(),nodes,edges,errors,truncated,node_limit=limit,depth_limit=depthLimit,action_dependency_limit=128,
            status=scopes.Count==0 ? "not_requested" : truncated || errors.Count>0 ? "partial" : "inspected",
            coverage="Listed relations only: persistent reactors, non-entity owners, extension dictionaries, dictionary entries, four fixed native ObjectId properties and up to 128 dependencies of each non-network action. Shared networks are not expanded into all actions; other action/network properties are not enumerated.",
            policy="Read-only bounded native dependency inventory; not edit authorization or proof of a complete mechanical group." };
    }

    static Dictionary<string, object> Inventory(Database db, Transaction tr, bool recovered = false, HashSet<string>? scopes=null)
    {
        var blocks = new List<object>();
        var entities = new List<Dictionary<string, object?>>();
        var warnings = new List<string>();
        if (recovered) warnings.Add("Recovered source copy: compare with original before editing; recovery may remove damaged data. Not a completed design change.");
        foreach (ObjectId id in (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead))
        {
            var block = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
            var handles = new List<string>();
            foreach (ObjectId member in block)
            {
                if (tr.GetObject(member, OpenMode.ForRead) is not Entity e) continue;
                var handle = e.Handle.ToString();
                handles.Add(handle);
                var item = new Dictionary<string, object?> { ["handle"] = handle, ["owner_handle"] = block.Handle.ToString(),
                    ["type"] = e.GetRXClass().DxfName, ["native_class"] = e.GetRXClass().Name,
                    ["layer"] = e.Layer, ["block"] = block.Name, ["is_layout"] = block.IsLayout };
                item["persistent_reactor_handles"]=e.GetPersistentReactorIds().Cast<ObjectId>().Where(id=>!id.IsNull && !id.IsErased).Select(id=>id.Handle.ToString()).OrderBy(h=>h,StringComparer.Ordinal).ToArray();
                item["extension_dictionary_handle"]=e.ExtensionDictionary.IsNull ? null : e.ExtensionDictionary.Handle.ToString();
                try { var box = e.GeometricExtents; item["bbox"] = new[] { P(box.MinPoint), P(box.MaxPoint) }; }
                catch (Autodesk.AutoCAD.Runtime.Exception) { item["bbox"] = null; }
                switch (e)
                {
                    case Table table:
                        var cells = new List<object>();
                        for (int r = 0; r < table.Rows.Count; r++) for (int c = 0; c < table.Columns.Count; c++)
                            cells.Add(new { row = r, column = c, text = table.Cells[r, c].TextString });
                        item["cells"] = cells; break;
                    case BlockReference br:
                        item["block_handle"] = br.BlockTableRecord.Handle.ToString();
                        item["normal"] = V(br.Normal);
                        item["position"] = P(br.Position); item["rotation"] = br.Rotation;
                        item["scale"] = new[] { br.ScaleFactors.X, br.ScaleFactors.Y, br.ScaleFactors.Z };
                        item["dynamic"] = br.IsDynamicBlock;
                        if (br.IsDynamicBlock) item["parameters"] = br.DynamicBlockReferencePropertyCollection.Cast<DynamicBlockReferenceProperty>()
                            .Select(p => new { name = p.PropertyName, value = Convert.ToString(p.Value, CultureInfo.InvariantCulture), value_type = p.Value?.GetType().Name,
                                read_only = p.ReadOnly, units = p.UnitsType.ToString(), allowed = p.GetAllowedValues().Select(v => Convert.ToString(v, CultureInfo.InvariantCulture)).ToArray() }).ToArray();
                        item["attributes"] = br.AttributeCollection.Cast<ObjectId>().Select(a => (AttributeReference)tr.GetObject(a, OpenMode.ForRead))
                            .Select(a => new { handle = a.Handle.ToString(), tag = a.Tag, text = a.TextString }).ToArray();
                        break;
                    case MText text: item["text"] = text.Contents; break;
                    case DBText text: item["text"] = text.TextString; break;
                    case Dimension dim:
                        item["text"] = dim.DimensionText;
                        item["dimension_block_handle"] = dim.DimBlockId.IsNull ? null : dim.DimBlockId.Handle.ToString();
                        // AutoCAD may lazily evaluate an imported DIM when its
                        // measurement is first read. Its cache needs write mode
                        // on this private reopened database, never on the source.
                        try
                        {
                            dim.UpgradeOpen();
                            item["measurement"] = dim.Measurement;
                        }
                        catch (Autodesk.AutoCAD.Runtime.Exception error)
                        {
                            item["measurement"] = null;
                            item["measurement_error"] = error.ErrorStatus.ToString();
                            warnings.Add("Dimension measurement unavailable: " + handle + " (" + error.ErrorStatus + ")");
                        }
                        finally { if (dim.IsWriteEnabled) dim.DowngradeOpen(); }
                        break;
                    case Line line: item["start"] = P(line.StartPoint); item["end"] = P(line.EndPoint); break;
                    case Circle circle: item["center"] = P(circle.Center); item["radius"] = circle.Radius;item["normal"]=V(circle.Normal); break;
                    case Arc arc: item["center"] = P(arc.Center); item["radius"] = arc.Radius; item["start_angle"] = arc.StartAngle; item["end_angle"] = arc.EndAngle;item["normal"]=V(arc.Normal); break;
                    case Polyline polyline:
                        item["vertices"] = Enumerable.Range(0, polyline.NumberOfVertices).Select(i => new { point = P(polyline.GetPoint3dAt(i)), bulge = polyline.GetBulgeAt(i) }).ToArray();
                        item["closed"] = polyline.Closed; break;
                    case Ellipse ellipse: item["center"] = P(ellipse.Center); item["major_axis"] = V(ellipse.MajorAxis); item["ratio"] = ellipse.RadiusRatio;item["start_param"]=ellipse.StartParam;item["end_param"]=ellipse.EndParam;item["normal"]=V(ellipse.Normal); break;
                    case Spline spline: item["control_points"] = Enumerable.Range(0, spline.NumControlPoints).Select(i => P(spline.GetControlPointAt(i))).ToArray(); break;
                    case ProxyEntity _: warnings.Add("Proxy requires its native object enabler: " + handle); break;
                }
                if (!e.ExtensionDictionary.IsNull)
                {
                    var dictionary = (DBDictionary)tr.GetObject(e.ExtensionDictionary, OpenMode.ForRead);
                    // The explicit IEnumerable implementation yields CLR
                    // DictionaryEntry, whereas the native enumerator exposes
                    // ObjectId values. Avoid LINQ Cast<DBDictionaryEntry>.
                    var records = new List<object>();
                    using var entries = dictionary.GetEnumerator();
                    while (entries.MoveNext()) records.Add(new { name = entries.Key, handle = entries.Value.Handle.ToString() });
                    item["extension_records"] = records;
                }
                entities.Add(item);
            }
            blocks.Add(new { handle = block.Handle.ToString(), name = block.Name, is_layout = block.IsLayout,
                is_xref = block.IsFromExternalReference, members = handles });
            if (block.IsFromExternalReference) warnings.Add("External reference must be packaged/resolved: " + block.Name);
        }
        return new Dictionary<string, object> { ["schema_version"] = 1, ["blocks"] = blocks, ["entities"] = entities, ["warnings"] = warnings,
            ["native_dependencies"] = NativeDependencies(db,tr,scopes ?? new HashSet<string>()),
            ["summary"] = new { block_count = blocks.Count, entity_count = entities.Count, drawing_units = db.Insunits.ToString() },
            ["completeness"] = "Native inventory; mechanical ownership/constraints still need verified design evidence" };
    }
}

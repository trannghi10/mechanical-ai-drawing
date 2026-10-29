using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

namespace MechanicalCad;

public partial class Commands
{
    record ProbeDimension(string Handle,Point3d A,Point3d B,Point3d Line,Point3d Text,double Angle,double Measure,string Value,string Style,Vector3d Normal,double TextHeight);
    static double ProbeTextHeight(Dimension dim)
    {
        var tr=dim.Database.TransactionManager.TopTransaction;
        var texts=((BlockTableRecord)tr.GetObject(dim.DimBlockId,OpenMode.ForRead)).Cast<ObjectId>().Select(id=>tr.GetObject(id,OpenMode.ForRead)).OfType<MText>().ToArray();
        Require(texts.Length==1 && texts[0].Attachment==AttachmentPoint.MiddleCenter,"Probe needs one centered DIM MText");
        return texts[0].ActualHeight;
    }
    static ProbeDimension ProbeDim(RotatedDimension d)=>new(d.Handle.ToString(),d.XLine1Point,d.XLine2Point,d.DimLinePoint,d.TextPosition,d.Rotation,d.Measurement,d.DimensionText,d.DimensionStyle.Handle.ToString(),d.Normal,ProbeTextHeight(d));
    static object ProbeDimJson(ProbeDimension d)=>new {handle=d.Handle,defpoint2=P(d.A),defpoint3=P(d.B),dimline=P(d.Line),text_position=P(d.Text),angle=d.Angle,measurement=d.Measure,text=d.Value,style=d.Style,normal=V(d.Normal)};
    static HashSet<string> ProbeDictionaryKeys(DBDictionary dictionary)
    {
        var keys=new HashSet<string>();using var entries=dictionary.GetEnumerator();
        while(entries.MoveNext())keys.Add(entries.Key);
        return keys;
    }
    static void CheckProbeDim(RotatedDimension d,ProbeDimension before,Vector3d delta)
    {
        var after=ProbeDim(d);
        Write("poly-dim-current.json",new {before=ProbeDimJson(before),after=ProbeDimJson(after),expected_delta=V(delta)});
        Require(after.A.DistanceTo(before.A+delta)<1e-6 && after.B.DistanceTo(before.B+delta)<1e-6 && after.Line.DistanceTo(before.Line+delta)<1e-6 && after.Text.DistanceTo(before.Text+delta)<1e-6,"Polyline DIM control points did not translate: "+before.Handle);
        Require(Math.Abs(after.Measure-before.Measure)<1e-6 && Math.Abs(after.Angle-before.Angle)<1e-10 && after.Value==before.Value && after.Style==before.Style && after.Normal.IsEqualTo(before.Normal,new Tolerance(1e-10,1e-10)),"Polyline DIM properties changed: "+before.Handle);
    }

    static Point3d StretchPoint(JsonElement value)
    {
        var a=value.EnumerateArray().Select(v=>v.GetDouble()).ToArray();Require(a.Length==3 && a.All(double.IsFinite),"Stretch needs finite XYZ");return new Point3d(a[0],a[1],a[2]);
    }
    static object ProbeTextGeometry(Dimension dim)
    {
        var tr=dim.Database.TransactionManager.TopTransaction;
        var texts=new List<object>();
        foreach(ObjectId id in (BlockTableRecord)tr.GetObject(dim.DimBlockId,OpenMode.ForRead))
            if(tr.GetObject(id,OpenMode.ForRead) is MText text)
                texts.Add(new {location=P(text.Location),actual_height=text.ActualHeight,actual_width=text.ActualWidth,text_height=text.TextHeight,attachment=text.Attachment.ToString(),contents=text.Contents});
        return texts;
    }
    static void CheckStretchDimension(RotatedDimension dim,ProbeDimension before,JsonElement expected)
    {
        var a=StretchPoint(expected.GetProperty("a"));var b=StretchPoint(expected.GetProperty("b"));var after=ProbeDim(dim);
        var axis=new Vector3d(Math.Cos(before.Angle),Math.Sin(before.Angle),0);var normal=new Vector3d(-axis.Y,axis.X,0);
        var midpointDelta=((a-before.A)+(b-before.B))*.5;var text=before.Text+axis*midpointDelta.DotProduct(axis);
        // Default middle-center text moves by half its actual regenerated glyph height.
        // Keep the source text-to-dimension-line gap, including its original side.
        var side=Math.Sign((before.Text-before.Line).DotProduct(normal));
        Require(side!=0,"Stretch needs text offset from DIM line");
        text+=normal*(side*(after.TextHeight-before.TextHeight)*.5);
        Write("poly-dim-current.json",new {before=ProbeDimJson(before),after=ProbeDimJson(after),expected_a=P(a),expected_b=P(b),expected_text=P(text),text_geometry=ProbeTextGeometry(dim)});
        Require(after.A.DistanceTo(a)<1e-6 && after.B.DistanceTo(b)<1e-6,"Stretch DIM points mismatch: "+before.Handle);
        Require(Math.Abs(after.Measure-expected.GetProperty("measurement").GetDouble())<1e-6,"Stretch DIM measurement mismatch: "+before.Handle);
        Require(Math.Abs((after.Line-before.Line).DotProduct(normal))<1e-6 && Math.Abs(after.Line.Z-before.Line.Z)<1e-6 && after.Text.DistanceTo(text)<1e-6,"Stretch DIM display positioning mismatch: "+before.Handle);
        Require(Math.Abs(after.Angle-before.Angle)<1e-10 && after.Value==before.Value && after.Style==before.Style && after.Normal.IsEqualTo(before.Normal,new Tolerance(1e-10,1e-10)),"Stretch DIM style/angle/normal changed: "+before.Handle);
    }

    static HashSet<string> ProbeVisuals(Database db,Transaction tr,IEnumerable<string> dimensions)
    {
        var result=new HashSet<string>();
        foreach(var handle in dimensions)
        {
            var dim=(Dimension)tr.GetObject(Id(db,handle),OpenMode.ForRead);
            if(!dim.DimBlockId.IsNull)
                foreach(ObjectId id in (BlockTableRecord)tr.GetObject(dim.DimBlockId,OpenMode.ForRead))result.Add(id.Handle.ToString());
        }
        return result;
    }

    static object ProbeSubentity(AssocGeomDependency geom,Polyline poly)
    {
        var errors=new List<object>();var data=new Dictionary<string,object?> {
            ["dependency_handle"]=geom.Handle.ToString(),["source_handle"]=geom.DependentOnObject.Handle.ToString(),
            ["action_handle"]=geom.OwningAction.Handle.ToString(),["subentity_type"]=((SubentityType)geom.SubentityType).ToString(),
            ["is_caching_geometry"]=geom.IsCachingSubentityGeometry};
        try {data["persistent_id_class"]=geom.PersistentSubentId?.GetType().FullName;}
        catch(System.Exception e) {errors.Add(new {property="PersistentSubentId",error=e.GetType().Name,message=e.Message});}
        try
        {
            var ids=((System.Collections.IEnumerable)geom.TransientSubentIds).Cast<SubentityId>().ToArray();
            Require(ids.Length<=16,"Subentity probe limit exceeded");
            data["transient_ids"]=ids.Select(id=>new {type=id.Type.ToString(),index=id.IndexPtr.ToInt64()}).ToArray();
        }
        catch(System.Exception e) {errors.Add(new {property="TransientSubentIds",error=e.GetType().Name,message=e.Message});}
        if(geom.SubentityType==(uint)SubentityType.Vertex)
        {
            try
            {
                var points=((System.Collections.IEnumerable)geom.VertexSubentityGeometry).Cast<Point3d>().ToArray();
                Require(points.Length<=16,"Vertex probe limit exceeded");
                data["vertices"]=points.Select(p=>new {point=P(p),matching_polyline_vertices=Enumerable.Range(0,poly.NumberOfVertices).Where(i=>poly.GetPoint3dAt(i).DistanceTo(p)<1e-6).ToArray()}).ToArray();
            }
            catch(System.Exception e) {errors.Add(new {property="VertexSubentityGeometry",error=e.GetType().Name,message=e.Message});}
        }
        if(geom.SubentityType==(uint)SubentityType.Edge)
        {
            Curve3d[] curves=Array.Empty<Curve3d>();
            try
            {
                curves=((System.Collections.IEnumerable)geom.EdgeSubentityGeometry).Cast<Curve3d>().ToArray();
                Require(curves.Length<=16,"Edge probe limit exceeded");
                data["edges"]=curves.Select(c=>c is LineSegment3d line ? (object)new {type=c.GetType().FullName,start=P(line.StartPoint),end=P(line.EndPoint)} : new {type=c.GetType().FullName}).ToArray();
            }
            catch(System.Exception e) {errors.Add(new {property="EdgeSubentityGeometry",error=e.GetType().Name,message=e.Message});}
            finally {foreach(var curve in curves)curve.Dispose();}
        }
        data["errors"]=errors;data["endpoint_binding_proven"]=false;return data;
    }
    static object ProbeSubentitiesReport(Database db,Transaction tr,string root,Dictionary<string,string> actions,Dictionary<string,string> actionDimensions,string sourceHash)
    {
        var poly=(Polyline)tr.GetObject(Id(db,root),OpenMode.ForRead);
        return new {status="inspected_native_subentities",source_sha256=sourceHash,polyline_handle=root,
            dependencies=actions.Select(entry=>new {dimension_handle=actionDimensions[entry.Key],geometry=ProbeSubentity((AssocGeomDependency)tr.GetObject(Id(db,entry.Value),OpenMode.ForRead),poly)}).ToArray(),
            action_parameters=actions.Keys.Select(h=>ProbeActionParameters(db,tr,h)).ToArray(),
            policy="Read-only native getter evidence. Object or edge dependency alone does not prove a DIM endpoint-to-vertex binding.",edit_authorization=false,customer_revision_created=false};
    }
    static object ProbeActionParameters(Database db,Transaction tr,string handle)
    {
        var action=(AssocAction)tr.GetObject(Id(db,handle),OpenMode.ForRead);
        var body=tr.GetObject(action.ActionBody,OpenMode.ForRead);var rows=new List<object>();var errors=new List<object>();
        var queue=new Queue<(DBObject obj,int depth)>();queue.Enqueue((action,0));queue.Enqueue((body,0));var seen=new HashSet<ObjectId>();
        while(queue.Count>0 && rows.Count<32)
        {
            var (obj,depth)=queue.Dequeue();if(!seen.Add(obj.ObjectId))continue;
            var values=new Dictionary<string,object?>();
            foreach(var name in new[]{"Name","ParamCount","OwnedParams"})
            {
                var property=obj.GetType().GetProperty(name);if(property==null || !property.CanRead)continue;
                try
                {
                    var value=property.GetValue(obj);
                    if(value is string || value is int)values[name]=value;
                    else if(value is System.Collections.IEnumerable list)
                    {
                        var ids=list.Cast<object>().OfType<ObjectId>().Take(33).ToArray();Require(ids.Length<=32,"Action parameter limit exceeded");
                        values[name]=ids.Select(id=>id.Handle.ToString()).ToArray();
                        if(depth<3)foreach(var id in ids)queue.Enqueue((tr.GetObject(id,OpenMode.ForRead),depth+1));
                    }
                }
                catch(System.Exception e){errors.Add(new {handle=obj.Handle.ToString(),property=name,error=e.GetType().Name});}
            }
            if(obj is AssocVertexActionParam vertex)
            {
                try
                {
                    using var reference=vertex.GetVertexRef();var fields=new Dictionary<string,object?>();
                    foreach(var name in new[]{"Point","EntityId","SubentId","IsEmpty","IsValid"})
                    {
                        var property=reference.GetType().GetProperty(name);if(property==null || !property.CanRead)continue;
                        var value=property.GetValue(reference);
                        if(value is Point3d point)fields[name]=P(point);else if(value is ObjectId id)fields[name]=id.IsNull?null:id.Handle.ToString();else if(value is bool flag)fields[name]=flag;
                    }
                    values["vertex_ref"]=fields;
                }
                catch(System.Exception e){errors.Add(new {handle=obj.Handle.ToString(),property="GetVertexRef",error=e.GetType().Name});}
            }
            rows.Add(new {handle=obj.Handle.ToString(),native_class=obj.GetRXClass().Name,managed_class=obj.GetType().FullName,depth,values});
        }
        return new {action_handle=handle,rows,errors,truncated=queue.Count>0,endpoint_binding_proven=false};
    }

    [CommandMethod("MECHANICALPOLYDIMPROBE",CommandFlags.Session)]
    public void PolylineDimensionProbe()
    {
        try { PolylineDimensionProbeChecked(); }
        catch(System.Exception error) { Write("poly-dim-error.json",new {type=error.GetType().FullName,message=error.Message,stack=error.StackTrace}); }
    }

    static void PolylineDimensionProbeChecked()
    {
        using var input=JsonDocument.Parse(File.ReadAllBytes("poly-dim-probe.json"));var cfg=input.RootElement;
        Require(Hash("input.cad")==S(cfg,"source_sha256"),"Polyline probe source hash mismatch");
        var values=cfg.GetProperty("delta").EnumerateArray().Select(e=>e.GetDouble()).ToArray();
        Require(values.Length==3 && values.All(double.IsFinite) && Math.Abs(values[2])<1e-10,"Polyline probe needs finite XY translation");
        var delta=new Vector3d(values[0],values[1],values[2]);var root=S(cfg,"polyline_handle");
        bool stretch=cfg.TryGetProperty("stretch_points",out var stretchJson);
        var stretchPoints=stretch?stretchJson.EnumerateArray().Select(StretchPoint).ToArray():Array.Empty<Point3d>();
        var stretchDims=stretch?cfg.GetProperty("stretch_dimensions").EnumerateArray().ToDictionary(e=>S(e,"handle"),e=>e):new Dictionary<string,JsonElement>();
        var nativeVertexBindings=cfg.TryGetProperty("native_vertex_bindings",out var nativeBindingJson)?nativeBindingJson.EnumerateArray().ToDictionary(e=>S(e,"dimension_handle"),e=>e):new Dictionary<string,JsonElement>();
        Require(nativeVertexBindings.Count==0 || stretch,"Native endpoint update requires stretch mode");
        bool nativeAutoEndpoints=cfg.TryGetProperty("native_auto_endpoints",out var autoEndpointJson) && autoEndpointJson.GetBoolean();
        Require(!nativeAutoEndpoints || nativeVertexBindings.Count>0,"Native auto endpoint probe needs verified bindings");

        var legacy=cfg.GetProperty("legacy_associations").EnumerateArray().ToDictionary(e=>S(e,"association_ref"),e=>S(e,"dimension_handle"));
        Require(legacy.Count==4,"Polyline probe requires four independently bound legacy DIMASSOC records");
        using var db=new Database(false,true);db.ReadDwgFile(Path.GetFullPath("input.cad"),FileOpenMode.OpenForReadAndAllShare,true,null);db.CloseInput(true);
        var previous=HostApplicationServices.WorkingDatabase;HostApplicationServices.WorkingDatabase=db;
        try
        {
            var dimensions=new HashSet<string>();var actions=new Dictionary<string,string>();var actionDimensions=new Dictionary<string,string>();var actionDimDependencies=new Dictionary<string,string>();
            Dictionary<string,ProbeDimension> beforeDims;Dictionary<string,string> before;HashSet<string> beforeVisuals;
            object beforeSubentities;
            Point3d[] beforePoints;
            using(var tr=db.TransactionManager.StartTransaction())
            {
                var poly=tr.GetObject(Id(db,root),OpenMode.ForRead) as Polyline;
                Require(poly!=null && poly.Closed && poly.NumberOfVertices==8 && poly.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-8,1e-8)) && poly.ExtensionDictionary.IsNull,"Polyline probe needs plain closed eight-vertex XY polyline");
                Require(tr.GetObject(poly!.OwnerId,OpenMode.ForRead) is BlockTableRecord owner && owner.IsLayout,"Polyline probe requires layout owner");
                Require(Enumerable.Range(0,8).All(i=>Math.Abs(poly.GetBulgeAt(i))<1e-10),"Polyline probe requires straight edges");
                beforePoints=Enumerable.Range(0,8).Select(poly.GetPoint3dAt).ToArray();
                var reactors=poly.GetPersistentReactorIds().Cast<ObjectId>().ToArray();Require(reactors.Length==6,"Polyline probe requires complete six-reactor group");
                foreach(var id in reactors)
                {
                    var obj=tr.GetObject(id,OpenMode.ForRead);
                    if(obj is AssocGeomDependency geom)
                    {
                        Require(geom.DependentOnObject==poly.ObjectId,"Polyline geometric dependency points elsewhere");
                        var action=(AssocAction)tr.GetObject(geom.OwningAction,OpenMode.ForRead);
                        Require(tr.GetObject(action.ActionBody,OpenMode.ForRead).GetRXClass().Name=="AcDbAssocRotatedDimActionBody","Polyline probe requires native rotated-DIM action");
                        var deps=action.GetDependencies(true,true).Cast<ObjectId>().Select(h=>(AssocDependency)tr.GetObject(h,OpenMode.ForRead)).ToArray();
                        Require(deps.Length==2 && deps.Any(d=>d.ObjectId==geom.ObjectId) && deps.All(d=>d.OwningAction==action.ObjectId),"Polyline DIM action dependency mismatch");
                        var other=deps.Single(d=>d.ObjectId!=geom.ObjectId);var dim=tr.GetObject(other.DependentOnObject,OpenMode.ForRead) as RotatedDimension;
                        Require(dim!=null && dim.OwnerId==poly.OwnerId && dim.ExtensionDictionary.IsNull && dim.GetPersistentReactorIds().Cast<ObjectId>().ToHashSet().SetEquals(new[] {other.ObjectId}),"Native DIM has unsupported owner/dictionary/reactors");
                        dimensions.Add(dim!.Handle.ToString());actions.Add(action.Handle.ToString(),geom.Handle.ToString());
                        actionDimensions.Add(action.Handle.ToString(),dim.Handle.ToString());actionDimDependencies.Add(action.Handle.ToString(),other.Handle.ToString());
                    }
                    else
                    {
                        Require(obj.GetRXClass().Name=="AcDbDimAssoc" && legacy.ContainsKey(obj.Handle.ToString()),"Polyline has an unbound legacy reactor");
                        var dictionary=tr.GetObject(obj.OwnerId,OpenMode.ForRead) as DBDictionary;
                        Require(dictionary!=null && ProbeDictionaryKeys(dictionary).SetEquals(new[] {"ACAD_DIMASSOC"}) && dictionary.GetAt("ACAD_DIMASSOC")==id,"Legacy DIMASSOC dictionary mismatch");
                        var dim=tr.GetObject(dictionary!.OwnerId,OpenMode.ForRead) as RotatedDimension;
                        Require(dim!=null && dim.Handle.ToString()==legacy[obj.Handle.ToString()] && dim.OwnerId==poly.OwnerId && dim.ExtensionDictionary==dictionary.ObjectId && dim.GetPersistentReactorIds().Cast<ObjectId>().ToHashSet().SetEquals(new[] {id}),"Legacy DIMASSOC DIM ownership mismatch");
                        dimensions.Add(dim!.Handle.ToString());
                    }
                }
                Require(actions.Count==2 && dimensions.Count==6 && legacy.Values.All(dimensions.Contains),"Incomplete polyline DIM closure");
                if(cfg.TryGetProperty("expected_dimension_handles",out var expectedDimensions))
                {
                    Require(dimensions.SetEquals(expectedDimensions.EnumerateArray().Select(e=>e.GetString()!)),"Discovered DIM group does not match native source");
                    Require(cfg.TryGetProperty("expected_action_handles",out var expectedActions) && actions.Keys.ToHashSet().SetEquals(expectedActions.EnumerateArray().Select(e=>e.GetString()!)),"Discovered action group does not match native source");
                }
                beforeSubentities=ProbeSubentitiesReport(db,tr,root,actions,actionDimensions,Hash("input.cad"));
                if(cfg.TryGetProperty("inspect_subentities_only",out var inspectOnly) && inspectOnly.GetBoolean())
                {
                    Write("poly-dim-subentities.json",beforeSubentities);
                    return;
                }
                before=CenterState(db,tr);beforeVisuals=ProbeVisuals(db,tr,dimensions);
                var visualBlocks=dimensions.Select(h=>((Dimension)tr.GetObject(Id(db,h),OpenMode.ForRead)).DimBlockId).Where(id=>!id.IsNull).Select(id=>id.Handle.ToString()).ToHashSet();
                foreach(var entry in before.Where(p=>!dimensions.Contains(p.Key)))
                {
                    using var row=JsonDocument.Parse(entry.Value);
                    foreach(var key in new[] {"dimension_block_handle","block_handle"})
                        if(row.RootElement.TryGetProperty(key,out var value) && value.ValueKind==JsonValueKind.String)
                            Require(!visualBlocks.Contains(value.GetString()!),"DIM visual block has users outside probe group");
                }
                beforeDims=dimensions.ToDictionary(h=>h,h=>ProbeDim((RotatedDimension)tr.GetObject(Id(db,h),OpenMode.ForWrite)));
                if(stretch)Write("poly-dim-source-text.json",dimensions.ToDictionary(h=>h,h=>ProbeTextGeometry((Dimension)tr.GetObject(Id(db,h),OpenMode.ForRead))));
                if(stretch)
                {
                    Require(stretchPoints.Length==8 && stretchDims.Keys.ToHashSet().SetEquals(dimensions),"Incomplete stretch points/DIM set");
                    var oldPoints=cfg.GetProperty("stretch_before_points").EnumerateArray().Select(StretchPoint).ToArray();
                    Require(oldPoints.Length==8 && oldPoints.Zip(beforePoints).All(p=>p.First.DistanceTo(p.Second)<1e-6),"Stretch source points changed");
                    double dx=stretchPoints[5].X-beforePoints[5].X;
                    Require(Math.Abs(dx)>1e-7 && Enumerable.Range(0,4).All(i=>stretchPoints[i].DistanceTo(beforePoints[i])<1e-6) && Enumerable.Range(4,4).All(i=>stretchPoints[i].DistanceTo(beforePoints[i]+new Vector3d(dx,0,0))<1e-6),"Stretch must keep left half and translate right half rigidly");
                    Require(beforePoints.Take(4).Max(p=>p.X)<beforePoints.Skip(4).Min(p=>p.X) && stretchPoints.Take(4).Max(p=>p.X)<stretchPoints.Skip(4).Min(p=>p.X),"Stretch left/right partition collapsed");
                    Require(Math.Abs(beforePoints[0].Y-beforePoints[7].Y)<1e-6 && Math.Abs(beforePoints[3].Y-beforePoints[4].Y)<1e-6 && Enumerable.Range(0,3).All(i=>beforePoints[i].Y>beforePoints[i+1].Y) && Enumerable.Range(4,3).All(i=>beforePoints[i].Y<beforePoints[i+1].Y),"Stretch needs canonical chamfered profile");
                    Require(poly.ConstantWidth==0 && Enumerable.Range(0,8).All(i=>poly.GetStartWidthAt(i)==0 && poly.GetEndWidthAt(i)==0),"Stretch does not support wide polylines");
                    foreach(var handle in dimensions)
                    {
                        var d=(RotatedDimension)tr.GetObject(Id(db,handle),OpenMode.ForRead);var expected=stretchDims[handle];
                        Require(d.UsingDefaultTextPosition,"Stretch probe requires default DIM text position: "+handle);
                        Require(beforeDims[handle].A.DistanceTo(StretchPoint(expected.GetProperty("before_a")))<1e-6 && beforeDims[handle].B.DistanceTo(StretchPoint(expected.GetProperty("before_b")))<1e-6,"Stretch source DIM points changed: "+handle);
                    }
                    foreach(var entry in nativeVertexBindings)
                    {
                        var binding=entry.Value;var action=S(binding,"action_handle");var index=binding.GetProperty("vertex_index").GetInt32();
                        Require(S(binding,"field")=="defpoint3" && index>=0 && index<8 && actions.ContainsKey(action)
                            && actionDimensions[action]==entry.Key && actions[action]==S(binding,"geometry_dependency"),"Native endpoint binding topology mismatch");
                        var geom=(AssocGeomDependency)tr.GetObject(Id(db,actions[action]),OpenMode.ForRead);
                        Require(geom.SubentityType==(uint)SubentityType.Vertex && !geom.IsCachingSubentityGeometry,"Native endpoint needs live vertex geometry");
                        var points=((System.Collections.IEnumerable)geom.VertexSubentityGeometry).Cast<Point3d>().ToArray();
                        var ids=((System.Collections.IEnumerable)geom.TransientSubentIds).Cast<SubentityId>().ToArray();
                        Require(points.Length==1 && points[0].DistanceTo(beforePoints[index])<1e-6 && points[0].DistanceTo(beforeDims[entry.Key].B)<1e-6
                            && points[0].DistanceTo(beforeDims[entry.Key].A)>1e-6 && ids.Length==1 && ids[0].IndexPtr.ToInt64()==binding.GetProperty("transient_subentity_index").GetInt64(),"Native endpoint binding geometry mismatch");
                        Require(stretchPoints[index].DistanceTo(StretchPoint(stretchDims[entry.Key].GetProperty("b")))<1e-6,"Native endpoint target differs from bound vertex");
                    }
                }

                tr.Commit();
            }
            void VerifyDimension(string handle,RotatedDimension dim)
            {if(stretch)CheckStretchDimension(dim,beforeDims[handle],stretchDims[handle]);else CheckProbeDim(dim,beforeDims[handle],delta);}
            using(var tr=db.TransactionManager.StartTransaction())
            {
                var poly=(Polyline)tr.GetObject(Id(db,root),OpenMode.ForWrite);
                if(stretch)
                {
                    for(int i=0;i<8;i++)poly.SetPointAt(i,new Point2d(stretchPoints[i].X,stretchPoints[i].Y));
                    foreach(var handle in dimensions)
                    {
                        var dim=(RotatedDimension)tr.GetObject(Id(db,handle),OpenMode.ForWrite);var targetA=StretchPoint(stretchDims[handle].GetProperty("a"));
                        if(!nativeAutoEndpoints || dim.XLine1Point.DistanceTo(targetA)>1e-6)dim.XLine1Point=targetA;
                        if(!nativeAutoEndpoints || !nativeVertexBindings.ContainsKey(handle))dim.XLine2Point=StretchPoint(stretchDims[handle].GetProperty("b"));
                    }
                }
                else
                {
                    poly.TransformBy(Matrix3d.Displacement(delta));
                    foreach(var handle in dimensions)((RotatedDimension)tr.GetObject(Id(db,handle),OpenMode.ForWrite)).TransformBy(Matrix3d.Displacement(delta));
                }
                tr.Commit();
            }
            using(var tr=db.TransactionManager.StartTransaction())
            {
                foreach(var entry in actions)
                {
                    ((AssocGeomDependency)tr.GetObject(Id(db,entry.Value),OpenMode.ForWrite)).SetStatus(AssocStatus.ChangedDirectlyAssocStatus,true);
                    var action=(AssocAction)tr.GetObject(Id(db,entry.Key),OpenMode.ForWrite);action.SetStatus(AssocStatus.ChangedDirectlyAssocStatus,false,false);action.Evaluate(AssocManager.GlobalEvaluationMultiCallback());
                    Write("poly-dim-native-evaluation.json",new {action_handle=entry.Key,dimension_handle=actionDimensions[entry.Key],status=action.Status.ToString(),native_auto_endpoints=nativeAutoEndpoints,
                        actual=ProbeDimJson(ProbeDim((RotatedDimension)tr.GetObject(Id(db,actionDimensions[entry.Key]),OpenMode.ForRead)))});
                    Require(action.Status==AssocStatus.IsUpToDateAssocStatus,"Polyline DIM action not up to date: "+entry.Key+" "+action.Status);
                }
                foreach(var handle in dimensions)
                {
                    var dim=(RotatedDimension)tr.GetObject(Id(db,handle),OpenMode.ForWrite);dim.RecomputeDimensionBlock(true);VerifyDimension(handle,dim);
                }
                tr.Commit();
            }
            db.SaveAs(Path.GetFullPath("poly-dim-probe.dwg"),DwgVersion.AC1032);
            using var reopened=new Database(false,true);reopened.ReadDwgFile(Path.GetFullPath("poly-dim-probe.dwg"),FileOpenMode.OpenForReadAndAllShare,true,null);reopened.CloseInput(true);
            HostApplicationServices.WorkingDatabase=reopened;
            try
            {
                using(var tr=reopened.TransactionManager.StartTransaction())
                {
                    void CheckAction(string handle)
                    {
                        var action=(AssocAction)tr.GetObject(Id(reopened,handle),OpenMode.ForRead);
                        Require(tr.GetObject(action.ActionBody,OpenMode.ForRead).GetRXClass().Name=="AcDbAssocRotatedDimActionBody","Polyline DIM action body changed");
                        var geom=(AssocGeomDependency)tr.GetObject(Id(reopened,actions[handle]),OpenMode.ForRead);
                        var dep=(AssocDependency)tr.GetObject(Id(reopened,actionDimDependencies[handle]),OpenMode.ForRead);
                        Require(geom.OwningAction==action.ObjectId && dep.OwningAction==action.ObjectId && geom.DependentOnObject==Id(reopened,root) && dep.DependentOnObject==Id(reopened,actionDimensions[handle]) && action.GetDependencies(true,true).Cast<ObjectId>().ToHashSet().SetEquals(new[] {geom.ObjectId,dep.ObjectId}),"Polyline DIM action source binding changed");
                    }
                    foreach(var handle in actions.Keys)CheckAction(handle);
                    foreach(var handle in dimensions)VerifyDimension(handle,(RotatedDimension)tr.GetObject(Id(reopened,handle),OpenMode.ForWrite));
                    var poly=(Polyline)tr.GetObject(Id(reopened,root),OpenMode.ForRead);
                    Require(poly.NumberOfVertices==8 && Enumerable.Range(0,8).All(i=>poly.GetPoint3dAt(i).DistanceTo(stretch?stretchPoints[i]:beforePoints[i]+delta)<1e-6),"Polyline readback translation mismatch");
                    foreach(var entry in actions)
                    {
                        var action=(AssocAction)tr.GetObject(Id(reopened,entry.Key),OpenMode.ForWrite);
                        Require(action.Status==AssocStatus.IsUpToDateAssocStatus,"Saved polyline DIM action is stale");
                        action.SetStatus(AssocStatus.ChangedDirectlyAssocStatus,false,false);action.Evaluate(AssocManager.GlobalEvaluationMultiCallback());
                        Require(action.Status==AssocStatus.IsUpToDateAssocStatus,"Reopened polyline DIM action failed evaluation");
                    }
                    foreach(var handle in dimensions)VerifyDimension(handle,(RotatedDimension)tr.GetObject(Id(reopened,handle),OpenMode.ForWrite));
                    foreach(var handle in actions.Keys)CheckAction(handle);
                    var after=CenterState(reopened,tr);var visuals=ProbeVisuals(reopened,tr,dimensions);var selected=dimensions.Append(root).ToHashSet();
                    Require(SameNativeSnapshot(before[root],after[root],new HashSet<string>{"bbox","vertices"}),"Polyline properties/topology changed");
                    foreach(var handle in dimensions)Require(SameNativeSnapshot(before[handle],after[handle],new HashSet<string>{"bbox","dimension_block_handle",stretch?"measurement":"_unused"}),"DIM properties/topology changed: "+handle);
                    var beforeRest=before.Where(p=>!selected.Contains(p.Key) && !beforeVisuals.Contains(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);
                    var afterRest=after.Where(p=>!selected.Contains(p.Key) && !visuals.Contains(p.Key)).ToDictionary(p=>p.Key,p=>p.Value);
                    Require(beforeRest.Keys.ToHashSet().SetEquals(afterRest.Keys) && beforeRest.All(p=>SameNativeSnapshot(p.Value,afterRest[p.Key])),"Polyline probe changed objects outside DIM visual ownership");
                    Write("poly-dim-receipt.json",new {status=stretch?"validated_polyline_dimension_stretch_probe":"validated_polyline_dimension_translation_probe",source_sha256=Hash("input.cad"),output_sha256=Hash("poly-dim-probe.dwg"),polyline_handle=root,dimension_handles=dimensions.OrderBy(h=>h).ToArray(),action_handles=actions.Keys.OrderBy(h=>h).ToArray(),delta=values,
                        unselected_inventory_entries_verified=beforeRest.Count,excluded_owned_dimension_visuals_before=beforeVisuals.Count,excluded_owned_dimension_visuals_after=visuals.Count,persisted_state_verified_before_evaluation=true,reopened_evaluation_stable=true,
                        native_dependencies=NativeDependencies(reopened,tr,selected),
                        native_auto_endpoints=nativeAutoEndpoints,native_updated_endpoints=nativeVertexBindings.Keys.Where(h=>nativeAutoEndpoints).OrderBy(h=>h).Select(h=>new {dimension_handle=h,field="defpoint3",writer_assigned=false}).ToArray(),
                        native_subentities_before=beforeSubentities,native_subentities_after=ProbeSubentitiesReport(reopened,tr,root,actions,actionDimensions,Hash("poly-dim-probe.dwg")),
                        native_text_heights=dimensions.ToDictionary(h=>h,h=>new {before=beforeDims[h].TextHeight,after=ProbeTextHeight((Dimension)tr.GetObject(Id(reopened,h),OpenMode.ForRead))}),
                        customer_revision_created=false,edit_authorization=false});
                    tr.Commit();
                }
                reopened.DxfOut(Path.GetFullPath("poly-dim-probe.dxf"),16,DwgVersion.AC1032);
            }
            finally {HostApplicationServices.WorkingDatabase=db;}
        }
        finally {HostApplicationServices.WorkingDatabase=previous;}
    }
}


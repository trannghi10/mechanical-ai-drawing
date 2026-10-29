"""Synthetic fixture with a nested endpoint used by a perpendicular DIM snap."""
import json
import ezdxf
from ezdxf.entities import DXFTagStorage
from cad.geometry import snapshot
from cad.dimensions import dimension_snapshot
from cad.dimension_associations import source_binding,follow
from cad.edit_engine import Operation


def make_fixture():
    doc=ezdxf.new('R2018');doc.units=4;m=doc.modelspace();y=76.499997
    profile=m.add_lwpolyline([(14,90.5),(0,y),(0,14),(14,0),(76.5,0),(90.5,14),(90.5,76.5),(76.5,90.5)],close=True)
    wrapper=m.add_linear_dim(base=(90.5,100),p1=(0,y),p2=(90.5,y),angle=0);wrapper.render();dim=wrapper.dimension
    extension=dim.new_extension_dict();handle=doc.entitydb.next_handle()
    tags=['0','DIMASSOC','5',handle,'330',extension.dictionary.dxf.handle,'100','AcDbDimAssoc','330',dim.dxf.handle,'90','3','70','0','71','0']
    for snap,marker,parameter,has_last,z in [(1,1,1,0,2e50),(8,6,(y-14)/62.5,1,0),(1,1,1,0,2e50)]:
        tags += ['1','AcDbOsnapPointRef','72',str(snap),'331',profile.dxf.handle,'73','2','91',str(marker),'40',str(parameter),'10','0','20','0','30',str(z),'75',str(has_last)]
    assoc=DXFTagStorage.from_text('\n'.join(tags)+'\n',doc);doc.entitydb.add(assoc);doc.objects.add_object(assoc)
    extension['ACAD_DIMASSOC']=assoc;assoc.set_reactors([extension.dictionary.dxf.handle]);dim.set_reactors([handle]);profile.set_reactors([handle]);doc.header['$DIMASSOC']=2
    return doc,profile,dim,assoc


def width_operations(profile,dim,width=95,anchor_dy=0):
    before=snapshot(profile);after=json.loads(json.dumps(before));delta=width-90.5
    for point in after['points'][4:]:point[0]+=delta
    after['points'][1][1]+=anchor_dy
    op=Operation(ref=profile.dxf.handle,action='replace_geometry',before=json.dumps(before),after=json.dumps(after),xyz=[],reason='synthetic perpendicular association width')
    geometry=dimension_snapshot(dim);binding=source_binding(dim)
    assert binding['status']=='verified_source_points',binding
    record=dict(dimension_association=binding,coordinate_frame='layout:Model')
    records={profile.dxf.handle:dict(type='LWPOLYLINE',geometry=before,coordinate_frame='layout:Model')}
    result=follow(record,geometry,geometry,records,[op])
    return [op,Operation(ref=dim.dxf.handle,action='replace_geometry',before=json.dumps(geometry),after=json.dumps(result),xyz=[],reason='follow real perpendicular foot')]

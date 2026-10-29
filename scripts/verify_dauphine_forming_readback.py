"""Measure the actual ODA reopened DWG, including native DIM tolerance."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf8')
import ezdxf
from ezdxf import bbox
from cad.dimensions import native_tolerance
from cad.edit_engine import digest
from backend.services import catalog_service as storage


def main(revision_id):
    doc_id='34ee84f35e1a44fb81c56044397a0fff'
    folder=storage.folder(doc_id)/'revisions'/revision_id
    receipt_path=Path('storage/validation-fixtures/dauphine-combined')/revision_id/'receipt.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf8'))
    proof=receipt['forming_review'][0]
    assert proof['status']=='verified_source_calibrated_blank',proof
    reopened=folder/'reopen-selection/modified.dxf'
    document=ezdxf.readfile(reopened)
    dim=document.entitydb[proof['dimension_ref']]
    length=abs(dim.get_measurement()*dim.override().get('dimlfac',1))
    assert abs(length-proof['target_nominal_mm'])<1e-6
    assert native_tolerance(dim)==proof['native_tolerance']
    dimensions={ref:document.entitydb[ref].get_measurement() for ref in ['3B8BA7','3B8BAA','3E1110','3B8BE3','3B8BB9','3E5E00','3E5DF3','3E5DFD']}
    assert abs(dimensions['3E1110']-(2500-10-length))<1e-6
    assert abs(dimensions['3B8BE3']+dimensions['3B8BB9']+697-1220)<1e-6
    assert abs(dimensions['3E5E00']-953)<1e-6
    assert abs(dimensions['3E5DF3']-823)<1e-6 and abs(dimensions['3E5DFD']-130)<1e-6
    copies={}
    for ref in ['3B9078','3B9117']:
        entity=document.entitydb[ref]
        bound=bbox.extents(entity.virtual_entities())
        size=[bound.size.x,bound.size.y]
        assert abs(size[0]-length)<1e-6 and abs(size[1]-697)<1e-6,size
        copies[ref]=size
    source=storage.folder(doc_id)/storage.read_status(doc_id)['dxf']
    assert digest(source)==receipt['source_hash']
    import urllib.request
    downloaded=urllib.request.urlopen('http://127.0.0.1:8765'+receipt['job']['download_url'],timeout=30).read()
    import hashlib
    assert hashlib.sha256(downloaded).hexdigest()==receipt['dwg_hash']
    from backend.services.revision_service import revision_preview
    from cad.vision import rasterize_svg
    for sid,name in [('3B8A74','formed-blank-after'),('3B8B05','cut-blank-after')]:
        svg=revision_preview(doc_id,revision_id,sid)
        (receipt_path.parent/(name+'.svg')).write_text(svg,encoding='utf8')
        (receipt_path.parent/(name+'.png')).write_bytes(rasterize_svg(svg,width=1400))
    readback=dict(revision_id=revision_id,source_unchanged=True,dwg_hash=receipt['dwg_hash'],http_download='200 hash matched',
        native_dimensions_mm=dimensions,blank_copy_bounds_mm=copies,native_tolerance=native_tolerance(dim),
        forming_proof=proof,complete_product_backup=False)
    storage.write_json(receipt_path.parent/'forming-readback.json',readback)
    print(json.dumps(readback,ensure_ascii=False,indent=2))


if __name__=='__main__':main(sys.argv[1])

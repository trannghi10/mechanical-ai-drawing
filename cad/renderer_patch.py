"""Patches for ezdxf rendering to prevent black masks and blank boxes."""
from ezdxf.addons.drawing import mtext_complex, frontend
from ezdxf.addons.drawing.backend import BackendProperties
from ezdxf.npshapes import NumpyPoints2d
from ezdxf.math import Vec2

# This version belongs to rendered images, never to sheet detection or CAD data.
# All persistent SVG caches must include it so old black masks cannot survive
# a renderer fix, a source re-import or a change of the selected crop.
RENDER_VERSION=6


def render_cache_key(source,scope):
    import hashlib,json
    from cad.edit_engine import digest
    value=[RENDER_VERSION,digest(source),scope]
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf8')).hexdigest()[:24]


def cached_svg(path,render):
    """Publish an SVG atomically; a failed renderer never publishes a cache."""
    from pathlib import Path
    import uuid
    path=Path(path)
    if path.exists():return path.read_text(encoding='utf8')
    content=render();temporary=path.with_suffix('.'+uuid.uuid4().hex[:8]+'.tmp')
    try:
        temporary.write_text(content,encoding='utf8');temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return content

_ORIG_COLUMN_BG_RENDER = mtext_complex.ColumnBackgroundRenderer.render
_ORIG_DRAW_OLE2FRAME = frontend.UniversalFrontend.draw_ole2frame_entity

def patched_column_bg_render(self, left, bottom, right, top, m=None):
    """Render MText background mask with clean white fill instead of forced black box."""
    offset = self.offset
    vertices = list(mtext_complex.corner_vertices(
        left - offset, bottom - offset, right + offset, top + offset, m
    ))
    if self.bg_properties is not None:
        # Resolve target backend through the pipeline stages
        stage = self.backend
        while hasattr(stage, '_pipeline'):
            stage = stage._pipeline
        while hasattr(stage, 'next_stage'):
            stage = stage.next_stage
        out_backend = getattr(stage, 'backend', stage)
        
        white_prop = BackendProperties(
            color='#ffffff',
            lineweight=self.bg_properties.lineweight,
            layer=self.bg_properties.layer,
            pen=self.bg_properties.pen,
            handle=''
        )
        try:
            out_backend.draw_filled_polygon(NumpyPoints2d([Vec2(v) for v in vertices]), white_prop)
        except Exception:
            pass
    if self.has_text_frame:
        self._render_outline(vertices)

def patched_draw_ole2frame(self, entity, properties):
    """Avoid drawing solid black rectangle for empty or unsupported OLE2FRAME objects."""
    # OLE objects without preview graphics should not obscure drawing content
    return

def apply_renderer_fixes():
    mtext_complex.ColumnBackgroundRenderer.render = patched_column_bg_render
    frontend.UniversalFrontend.draw_ole2frame_entity = patched_draw_ole2frame

# Apply automatically on import
apply_renderer_fixes()

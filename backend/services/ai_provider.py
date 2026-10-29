"""Explicit provider selection with an offline default and no cloud fallback."""
import os


def settings():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=True, encoding='utf-8-sig')
    provider=os.environ.get('AI_PROVIDER','ollama').lower().strip()
    if provider=='native':
        from backend.services.native_ai_service import settings as local_settings
        _,model=local_settings()
    elif provider=='ollama':
        from backend.services.ollama_service import settings as local_settings
        _,model=local_settings()
    elif provider=='openai':
        if os.environ.get('AI_OFFLINE','1').lower() not in ('0','false','no'):
            raise ValueError('Chế độ nội bộ đang bật; đã chặn OpenAI để bảo vệ dữ liệu CAD.')
        from backend.services.openai_service import settings as cloud_settings
        _,model=cloud_settings()
    elif provider=='gemini':
        if os.environ.get('AI_OFFLINE','1').lower() not in ('0','false','no'):
            raise ValueError('Chế độ nội bộ đang bật; đã chặn Gemini để bảo vệ dữ liệu CAD.')
        from backend.services.gemini_service import settings as cloud_settings
        _,model=cloud_settings()
    else:raise ValueError('AI_PROVIDER không được hỗ trợ')
    return provider,model


def generate_plan(prompt,parts,schema):
    provider,_=settings()
    if provider=='native':
        from backend.services.native_ai_service import generate_plan as generate
    elif provider=='ollama':
        from backend.services.ollama_service import generate_plan as generate
    elif provider=='openai':
        from backend.services.openai_service import generate_plan as generate
    else:
        from backend.services.gemini_service import generate_plan as generate
    return generate(prompt,parts,schema)

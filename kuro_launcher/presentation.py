"""Resolve the selected character through the canonical local model catalog."""
import json
import math
from pathlib import Path
from urllib.parse import unquote


def presentation_descriptor(open_llm_dir: Path, character) -> dict:
    if character is None:
        raise ValueError('尚未選擇角色')
    catalog = json.loads((open_llm_dir / 'model_dict.json').read_text(encoding='utf-8-sig'))
    model = next((m for m in catalog if m.get('name') == character.live2d_model_name), None)
    if not model:
        raise ValueError('角色模型未登錄')
    relative = unquote(str(model.get('url', ''))).replace('\\', '/')
    if not relative.startswith('/live2d-models/'):
        raise ValueError('角色模型必須位於本機 live2d-models')
    root = (open_llm_dir / 'live2d-models').resolve()
    target = (open_llm_dir / relative.lstrip('/')).resolve()
    if not target.is_relative_to(root) or not target.is_file() or not target.name.endswith('.model3.json'):
        raise ValueError('角色模型缺少檔案或超出允許目錄')
    scale = float(model.get('kScale', 0.45)) * 2
    if not math.isfinite(scale):
        raise ValueError('角色模型比例無效')
    return {'confUid': character.conf_uid, 'confName': character.conf_name,
            'modelPath': target.relative_to(root).as_posix(), 'scaleWidth': max(0.8, min(scale, 4))}

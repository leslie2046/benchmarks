"""DeepEval's Golden is the authoritative record schema; app state stays outside it."""
import json
import os
from typing import Literal

# Configure before the first SDK import. This integration never uses Confident AI.
os.environ['DEEPEVAL_TELEMETRY_OPT_OUT'] = '1'
os.environ['DEEPEVAL_DISABLE_DOTENV'] = '1'
os.environ['DEEPEVAL_DISABLE_LEGACY_KEYFILE'] = '1'

from deepeval.dataset import Golden
from pydantic import ConfigDict, model_validator

APP_FIELDS = {'id', 'dataset_id', 'created_at', 'updated_at', 'status'}
ALIASES = {field.serialization_alias: name for name, field in Golden.model_fields.items()
           if field.serialization_alias}
ALIASES.update({'imagesMapping': 'images_mapping', 'reference_contexts': 'context',
                'contexts': 'context', 'metadata': 'additional_metadata', 'question': 'input',
                'user_input': 'input', 'answer': 'expected_output', 'reference': 'expected_output',
                'ground_truth': 'expected_output'})


def normalize_record(value):
    """Accept SDK field names/JSON aliases and losslessly adapt older PrismLab rows."""
    data = dict(value)
    for alias, field in ALIASES.items():
        if alias in data:
            old = data.pop(alias)
            if field in data and data[field] != old:
                raise ValueError(f'Conflicting fields: {field}')
            data[field] = old
    # SDK 4.3.2 declares Dict with a None default; omit explicit null on validation.
    if data.get('images_mapping') is None:
        data.pop('images_mapping', None)
    # The SDK eagerly loads local images in its dataclass constructor. Uploaded
    # records must never be able to read files from the API host.
    images = data.get('images_mapping')
    if isinstance(images, dict):
        for image in images.values():
            if not isinstance(image, dict):
                raise ValueError('images_mapping must contain serialized images')
            if not image.get('dataBase64') and not str(image.get('url', '')).startswith(('https://', 'http://')):
                raise ValueError('Imported images require inline data or an HTTP URL')
    # Golden only permits strings. Preserve the original typed values as metadata.
    legacy = {}
    for field in ('input', 'expected_output'):
        item = data.get(field)
        if item is not None and not isinstance(item, str):
            legacy[field] = item
            data[field] = json.dumps(item, ensure_ascii=False, allow_nan=False)
    if legacy:
        metadata = dict(data.get('additional_metadata') or {})
        name = '_prismlab_legacy_values'
        while name in metadata:
            name += '_'
        metadata[name] = legacy
        data['additional_metadata'] = metadata
    return data


class DatasetItem(Golden):
    """Golden plus a single application lifecycle field (excluded on SDK export)."""
    model_config = ConfigDict(extra='forbid', populate_by_name=True, allow_inf_nan=False)
    status: Literal['active', 'archived'] = 'active'

    @model_validator(mode='before')
    @classmethod
    def compatible(cls, value):
        return normalize_record(value) if isinstance(value, dict) else value

    @model_validator(mode='after')
    def valid_record(self):
        if not self.input.strip():
            raise ValueError('input 不能为空')
        if len(json.dumps(self.model_dump(mode='json'), ensure_ascii=False, allow_nan=False)) > 200000:
            raise ValueError('单条数据过大（最多 200000 字符）')
        return self


def canonical_item(row):
    app = {key: row[key] for key in APP_FIELDS if key in row}
    record = {key: value for key, value in row.items() if key not in APP_FIELDS}
    return {**DatasetItem.model_validate(record).model_dump(mode='json'), **app}


def golden_dict(row):
    """Exactly Golden.model_dump(mode='json'); no IDs, timestamps or archive status."""
    item = canonical_item(row)
    return {key: value for key, value in item.items() if key not in APP_FIELDS}

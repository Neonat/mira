"""Atomic local staging files. These are not shared database records."""
import hashlib
import json
import os
import tempfile
from pathlib import Path


def atomic_bytes(path, data, *, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError(f'Existing immutable file is inconsistent: {path.name}')
                return False
        else:
            os.replace(temporary, path)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode())


def raw_snapshot(data, directory, suffix):
    path = Path(directory) / 'raw' / f'{hashlib.sha256(data).hexdigest()}.{suffix}'
    atomic_bytes(path, data, immutable=True)
    return str(path.resolve())

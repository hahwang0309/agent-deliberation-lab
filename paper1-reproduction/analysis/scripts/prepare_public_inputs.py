"""Fetch/verify the fixed public snapshot, then stage figure inputs (no API keys)."""
import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import quote

REVISION = 'c13fd45abfafc9f0bcc5b8157d8ea73038138ae8'
BASE = f'https://huggingface.co/datasets/haha0309/agent-deliberation-study1/resolve/{REVISION}/'
ROOT = Path(__file__).resolve().parents[1]


def safe_path(root, name):
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or '\\' in name:
        raise ValueError(f'Unsafe manifest path: {name}')
    dest = root.joinpath(*rel.parts)
    if not dest.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Path outside root: {name}')
    return dest


def fetch(name, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + '.partial')
    with urllib.request.urlopen(BASE + quote(name), timeout=120) as response:
        with partial.open('wb') as out:
            shutil.copyfileobj(response, out)
    partial.replace(dest)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--download', type=Path, help='Download exact public snapshot here')
    g.add_argument('--data', type=Path, help='Verify existing exact snapshot')
    a = p.parse_args()
    data = (a.download or a.data).resolve()
    if a.download:
        data.mkdir(parents=True, exist_ok=True)
        fetch('manifest.json', data/'manifest.json')
    manifest = json.loads((data/'manifest.json').read_text())['files']
    if not manifest:
        raise ValueError('Empty manifest')
    for name, expected in sorted(manifest.items()):
        dest = safe_path(data, name)
        valid = dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == expected
        if not valid and a.download:
            fetch(name, dest)
        if not dest.is_file() or hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Missing or mismatched input: {name}')
    staged = 0
    for name in manifest:
        rel = PurePosixPath(name)
        if rel.parts[:2] == ('numeric', 'plot-inputs') and len(rel.parts) > 3 and rel.parts[2] in ('data', 'docs'):
            dest = safe_path(ROOT, str(PurePosixPath(*rel.parts[2:])))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data/name, dest)
            staged += 1
    report = {'dataset_revision': REVISION, 'verified_files': len(manifest),
              'staged_figure_inputs': staged, 'scripts_overwritten': 0, 'api_calls': 0}
    (ROOT/'public-input-check.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

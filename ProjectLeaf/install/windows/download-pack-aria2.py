#!/usr/bin/env python3
"""
Flower Pack 1.2.0 - aria2c downloader for Pack 1.

Reads the Flower Pack registry, builds an aria2c input file, and downloads
with multi-connection segmentation. After download it writes Flower Pack
.flower-verified sidecars and optionally runs flower-pack to create symlinks.

    Example:
    python download-pack-aria2.py
    python download-pack-aria2.py --concurrent-files 4 --split 16
    python download-pack-aria2.py --model-root D:\\Models --no-install
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


PACK_ROOT_CANDIDATES = [
    Path(r'C:\flower-pack-1.2.0\flower-pack-1.2.0'),
    Path(r'C:\flower-pack-1.2.0'),
]

DEFAULT_MODEL_ROOT = Path(r'C:\R\LeafOS0.2.2\models')
DEFAULT_HF_ENDPOINT = 'https://huggingface.co'


def print_color(text: str, color: int = 195) -> None:
    # Map xterm-256 approximations to the FlowerOS pastel/green true-color palette.
    palette = {
        195: "\033[38;2;183;240;199m",  # mint / info
        217: "\033[38;2;255;183;197m",  # bloom / header
        210: "\033[38;2;255;154;162m",  # error
        221: "\033[38;2;255;250;181m",  # butter / warning
    }
    code = palette.get(color, f"\033[38;5;{color}m")
    print(f'{code}{text}\033[0m')


def find_pack_root() -> Path:
    for candidate in PACK_ROOT_CANDIDATES:
        if (candidate / 'flower-pack.ps1').is_file():
            return candidate
    raise FileNotFoundError(
        'flower-pack.ps1 was not found under any configured directory.'
    )


def find_launcher(pack_root: Path) -> Path:
    return pack_root / 'flower-pack.ps1'


def load_json(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_first(obj: dict, names: list[str], default=None):
    for name in names:
        if name in obj and obj[name] is not None:
            return obj[name]
    return default


def parse_size(value) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    match = re.match(r'([0-9]+(?:\.[0-9]+)?)\s*(TB|TiB|GB|GiB|MB|MiB|KB|KiB|B?)', text, re.IGNORECASE)
    if not match:
        return 0
    number = float(match.group(1))
    unit = match.group(2).upper()
    multipliers = {
        'B': 1, '': 1,
        'KB': 1024, 'KIB': 1024,
        'MB': 1024 ** 2, 'MIB': 1024 ** 2,
        'GB': 1024 ** 3, 'GIB': 1024 ** 3,
        'TB': 1024 ** 4, 'TIB': 1024 ** 4,
    }
    return int(number * multipliers.get(unit, 1))


def hf_api_request(repo: str, hf_endpoint: str, hf_token: str | None) -> dict:
    url = f'{hf_endpoint}/api/models/{quote(repo, safe="/")}?blobs=true'
    headers = {'User-Agent': 'flower-pack-aria2/1.0'}
    if hf_token:
        headers['Authorization'] = f'Bearer {hf_token}'
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))


def match_siblings(metadata: dict, quant_id: str):
    pattern = re.compile(
        r'[-_.]' + re.escape(quant_id) + r'(-\d{5}-of-\d{5})?\.gguf$',
        re.IGNORECASE,
    )
    sha = metadata.get('sha', '')
    for sibling in metadata.get('siblings', []):
        rfilename = sibling.get('rfilename', '')
        if pattern.search(rfilename):
            size = sibling.get('size') or sibling.get('lfs', {}).get('size') or 0
            digest = sibling.get('lfs', {}).get('sha256', '')
            yield {
                'filename': rfilename,
                'size': int(size or 0),
                'sha256': digest,
                'revision': sha,
            }


def build_download_plan(pack_root: Path, pack_id: int, hf_endpoint: str, hf_token: str | None):
    registry_dir = pack_root / 'share' / 'floweros' / 'registry'
    models_path = registry_dir / 'models.json'
    packs_path = registry_dir / 'packs.json'

    if not models_path.is_file() or not packs_path.is_file():
        raise FileNotFoundError(f'Registry files not found in {registry_dir}')

    models_doc = load_json(models_path)
    packs_doc = load_json(packs_path)

    models = models_doc.get('models', models_doc)
    packs = packs_doc.get('packs', packs_doc)

    models_index = {str(m.get('model_id', m.get('id'))): m for m in models}

    pack = None
    for p in packs:
        pid = str(get_first(p, ['pack_id', 'id'], ''))
        if pid == str(pack_id):
            pack = p
            break
    if pack is None:
        raise ValueError(f'Pack {pack_id} not found in registry')

    entries = get_first(pack, ['entries', 'items', 'models'], [])
    artifacts = []
    seen = set()
    repo_cache = {}

    for entry in entries:
        model_id = str(get_first(entry, ['model_id', 'modelId'], ''))
        quant_id = str(get_first(entry, ['quant_id', 'quantId'], ''))
        role = str(get_first(entry, ['role', 'name'], ''))
        variant = str(get_first(entry, ['variant'], ''))
        entry_id = str(get_first(entry, ['entry_id'], ''))

        model = models_index.get(model_id)
        if model is None:
            raise ValueError(f'Model not found in registry: {model_id}')

        repo = str(get_first(model, ['repository_ref', 'repository', 'repo'], ''))
        if not repo:
            raise ValueError(f'No repository for model {model_id}')

        if repo not in repo_cache:
            repo_cache[repo] = hf_api_request(repo, hf_endpoint, hf_token)

        metadata = repo_cache[repo]
        for match in match_siblings(metadata, quant_id):
            key = (repo, match['filename'])
            if key in seen:
                continue
            seen.add(key)
            artifacts.append({
                'entry_id': entry_id,
                'role': role,
                'variant': variant,
                'model_id': model_id,
                'quant_id': quant_id,
                'repo': repo,
                'revision': match['revision'],
                'filename': match['filename'],
                'size': match['size'],
                'sha256': match['sha256'],
            })

    return artifacts


def store_dir(model_root: Path, repo: str, revision: str) -> Path:
    repo_key = repo.replace('/', '--')
    return model_root / 'store' / repo_key / revision


def write_aria2_input_file(artifacts: list[dict], model_root: Path, input_path: Path, hf_endpoint: str, hf_token: str | None = None) -> int:
    lines = []
    if hf_token:
        lines.append('header=Authorization: Bearer ' + hf_token)
        lines.append('')
    for a in artifacts:
        out_dir = store_dir(model_root, a['repo'], a['revision'])
        encoded_filename = quote(a['filename'], safe='/')
        url = f'{hf_endpoint}/{a["repo"]}/resolve/{a["revision"]}/{encoded_filename}?download=true'
        lines.append(url)
        lines.append(f'  out={a["filename"]}')
        lines.append(f'  dir={out_dir}')
        if a['sha256']:
            lines.append(f'  checksum=sha-256={a["sha256"]}')
        lines.append('')

    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text('\n'.join(lines), encoding='utf-8')
    return len(lines)


def write_verified_sidecars(artifacts: list[dict], model_root: Path) -> int:
    """Write .flower-verified sidecars so flower-pack install skips re-hashing."""
    count = 0
    for a in artifacts:
        if not a['sha256'] or not a['size']:
            continue
        target = store_dir(model_root, a['repo'], a['revision']) / a['filename']
        sidecar = target.parent / (target.name + '.flower-verified')
        if target.exists() and target.stat().st_size == a['size']:
            sidecar.write_text(f'{a["sha256"]}:{a["size"]}\n', encoding='utf-8')
            count += 1
    return count


def run_aria2c(input_file: Path, concurrent_files: int, split: int, work_dir: Path) -> None:
    aria2c = shutil.which('aria2c')
    if aria2c is None:
        raise FileNotFoundError(
            'aria2c was not found in PATH. Install it first, e.g.:\n'
            '  winget install aria2.aria2\n'
            '  choco install aria2\n'
            '  scoop install aria2'
        )

    cmd = [
        aria2c,
        '--continue=true',
        '--max-concurrent-downloads', str(concurrent_files),
        '--split', str(split),
        '--max-connection-per-server', str(split),
        '--min-split-size=16M',
        '--max-tries=20',
        '--retry-wait=5',
        '--timeout=60',
        '--file-allocation=none',
        '--auto-file-renaming=false',
        '--summary-interval=10',
        '--input-file', str(input_file),
    ]

    print_color(f'[+] aria2c: {aria2c}', 195)
    print_color(f'[+] Connections: {concurrent_files} files x {split} segments = up to {concurrent_files * split} connections', 195)
    print_color(f'[+] Input file: {input_file}', 195)
    print()

    subprocess.run(cmd, cwd=work_dir, check=True)


def run_flower_pack_install(pack_root: Path, pack_id: int) -> None:
    launcher = find_launcher(pack_root)
    pwsh = shutil.which('pwsh') or shutil.which('powershell')
    if pwsh is None:
        raise FileNotFoundError('pwsh or powershell not found in PATH')

    cmd = [
        pwsh, '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', str(launcher),
        'install', str(pack_id), '--yes',
    ]
    print_color(f'[+] Running: {" ".join(cmd)}', 195)
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Download Flower Pack models via aria2c with multi-connection segmentation.',
    )
    parser.add_argument('--pack-id', type=int, default=1, help='Pack number to download (default: 1)')
    parser.add_argument('--pack-root', type=Path, help='Flower Pack installation root')
    parser.add_argument('--model-root', type=Path, default=DEFAULT_MODEL_ROOT, help='Model destination root')
    parser.add_argument('--hf-endpoint', default=DEFAULT_HF_ENDPOINT, help='Hugging Face endpoint')
    parser.add_argument('--concurrent-files', type=int, default=None,
                        help='Files downloaded at once (default: max(2, cores-2) capped at 6)')
    parser.add_argument('--split', type=int, default=16,
                        help='Segments per file (default: 16)')
    parser.add_argument('--turbo', action='store_true',
                        help='Ignore core cap and use (cores - 2) concurrent files with 16 segments')
    parser.add_argument('--no-install', action='store_true',
                        help='Skip running flower-pack install after download')
    parser.add_argument('--hf-token', default=None,
                        help='Hugging Face access token (or set HF_TOKEN env var)')
    parser.add_argument('--no-sidecars', action='store_true',
                        help='Skip writing .flower-verified sidecars')
    parser.add_argument('--dry-run', action='store_true',
                        help='Build input file and exit without downloading')
    args = parser.parse_args()
    if args.hf_token:
        os.environ['HF_TOKEN'] = args.hf_token

    cores = os.cpu_count() or 4
    if args.concurrent_files is not None:
        concurrent_files = max(1, args.concurrent_files)
    elif args.turbo:
        concurrent_files = max(2, cores - 2)
    else:
        concurrent_files = min(max(2, cores - 2), 6)

    split = max(1, args.split)

    print_color('Flower Pack 1.2.0 - aria2c multi-connection downloader', 217)
    print(f'[+] CPU cores detected: {cores}')
    print(f'[+] Concurrent files: {concurrent_files}')
    print(f'[+] Segments per file: {split}')
    print(f'[+] Max connections: {concurrent_files * split}')
    print()

    pack_root = args.pack_root or find_pack_root()
    model_root = args.model_root
    model_root.mkdir(parents=True, exist_ok=True)
    hf_token = os.environ.get('HF_TOKEN')

    print(f'[+] Flower Pack root: {pack_root}')
    print(f'[+] Model root: {model_root}')
    print(f'[+] Pack: {args.pack_id}')
    print()

    print('[+] Reading registry and resolving HF metadata...')
    try:
        artifacts = build_download_plan(pack_root, args.pack_id, args.hf_endpoint, hf_token)
    except urllib.error.HTTPError as e:
        print(f'\033[38;5;210m[ERROR] HTTP {e.code} while fetching registry or HF API: {e.url}\033[0m', file=sys.stderr)
        return 1

    if not artifacts:
        print_color('[ERROR] No downloadable artifacts found.', 210)
        return 1

    total_bytes = sum(a['size'] for a in artifacts)
    total_gib = total_bytes / (1024 ** 3)
    missing_sha = sum(1 for a in artifacts if not a['sha256'])

    print(f'[+] Artifacts to download: {len(artifacts)}')
    print(f'[+] Total expected size: {total_gib:.2f} GiB')
    if missing_sha:
        print_color(f'[!] {missing_sha} artifact(s) lack SHA-256; aria2c will not verify them', 221)
    print()

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    work_dir = Path(os.environ.get('TEMP', '.'))
    input_file = work_dir / f'flower-pack-{args.pack_id}-{timestamp}.aria2.txt'
    write_aria2_input_file(artifacts, model_root, input_file, args.hf_endpoint, hf_token)
    print(f'[+] Input file written: {input_file}')
    print()

    if args.dry_run:
        print_color('[+] Dry run complete. Exiting without downloading.', 195)
        return 0

    try:
        run_aria2c(input_file, concurrent_files, split, work_dir)
    except FileNotFoundError as e:
        print_color(f'[ERROR] {e}', 210)
        return 1
    except subprocess.CalledProcessError as e:
        print_color(f'[ERROR] aria2c exited with code {e.returncode}', 210)
        return e.returncode

    print()
    print_color('[+] aria2c finished.', 195)

    if not args.no_sidecars:
        sidecar_count = write_verified_sidecars(artifacts, model_root)
        print(f'[+] Wrote {sidecar_count} .flower-verified sidecar(s).')

    if not args.no_install:
        print()
        print('[+] Finalizing with flower-pack install...')
        try:
            run_flower_pack_install(pack_root, args.pack_id)
        except subprocess.CalledProcessError as e:
            print_color(f'[ERROR] flower-pack install exited with code {e.returncode}', 210)
            return e.returncode

    print_color('[+] Done.', 195)
    return 0


if __name__ == '__main__':
    sys.exit(main())

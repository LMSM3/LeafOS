#!/usr/bin/env python3
"""
Flower Pack 1.2.0 - hf_transfer downloader for Pack 1.

Uses the Rust-based hf_transfer backend from huggingface_hub for high-throughput
single-connection-per-file downloads. Reads the Flower Pack registry, resolves
the exact artifacts, and writes them directly into the store tree with optional
.flower-verified sidecars and a final flower-pack install step.

For this to help, the HF read token should have good rate limits (HF Pro / Enterprise).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError

# huggingface_hub 1.25+ uses the Xet high-performance transfer backend.
# HF_HUB_ENABLE_HF_TRANSFER is deprecated.
os.environ.setdefault('HF_XET_HIGH_PERFORMANCE', '1')


def _check_dependencies() -> None:
    try:
        import huggingface_hub  # noqa: F401
        import hf_transfer  # noqa: F401
    except ImportError as exc:
        print('[ERROR] Missing Hugging Face dependencies. Install with:', file=sys.stderr)
        print('  python -m pip install --upgrade huggingface_hub hf_transfer', file=sys.stderr)
        raise SystemExit(1) from exc
    print(f'[+] huggingface_hub: {huggingface_hub.__version__}')
    print('[+] hf_transfer: installed')


_check_dependencies()

from huggingface_hub import hf_hub_download  # noqa: E402


PACK_ROOT_CANDIDATES = [
    Path(r'C:\flower-pack-1.2.0\flower-pack-1.2.0'),
    Path(r'C:\flower-pack-1.2.0'),
]

DEFAULT_MODEL_ROOT = Path(r'C:\R\LeafOS0.2.1\models')
DEFAULT_HF_ENDPOINT = 'https://huggingface.co'
TOKEN_PATH = Path(os.environ.get('USERPROFILE', '~')) / '.cache' / 'huggingface' / 'token'


def print_color(text: str, color: int = 195) -> None:
    print(f'\033[38;5;{color}m{text}\033[0m')


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


def read_cached_token(token_type: str = 'read') -> str | None:
    """Return a cached token if it looks like a Hugging Face token."""
    try:
        token = TOKEN_PATH.read_text(encoding='utf-8').strip()
        if token and token.lower().startswith(('hf_', 'hfat_')):
            return token
    except FileNotFoundError:
        pass
    return None


VAULT_EXE = Path(__file__).with_name('token_vault.exe')


def vault_get(kind: str) -> str | None:
    """Decrypt a token from the Windows DPAPI vault."""
    if not VAULT_EXE.is_file():
        return None
    try:
        result = subprocess.run(
            [str(VAULT_EXE), 'get', kind],
            capture_output=True, text=True, check=True, timeout=60,
        )
        token = result.stdout.strip()
        if token.lower().startswith(('hf_', 'hfat_')):
            return token
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def resolve_token(args_token: str | None) -> tuple[str | None, str]:
    """Return (token, source). Prefers CLI arg, then env, then DPAPI vault."""
    if args_token:
        return args_token, 'command-line'
    env_token = os.environ.get('HF_TOKEN') or os.environ.get('HF_READ_TOKEN')
    if env_token:
        return env_token, 'environment'
    vault_token = vault_get('read')
    if vault_token:
        return vault_token, 'vault'
    cached = read_cached_token()
    if cached:
        return cached, 'cached'
    return None, 'anonymous'


def hf_api_request(repo: str, hf_endpoint: str, hf_token: str | None) -> dict:
    import urllib.request
    url = f'{hf_endpoint}/api/models/{quote(repo, safe="/")}?blobs=true'
    headers = {'User-Agent': 'flower-pack-hftransfer/1.0'}
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
        entry_id = str(get_first(entry, ['entry_id'], '') or '')

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


def write_verified_sidecar(artifact: dict, model_root: Path) -> bool:
    if not artifact.get('sha256') or not artifact.get('size'):
        return False
    target = store_dir(model_root, artifact['repo'], artifact['revision']) / artifact['filename']
    sidecar = target.parent / (target.name + '.flower-verified')
    try:
        if target.exists() and target.stat().st_size == artifact['size']:
            sidecar.write_text(f"{artifact['sha256']}:{artifact['size']}\n", encoding='utf-8')
            return True
    except OSError:
        pass
    return False


def download_one(artifact: dict, model_root: Path, hf_endpoint: str, hf_token: str | None) -> dict:
    repo = artifact['repo']
    filename = artifact['filename']
    revision = artifact['revision']
    out_dir = store_dir(model_root, repo, revision)
    out_dir.mkdir(parents=True, exist_ok=True)

    start = datetime.utcnow()
    try:
        hf_hub_download(
            repo_id=repo,
            filename=filename,
            revision=revision,
            local_dir=out_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
            token=hf_token,
            endpoint=hf_endpoint if hf_endpoint != DEFAULT_HF_ENDPOINT else None,
            force_download=False,
        )
        elapsed = (datetime.utcnow() - start).total_seconds()
        wrote_sidecar = write_verified_sidecar(artifact, model_root)
        return {
            'artifact': artifact,
            'ok': True,
            'seconds': elapsed,
            'sidecar': wrote_sidecar,
        }
    except Exception as exc:
        return {
            'artifact': artifact,
            'ok': False,
            'error': str(exc),
        }


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
        description='Download Flower Pack models via huggingface_hub + hf_transfer.',
    )
    parser.add_argument('--pack-id', type=int, default=1, help='Pack number to download (default: 1)')
    parser.add_argument('--pack-root', type=Path, help='Flower Pack installation root')
    parser.add_argument('--model-root', type=Path, default=DEFAULT_MODEL_ROOT, help='Model destination root')
    parser.add_argument('--hf-endpoint', default=DEFAULT_HF_ENDPOINT, help='Hugging Face endpoint')
    parser.add_argument('--hf-token', default=None, help='HF read token (or use HF_TOKEN env var / cached token)')
    parser.add_argument('--workers', type=int, default=None,
                        help='Concurrent file downloads (default: max(2, cores-2) capped at 6)')
    parser.add_argument('--turbo', action='store_true',
                        help='Ignore core cap and use (cores - 2) concurrent files')
    parser.add_argument('--no-install', action='store_true',
                        help='Skip running flower-pack install after download')
    parser.add_argument('--no-sidecars', action='store_true',
                        help='Skip writing .flower-verified sidecars')
    parser.add_argument('--dry-run', action='store_true',
                        help='List artifacts and exit without downloading')
    args = parser.parse_args()

    cores = os.cpu_count() or 4
    if args.workers is not None:
        workers = max(1, args.workers)
    elif args.turbo:
        workers = max(2, cores - 2)
    else:
        workers = min(max(2, cores - 2), 6)

    print_color('Flower Pack 1.2.0 - hf_transfer downloader', 217)
    xet_on = os.environ.get('HF_XET_HIGH_PERFORMANCE', '')
    print(f'[+] HF_XET_HIGH_PERFORMANCE={xet_on}')
    print(f'[+] CPU cores detected: {cores}')
    print(f'[+] Concurrent files: {workers}')
    print()

    pack_root = args.pack_root or find_pack_root()
    model_root = args.model_root
    model_root.mkdir(parents=True, exist_ok=True)

    hf_token, token_source = resolve_token(args.hf_token)
    if hf_token:
        print(f'[+] Using HF token from {token_source}: {hf_token[:4]}... ({len(hf_token)} chars)')
        os.environ['HF_TOKEN'] = hf_token
    else:
        print_color('[!] No HF token found. Anonymous downloads may be rate-limited.', 221)

    print(f'[+] Flower Pack root: {pack_root}')
    print(f'[+] Model root: {model_root}')
    print(f'[+] Pack: {args.pack_id}')
    print()

    print('[+] Reading registry and resolving HF metadata...')
    try:
        artifacts = build_download_plan(pack_root, args.pack_id, args.hf_endpoint, hf_token)
    except HTTPError as e:
        print(f'\033[38;5;210m[ERROR] HTTP {e.code} while fetching registry or HF API: {e.url}\033[0m', file=sys.stderr)
        return 1

    if not artifacts:
        print_color('[ERROR] No downloadable artifacts found.', 210)
        return 1

    total_bytes = sum(a['size'] for a in artifacts)
    missing_sha = sum(1 for a in artifacts if not a['sha256'])

    print(f'[+] Artifacts to download: {len(artifacts)}')
    print(f'[+] Total expected size: {total_bytes / (1024 ** 3):.2f} GiB')
    if missing_sha:
        print_color(f'[!] {missing_sha} artifact(s) lack SHA-256', 221)
    print()

    if args.dry_run:
        for a in artifacts:
            print(f"{a['repo']}/{a['filename']} -> {store_dir(model_root, a['repo'], a['revision'])}")
        return 0

    completed = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        def worker(a):
            return download_one(a, model_root, args.hf_endpoint, hf_token)

        futures = {pool.submit(worker, a): a for a in artifacts}
        for future in futures:
            result = future.result()
            if result['ok']:
                completed += 1
                a = result['artifact']
                size_gib = a['size'] / (1024 ** 3)
                sec = result['seconds'] or 0.1
                rate = (a['size'] / sec) / (1024 ** 2)
                print_color(
                    f'[{completed}/{len(artifacts)}] OK {a["filename"]} ({size_gib:.2f} GiB in {sec:.1f}s @ {rate:.2f} MiB/s)',
                    82
                )
            else:
                failed += 1
                a = result['artifact']
                print_color(f'[{completed + failed}/{len(artifacts)}] FAIL {a["filename"]}: {result["error"]}', 210)

    print()
    print_color(f'[+] Downloads complete: {completed}/{len(artifacts)}', 195 if failed == 0 else 221)
    if failed:
        return 1

    if args.no_sidecars:
        print('[*] Skipping sidecar writes.')
    else:
        sidecars = sum(1 for a in artifacts if write_verified_sidecar(a, model_root))
        print(f'[+] Wrote {sidecars} .flower-verified sidecar(s).')

    if args.no_install:
        print('[*] Skipping flower-pack install.')
    else:
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

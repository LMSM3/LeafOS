import os
import sys
import time
from datetime import datetime
from pathlib import Path

repo = 'GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF'
filename = 'MiniCPM5-1B-Claude-Opus-Fable5-Thinking-Q4_K_M.gguf'
revision = '5a4ed2c3605634e7b043e8b98fa01e504b0dfbed'
local_dir = r'C:\R\LeafOS0.2.1\_hft-test'

token = os.environ.get('HF_TOKEN')
print(f'[+] hf_transfer enabled: {os.environ.get("HF_HUB_ENABLE_HF_TRANSFER")}')
print(f'[+] token present: {bool(token)}')

Path(local_dir).mkdir(parents=True, exist_ok=True)
start = time.time()
try:
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(
        repo_id=repo,
        filename=filename,
        revision=revision,
        local_dir=local_dir,
        local_dir_use_symlinks=False,
        resume_download=True,
        token=token,
    )
    elapsed = time.time() - start
    sz = Path(p).stat().st_size
    print(f'SPEEDTEST total_bytes={sz} elapsed_s={elapsed:.1f} rate_mibps={sz / elapsed / 1024 / 1024:.2f}')
except Exception as exc:
    elapsed = time.time() - start
    print(f'SPEEDTEST ERROR after {elapsed:.1f}s: {exc}', file=sys.stderr)
    raise

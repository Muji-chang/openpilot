import json
import os
import stat
import subprocess
import sys
from collections.abc import Iterable
from contextlib import suppress
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpilot.selfdrive.modeld.helpers import usbgpu_present


def get_build_key(root: Path) -> dict | None:
  # Custom SCons flags can change the selected targets or skip execution entirely.
  if os.getenv('SCONSFLAGS') or os.getenv('RELEASE'):
    return None

  try:
    agnos = Path('/VERSION').read_text().strip()
    if not agnos or agnos != os.getenv('AGNOS_VERSION', agnos):
      return None

    git = ['git', '--no-optional-locks', '-C', str(root)]
    commit = subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
    if subprocess.check_output([*git, 'status', '--porcelain', '--untracked-files=normal', '--ignore-submodules=none'],
                               stderr=subprocess.DEVNULL, timeout=5):
      return None
    numpy_version = version('numpy')
  except (OSError, ValueError, ImportError, subprocess.SubprocessError):
    return None

  return {
    'commit': commit,
    'agnos': agnos,
    'python': sys.version,
    'numpy': numpy_version,
    'ion': Path('/dev/ion').exists(),
    'usbgpu': usbgpu_present(),
    'tici_dos': 'TICI_DOS' in os.environ,
    'enable_spi': 'ENABLE_SPI' in os.environ,
    'debug': bool(os.getenv('DEBUG')),
    'final_provisioning': bool(os.getenv('FINAL_PROVISIONING')),
  }


def artifact_stats(root: Path, paths: Iterable[str]) -> dict[str, list[int]]:
  artifacts = {}
  for name in paths:
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
      raise ValueError(f'invalid build artifact path: {name}')
    info = (root / path).stat()
    if not stat.S_ISREG(info.st_mode):
      raise ValueError(f'build artifact is not a regular file: {name}')
    artifacts[name] = [info.st_size, info.st_mtime_ns, stat.S_IMODE(info.st_mode)]
  return artifacts


def check_build_cache(cache_path: Path, build_key: dict) -> str | None:
  try:
    record = json.loads(cache_path.read_text(encoding='utf-8'))
    if not isinstance(record, dict) or not isinstance(artifacts := record.get('artifacts'), dict) or not artifacts:
      return 'invalid build record'
    if record.get('key') != build_key:
      return 'program version, AGNOS, or build configuration changed'
    if artifact_stats(cache_path.parent, artifacts) != artifacts:
      return 'build artifacts changed'
  except FileNotFoundError as e:
    return 'no successful build record' if e.filename == str(cache_path) else f'missing build artifact: {e.filename}'
  except (OSError, ValueError):
    return 'unreadable build record or artifacts'
  return None


def write_build_cache(cache_path: Path, build_key: dict, inventory: Path) -> None:
  temp_path = None
  try:
    paths = json.loads(inventory.read_text(encoding='utf-8'))
    if not isinstance(paths, list) or not paths or not all(isinstance(path, str) for path in paths):
      raise ValueError('empty or invalid SCons artifact inventory')

    record = {'key': build_key, 'artifacts': artifact_stats(cache_path.parent, paths)}
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=cache_path.parent,
                            prefix='.mujitest_build-', suffix='.tmp', delete=False) as f:
      temp_path = Path(f.name)
      json.dump(record, f)
      f.flush()
      os.fsync(f.fileno())
    temp_path.replace(cache_path)
    temp_path = None
  except (OSError, ValueError) as e:
    print(f'Could not record successful build: {e}', flush=True)
  finally:
    if temp_path is not None:
      with suppress(OSError):
        temp_path.unlink(missing_ok=True)

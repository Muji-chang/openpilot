#!/usr/bin/env python3
import argparse
import fcntl
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

# NOTE: Do NOT import anything here that needs be built (e.g. params)
from openpilot.common.basedir import BASEDIR
from openpilot.common.spinner import Spinner
from openpilot.common.text_window import TextWindow
from openpilot.system.hardware import HARDWARE, AGNOS
from openpilot.system.manager.build_cache import get_build_key, check_build_cache, write_build_cache


def build(inventory: Path | None = None) -> None:
  spinner = Spinner()
  spinner.update_progress(0, 100)

  HARDWARE.set_power_save(False)
  if AGNOS:
    os.sched_setaffinity(0, range(8))  # ensure we can use the isolcpus cores

  env = {**os.environ, "PWD": BASEDIR}
  if inventory is not None:
    env["MUJITEST_BUILD_INVENTORY"] = str(inventory)

  # building with all cores can result in using too much memory, so retry serially
  compile_output: list[bytes] = []
  for parallelism in ([], ["-j4"], ["-j1"]):
    compile_output.clear()
    if inventory is not None:
      inventory.unlink(missing_ok=True)
    with subprocess.Popen(["scons", *parallelism], cwd=BASEDIR, env=env, stderr=subprocess.PIPE) as scons:
      assert scons.stderr is not None

      # Read progress from stderr and update spinner
      while scons.poll() is None:
        try:
          line = scons.stderr.readline()
          if line is None:
            continue
          line = line.rstrip()

          prefix = b'progress: '
          if line.startswith(prefix):
            progress = float(line[len(prefix):])
            spinner.update_progress(100 * min(1., progress / 100.), 100.)
          elif len(line):
            compile_output.append(line)
            print(line.decode('utf8', 'replace'))
        except Exception:
          pass

      # Drain and close the pipe before retrying or returning.
      for line in scons.stderr.read().split(b'\n'):
        line = line.rstrip()
        if len(line):
          compile_output.append(line)

    if scons.returncode == 0:
      break

  if scons.returncode != 0:
    # Build failed log errors
    error_s = b"\n".join(compile_output).decode('utf8', 'replace')

    # Show TextWindow
    spinner.close()
    if not os.getenv("CI"):
      with TextWindow("openpilot failed to build\n \n" + error_s) as t:
        t.wait_for_exit()
    exit(1)


def main(reuse_build: bool) -> None:
  if not AGNOS:
    build()
    return

  cache_path = Path(BASEDIR) / '.mujitest_build.json'
  with cache_path.with_suffix('.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    build_key = get_build_key(cache_path.parent)
    if reuse_build and build_key is not None:
      miss = check_build_cache(cache_path, build_key)
      if miss is None:
        print('Reusing verified build artifacts; skipping SCons', flush=True)
        HARDWARE.set_power_save(False)
        return
      print(f'Running SCons: {miss}', flush=True)

    # A failed or interrupted build must never leave a reusable success record.
    cache_path.unlink(missing_ok=True)
    if build_key is None:
      if reuse_build:
        print('Running SCons: source or build environment could not be verified', flush=True)
      build()
      return

    with TemporaryDirectory(prefix='mujitest-build-') as tempdir:
      inventory = Path(tempdir) / 'artifacts.json'
      build(inventory)
      if get_build_key(cache_path.parent) == build_key:
        write_build_cache(cache_path, build_key, inventory)
      else:
        print('Build inputs changed; skipping the build record', flush=True)


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('--reuse-build', action='store_true')
  main(parser.parse_args().reuse_build)

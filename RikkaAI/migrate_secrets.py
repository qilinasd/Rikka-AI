"""One-time migration of legacy plaintext API keys.

Run with the same Python interpreter used by RikkaAI. The command creates a
backup outside the repository, writes and verifies every discovered secret,
then removes only API-key fields from JSON. Source cleanup is deliberately a
separate step so a failed migration cannot destroy the only usable copy.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from secret_store import get, preset_name, set_secret

ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT.parent / ".secret-backup"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _discover(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    cfg = root / "memory_data" / "user_config.json"
    if cfg.exists():
        data = _json(cfg)
        if data.get("api_key"):
            found["global_api_key"] = data["api_key"]
        for preset in data.get("presets", []):
            if preset.get("api_key") and preset.get("name"):
                found[preset_name(preset["name"])] = preset["api_key"]
        for preset in data.get("sleep_compute_custom_models", []):
            if preset.get("api_key") and preset.get("name"):
                found[preset_name(preset["name"])] = preset["api_key"]
    partners = root / "memory_data" / "partners.json"
    if partners.exists():
        for partner in _json(partners):
            if partner.get("api_key"):
                found[preset_name(partner.get("id") or partner.get("name"))] = partner["api_key"]
    source_files = [root / "config.py", root / "brain" / "tools.py",
                    root / "默认业务空间-apiKey-6332963.csv",
                    root.parent / "默认业务空间-apiKey-6332963.csv"]
    patterns = {
        "vision_api_key": r"VISION_API_KEY\s*=\s*[\"']([^\"']+)",
    }
    for path in source_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                value = next((g for g in match.groups() if g), "").strip()
                if value and "your-api-key" not in value:
                    found.setdefault(name, value)
    return found


def _backup(root: Path, stamp: str) -> Path:
    target = BACKUP_ROOT / stamp
    target.mkdir(parents=True, exist_ok=False)
    for relative in [Path("memory_data/user_config.json"), Path("memory_data/partners.json"),
                     Path("config.py"), Path("brain/tools.py")]:
        source = root / relative
        if source.exists():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    for source in [root.parent / "默认业务空间-apiKey-6332963.csv"]:
        if source.exists():
            shutil.copy2(source, target / source.name)
    return target


def _strip_json_secrets(root: Path) -> None:
    cfg = root / "memory_data" / "user_config.json"
    if cfg.exists():
        data = _json(cfg)
        data.pop("api_key", None)
        for preset in data.get("presets", []):
            if preset.get("name") and preset.get("api_key"):
                preset["secret_ref"] = preset_name(preset["name"])
            preset.pop("api_key", None)
        for preset in data.get("sleep_compute_custom_models", []):
            if preset.get("name") and preset.get("api_key"):
                preset["secret_ref"] = preset_name(preset["name"])
            preset.pop("api_key", None)
        cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partners = root / "memory_data" / "partners.json"
    if partners.exists():
        data = _json(partners)
        for partner in data:
            if partner.get("api_key"):
                partner["secret_ref"] = preset_name(partner.get("id") or partner.get("name"))
            partner.pop("api_key", None)
        partners.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def migrate(root: Path = ROOT, strip_json: bool = True) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = _backup(root, stamp)
    found = _discover(root)
    # A prior failed run may have completed JSON cleanup after writing only
    # session credentials. Recover solely from the protected local backup.
    backups = sorted(BACKUP_ROOT.glob("*/memory_data/user_config.json"), reverse=True)
    for backup_file in backups:
        found.update(_discover(backup_file.parents[1]))
    if not found:
        raise RuntimeError("未发现可迁移的 API Key")
    failures = []
    for name, value in found.items():
        if not set_secret(name, value, overwrite=False) or get(name) != value:
            failures.append(name)
    if failures:
        raise RuntimeError("凭据写入或验证失败: " + ", ".join(failures) + f"；备份位于 {backup}")
    if strip_json:
        _strip_json_secrets(root)
    print(f"迁移成功: {len(found)} 个凭据；备份: {backup}")
    return backup


def restore_latest(root: Path = ROOT) -> Path:
    backups = sorted(BACKUP_ROOT.glob("*/memory_data/user_config.json"), reverse=True)
    if not backups:
        raise RuntimeError("没有找到迁移备份")
    source_root = backups[0].parents[1]
    for relative in [Path("memory_data/user_config.json"), Path("memory_data/partners.json")]:
        source = source_root / relative
        if source.exists():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    print(f"已恢复备份: {source_root}")
    return source_root


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-json", action="store_true", help="只写入并验证，不清理 JSON")
    parser.add_argument("--restore-latest", action="store_true", help="恢复最近一次配置备份")
    args = parser.parse_args()
    if args.restore_latest:
        restore_latest()
    else:
        migrate(strip_json=not args.keep_json)

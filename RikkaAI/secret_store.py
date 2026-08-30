"""Secret storage for RikkaAI.

Environment variables take precedence. On Windows, secrets are stored in the
current user's Credential Manager without requiring a third-party package.
The optional ``keyring`` package is used when available and falls back to the
native API when it is not installed in the active interpreter.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import getpass
import json
import os
import uuid
from pathlib import Path
from typing import Optional

SERVICE = "RikkaAI"

_ENV_NAMES = {
    "global_api_key": "RIKKAAI_API_KEY",
    "vision_api_key": "RIKKAAI_VISION_API_KEY",
}


def env_name(name: str) -> str:
    if name in _ENV_NAMES:
        return _ENV_NAMES[name]
    if name.startswith("preset_"):
        safe = "".join(c if c.isalnum() else "_" for c in name[7:]).upper()
        return f"RIKKAAI_PRESET_{safe}_API_KEY"
    return "RIKKAAI_" + "".join(c if c.isalnum() else "_" for c in name).upper()


def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


if os.name == "nt":
    class _CREDENTIAL_ATTRIBUTE(ctypes.Structure):
        _fields_ = [("Keyword", wintypes.LPWSTR), ("Flags", wintypes.DWORD),
                    ("ValueSize", wintypes.DWORD), ("Value", ctypes.POINTER(ctypes.c_ubyte))]

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTE)),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]

    _advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    _advapi.CredReadW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
    _advapi.CredReadW.restype = wintypes.BOOL
    _advapi.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wintypes.DWORD]
    _advapi.CredWriteW.restype = wintypes.BOOL
    _advapi.CredDeleteW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    _advapi.CredDeleteW.restype = wintypes.BOOL
    _advapi.CredFree.argtypes = [ctypes.c_void_p]


def _target(name: str) -> str:
    return f"{SERVICE}/{name}"


def _native_get(name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    ptr = ctypes.POINTER(_CREDENTIAL)()
    if not _advapi.CredReadW(_target(name), 1, 0, ctypes.byref(ptr)):
        return None
    try:
        item = ptr.contents
        if not item.CredentialBlob or not item.CredentialBlobSize:
            return None
        raw = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        _advapi.CredFree(ptr)


def _native_set(name: str, value: str) -> bool:
    if os.name != "nt":
        return False
    raw = value.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    item = _CREDENTIAL()
    item.Type = 1
    item.TargetName = _target(name)
    item.CredentialBlobSize = len(raw)
    item.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    item.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE (private to this user)
    item.UserName = getpass.getuser()
    return bool(_advapi.CredWriteW(ctypes.byref(item), 0))


def _native_delete(name: str) -> bool:
    return os.name == "nt" and bool(_advapi.CredDeleteW(_target(name), 1, 0))


def _dpapi_path() -> Path:
    path = Path(__file__).resolve().parent.parent / ".secret-store"
    path.mkdir(parents=True, exist_ok=True)
    return path / "secrets.json.dpapi"


if os.name == "nt":
    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    _crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    _crypt.CryptProtectData.argtypes = [ctypes.POINTER(_BLOB), wintypes.LPCWSTR,
                                        ctypes.POINTER(_BLOB), wintypes.LPVOID, wintypes.LPVOID,
                                        wintypes.DWORD, ctypes.POINTER(_BLOB)]
    _crypt.CryptProtectData.restype = wintypes.BOOL
    _crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(_BLOB), ctypes.POINTER(wintypes.LPWSTR),
                                          ctypes.POINTER(_BLOB), wintypes.LPVOID, wintypes.LPVOID,
                                          wintypes.DWORD, ctypes.POINTER(_BLOB)]
    _crypt.CryptUnprotectData.restype = wintypes.BOOL


def _dpapi_load() -> dict:
    if os.name != "nt":
        return {}
    path = _dpapi_path()
    if not path.exists():
        return {}
    try:
        encrypted = path.read_bytes()
        src_buf = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
        src = _BLOB(len(encrypted), src_buf)
        out = _BLOB()
        if not _crypt.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
            return {}
        try:
            raw = ctypes.string_at(out.pbData, out.cbData)
            return json.loads(raw.decode("utf-8"))
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
    except Exception:
        return {}


def _dpapi_save(values: dict) -> bool:
    if os.name != "nt":
        return False
    try:
        raw = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        src_buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        src = _BLOB(len(raw), src_buf)
        out = _BLOB()
        if not _crypt.CryptProtectData(ctypes.byref(src), "RikkaAI secrets", None, None, None, 0, ctypes.byref(out)):
            return False
        try:
            _dpapi_path().write_bytes(ctypes.string_at(out.pbData, out.cbData))
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
        return True
    except Exception:
        return False


def _persistent_env_set(name: str, value: str) -> bool:
    """Last-resort Windows user-environment fallback for restricted sessions."""
    if os.name != "nt":
        return False
    try:
        import winreg
        variable = env_name(name)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, variable, 0, winreg.REG_SZ, value)
        os.environ[variable] = value
        return os.environ.get(variable) == value
    except Exception:
        return False


def get(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(env_name(name), "").strip()
    if value:
        return value
    kr = _keyring()
    if kr:
        try:
            value = (kr.get_password(SERVICE, name) or "").strip()
            if value:
                return value
        except Exception:
            pass
    return _native_get(name) or _dpapi_load().get(name) or default


def set_secret(name: str, value: str, overwrite: bool = False) -> bool:
    value = str(value or "").strip()
    if not value:
        return False
    if not overwrite and get(name):
        return True
    kr = _keyring()
    if kr:
        try:
            kr.set_password(SERVICE, name, value)
            return get(name) == value
        except Exception:
            pass
    native_ok = _native_set(name, value) and _native_get(name) == value
    values = _dpapi_load()
    values[name] = value
    dpapi_ok = _dpapi_save(values) and _dpapi_load().get(name) == value
    return native_ok or dpapi_ok or _persistent_env_set(name, value)


def delete(name: str) -> bool:
    kr = _keyring()
    if kr:
        try:
            kr.delete_password(SERVICE, name)
        except Exception:
            pass
    values = _dpapi_load()
    values.pop(name, None)
    _dpapi_save(values)
    return _native_delete(name) or name not in values


def configured(name: str) -> bool:
    return bool(get(name, ""))


def preset_name(name: str) -> str:
    """Return the legacy name-derived ref used by migrated configurations."""
    safe = "".join(c if c.isalnum() else "_" for c in str(name).strip()).strip("_").lower()
    return "preset_" + (safe or "unnamed")


def new_preset_ref(kind: str = "preset") -> str:
    """Create a non-reusable secret reference for a newly created preset."""
    return f"{kind}_{uuid.uuid4().hex}"


def image_generation_preset_name(name: str) -> str:
    """Return a secret name isolated from chat-model preset credentials."""
    safe = "".join(c if c.isalnum() else "_" for c in str(name).strip()).strip("_").lower()
    return "image_generation_preset_" + (safe or "unnamed")


def vision_preset_name(name: str) -> str:
    """Return a secret name isolated from chat and image-generation presets."""
    safe = "".join(c if c.isalnum() else "_" for c in str(name).strip()).strip("_").lower()
    return "vision_preset_" + (safe or "unnamed")


def sleep_preset_name(name: str) -> str:
    """Return a secret name isolated for Sleep-time Compute model presets."""
    safe = "".join(c if c.isalnum() else "_" for c in str(name).strip()).strip("_").lower()
    return "sleep_preset_" + (safe or "unnamed")

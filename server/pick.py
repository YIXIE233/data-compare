"""Native Windows common item dialog (IFileOpenDialog) via ctypes COM.

Modern Explorer-style dialog: supports UNC/network shares, fast access bar,
no subprocess. Blocks until pick or cancel.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

ole32 = ctypes.OleDLL("ole32")
shell32 = ctypes.WinDLL("shell32")
shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
shell32.SHCreateItemFromParsingName.argtypes = [wt.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
user32 = ctypes.windll.user32

class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", wt.BYTE * 8)]


def _guid(s: str) -> GUID:
    g = GUID()
    if ole32.CLSIDFromString(s, ctypes.byref(g)) != 0:
        raise OSError(f"bad GUID: {s}")
    return g


CLSID_FileOpenDialog = _guid("{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}")
IID_IFileOpenDialog = _guid("{D57C7288-D4AD-4768-BE02-9D969532D960}")
IID_IShellItem = _guid("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")

COINIT_APARTMENTTHREADED = 0x2
CLSCTX_INPROC = 0x1
FOS_PICKFOLDERS = 0x20
FOS_FILEMUSTEXIST = 0x1000
SIGDN_FILESYSPATH = -2147123200  # 0x80058000 as signed int32
HR_CANCELLED = -2147023673  # HRESULT_FROM_WIN32(ERROR_CANCELLED)

# IFileOpenDialog vtable indices (IUnknown=0..2, IModalWindow.Show=3, IFileDialog=4..26)
VT_SHOW, VT_SETFILETYPES, VT_SETOPTIONS, VT_GETOPTIONS = 3, 4, 9, 10
VT_SETFOLDER, VT_SETTITLE, VT_GETRESULT = 12, 17, 20
VT_RELEASE = 2
VT_SHELLITEM_GETDISPLAYNAME = 5


class COMDLG_FILTERSPEC(ctypes.Structure):
    _fields_ = [("pszName", wt.LPCWSTR), ("pszSpec", wt.LPCWSTR)]


def _vcall(obj, idx, restype, argtypes, *args):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[idx])
    return fn(obj, *args)


def _release(obj):
    if obj:
        _vcall(obj, VT_RELEASE, ctypes.c_ulong, [])


def _shell_item(path: str) -> ctypes.c_void_p | None:
    item = ctypes.c_void_p()
    hr = shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(IID_IShellItem), ctypes.byref(item))
    return item if hr == 0 else None


def _pick(folder: bool, title: str, start: str | None, filters=None) -> str | None:
    dlg = ctypes.c_void_p()
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    inited = hr >= 0
    try:
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_FileOpenDialog), None, CLSCTX_INPROC,
            ctypes.byref(IID_IFileOpenDialog), ctypes.byref(dlg),
        )
        if hr != 0:
            raise OSError(f"CoCreateInstance failed: {hr:#x}")

        opts = wt.DWORD()
        _vcall(dlg, VT_GETOPTIONS, ctypes.c_long, [ctypes.POINTER(wt.DWORD)], ctypes.byref(opts))
        opts.value |= (FOS_PICKFOLDERS | FOS_FILEMUSTEXIST) if folder else FOS_FILEMUSTEXIST
        _vcall(dlg, VT_SETOPTIONS, ctypes.c_long, [wt.DWORD], opts)

        if filters:
            arr = (COMDLG_FILTERSPEC * len(filters))(*[COMDLG_FILTERSPEC(n, s) for n, s in filters])
            _vcall(dlg, VT_SETFILETYPES, ctypes.c_long, [ctypes.c_uint, ctypes.c_void_p], len(filters), arr)

        _vcall(dlg, VT_SETTITLE, ctypes.c_long, [wt.LPCWSTR], title)

        if start:
            item = _shell_item(start)
            if item:
                _vcall(dlg, VT_SETFOLDER, ctypes.c_long, [ctypes.c_void_p], item)
                _release(item)

        hwnd = user32.GetForegroundWindow()
        hr = _vcall(dlg, VT_SHOW, ctypes.c_long, [wt.HWND], hwnd)
        if hr == HR_CANCELLED:
            return None
        if hr != 0:
            raise OSError(f"Show failed: {hr:#x}")

        result = ctypes.c_void_p()
        hr = _vcall(dlg, VT_GETRESULT, ctypes.c_long, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(result))
        if hr != 0 or not result:
            return None
        try:
            name = ctypes.c_void_p()
            hr = _vcall(result, VT_SHELLITEM_GETDISPLAYNAME, ctypes.c_long,
                       [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)], SIGDN_FILESYSPATH, ctypes.byref(name))
            if hr != 0 or not name:
                return None
            try:
                return ctypes.wstring_at(name.value)
            finally:
                ole32.CoTaskMemFree(name)
        finally:
            _release(result)
    finally:
        _release(dlg)
        if inited:
            ole32.CoUninitialize()


def pick_file(start: str | None = None) -> str | None:
    return _pick(False, "选择来源文件", start,
                 filters=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])


def pick_dir(start: str | None = None) -> str | None:
    return _pick(True, "选择文件夹", start)

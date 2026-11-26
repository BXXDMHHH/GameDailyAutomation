"""Fail-closed Windows interactive-session and lock-screen detection."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from enum import StrEnum


class SessionState(StrEnum):
    UNAVAILABLE = "unavailable"
    DISCONNECTED = "disconnected"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


@dataclass(frozen=True, slots=True)
class SessionStatus:
    state: SessionState
    session_id: int | None = None
    desktop_name: str | None = None
    detail: str | None = None

    @property
    def can_run_interactive_tasks(self) -> bool:
        return self.state == SessionState.UNLOCKED


def inspect_windows_session() -> SessionStatus:
    """Allow execution only for an active session whose input desktop is Default."""
    if os.name != "nt":
        return SessionStatus(SessionState.UNAVAILABLE, detail="Windows session APIs are unavailable on this platform.")

    try:
        from ctypes import wintypes

        wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        user = ctypes.WinDLL("user32", use_last_error=True)

        kernel.GetCurrentProcessId.restype = wintypes.DWORD
        kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        kernel.ProcessIdToSessionId.restype = wintypes.BOOL
        wts.WTSQuerySessionInformationW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD),
        ]
        wts.WTSQuerySessionInformationW.restype = wintypes.BOOL
        wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        wts.WTSFreeMemory.restype = None
        user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        user.OpenInputDesktop.restype = wintypes.HANDLE
        user.GetUserObjectInformationW.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        user.GetUserObjectInformationW.restype = wintypes.BOOL
        user.CloseDesktop.argtypes = [wintypes.HANDLE]
        user.CloseDesktop.restype = wintypes.BOOL

        session_id = wintypes.DWORD()
        if not kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), ctypes.byref(session_id)):
            raise OSError(ctypes.get_last_error(), "ProcessIdToSessionId failed")

        buffer = ctypes.c_void_p()
        returned = wintypes.DWORD()
        WTSConnectState = 8
        if not wts.WTSQuerySessionInformationW(
            None, session_id.value, WTSConnectState,
            ctypes.byref(buffer), ctypes.byref(returned)
        ):
            raise OSError(ctypes.get_last_error(), "WTSQuerySessionInformationW failed")
        try:
            if returned.value < ctypes.sizeof(wintypes.DWORD):
                raise OSError("WTS returned an invalid session-state buffer")
            connect_state = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
        finally:
            wts.WTSFreeMemory(buffer)

        # WTSConnectState.WTSActive == 0.
        if connect_state != 0:
            return SessionStatus(
                SessionState.DISCONNECTED, session_id.value,
                detail=f"Windows session connection state is {connect_state}.",
            )

        DESKTOP_READOBJECTS = 0x0001
        DESKTOP_SWITCHDESKTOP = 0x0100
        UOI_NAME = 2
        desktop = user.OpenInputDesktop(0, False, DESKTOP_READOBJECTS | DESKTOP_SWITCHDESKTOP)
        if not desktop:
            return SessionStatus(
                SessionState.LOCKED, session_id.value,
                detail="The input desktop cannot be opened; refusing to launch desktop automation.",
            )
        try:
            needed = wintypes.DWORD()
            user.GetUserObjectInformationW(desktop, UOI_NAME, None, 0, ctypes.byref(needed))
            if needed.value == 0:
                raise OSError(ctypes.get_last_error(), "Cannot query input desktop name")
            name_buffer = ctypes.create_unicode_buffer(
                max(2, needed.value // ctypes.sizeof(wintypes.WCHAR))
            )
            if not user.GetUserObjectInformationW(
                desktop, UOI_NAME, name_buffer, needed.value, ctypes.byref(needed)
            ):
                raise OSError(ctypes.get_last_error(), "Cannot read input desktop name")
            desktop_name = name_buffer.value
        finally:
            user.CloseDesktop(desktop)

        if desktop_name.casefold() != "default":
            return SessionStatus(
                SessionState.LOCKED, session_id.value, desktop_name,
                "The input desktop is not the interactive Default desktop.",
            )
        return SessionStatus(SessionState.UNLOCKED, session_id.value, desktop_name)
    except Exception as exc:
        return SessionStatus(
            SessionState.UNAVAILABLE,
            detail=f"Windows session inspection failed closed: {type(exc).__name__}: {exc}",
        )

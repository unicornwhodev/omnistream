import { spawn } from "node:child_process";

const utcPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
const fileTimePattern = /^(?:0|[1-9]\d{0,19})$/;
const maxFileTime = 0xffff_ffff_ffff_ffffn;

function normalizeUtc(value) {
  if (typeof value !== "string" || !utcPattern.test(value)) return null;
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) return null;
  return new Date(milliseconds).toISOString();
}

function parsePid(value) {
  if (!Number.isInteger(value) || value <= 0 || value > 0x7fffffff) return null;
  return value;
}

function normalizeFileTime(value) {
  if (typeof value !== "string" || !fileTimePattern.test(value)) return null;
  try {
    const parsed = BigInt(value);
    if (parsed <= 0n || parsed > maxFileTime) return null;
    return parsed.toString();
  } catch {
    return null;
  }
}

export function parseLaunchedProcessIdentity(value) {
  let parsed;
  try {
    parsed = typeof value === "string" ? JSON.parse(value.trim()) : value;
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const pid = parsePid(parsed.pid);
  const startedAtUtc = normalizeUtc(parsed.startedAtUtc);
  const startedAtFileTimeUtc = normalizeFileTime(parsed.startedAtFileTimeUtc);
  if (!pid || !startedAtUtc || !startedAtFileTimeUtc) return null;
  return { pid, startedAtUtc, startedAtFileTimeUtc };
}

export function processIdentityMatches(expected, observed) {
  const left = parseLaunchedProcessIdentity(expected);
  const right = parseLaunchedProcessIdentity(observed);
  return Boolean(left && right && left.pid === right.pid && left.startedAtFileTimeUtc === right.startedAtFileTimeUtc);
}

function boundedText(chunks) {
  return chunks.join("").slice(0, 512).trim();
}

function spawnPowerShell(powershellExe, command, timeoutMs, onResult) {
  return new Promise((resolve) => {
    let settled = false;
    let stdout = "";
    let timeout = null;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      if (timeout) clearTimeout(timeout);
      resolve(value);
    };
    let child;
    try {
      child = spawn(powershellExe, [
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        command
      ], {
        windowsHide: true,
        stdio: ["ignore", "pipe", "ignore"]
      });
    } catch {
      finish(null);
      return;
    }
    timeout = setTimeout(() => {
      child.kill();
      finish(null);
    }, timeoutMs);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.once("error", () => finish(null));
    child.once("exit", (code) => finish(onResult(code, boundedText([stdout]))));
  });
}

/**
 * Read a process creation time from PowerShell without accepting any
 * user-controlled script input. The PID was validated as a 32-bit integer
 * before interpolating it into the fixed command.
 */
export async function queryProcessIdentity(pid, {
  powershellExe,
  timeoutMs = 5_000
} = {}) {
  const safePid = parsePid(pid);
  if (!safePid || typeof powershellExe !== "string" || !powershellExe) return null;
  const command = "$ErrorActionPreference='Stop';$p=Get-Process -Id " + safePid + ";$identity=[ordered]@{pid=" + safePid + ";startedAtUtc=$p.StartTime.ToUniversalTime().ToString('o');startedAtFileTimeUtc=[string]$p.StartTime.ToFileTimeUtc()}|ConvertTo-Json -Compress;[Console]::Out.Write($identity)";
  return spawnPowerShell(powershellExe, command, timeoutMs, (code, stdout) => {
    if (code !== 0) return null;
    return parseLaunchedProcessIdentity(stdout);
  });
}

/**
 * Read the native top-level-window handle without exposing command arguments
 * or process environment.  The hidden Kit launcher is validated separately;
 * an actual `0` handle after the streaming runtime is connected is the
 * observable Windows-side assertion used by the E2E test.
 */
export async function queryMainWindowHandle(pid, {
  powershellExe,
  timeoutMs = 5_000
} = {}) {
  const safePid = parsePid(pid);
  if (!safePid || typeof powershellExe !== "string" || !powershellExe) return null;
  const command = "$ErrorActionPreference='Stop';$p=Get-Process -Id " + safePid + ";[Console]::Out.Write(([string]$p.MainWindowHandle).Trim())";
  return spawnPowerShell(powershellExe, command, timeoutMs, (code, stdout) => {
    if (code !== 0 || !/^-?\d+$/.test(stdout)) return null;
    return stdout;
  });
}

const nativeProcessTypeDefinition = String.raw`
using System;
using System.Runtime.InteropServices;
public static class CodexProcessIdentityNative {
  [StructLayout(LayoutKind.Sequential)]
  public struct FILETIME {
    public uint dwLowDateTime;
    public uint dwHighDateTime;
    public ulong ToUInt64() { return ((ulong)dwHighDateTime << 32) | dwLowDateTime; }
  }
  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern IntPtr OpenProcess(uint desiredAccess, [MarshalAs(UnmanagedType.Bool)] bool inheritHandle, uint processId);
  [DllImport("kernel32.dll", SetLastError = true)]
  [return: MarshalAs(UnmanagedType.Bool)]
  public static extern bool GetProcessTimes(IntPtr process, out FILETIME creationTime, out FILETIME exitTime, out FILETIME kernelTime, out FILETIME userTime);
  [DllImport("kernel32.dll", SetLastError = true)]
  [return: MarshalAs(UnmanagedType.Bool)]
  public static extern bool TerminateProcess(IntPtr process, uint exitCode);
  [DllImport("kernel32.dll", SetLastError = true)]
  [return: MarshalAs(UnmanagedType.Bool)]
  public static extern bool CloseHandle(IntPtr handle);
}`;

function quotePowerShellLiteral(value) {
  return "'" + value.replace(/'/g, "''") + "'";
}

/**
 * Stop a process only when the PID still names the exact process this session
 * launched. A native Win32 handle is opened once, its creation FILETIME is
 * checked, then that same handle is terminated. No PID is resolved again
 * after identity verification, closing the check-then-kill reuse window.
 */
export async function stopProcessIfIdentityMatches(identity, {
  powershellExe,
  timeoutMs = 8_000
} = {}) {
  const expected = parseLaunchedProcessIdentity(identity);
  if (!expected || typeof powershellExe !== "string" || !powershellExe) return "invalid_identity";
  const command = "$ErrorActionPreference='Stop';Add-Type -TypeDefinition " + quotePowerShellLiteral(nativeProcessTypeDefinition) + ";$h=[CodexProcessIdentityNative]::OpenProcess(4097,$false," + expected.pid + ");if($h -eq [IntPtr]::Zero){[Console]::Out.Write('unavailable');exit 4};try{$creation=[CodexProcessIdentityNative+FILETIME]::new();$exit=[CodexProcessIdentityNative+FILETIME]::new();$kernel=[CodexProcessIdentityNative+FILETIME]::new();$user=[CodexProcessIdentityNative+FILETIME]::new();if(-not [CodexProcessIdentityNative]::GetProcessTimes($h,[ref]$creation,[ref]$exit,[ref]$kernel,[ref]$user)){[Console]::Out.Write('unavailable');exit 4};$actual=$creation.ToUInt64().ToString([Globalization.CultureInfo]::InvariantCulture);if($actual -cne '" + expected.startedAtFileTimeUtc + "'){[Console]::Out.Write('identity_mismatch');exit 3};if(-not [CodexProcessIdentityNative]::TerminateProcess($h,1)){[Console]::Out.Write('unavailable');exit 4};[Console]::Out.Write('stopped')}finally{[void][CodexProcessIdentityNative]::CloseHandle($h)}";
  return spawnPowerShell(powershellExe, command, timeoutMs, (code, stdout) => {
    if (code === 0 && stdout === "stopped") return "stopped";
    if (code === 3 && stdout === "identity_mismatch") return "identity_mismatch";
    return "unavailable";
  }) || "unavailable";
}

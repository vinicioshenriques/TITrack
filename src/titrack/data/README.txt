TITrack - Torchlight Infinite Loot Tracker
==========================================

FIRST TIME SETUP
----------------
Windows: if you downloaded this as a ZIP file, you may need to "unblock" it before
the application will run properly:

1. Right-click the downloaded ZIP file (before extracting)
2. Click "Properties"
3. At the bottom, check "Unblock"
4. Click "OK"
5. Now extract the ZIP and run TITrack.exe

Linux: extract the Linux ZIP and run ./TITrack from the extracted folder.
On Arch/CachyOS, install gtk3 and webkit2gtk if native window mode is not
available on your system.

REQUIREMENTS
------------
TITrack runs in a native window by default. This requires:

- Windows 10/11 with WebView2 Runtime, or
- Linux with GTK/WebKitGTK

If the native window backend is not available, TITrack will automatically
open in your default browser instead. Browser mode works identically to
native window mode.

To install WebView2 Runtime manually:
   https://developer.microsoft.com/en-us/microsoft-edge/webview2/

BROWSER MODE (FALLBACK)
-----------------------
You can also force browser mode manually:

1. Open Command Prompt in the TITrack folder
2. Run: TITrack.exe serve --no-window
3. Your default browser will open to the dashboard

On Linux, run: ./TITrack serve --no-window

Or create a shortcut:
- Right-click TITrack.exe -> Create shortcut
- Right-click the shortcut -> Properties
- In "Target", add: serve --no-window
- Example: "C:\path\to\TITrack.exe" serve --no-window

USAGE
-----
1. Run TITrack.exe
2. If prompted, select your Torchlight Infinite game folder
3. In Torchlight Infinite, go to Settings and click "Enable Log"
4. Log out to the character select screen, then log back in
   IMPORTANT: Do NOT close the game - just log out and back in!
5. TITrack will detect your character and start tracking loot

To sync your existing inventory, open your in-game bag and click the
Sort button - this updates TITrack with your current items.

MORE INFO
---------
GitHub: https://github.com/astockman99/TITrack

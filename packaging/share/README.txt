GG AI Desktop — share pack (GROK TUI)

This is the desktop program. The motor that matters is GROK TUI
(Grok 4.6 in the in-app terminal). Local Qwen GGUF files are NOT
included and are not required for GROK TUI.

Linux only. Not a Windows .exe.

What you need
-------------
1. Python 3 with PySide6 and Qt WebEngine
     Fedora:  sudo dnf install python3-pyside6 python3-pyside6-devel \
              qt6-qtwebengine
     or:      pip install PySide6
2. The Grok Build CLI (`grok`) and a login
     Install Grok Build from xAI, then:  grok login
3. A folder to work in (your project). Default: current directory.

Run
---
  chmod +x run-gg-ai-desktop.sh update-gg-ai-desktop.sh
  ./run-gg-ai-desktop.sh

Update (download new functions from git/GitHub)
------------------------------------------------
  ./update-gg-ai-desktop.sh

  First time, set the shared repo once:
    ./update-gg-ai-desktop.sh --set-origin https://github.com/YOU/gg-ai-desktop.git

  After that, the same command pulls with --ff-only (no force, no rewrite).
  ./run-gg-ai-desktop.sh --update
  starts by pulling, then launches.

GitHub
------
There is no GitHub remote on this machine yet (no `gh`, no origin).
Create an empty GitHub repo, then from GoldGoblins or from this zip:

  git remote add origin https://github.com/YOU/gg-ai-desktop.git
  git push -u origin main
  ./update-gg-ai-desktop.sh --set-origin https://github.com/YOU/gg-ai-desktop.git

Others clone that URL and run the launcher. New features land with update.

Optional environment
--------------------
  GG_GROK_BIN     path to the grok binary
  GG_GROK_HOME    grok home (sessions, login cache)
  GG_WORKSPACE    project folder GROK TUI opens in. Default: $PWD
  GG_AI_ORIGIN    git URL used by update-gg-ai-desktop.sh

First start: choose GROK TUI at the bottom of the chat pane.
Log in through the TUI if grok asks.

Do not put GGUF model weights in the GitHub repo. GROK TUI only needs the
grok CLI and a login.

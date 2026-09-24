#!/bin/zsh
cd -- "${0:A:h}"
for converter_python in "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
  if [[ -x "$converter_python" ]] && "$converter_python" -c 'import sys, tkinter; assert sys.version_info >= (3, 10)' >/dev/null 2>&1; then
    "$converter_python" app.py
    exit $?
  fi
done
osascript -e 'display dialog "Python 3.10 or newer with Tkinter is required. Install Python from python.org, then open this launcher again." buttons {"OK"} default button "OK"'

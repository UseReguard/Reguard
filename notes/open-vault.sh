#!/usr/bin/env bash
# Open the "EU-AI-Compliance" Obsidian vault from anywhere
# in this repo. Works in WSL by handing the obsidian:// URI off to
# Windows, which is where Obsidian is registered.
#
# Usage:
#   ./notes/open-vault.sh                       # open the vault root
#   ./notes/open-vault.sh "MVP Roadmap.md"      # open a note
#   ./notes/open-vault.sh --path                # print the WSL path to the vault
#   ./notes/open-vault.sh --windows-path        # print the Windows path
#
# Notes accept the path as you'd see it in Obsidian's file tree — no
# leading slash, no `.md` required. Obsidian resolves both forms.

set -euo pipefail

VAULT_NAME="EU-AI-Compliance"
VAULT_WIN="C:\\Users\\mrcel\\Desktop\\Obsidian Vaults\\${VAULT_NAME}"
VAULT_WSL="/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/${VAULT_NAME}"

# urlencode a single path component (Obsidian wants spaces as %20,
# slashes preserved). Only the characters that can actually appear in
# an Obsidian file path are touched.
urlencode() {
    local s="$1"
    s="${s// /%20}"
    s="${s//#/%23}"
    s="${s//\?/%3F}"
    s="${s//&/%26}"
    printf '%s' "$s"
}

# Strip a trailing .md if present so callers can pass either "Foo" or
# "Foo.md" — both resolve in Obsidian.
normalize_note() {
    local n="$1"
    n="${n%.md}"
    printf '%s' "$n"
}

# Hand a URI to Windows. `cmd.exe /c start "" <uri>` is the most reliable
# shell-out from WSL for protocol handlers: the empty quoted title is
# required so `start` doesn't treat the URI as a window title.
launch() {
    local uri="$1"
    if command -v cmd.exe >/dev/null 2>&1; then
        cmd.exe /c start "" "$uri" >/dev/null 2>&1
    elif command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -NoProfile -Command "Start-Process '$uri'" >/dev/null 2>&1
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$uri" >/dev/null 2>&1
    else
        echo "open-vault.sh: no handler found (need cmd.exe, powershell.exe, or xdg-open)" >&2
        echo "URI was: $uri" >&2
        return 1
    fi
}

case "${1:-}" in
    -h|--help)
        sed -n '2,13p' "$0"
        ;;
    --path)
        printf '%s\n' "$VAULT_WSL"
        ;;
    --windows-path)
        printf '%s\n' "$VAULT_WIN"
        ;;
    "")
        launch "obsidian://open?vault=$(urlencode "$VAULT_NAME")"
        ;;
    *)
        note="$(normalize_note "$1")"
        launch "obsidian://open?vault=$(urlencode "$VAULT_NAME")&file=$(urlencode "$note")"
        ;;
esac

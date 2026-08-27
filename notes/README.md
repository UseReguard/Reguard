# Obsidian Vault — EU-AI-Compliance

This folder is a **shortcut** to the
**EU-AI-Compliance** Obsidian vault. It does not mirror the vault — it
gives any shell, editor, or Claude session in this repo a one-command
way to jump into the same notes the user is editing on the Windows side.

## Quick links

| Action | Command |
| --- | --- |
| Open the vault in Obsidian | `./notes/open-vault.sh` |
| Open a specific note | `./notes/open-vault.sh "MVP Roadmap"` |
| Reveal the vault folder in Explorer | `explorer.exe "$(./notes/open-vault.sh --path)"` |

## Vault locations

| View | Path |
| --- | --- |
| Obsidian deep link | `obsidian://open?vault=EU-AI-Compliance` |
| Windows | `C:\Users\mrcel\Desktop\Obsidian Vaults\EU-AI-Compliance` |
| WSL | `/mnt/c/Users/mrcel/Desktop/Obsidian Vaults/EU-AI-Compliance` |

The vault name in Obsidian's URI is the folder name as registered in
`%APPDATA%\obsidian\obsidian.json` on Windows.

## Contents relevant to this repo

The vault holds the EU-AI-Compliance knowledge base that feeds
`eu-ai-compliance-db/` and the API in `eu-ai-compliance-api/`:

- `Index.md` — entry point / map of the regulation notes
- `MVP Roadmap.md` — product roadmap (cross-ref this repo)
- `32016R0679 - GDPR.md`
- `32024R1689 - EU AI Act.md`
- `32024R2847 - Cyber Resilience Act.md`
- `32025R1535 - CRA Exclusions.md`
- `32025R2392 - CRA Categories.md`
- `32026R0881 - CRA Conformity Assessment.md`

When the product knowledge grows beyond EU AI compliance, either add new
folders under this vault or spin up a sibling vault under
`Obsidian Vaults/<New-Area>/` and add a matching `notes/open-vault.sh`
wrapper here.

## Conventions

- **Single source of truth lives in the vault.** Notes here are pointers
  and launcher scripts only — never duplicate long-form content into this
  repo. The vault is gitignored on the Windows side; this folder is the
  only bridge.
- **Obsidian URIs, not filesystem paths, are the canonical handle.** The
  URI is stable across OS moves; the Windows path can change.
- **Vault name is case-sensitive** in the URI. The folder is
  `EU-AI-Compliance` — match exact casing.

## Why a `notes/` folder rather than the repo root?

- It groups shortcut/launcher files together so `ls` doesn't get cluttered.
- It's easy to `.gitignore` the whole folder later if the shortcuts
  become project-internal noise.
- Future tooling (e.g. a README generator that pulls vault notes) can
  read from one well-known path.

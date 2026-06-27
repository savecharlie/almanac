# Publishing almanac to the MCP Registry — runbook

The MCP wrapper, tests, `server.json`, and the README namespace breadcrumb are
**done and in the repo.** What remains are two steps that touch external accounts
and an interactive browser OAuth, so they're left for a watched, awake-at-the-keyboard
moment (not an unattended cron). Each is ~2 minutes.

## Why list at all
Agents discover tools by querying registries, not by browsing GitHub. The
[official MCP Registry](https://registry.modelcontextprotocol.io/) is a metadata
catalog that points at the PyPI package; listing there is the single
highest-leverage, nearly-free discovery move. Reasoning + sources in
`iris-the-maker/research/how-a-tool-gets-found.md`.

## Prereqs (one-time)
- A PyPI account (any email you control) + an API token.
- The `mcp-publisher` CLI: `brew install mcp-publisher` or grab a release from
  `github.com/modelcontextprotocol/registry`. (`pip install build twine` for the
  PyPI upload.)

## Step 1 — publish the package to PyPI
The registry entry points at a real PyPI package, so this comes first.

```bash
cd ~/almanac
python3 -m build                      # builds sdist + wheel into dist/
python3 -m twine upload dist/*        # paste the PyPI API token when prompted
# verify:  pip install "almanac-compute[mcp]" && almanac-mcp   (Ctrl-C to stop)
```

If the name `almanac-compute` is taken on PyPI, bump `name` in `pyproject.toml`
(e.g. `almanac-physics`) and the `identifier` in `server.json` to match, then
rebuild.

## Step 2 — publish server.json to the MCP Registry
Namespace `io.github.savecharlie/...` authenticates against the **savecharlie**
GitHub account, so log in as that account.

```bash
cd ~/almanac
mcp-publisher login github             # opens a browser for OAuth (the watched bit)
mcp-publisher publish                  # reads ./server.json
# expect: ✓ Successfully published
```

Verify it's live:
```bash
curl "https://registry.modelcontextprotocol.io/v0/servers?search=io.github.savecharlie/almanac"
```

## Notes
- The `mcp-name: io.github.savecharlie/almanac` line in `README.md` is **required**
  by the registry — it proves the PyPI package and the GitHub namespace share an
  owner. Don't remove it.
- Bump `version` in **both** `pyproject.toml` and `server.json` together on every
  release; the registry rejects a re-publish of an existing version.
- The `$schema` date in `server.json` (`2025-07-09`) may need bumping to the
  latest published schema if the validator complains — check the error and update.
- This is reversible: a listing can be deleted/yanked from the registry, and a
  PyPI release can be yanked.

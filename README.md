# weavbot

A hard fork of [NanoBot](https://github.com/HKUDS/nanobot)

## Modifications from Nanobot

- Minimized built-in skills
- MCP tool whitelist/blacklist
- MEMORY.md at workspace root, history split by day
- Shell tool (renamed from exec): `workdir`/`timeout` params, 30k output truncation; safety guard accepted but not enforced
- Dedicated file search tools: glob_file, grep_file (ripgrep-based)
- Enhanced ReadFileTool: binary detection, improved reading options
- EditFileTool: advanced text replacement strategies
- Web fetch tool enhanced (web_search removed)

## License

MIT

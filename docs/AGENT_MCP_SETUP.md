# Connect Steadfast to an MCP-compatible AI client

Steadfast publishes a local stdio MCP server. The official registry entry is metadata/discovery; clients that support local stdio MCP can launch the installed package directly.

## 1. Install and verify the executable

Install Python 3.10+ and run:

```bash
python -m pip install --upgrade steadfast-governance
steadfast --help
steadfast mcp-server
```

The last command starts the MCP stdio process and stays open waiting for protocol messages. Do not run it in a terminal and expect a human-readable report. Stop it with Ctrl+C after checking that it starts without a traceback.

## 2. Add a local MCP server entry

For clients that accept the standard `mcpServers` JSON format, add this entry to their MCP configuration:

```json
{
  "mcpServers": {
    "steadfast": {
      "command": "steadfast",
      "args": ["mcp-server"]
    }
  }
}
```

If the client launches tools in a restricted environment or cannot find the executable, use the absolute path to the installed `steadfast` executable as `command`. Keep the command local: the stdio server reads the repository selected by the client's working directory; it is not a hosted remote endpoint.

## 3. Client-specific notes

- **Claude Code, Cursor, Codex:** use the supported `steadfast onboard --agent claude`, `--agent cursor`, or `--agent codex` flow for Steadfast's existing repo-local integration, or add the MCP entry above if configuring MCP manually.
- **Gemini CLI, Kimi, DeepSeek, GitHub Copilot and other clients:** use the JSON entry only if that particular client/version supports local stdio MCP servers and its configuration format is compatible. Otherwise translate the same command and argument into the client's documented MCP settings; do not assume every product or web interface supports arbitrary local MCP servers.
- **Hosted/web-only assistants:** a local stdio command cannot be reached by a remote service. This package does not provide a hosted HTTP MCP endpoint.

## 4. Confirm the connection

After restarting the client, confirm that it lists the `steadfast` server and exposes tools with names beginning `steadfast_` (for example `steadfast_discover` and `steadfast_report`). Ask the client to call `steadfast_discover` and return the structured result. If the server is not listed, check that the executable is on the client's PATH and that the JSON is in the correct configuration file for that client.

## Safety and limits

Steadfast's MCP tools provide repository-local governance and inspection. Reports are signals for human review, not proof of correctness or security. Review repository content and policy before relying on findings.

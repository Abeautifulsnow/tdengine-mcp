# TDengine Query MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![smithery badge](https://smithery.ai/badge/@Abeautifulsnow/tdengine-mcp)](https://smithery.ai/server/@Abeautifulsnow/tdengine-mcp)

A Model Context Protocol (MCP) server that provides **read-only** TDengine database queries for AI assistants. Execute queries, explore database structures, and investigate your data directly from your AI-powered tools.

> **Requirements**: Python 3.12+ and the [MCP Python SDK v2](https://pypi.org/project/mcp/) (`mcp>=2.3,<3`). See [Migrating to MCP SDK v2](#migrating-to-mcp-sdk-v2) if you are coming from `0.0.x`.

## Supported AI Tools

This MCP server works with any tool that supports the Model Context Protocol, including:

- **Cursor IDE**: Set up in `.cursor/mcp.json`
- **Anthropic Claude**: Use with a compatible MCP client
- **Other MCP-compatible AI assistants**: Follow the tool's MCP configuration instructions

## Features & Limitations

### What It Does

- ✅ Execute **read-only** TDengine queries (SELECT, SHOW, DESCRIBE only)
- ✅ Provide database/stable information and metadata
- ✅ List available database and stables

### What It Doesn't Do

- ❌ Execute write operations (INSERT, UPDATE, DELETE, CREATE, ALTER, etc.)
- ❌ Provide database design or schema generation capabilities
- ❌ Function as a full database management tool

This tool is designed specifically for **data investigation and exploration** through read-only queries. **It is not intended for database administration, schema management, or data modification.**

## How to use

### Run from source code

**The recommended way** to use this MCP server is to run it directly with `uv` without installation. This is how both Claude Desktop and Cursor are configured to use it in the examples below.

If you want to clone the repository:

```bash
git clone https://github.com/Abeautifulsnow/tdengine-mcp.git
cd tdengine-mcp
```

Then you can run the server directly:

```bash
uv run src/tdengine_mcp_server -th 192.100.8.22 -db log -ll debug
```

Alternatively you can change the `.env` file in the `src/tdengine_mcp_server/` directory to set the environment variables and run the server with the following command:

```bash
uv run src/tdengine_mcp_server
```

> Important: the .env file will have **higher priority** than the command line arguments.

### Install From Pypi by `pip` command

```bash
# Install globally with pip
pip install tdengine_mcp_server
```

and then run:

```bash
python -m tdengine_mcp_server -h
```

### Install by `uvx` command

```bash
uvx tdengine-mcp-server -h
```

### Install From smithery by `npx` command

```bash
npx -y @smithery/cli@latest install @Abeautifulsnow/tdengine-mcp --client cursor --config '"{}"'
```

You can change the client after the `--client` option with alternatives `claude`, 'windsurf' and so on. Also you can refer to this: [smithery/tdengine-mcp-server](https://smithery.ai/server/@Abeautifulsnow/tdengine-mcp)

## Configuration Options

### .env file

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| LOG_LEVEL | Set the log level (DEBUG, INFO, WARN, ERROR) | INFO |
| TDENGINE_HOST | Database host for environment | localhost |
| TDENGINE_PORT | Database port | 6041 |
| TDENGINE_USERNAME | Database username | root |
| TDENGINE_PASSWORD | Database password | taosdata |
| TDENGINE_DATABASE | Database name | log |
| TDENGINE_TIMEOUT | Set the connection timeout in seconds | 30 |
| TRANSPORT | Control the transport to use (`stdio` / `sse` / `streamable-http`; `http` is an alias of `streamable-http`) | stdio |
| MCP_HOST | Host to bind for the HTTP transports (`sse` / `streamable-http`) | 0.0.0.0 |
| MCP_PORT | Port to bind for the HTTP transports (`sse` / `streamable-http`) | 8000 |

> `.env` is loaded by the server itself (`python-dotenv`), not by the MCP SDK. Since SDK v2 no longer reads `MCP_*` variables or `.env` files on its own, `MCP_HOST` / `MCP_PORT` are honoured by this server's own configuration layer.

### cli usage

```text
$ python3 -m tdengine_mcp_server -h

usage: __main__.py [-h] [-th TAOS_HOST] [-tp TAOS_PORT] [-tu TAOS_USERNAME]
                   [-pwd TAOS_PASSWORD] [-db TAOS_DATABASE] [-to TAOS_TIMEOUT]
                   [-ll LOG_LEVEL] [-trans {sse,stdio,http,streamable-http}]
                   [--host HOST] [--port PORT]

TDengine MCP Server

options:
  -h, --help            show this help message and exit
  -th, --taos-host TAOS_HOST
                        TDengine host address. Default: `localhost`
  -tp, --taos-port TAOS_PORT
                        TDengine port number. Default: `6041`
  -tu, --taos-username TAOS_USERNAME
                        TDengine username. Default: `root`
  -pwd, --taos-password TAOS_PASSWORD
                        TDengine password. Default: `taosdata`
  -db, --taos-database TAOS_DATABASE
                        TDengine database name. Default: `default`
  -to, --taos-timeout TAOS_TIMEOUT
                        TDengine connection timeout. Default: `30`
  -ll, --log-level LOG_LEVEL
                        Log level. Default: `INFO`
  -trans {sse,stdio,http,streamable-http}, --transport {sse,stdio,http,streamable-http}
                        The transport to use (`http` is an alias of
                        `streamable-http`). Default: `sse`
  --host HOST           Host to bind for the HTTP transports (sse /
                        streamable-http). Default: `0.0.0.0`
  --port PORT           Port to bind for the HTTP transports (sse /
                        streamable-http). Default: `8000`
```

HTTP endpoints: `sse` serves `GET /sse` (messages back to `POST /messages/`), `http` / `streamable-http` serves `/mcp`. The HTTP transport runs stateless with JSON responses, so it can sit behind a plain reverse proxy or load balancer.

## Integration with AI Assistants

Your AI assistant can interact with TDengine databases through the MCP server. Here are some examples:

Example queries:

```
Can you use the query tool to show me the first 10 records from the database?
```

```
I need to analyze our sales data. Can you run a SQL query to get the total sales per region for last month from the development database?
```

```
Can you list all the available databases we have?
```

### Using TDengine MCP Tools

The server exposes six tools, two resources and two prompts:

| Tool | Purpose |
|---|---|
| `query_taos_db_data` | Run any read-only SQL (`SELECT`, `SHOW`, `DESCRIBE`, ...) |
| `get_all_dbs` | List databases |
| `get_all_stables` | List stables of a database (defaults to the configured one) |
| `get_field_infos` | `DESCRIBE` a stable (field name / type / length / note) |
| `test_table_exists` | Check whether a stable exists |
| `switch_db` | `USE <db>` for the current session |

| Resource | Purpose |
|---|---|
| `taos://database` | Database list as text |
| `taos://schemas` | All stables + field schema as JSON |

| Prompt | Purpose |
|---|---|
| `taos_query` | TDengine-oriented prompt for writing queries |
| `describe_query_prompt` | Ask the model to explain a given SQL statement |

Example:

```
Use the query_taos_db_data tool to run:

SELECT * FROM customers WHERE itemid > '2025-01-01' LIMIT 10;
```

```
Use the get_field_infos tool to check the meta info about the specified stable.
```

## Security Considerations

- ✅ Only read-only queries are allowed (SELECT, SHOW, DESCRIBE)

## Troubleshooting

### Connection Issues

If you're having trouble connecting:

1. Verify your database credentials in your MCP configuration
2. Ensure the TDengine server is running and accessible
3. Check for firewall rules blocking connections
4. Enable debug mode by setting `LOG_LEVEL` in your configuration

### Common Errors

**Error: Query execution failed**

- Verify your SQL syntax
- Check that you're only using supported query types (SELECT, SHOW, DESCRIBE)
- Ensure your query is truly read-only

## Migrating to MCP SDK v2

Version `0.1.0` upgrades the server from MCP Python SDK `1.6.0` to `2.3.0`. The MCP surface (tool / resource / prompt names and arguments) is unchanged, so existing MCP clients keep working. Internally:

- `FastMCP` was renamed to `MCPServer`; `mcp.server.fastmcp.*` no longer exists and all imports moved to `mcp.server.mcpserver.*`.
- Transport options (`host`, `port`, `json_response`, `stateless_http`) are no longer constructor settings: they are passed to `run()`, and `streamable-http` (alias `http`) is available as a third transport. The `MCP_HOST` / `MCP_PORT` environment variables are read by this project instead of the SDK.
- Tool handlers that raise now surface a generic `Error executing tool <name>` to the client, so database and SQL errors are raised as `ToolError` to keep the real reason visible to the model.
- Sync handlers run on a worker thread in v2, so the blocking `taosrest` HTTP calls no longer stall the event loop.
- `mcp` 2.x pulls `mcp-types`, `httpx2` and `opentelemetry-api`, and requires `pydantic>=2.12`; `httpx` / `httpx-sse` / `pydantic-settings` are no longer installed.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

For more information or support, please [open an issue](https://github.com/Abeautifulsnow/tdengine-mcp/issues) on the GitHub repository. 

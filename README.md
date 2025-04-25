# TDengine Query MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![smithery badge](https://smithery.ai/badge/@Abeautifulsnow/tdengine-mcp)](https://smithery.ai/server/@Abeautifulsnow/tdengine-mcp)

A Model Context Protocol (MCP) server that provides **read-only** TDengine database queries for AI assistants. Execute queries, explore database structures, and investigate your data directly from your AI-powered tools.

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

### Installing via Smithery

To install TDengine Query Server for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@Abeautifulsnow/tdengine-mcp):

```bash
npx -y @smithery/cli install @Abeautifulsnow/tdengine-mcp --client claude
```

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

to get the how-to-use infomation.

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

### cli usage

```text
$ python3 -m tdengine_mcp_server -h

usage: __main__.py [-h] [-th TAOS_HOST] [-tp TAOS_PORT] [-tu TAOS_USERNAME] [-pwd TAOS_PASSWORD] [-db TAOS_DATABASE] [-to TAOS_TIMEOUT] [-ll LOG_LEVEL]

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
  -trans, --transport {sse,stdio}
                        The transport to use. Default: `sse`
```

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

The TDengine Query MCP server provides three main tools that your AI assistant can use:

#### 1. query

Execute read-only SQL queries against a specific stable:

```
Use the query tool to run:

SELECT * FROM customers WHERE itemid > '2025-01-01' LIMIT 10;
```

#### 2. info

Get detailed information about your stable:

```
Use the info tool to check the meta info about the specified stable.

DESCRIBE disks_info;
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

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

For more information or support, please [open an issue](https://github.com/Abeautifulsnow/tdengine-mcp/issues) on the GitHub repository. 

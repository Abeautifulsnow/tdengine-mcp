"""TDengine MCP Server.

Migrated to the MCP Python SDK v2 API:
``mcp.server.fastmcp.FastMCP`` no longer exists in v2, the high level server
class is ``mcp.server.mcpserver.MCPServer`` (same decorator surface).
"""

import argparse
import importlib.metadata
import logging
import os
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncIterator,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    TypedDict,
)

from dotenv import load_dotenv
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.prompts.base import Message, UserMessage
from pydantic import Field
from taosrest import RestClient

from .template import get_prompt_template

logger = logging.getLogger(__name__)

SERVER_NAME = "[TDengine-MCP-Server]"

#: Transports understood by the SDK. ``streamable-http`` is new in SDK v2.
Transport = Literal["stdio", "sse", "streamable-http"]

#: ``http`` is the name this project has exposed since 0.0.9, the SDK calls it
#: ``streamable-http``. Both spellings are accepted.
TRANSPORT_ALIASES = {"http": "streamable-http"}
SUPPORTED_TRANSPORTS = ("stdio", "sse", "streamable-http")

# Host/port defaults for the HTTP based transports. Keep listening on all
# interfaces by default: SDK v1 used to read ``MCP_HOST``/``MCP_PORT`` env vars
# (default ``0.0.0.0:8000``), SDK v2 no longer reads them, so we do it here.
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8000


def _resolve_version() -> str:
    """Report the installed package version in ``serverInfo``.

    SDK v1 fell back to the version of the ``mcp`` package itself, v2 reports an
    empty string unless the server passes its own version.
    """

    try:
        return importlib.metadata.version("tdengine-mcp-server")
    except importlib.metadata.PackageNotFoundError:  # running from source
        return "0.1.0"


__version__ = _resolve_version()


NOT_ALLOWED_TAOS_SQL: Tuple = (
    "ALTER",
    "CREATE",
    "DELETE",
    "DROP",
    "INSERT",
    "UPDATE",
    "TRIM",
    "FLUSH",
    "BALANCE",
    "REDISTRIBUTE",
    "GRANT",
    "REVOKE",
    "RESET",
    "KILL",
    "COMPACT",
)


class TaosSqlResponse(TypedDict):
    """The response from the TDengine database.

    TaosV2: The response format below is from TDengine V2.
    TaosV3: The `status` and `head` fields will be removed from the response, and a `code` field will be added
    """

    status: str
    head: List[str]
    # Column（string）、Column type（string）、Column length（int）
    column_meta: List[List[str | int]]
    data: List[List[Any]]
    rows: int


class TaosConfig(TypedDict):
    """TDengine configuration"""

    host: str
    port: int
    username: str
    password: str
    database: str
    timeout: int


class TAOSClient:
    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.timeout = timeout

        self.client: RestClient = self.init_db()

    def init_db(self) -> RestClient:
        """Build the REST client. ``taosrest`` connects lazily on first query."""

        _url = f"http://{self.host}:{self.port}"
        try:
            client = RestClient(
                url=_url,
                user=self.username,  # type: ignore
                password=self.password,  # type: ignore
                database=self.database,  # type: ignore
                timeout=self.timeout,  # type: ignore
            )
            logger.info("Have initialized the taos client.")
            return client
        except Exception as e:
            logger.error(
                f"Failed to connect to taos db => url: {_url}, host: {self.host}, username: {self.username}, database: {self.database}"
            )
            raise e

    def execute_sql(self, sql_stmt: str) -> TaosSqlResponse:
        """Execute SQL query and return the result."""

        logger.debug(f"Received TaosSQL statement: {sql_stmt}")
        validate_sql_stmt(sql_stmt)

        try:
            result = self.client.sql(sql_stmt)

            return TaosSqlResponse(
                status=result.get("status", ""),
                # https://docs.taosdata.com/2.6/reference/rest-api/#http-%E8%BF%94%E5%9B%9E%E6%A0%BC%E5%BC%8F
                # head可能会在后续版本移除, 当前版本2还能使用, 官方推荐使用column_meta
                head=result.get("head", []),
                column_meta=result.get("column_meta", []),
                data=result.get("data", []),
                rows=result.get("rows", -1),
            )
        except ToolError:
            raise
        except Exception as e:
            logger.error(f"Failed to execute SQL statement: {sql_stmt}")
            # SDK v2 turns an uncaught handler exception into a generic
            # "Error executing tool <name>" for the client. ToolError is the
            # channel that keeps the real message visible to the model.
            raise ToolError(f"Failed to execute SQL statement: {e}") from e


class TaosContext:
    def __init__(self, client: TAOSClient):
        self.client = client


def create_lifespan(client: TAOSClient):
    """Build the lifespan for the given client.

    SDK v2: the lifespan signature is unchanged,
    ``ctx.request_context.lifespan_context`` still resolves to the yielded value.
    """

    @asynccontextmanager
    async def lifespan(server: MCPServer) -> AsyncIterator[TaosContext]:
        """Manage application lifecycle for TDengine client."""

        logger.info(
            f"{SERVER_NAME} serving "
            f"{client.host}:{client.port}/{client.database}"
        )
        try:
            yield TaosContext(client)
        finally:
            pass

    return lifespan


def validate_sql_stmt(sql_stmt: str):
    """Check if the SQL statement is allowed."""

    logger.debug(f"Received TaosSQL statement: {sql_stmt}")
    sql_stmt = sql_stmt.strip()
    if sql_stmt.upper().startswith(NOT_ALLOWED_TAOS_SQL):
        logger.warning(f"Only isReadOnly statements are allowed. Received: {sql_stmt}")
        raise ToolError(
            "Security restrictions: Only read-only statements such as queries are allowed to be executed. All other operations are prohibited."
        )


def get_taos_config(args: argparse.Namespace) -> TaosConfig:
    """Retrieve the configuration for the TDengine database."""

    logger.debug("Retrieving TDengine configuration...")
    return {
        "host": os.environ.get("TDENGINE_HOST", args.taos_host),
        "port": os.environ.get("TDENGINE_PORT", args.taos_port),
        "username": os.environ.get("TDENGINE_USERNAME", args.taos_username),
        "password": os.environ.get("TDENGINE_PASSWORD", args.taos_password),
        "database": os.environ.get("TDENGINE_DATABASE", args.taos_database),
        "timeout": int(os.environ.get("TDENGINE_TIMEOUT", args.taos_timeout)),
    }


def register_tools(mcp: MCPServer):
    """Register tools for the MCP server."""

    @mcp.tool(name="test_table_exists")
    def test_table_exists(
        ctx: Context,
        stable_name: str = Field(description="The name of the stable"),
    ) -> Dict[str, bool]:
        """**Important**: Check if the `stable` exists in the current `Taos database(涛思数据库)` configuration.

        Args:
            stable_name (str): The name of the stable.

        Returns:
            Dict: The `stable_name` exists or not in the current Taos configuration.

            The key of the dictionary is the `stable_name` name, and the value is a boolean indicating whether the `stable_name` exists.
        """

        taos = ctx.request_context.lifespan_context.client
        query = f"SHOW STABLES LIKE '{stable_name}'"
        result = taos.execute_sql(query)
        # `SHOW STABLES LIKE` returns an empty `data` list when nothing matches,
        # a non-empty one otherwise. Previously this was `bool(result)`, which is
        # always True because the response dict is never empty.
        return {stable_name: bool(result.get("data"))}

    @mcp.tool(name="get_all_dbs")
    def get_all_dbs(ctx: Context) -> TaosSqlResponse:
        """Get all databases.

        Returns:
            TaosSqlResponse: All databases in the current Taos configuration.
        """

        taos = ctx.request_context.lifespan_context.client
        result = taos.execute_sql("SHOW DATABASES;")

        return result

    @mcp.tool(name="get_all_stables")
    def get_all_stables(
        ctx: Context,
        db_name: Optional[str] = Field(
            None,
            description="The name of the database. Default is None which means the configured database.",
        ),
    ) -> TaosSqlResponse:
        """Get all stables.

        Args:
            db_name (Optional[str]): The name of the database. Defaults to None. When the value is None, it means the configured database is used.

        Returns:
            TaosSqlResponse: All stables in the current Taos database.
        """

        taos = ctx.request_context.lifespan_context.client
        if db_name is None or db_name == "":
            db_name = taos.database

        result = taos.execute_sql(f"SHOW {db_name}.STABLES;")

        return result

    @mcp.tool(name="switch_db")
    def switch_db(
        ctx: Context,
        db_name: str = Field(description="The name of the database to switch to"),
    ) -> TaosSqlResponse:
        """Switch to the specified database.

        Args:
            db_name (str): The name of the database to switch to.

        Returns:
            TaosSqlResponse: The result of the `USE` command.
        """

        taos = ctx.request_context.lifespan_context.client
        result = taos.execute_sql(f"USE {db_name};")

        return result

    @mcp.tool(name="get_field_infos")
    def get_field_infos(
        ctx: Context,
        db_name: Optional[str] = Field(
            None,
            description="The name of the database. Default is None which means the configured database.",
        ),
        stable_name: str = Field(description="The name of the stable"),
    ) -> TaosSqlResponse:
        """Get the field information of the specified stable.

        Args:
            db_name (Optional[str]): The name of the database. Defaults to None. When the value is None, it means the configured database is used.
            stable_name (str): The name of the stable.

        Returns:
            TaosSqlResponse: The field information of the specified stable.
        """

        taos = ctx.request_context.lifespan_context.client
        if db_name is None or db_name == "":
            db_name = taos.database

        result = taos.execute_sql(f"DESCRIBE {db_name}.{stable_name};")

        return result

    @mcp.tool(name="query_taos_db_data")
    def query_taos_db_data(
        ctx: Context,
        sql_stmt: str = Field(
            description="The sql statement you want to retrieve data from taos db"
        ),
    ) -> TaosSqlResponse:
        """**Important**: Run a read-only SQL query on `Taos database(涛思数据库)`.

        Args:
            sql_stmt (str): The sql statement you want to retrieve data from taos db.

        Returns:
            TaosSqlResponse: All data from the specified table.

        """

        taos = ctx.request_context.lifespan_context.client
        return taos.execute_sql(sql_stmt)  # type: ignore


def register_resources(mcp: MCPServer, taos: TAOSClient):
    """Register resources backed by the shared TDengine client."""

    @mcp.resource("taos://database", mime_type="text/plain")
    def get_current_taos_database() -> List:
        """Get current taos database."""

        result = taos.execute_sql("SHOW DATABASES;")
        return result.get("data", [])

    @mcp.resource("taos://schemas", mime_type="application/json")
    def get_current_db_all_taos_schema() -> Dict[str, Any]:
        """Provide all schema in the current database."""

        schema = {}
        stables = taos.execute_sql("SHOW STABLES;")

        for stable in stables["data"]:
            if stable:
                stable_name = stable[0]
                column = taos.execute_sql(f"DESCRIBE {stable_name};")
                logger.debug(f"{stable_name} - Field meta: {column}")

                data = column.get("data", [])
                column_meta = column.get("column_meta", [])

                # Retrieve the meta definition information of the field
                table_column_meta = [meta[0] for meta in column_meta]
                table_schema = []

                # Combine the field information and the actual field data
                for d in data:
                    table_schema.append(dict(zip(table_column_meta, d)))

                schema[stable_name] = table_schema

        return schema


def register_prompts(mcp: MCPServer):
    @mcp.prompt()
    def taos_query() -> str:
        """A guide to steer llm how to query Taos(涛思) database."""

        return get_prompt_template("prompt")

    @mcp.prompt()
    def describe_query_prompt(
        query: str = Field(description="The SQL query string"),
    ) -> List[Message]:
        """
        Generate a prompt to ask an LLM to explain what a given SQL query does.

        Args:
            query: The SQL query string.

        Returns:
            A list containing a prompt message to explain the query.
        """

        logger.debug(f"Entering describe_query_prompt() with query: {query}")
        prompt_text = (
            f"Explain the following SQL query:\n\n{query}\n\n"
            "Describe what data it retrieves and suggest any potential improvements."
        )
        logger.debug(f"Generated describe_query_prompt text: {prompt_text}")
        result = [UserMessage(prompt_text)]
        logger.debug("Exiting describe_query_prompt()")
        return result  # type: ignore


def parse_arguments():
    parser = argparse.ArgumentParser(description="TDengine MCP Server")
    parser.add_argument(
        "-th",
        "--taos-host",
        type=str,
        default="localhost",
        help="TDengine host address. Default: `%(default)s`",
    )
    parser.add_argument(
        "-tp",
        "--taos-port",
        type=int,
        default=6041,
        help="TDengine port number. Default: `%(default)d`",
    )
    parser.add_argument(
        "-tu",
        "--taos-username",
        type=str,
        default="root",
        help="TDengine username. Default: `%(default)s`",
    )
    parser.add_argument(
        "-pwd",
        "--taos-password",
        type=str,
        default="taosdata",
        help="TDengine password. Default: `%(default)s`",
    )
    parser.add_argument(
        "-db",
        "--taos-database",
        type=str,
        default="default",
        help="TDengine database name. Default: `%(default)s`",
    )
    parser.add_argument(
        "-to",
        "--taos-timeout",
        type=int,
        default=30,
        help="TDengine connection timeout. Default: `%(default)d`",
    )
    parser.add_argument(
        "-ll",
        "--log-level",
        type=str,
        default="INFO",
        help="Log level. Default: `%(default)s`",
    )
    parser.add_argument(
        "-trans",
        "--transport",
        type=str,
        choices=["sse", "stdio", "http", "streamable-http"],
        default="sse",
        help="The transport to use (`http` is an alias of `streamable-http`). Default: `%(default)s`",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=DEFAULT_HTTP_HOST,
        help="Host to bind for the HTTP transports (sse / streamable-http). Default: `%(default)s`",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Port to bind for the HTTP transports (sse / streamable-http). Default: `%(default)d`",
    )

    return parser.parse_args()


def create_app(config: TaosConfig, client: Optional[TAOSClient] = None) -> MCPServer:
    """Build the MCP server.

    SDK v2 notes:
    * ``FastMCP`` -> ``MCPServer`` and ``description`` / ``version`` are real
      constructor parameters now;
    * transport options (host / port / paths) moved from the constructor to
      ``run()``, so nothing transport specific is passed here.
    """

    taos = client if client is not None else TAOSClient(**config)

    mcp_app = MCPServer(
        name=SERVER_NAME,
        description="TDengine-MCP-Server",
        instructions="Read-only TDengine query server",
        version=__version__,
        lifespan=create_lifespan(taos),
        dependencies=["python-dotenv", "taospy"],
    )

    for register_func in (register_prompts, register_tools):
        register_func(mcp_app)
    register_resources(mcp_app, taos)

    return mcp_app


def main():
    # Initialize the Taos client
    # NOTE: SDK v2 no longer reads `.env` / `MCP_*` environment variables on its
    # own, loading the dotenv file is the app's responsibility (as before).
    load_dotenv()
    args = parse_arguments()

    # Set up logging. You can adjust the log level as needed. But the environment variable LOG_LEVEL has higher priority.
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", args.log_level).upper(),
        format="%(asctime)s - %(module)s.%(funcName)s:%(lineno)d - | %(levelname)s | - %(message)s",
    )

    transport: str = os.environ.get("TRANSPORT", args.transport).strip().lower()
    # `http` is accepted as an alias of `streamable-http`.
    transport = TRANSPORT_ALIASES.get(transport, transport)
    # Exit code 1 is a hard failure, never silently fall back to another transport.
    if transport not in SUPPORTED_TRANSPORTS:
        raise SystemExit(
            f"Unsupported transport: {transport!r}. "
            f"Choose from {', '.join([*SUPPORTED_TRANSPORTS, *TRANSPORT_ALIASES])}."
        )

    mcp_app = create_app(get_taos_config(args))

    host = os.environ.get("MCP_HOST", args.host)
    port = int(os.environ.get("MCP_PORT", args.port))

    logger.info(
        f"{SERVER_NAME} server started with transport: {transport}"
        + ("" if transport == "stdio" else f" ({host}:{port})")
    )

    if transport == "stdio":
        mcp_app.run(transport="stdio")
    elif transport == "streamable-http":
        # v2: host/port/json_response/stateless_http are run() options, they used
        # to be constructor settings. Stateless + JSON responses keep the server
        # usable behind a plain HTTP proxy / load balancer.
        mcp_app.run(
            transport="streamable-http",
            host=host,
            port=port,
            json_response=True,
            stateless_http=True,
        )
    else:
        mcp_app.run(transport="sse", host=host, port=port)


if __name__ == "__main__":
    main()

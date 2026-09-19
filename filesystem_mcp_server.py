"""MCP filesystem server for resume discovery and controlled file operations."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from backend.batch_processor import BatchProcessor
from backend.filesystem_service import FileSystemService, SUPPORTED_EXTENSIONS


SERVER_NAME = "filesystem-mcp-server"
SERVER_VERSION = "0.1.0"


def _ingest_resume(filepath: str | Path) -> dict[str, Any]:
    from backend.ingestion import ingest_resume

    return ingest_resume(filepath)


def create_server(
    service: FileSystemService,
    *,
    resume_root: str | Path,
    batch_processor: BatchProcessor | None = None,
) -> MCPServer:
    """Create an MCP registry backed by an injected filesystem service."""
    root = Path(resume_root).expanduser().resolve()
    processor = batch_processor or BatchProcessor(service, ingestor=_ingest_resume)
    server = MCPServer(
        name=SERVER_NAME,
        title="Resume Filesystem MCP Server",
        description="Safe filesystem tools and resume resources for profile matching.",
        version=SERVER_VERSION,
        instructions=(
            "Use list_files before selecting a resume. File operations are restricted "
            "to configured roots and writes are protected from accidental overwrite."
        ),
    )

    @server.tool(name="read_file", structured_output=True)
    def read_file(filepath: str) -> dict[str, Any]:
        """Read a supported TXT, PDF, DOCX, or PPTX file."""
        return service.read_file(filepath)

    @server.tool(name="list_files", structured_output=True)
    def list_files(directory: str, extension: str | None = None) -> dict[str, Any]:
        """List supported files and metadata in an allowed directory."""
        return service.list_files(directory, extension)

    @server.tool(name="write_file", structured_output=True)
    def write_file(
        filepath: str,
        content: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Write a supported file inside a configured writable root."""
        return service.write_file(filepath, content, overwrite=overwrite)

    @server.tool(name="search_in_file", structured_output=True)
    def search_in_file(filepath: str, keyword: str) -> dict[str, Any]:
        """Search one file or every supported file in a directory."""
        return service.search_in_file(filepath, keyword)

    @server.tool(name="batch_process", structured_output=True)
    async def batch_process(
        paths: list[str],
        operation: str,
        keyword: str | None = None,
        max_concurrency: int | None = None,
    ) -> dict[str, Any]:
        """Read, search, or ingest multiple files with bounded concurrency."""
        return await processor.process(
            paths,
            operation=operation,
            keyword=keyword,
            max_concurrency=max_concurrency,
        )

    @server.resource(
        "resumes://catalog",
        name="resume_catalog",
        title="Resume catalog",
        description="Available resume files and their metadata.",
        mime_type="application/json",
    )
    def resume_catalog() -> str:
        return json.dumps(service.list_files(root), ensure_ascii=False)

    @server.resource(
        "resume://{relative_path}",
        name="resume",
        title="Resume content",
        description="Extracted content and metadata for one resume.",
        mime_type="application/json",
    )
    def resume(relative_path: str) -> str:
        return json.dumps(service.read_file(root / relative_path), ensure_ascii=False)

    @server.resource(
        "config://server",
        name="server_config",
        title="Server configuration",
        description="Non-secret filesystem MCP server capabilities.",
        mime_type="application/json",
    )
    def server_config() -> str:
        return json.dumps(
            {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
                "resume_root": str(root),
                "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
                "transports": ["stdio", "streamable-http"],
            },
            ensure_ascii=False,
        )

    return server


def _configured_service() -> tuple[FileSystemService, Path]:
    load_dotenv()
    resume_root = Path(os.getenv("MCP_RESUME_ROOT", "data/resumes")).resolve()
    output_root = Path(os.getenv("MCP_OUTPUT_ROOT", "output")).resolve()
    configured_roots = os.getenv("MCP_ALLOWED_ROOTS", "data/resumes,output")
    allowed_roots = [Path(value.strip()).resolve() for value in configured_roots.split(",") if value.strip()]
    return (
        FileSystemService(
            allowed_roots=allowed_roots,
            writable_roots=[output_root],
        ),
        resume_root,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport to serve.",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HTTP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_HTTP_PORT", "8000")),
    )
    args = parser.parse_args()

    service, resume_root = _configured_service()
    server = create_server(service, resume_root=resume_root)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

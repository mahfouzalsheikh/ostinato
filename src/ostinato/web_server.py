"""FastAPI application for the real-time Ostinato MIDI surface."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt

from ostinato.realtime_midi import MidiService, MidiServiceError

STATIC_DIRECTORY = Path(__file__).with_name("web_static")


class PortSelection(BaseModel):
    """Exact discovered port names, or ``null`` to disconnect."""

    input: str | None = None
    output: str | None = None


class MidiPayload(BaseModel):
    """One complete raw MIDI message."""

    bytes: list[StrictInt] = Field(min_length=1, max_length=1024)


def create_app(service: MidiService | None = None) -> FastAPI:
    """Create an application with an injectable, hardware-free MIDI service."""

    midi = service or MidiService()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await midi.start()
        try:
            yield
        finally:
            await midi.stop()

    app = FastAPI(
        title="Project Ostinato",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.midi = midi
    app.mount("/assets", StaticFiles(directory=STATIC_DIRECTORY), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIRECTORY / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/midi/status")
    async def midi_status() -> dict[str, object]:
        return midi.snapshot()

    @app.put("/api/midi/ports")
    async def select_ports(selection: PortSelection) -> dict[str, object]:
        try:
            return midi.select_ports(
                input_name=selection.input,
                output_name=selection.output,
            )
        except MidiServiceError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/midi/send")
    async def send_midi(payload: MidiPayload) -> dict[str, object]:
        try:
            return midi.send(payload.bytes)
        except MidiServiceError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.websocket("/ws/midi")
    async def midi_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = midi.subscribe()
        owner = object()
        await websocket.send_json(midi.snapshot())

        async def send_events() -> None:
            while True:
                await websocket.send_json(await queue.get())

        async def receive_commands() -> None:
            while True:
                payload: Any = await websocket.receive_json()
                if not isinstance(payload, dict):
                    await websocket.send_json(
                        {"type": "error", "message": "command must be an object"}
                    )
                    continue
                try:
                    command = payload.get("type")
                    if command == "midi.send":
                        values = payload.get("bytes")
                        if not isinstance(values, list):
                            raise MidiServiceError("midi.send requires a bytes array")
                        midi.send(values, owner=owner)
                    elif command == "ports.select":
                        input_name = payload.get("input")
                        output_name = payload.get("output")
                        if input_name is not None and not isinstance(input_name, str):
                            raise MidiServiceError("input must be a string or null")
                        if output_name is not None and not isinstance(output_name, str):
                            raise MidiServiceError("output must be a string or null")
                        midi.select_ports(
                            input_name=input_name,
                            output_name=output_name,
                        )
                    elif command == "status.request":
                        await websocket.send_json(midi.snapshot())
                    else:
                        raise MidiServiceError(f"unknown command: {command}")
                except MidiServiceError as error:
                    await websocket.send_json({"type": "error", "message": str(error)})

        sender = asyncio.create_task(send_events())
        receiver = asyncio.create_task(receive_commands())
        try:
            done, pending = await asyncio.wait(
                (sender, receiver), return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            receiver.cancel()
            midi.release(owner)
            midi.unsubscribe(queue)

    return app


def run_web(*, host: str, port: int) -> int:
    """Run the production ASGI server until interrupted."""

    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0

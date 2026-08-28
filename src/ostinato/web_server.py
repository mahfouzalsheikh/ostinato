"""FastAPI application for the real-time Ostinato MIDI surface."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, model_validator

from ostinato.midi_detection import (
    MIDI_ROLES,
    MidiDetectionError,
    NoteObservation,
    detect_midi_roles,
)
from ostinato.midi_profile import MidiProfileStore, MidiProfileStoreError
from ostinato.realtime_midi import MidiService, MidiServiceError

STATIC_DIRECTORY = Path(__file__).with_name("web_static")
MidiNote = Annotated[int, Field(ge=0, le=127)]


class PortSelection(BaseModel):
    """Exact discovered port names, or ``null`` to disconnect."""

    input: str | None = None
    output: str | None = None


class MidiPayload(BaseModel):
    """One complete raw MIDI message."""

    bytes: list[StrictInt] = Field(min_length=1, max_length=1024)


class ChannelActivity(BaseModel):
    """Observed note activity for one channel during one guided phase."""

    channel: int = Field(ge=1, le=16)
    event_count: int = Field(ge=1)
    notes: list[MidiNote] = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)


class RoleDetection(BaseModel):
    """Detected candidates and the reviewed primary channel for one role."""

    primary_channel: int = Field(ge=1, le=16)
    candidates: list[ChannelActivity] = Field(min_length=1, max_length=16)
    note_min: int = Field(ge=0, le=127)
    note_max: int = Field(ge=0, le=127)
    event_count: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_selected_candidate(self) -> RoleDetection:
        """Keep reviewed summary fields tied to an observed candidate."""

        channels = [candidate.channel for candidate in self.candidates]
        if len(set(channels)) != len(channels):
            raise ValueError("candidate channels must be unique")
        selected = next(
            (
                candidate
                for candidate in self.candidates
                if candidate.channel == self.primary_channel
            ),
            None,
        )
        if selected is None:
            raise ValueError("primary channel must be one of the observed candidates")
        if self.note_min != min(selected.notes) or self.note_max != max(selected.notes):
            raise ValueError("note range must match the selected candidate")
        if self.event_count != selected.event_count:
            raise ValueError("event count must match the selected candidate")
        if self.confidence != selected.confidence:
            raise ValueError("confidence must match the selected candidate")
        return self


class DetectedRoles(BaseModel):
    """The three physical roles labeled by the guided performance."""

    treble: RoleDetection
    bass: RoleDetection
    chord: RoleDetection


class MidiProfilePayload(BaseModel):
    """Versioned guided profile accepted from the local setup wizard."""

    schema_version: Literal[1] = 1
    detection_method: Literal["guided-activity-v1"] = "guided-activity-v1"
    input_port: str = Field(min_length=1, max_length=512)
    output_port: str | None = Field(default=None, min_length=1, max_length=512)
    roles: DetectedRoles


class CapturedNote(BaseModel):
    """One guided note-on sent to the detector."""

    channel: int = Field(ge=1, le=16)
    note: int = Field(ge=0, le=127)


class GuidedCaptures(BaseModel):
    """User-labeled note-on observations for all physical roles."""

    treble: list[CapturedNote] = Field(min_length=1, max_length=4096)
    bass: list[CapturedNote] = Field(min_length=1, max_length=4096)
    chord: list[CapturedNote] = Field(min_length=1, max_length=4096)


def create_app(
    service: MidiService | None = None,
    profile_store: MidiProfileStore | None = None,
) -> FastAPI:
    """Create an application with an injectable, hardware-free MIDI service."""

    midi = service or MidiService()
    profiles = profile_store or MidiProfileStore()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            profile = profiles.load()
        except MidiProfileStoreError:
            profile = None
        if profile is not None:
            input_name = profile.get("input_port")
            output_name = profile.get("output_port")
            if isinstance(input_name, str) and (
                output_name is None or isinstance(output_name, str)
            ):
                midi.restore_ports(input_name=input_name, output_name=output_name)
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
    app.state.profile_store = profiles
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

    @app.post("/api/midi/detect")
    async def detect_channels(captures: GuidedCaptures) -> dict[str, object]:
        observations = {
            role: tuple(
                NoteObservation(channel=item.channel, note=item.note)
                for item in getattr(captures, role)
            )
            for role in MIDI_ROLES
        }
        try:
            return {"roles": detect_midi_roles(observations)}
        except MidiDetectionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/midi/profile")
    async def load_profile() -> dict[str, object] | None:
        try:
            return profiles.load()
        except MidiProfileStoreError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.put("/api/midi/profile")
    async def save_profile(profile: MidiProfilePayload) -> dict[str, object]:
        value = profile.model_dump(mode="json")
        value["saved_at"] = datetime.now(UTC).isoformat()
        try:
            return profiles.save(value)
        except MidiProfileStoreError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.delete("/api/midi/profile", status_code=204)
    async def clear_profile() -> None:
        try:
            profiles.clear()
        except MidiProfileStoreError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

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

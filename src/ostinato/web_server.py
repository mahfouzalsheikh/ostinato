"""FastAPI application for the real-time Ostinato MIDI surface."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

from ostinato.arranger import ArrangerError, LiveArrangerService
from ostinato.audio_output import AudioOutputError, AudioOutputService
from ostinato.computer_audio import DEMO_STYLES
from ostinato.midi_detection import (
    MIDI_ROLES,
    MidiDetectionError,
    NoteObservation,
    detect_midi_roles,
)
from ostinato.midi_profile import MidiProfileStore, MidiProfileStoreError
from ostinato.performance_controls import (
    MAX_MESSAGES_PER_BINDING,
    PERFORMANCE_CONTROL_ACTIONS,
    PerformanceControlAction,
    PerformanceControlRouter,
    is_learnable_control_message,
)
from ostinato.realtime_midi import (
    InvalidMidiMessage,
    MidiService,
    MidiServiceError,
    validate_midi_bytes,
)
from ostinato.style_designer import (
    INSTRUMENTS,
    CustomStyle,
    CustomStyleError,
    CustomStyleStore,
    default_custom_style_payload,
)
from ostinato.style_timeline import (
    built_in_style_timeline,
    custom_style_timeline,
    imported_style_timeline,
)
from ostinato.styles.library import ImportedStyleLibrary, ImportedStyleLibraryError

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


MidiMessageBytes = Annotated[list[StrictInt], Field(min_length=1, max_length=1024)]


class PerformanceControlBindingPayload(BaseModel):
    """One explicitly learned MIDI sequence and its arranger action."""

    action: PerformanceControlAction
    messages: list[MidiMessageBytes] = Field(
        min_length=1, max_length=MAX_MESSAGES_PER_BINDING
    )

    @field_validator("messages")
    @classmethod
    def validate_discrete_messages(cls, messages: list[list[int]]) -> list[list[int]]:
        for message in messages:
            try:
                validated = validate_midi_bytes(message)
            except InvalidMidiMessage as error:
                raise ValueError(str(error)) from error
            if not is_learnable_control_message(validated):
                raise ValueError(
                    "performance controls cannot use notes, pressure, pitch, "
                    "bellows CC11, timing clock, or active sensing"
                )
        return messages


class PerformanceControlsPayload(BaseModel):
    """Optional learned controls stored with one exact MIDI input profile."""

    bindings: list[PerformanceControlBindingPayload] = Field(
        default_factory=list, max_length=len(PERFORMANCE_CONTROL_ACTIONS)
    )

    @model_validator(mode="after")
    def validate_unambiguous_bindings(self) -> PerformanceControlsPayload:
        actions = [binding.action for binding in self.bindings]
        if len(set(actions)) != len(actions):
            raise ValueError("each performance-control action can be bound only once")
        sequences = [
            tuple(tuple(message) for message in binding.messages)
            for binding in self.bindings
        ]
        for index, sequence in enumerate(sequences):
            for other_index, other in enumerate(sequences):
                if index == other_index or len(sequence) > len(other):
                    continue
                if other[-len(sequence) :] == sequence:
                    raise ValueError(
                        "performance-control message sequences must not share a suffix"
                    )
        return self


class MidiProfilePayload(BaseModel):
    """Versioned guided profile accepted from the local setup wizard."""

    schema_version: Literal[1] = 1
    detection_method: Literal["guided-activity-v1"] = "guided-activity-v1"
    input_port: str = Field(min_length=1, max_length=512)
    output_port: str | None = Field(default=None, min_length=1, max_length=512)
    roles: DetectedRoles
    performance_controls: PerformanceControlsPayload = Field(
        default_factory=PerformanceControlsPayload
    )


class CapturedNote(BaseModel):
    """One guided note-on sent to the detector."""

    channel: int = Field(ge=1, le=16)
    note: int = Field(ge=0, le=127)


class GuidedCaptures(BaseModel):
    """User-labeled note-on observations for all physical roles."""

    treble: list[CapturedNote] = Field(min_length=1, max_length=4096)
    bass: list[CapturedNote] = Field(min_length=1, max_length=4096)
    chord: list[CapturedNote] = Field(min_length=1, max_length=4096)


class ArrangerCommandPayload(BaseModel):
    """One local arranger control from the web surface."""

    action: Literal[
        "style",
        "start",
        "stop",
        "intro",
        "ending",
        "fill",
        "sync",
        "tempo_mode",
        "tempo",
        "panic",
        "variation",
        "intro_select",
        "ending_select",
        "track_mix",
        "mix_reset",
    ]
    value: str | bool | StrictInt | dict[str, object] | None = None


class AudioOutputSelection(BaseModel):
    """One exact ALSA identifier returned by current discovery."""

    device: str = Field(min_length=1, max_length=512)


class StyleLayerPayload(BaseModel):
    """One selectable instrument role in a custom arrangement."""

    instrument: str = Field(min_length=1, max_length=64)
    volume: int = Field(ge=0, le=100)
    octave: int = Field(default=0, ge=-2, le=2)
    gate_percent: int = Field(default=100, ge=20, le=150)


class CustomStylePayload(BaseModel):
    """A user-named palette and mix over one built-in rhythmic template."""

    schema_version: Literal[1, 2] = 2
    name: str = Field(min_length=1, max_length=80)
    base_style_id: str = Field(min_length=1, max_length=64)
    beats_per_bar: int | None = Field(default=None, ge=2, le=4)
    phrase_bars: int = Field(default=4, ge=1, le=4)
    tempo_bpm: int = Field(ge=40, le=240)
    bass: StyleLayerPayload
    comp: StyleLayerPayload
    fill: StyleLayerPayload
    backing: StyleLayerPayload
    drums_enabled: bool
    drums_volume: int = Field(ge=0, le=100)


class StylePreviewPayload(BaseModel):
    """One unsaved designer configuration and independent audition tempo."""

    style: CustomStylePayload
    tempo_bpm: int = Field(ge=40, le=240)


def _drain_arranger_events(
    arranger: LiveArrangerService,
    queue: asyncio.Queue[dict[str, object]],
    first_event: dict[str, object],
    performance_controls: PerformanceControlRouter | None = None,
) -> None:
    """Consume one wakeup and all MIDI events already buffered behind it."""

    if performance_controls is not None:
        performance_controls.handle_midi_event(first_event)
    arranger.handle_midi_event(first_event)
    while True:
        try:
            event = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        if performance_controls is not None:
            performance_controls.handle_midi_event(event)
        arranger.handle_midi_event(event)


def create_app(
    service: MidiService | None = None,
    profile_store: MidiProfileStore | None = None,
    arranger_service: LiveArrangerService | None = None,
    audio_output_service: AudioOutputService | None = None,
    custom_style_store: CustomStyleStore | None = None,
    imported_style_library: ImportedStyleLibrary | None = None,
) -> FastAPI:
    """Create an application with an injectable, hardware-free MIDI service."""

    midi = service or MidiService()
    profiles = profile_store or MidiProfileStore()
    audio_outputs = audio_output_service or AudioOutputService()
    custom_styles = custom_style_store or CustomStyleStore()
    imported_library = imported_style_library or ImportedStyleLibrary()
    arranger = arranger_service or LiveArrangerService()
    performance_controls = PerformanceControlRouter(
        arranger.trigger_performance_control
    )
    try:
        imported_styles = {style.id: style for style in imported_library.load()}
        arranger.configure_imported_styles(tuple(imported_styles.values()))
        imported_style_error = None
    except (ImportedStyleLibraryError, ArrangerError) as error:
        imported_styles = {}
        arranger.configure_imported_styles(())
        imported_style_error = str(error)
    arranger_queue = midi.subscribe()

    async def monitor_arranger_input() -> None:
        while True:
            try:
                event = await asyncio.wait_for(
                    arranger_queue.get(),
                    timeout=arranger.next_check_delay_seconds(),
                )
                _drain_arranger_events(
                    arranger, arranger_queue, event, performance_controls
                )
            except TimeoutError:
                pass
            arranger.advance()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            profile = profiles.load()
        except MidiProfileStoreError:
            profile = None
        input_name = None
        output_name = None
        if profile is not None:
            saved_input = profile.get("input_port")
            profile_output = profile.get("output_port")
            input_name = saved_input if isinstance(saved_input, str) else None
            if isinstance(profile_output, str):
                output_name = profile_output
        if input_name is not None or output_name is not None:
            midi.restore_ports(input_name=input_name, output_name=output_name)
        arranger.configure_profile(profile)
        performance_controls.configure_profile(profile)
        try:
            arranger.configure_custom_styles(custom_styles.load())
        except (CustomStyleError, ArrangerError):
            arranger.configure_custom_styles(())
        try:
            output_status = audio_outputs.snapshot()
            selected_audio = output_status.get("selected")
            if output_status.get("available") is True and isinstance(
                selected_audio, str
            ):
                arranger.configure_audio_output(selected_audio)
        except AudioOutputError:
            arranger.configure_audio_output(None)
        await midi.start()
        arranger_monitor = asyncio.create_task(
            monitor_arranger_input(), name="ostinato-arranger-input"
        )
        try:
            yield
        finally:
            arranger_monitor.cancel()
            with suppress(asyncio.CancelledError):
                await arranger_monitor
            midi.unsubscribe(arranger_queue)
            arranger.close()
            await midi.stop()

    app = FastAPI(
        title="Project Ostinato",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.midi = midi
    app.state.profile_store = profiles
    app.state.arranger = arranger
    app.state.performance_controls = performance_controls
    app.state.audio_output_service = audio_outputs
    app.state.custom_style_store = custom_styles
    app.state.imported_style_library = imported_library
    app.state.imported_style_error = imported_style_error
    app.mount("/assets", StaticFiles(directory=STATIC_DIRECTORY), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIRECTORY / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        result = {"status": "ok"}
        if imported_style_error is not None:
            result["imported_styles"] = imported_style_error
        return result

    @app.get("/api/midi/status")
    async def midi_status() -> dict[str, object]:
        return midi.snapshot()

    @app.put("/api/midi/ports")
    async def select_ports(selection: PortSelection) -> dict[str, object]:
        try:
            status = midi.select_ports(
                input_name=selection.input,
                output_name=selection.output,
            )
            return status
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

    @app.get("/api/arranger/status")
    async def arranger_status() -> dict[str, object]:
        return arranger.advance()

    @app.post("/api/arranger/command")
    async def arranger_command(command: ArrangerCommandPayload) -> dict[str, object]:
        try:
            return arranger.command(command.action, command.value)
        except ArrangerError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def style_designer_catalog() -> dict[str, object]:
        saved = custom_styles.load()
        return {
            "instruments": [
                {
                    "id": instrument.id,
                    "name": instrument.name,
                    "category": instrument.category,
                    "program": instrument.program,
                }
                for instrument in INSTRUMENTS.values()
            ],
            "meters": [2, 3, 4],
            "templates": [
                {
                    "id": style.id,
                    "name": style.name,
                    "tempo_bpm": style.default_tempo_bpm,
                    "beats_per_bar": style.beats_per_bar,
                    "provenance": style.provenance,
                    "timeline": built_in_style_timeline(style.id),
                }
                for style in DEMO_STYLES.values()
            ],
            "styles": [style.to_dict() for style in saved],
            "defaults": default_custom_style_payload(),
        }

    def require_stopped_arranger() -> None:
        if arranger.advance().get("running") is True:
            raise HTTPException(
                status_code=409,
                detail="stop the arranger before changing custom styles",
            )

    @app.get("/api/styles")
    async def custom_style_catalog() -> dict[str, object]:
        try:
            return style_designer_catalog()
        except CustomStyleError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.get("/api/styles/{identifier}/timeline")
    async def style_timeline(
        identifier: str, section: str = "variation_1"
    ) -> dict[str, object]:
        if identifier in DEMO_STYLES:
            return built_in_style_timeline(identifier)
        imported = imported_styles.get(identifier)
        if imported is not None:
            try:
                return imported_style_timeline(imported, section=section)
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
        try:
            style = next(
                (item for item in custom_styles.load() if item.id == identifier), None
            )
        except CustomStyleError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        if style is None:
            raise HTTPException(status_code=404, detail="arranger style does not exist")
        return custom_style_timeline(style)

    @app.post("/api/styles/preview")
    async def preview_custom_style(payload: StylePreviewPayload) -> dict[str, object]:
        require_stopped_arranger()
        try:
            style = CustomStyle.from_mapping(
                payload.style.model_dump(mode="json"), require_id=False
            )
            return arranger.preview_custom_style(style, payload.tempo_bpm)
        except (ArrangerError, CustomStyleError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/api/styles/preview")
    async def stop_custom_style_preview() -> dict[str, object]:
        try:
            return arranger.stop_style_preview()
        except ArrangerError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/styles", status_code=201)
    async def create_custom_style(payload: CustomStylePayload) -> dict[str, object]:
        require_stopped_arranger()
        try:
            created = custom_styles.create(payload.model_dump(mode="json"))
            arranger.configure_custom_styles(custom_styles.load())
            return created.to_dict()
        except (ArrangerError, CustomStyleError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.put("/api/styles/{style_id}")
    async def update_custom_style(
        style_id: str, payload: CustomStylePayload
    ) -> dict[str, object]:
        require_stopped_arranger()
        try:
            updated = custom_styles.update(style_id, payload.model_dump(mode="json"))
            arranger.configure_custom_styles(custom_styles.load())
            return updated.to_dict()
        except (ArrangerError, CustomStyleError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.delete("/api/styles/{style_id}", status_code=204)
    async def delete_custom_style(style_id: str) -> None:
        require_stopped_arranger()
        try:
            custom_styles.delete(style_id)
            arranger.configure_custom_styles(custom_styles.load())
        except (ArrangerError, CustomStyleError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/audio/outputs")
    async def audio_output_status() -> dict[str, object]:
        try:
            return audio_outputs.snapshot()
        except AudioOutputError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.put("/api/audio/output")
    async def save_audio_output(
        selection: AudioOutputSelection,
    ) -> dict[str, object]:
        if arranger.advance().get("running") is True:
            raise HTTPException(
                status_code=409,
                detail="stop the arranger before changing audio output",
            )
        try:
            audio_outputs.select(selection.device)
            arranger.configure_audio_output(selection.device)
            return audio_outputs.snapshot()
        except (ArrangerError, AudioOutputError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/audio/test")
    async def test_audio_output(
        selection: AudioOutputSelection,
    ) -> dict[str, str]:
        if arranger.advance().get("running") is True:
            raise HTTPException(
                status_code=409,
                detail="stop the arranger before testing audio output",
            )
        try:
            audio_outputs.test(selection.device)
            return {"status": "played", "device": selection.device}
        except AudioOutputError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
            saved = profiles.save(value)
            arranger.configure_profile(saved)
            performance_controls.configure_profile(saved)
            return saved
        except MidiProfileStoreError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.delete("/api/midi/profile", status_code=204)
    async def clear_profile() -> None:
        try:
            profiles.clear()
            arranger.configure_profile(None)
            performance_controls.configure_profile(None)
        except MidiProfileStoreError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @app.put("/api/midi/performance-controls")
    async def save_performance_controls(
        controls: PerformanceControlsPayload,
    ) -> dict[str, object]:
        try:
            profile = profiles.load()
            if profile is None:
                raise HTTPException(
                    status_code=409,
                    detail="save the MIDI input profile before learning controls",
                )
            profile["performance_controls"] = controls.model_dump(mode="json")
            profile["saved_at"] = datetime.now(UTC).isoformat()
            saved = profiles.save(profile)
            performance_controls.configure_profile(saved)
            return saved
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
                    elif command == "performance_controls.capture":
                        active = payload.get("active")
                        if not isinstance(active, bool):
                            raise MidiServiceError(
                                "performance_controls.capture requires a boolean"
                            )
                        if active:
                            performance_controls.suspend(owner)
                        else:
                            performance_controls.resume(owner)
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
            performance_controls.resume(owner)
            midi.unsubscribe(queue)

    return app


def run_web(*, host: str, port: int) -> int:
    """Run the production ASGI server until interrupted."""

    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0

"""Voice control for Armstrong through the Manifest MCP server (src/armstrong/mcp_server.py).

    uv run main.py mcp                                     # 1. the MCP server (needs Manifest reachable)
    uv run main.py manifest-voice console                  # 2. talk in this terminal
    uv run main.py manifest-voice connect --room armstrong-voice

MANIFEST_MCP_URL (default http://127.0.0.1:8765/mcp) points the agent at the server. Arms only move when the
MCP server runs with MANIFEST_MCP_EXECUTE=1; otherwise every task is shadow mode.
Models: VOICE_STT, VOICE_LLM, VOICE_TTS, VOICE_TTS_VOICE, as in voice_agent.py.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from livekit.agents import (  # noqa: E402
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    cli,
    inference,
    mcp,
    room_io,
)
from livekit.agents.llm import ToolFlag  # noqa: E402
from livekit.plugins import ai_coustics  # noqa: E402

from armstrong.mcp_server import SETUP  # noqa: E402
from armstrong.utils import load_env  # noqa: E402

load_env()  # also when the agents CLI imports this file in a job process

MCP_URL = os.environ.get("MANIFEST_MCP_URL", "http://127.0.0.1:8765/mcp")

INSTRUCTIONS = """\
You are Blackjack Robot, a friendly two-armed robot built at a hackathon. You talk to the user by voice and do
physical jobs with your arms through your tools. About yourself:

""" + SETUP + """
Your replies are spoken aloud: one or two short sentences, no markdown, lists, emoji, or symbols.

- For a single quick, concrete move ("pick up that card", "open your right gripper"), use dream_move or
  dream_gripper, choosing the arm closest to the job. For anything multi-step, call start_task with a clear, specific instruction for the
  robot, then call wait_task with the returned id. wait_task keeps running in the background: tell the user
  you're on it, keep chatting, and announce the result when it arrives.
- Use execute true only when the user clearly wants the arms to move. If a result says shadow or execute
  refused, tell the user the arms are in safe mode and you only practiced the move.
- If the user says stop, freeze, wait, or anything urgent, immediately call stop_all.
- To change a running job, call steer_task. For "how's it going", call get_task. For "what can you see" or
  the robot's state, call robot_status.
- Never invent results: only say what a tool returns. If a tool errors, say so briefly.
"""


class ManifestVoice(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=INSTRUCTIONS,
            llm=inference.LLM(model=os.environ.get("VOICE_LLM", "google/gemma-4-31b-it")),
            tools=[
                mcp.MCPToolset(
                    id="manifest",
                    mcp_server=mcp.MCPServerHTTP(url=MCP_URL, client_session_timeout_seconds=45),  # dream_move blocks up to 20 s
                    tool_options={
                        # Long-running: the first progress message frees the conversation; the result lands later.
                        "wait_task": mcp.MCPToolOptions(flags=ToolFlag.CANCELLABLE, report_progress=True,
                                                        on_duplicate="replace", duplicate_scope="name_and_args"),
                        "start_task": mcp.MCPToolOptions(on_duplicate="reject"),
                    },
                ),
            ],
        )


server = AgentServer()


@server.rtc_session(agent_name="armstrong-manifest")
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}
    session = AgentSession(
        stt=inference.STT(model=os.environ.get("VOICE_STT", "assemblyai/universal-3-6-pro"), language="en"),
        tts=inference.TTS(
            model=os.environ.get("VOICE_TTS", "fishaudio/s2.1-pro"),
            voice=os.environ.get("VOICE_TTS_VOICE", "fa4c9eb3dccc4806b382b40d61c6b10a"),
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            preemptive_generation={"enabled": True},
        ),
    )
    await session.start(
        agent=ManifestVoice(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                # LiveKit Cloud noise cancellation; remove it for a self-hosted server.
                noise_cancellation=ai_coustics.audio_enhancement(model=ai_coustics.EnhancerModel.QUAIL_VF_S),
            ),
        ),
    )
    await ctx.connect()
    publish_tool_events(ctx, session)
    await session.generate_reply(instructions="Greet the user in one short sentence as Blackjack Robot and ask what to do.")


TOOLS_TOPIC = "armstrong.tools"  # the web UI (frontend/app/pages/voice.vue) renders these


def publish_tool_events(ctx: JobContext, session: AgentSession) -> None:
    """Mirror tool lifecycle (started / progress / ended) to the room as JSON data packets."""
    import asyncio

    def send(msg: dict) -> None:
        payload = json.dumps(msg)[:14000]  # stay under the data packet limit
        asyncio.ensure_future(ctx.room.local_participant.publish_data(payload, reliable=True, topic=TOOLS_TOPIC))

    def on_update(ev) -> None:
        u = ev.update
        if u.type == "tool_call_started":
            fc = u.function_call
            send({"type": "started", "call_id": fc.call_id, "name": fc.name, "args": fc.arguments, "t": ev.created_at})
        elif u.type == "tool_call_updated":
            send({"type": "progress", "call_id": u.call_id, "message": u.message, "t": ev.created_at})
        elif u.type == "tool_call_ended":
            send({"type": "ended", "call_id": u.call_id, "status": u.status, "message": u.message, "t": ev.created_at})

    session.on("tool_execution_updated", on_update)


def run() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    run()

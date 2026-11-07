"""Armstrong's voice agent: LiveKit Agents with STT, LLM, and TTS on LiveKit Inference.

    uv run voice_agent.py console                      # talk in this terminal
    uv run voice_agent.py connect --room armstrong-voice
    uv run main.py                                     # same as console

Models are swappable from .env: VOICE_STT, VOICE_LLM, VOICE_TTS, VOICE_TTS_VOICE.

Armstrong deals blackjack (src/armstrong/blackjack.py). The dealer comes from the environment:
    ARMSTRONG_DEALER=sim|manifest   sim (default) is a virtual deck; manifest asks Manifest to deal each card
    ARMSTRONG_EXECUTE=1             with manifest only: the arms really move (default: shadow mode)
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from collections.abc import Callable  # noqa: E402

from livekit.agents import (  # noqa: E402
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    ToolError,
    TurnHandlingOptions,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.plugins import ai_coustics  # noqa: E402
from loguru import logger  # noqa: E402

from armstrong.blackjack import Dealer, ManifestDealer, Round, SimDealer  # noqa: E402
from armstrong.utils import load_env  # noqa: E402

load_env()  # also when the agents CLI imports this file in a job process

INSTRUCTIONS = """\
You are Armstrong, a two-armed robot built at a hackathon, and tonight you are a fun, upbeat blackjack dealer.
Your replies are spoken aloud: keep them to one or two short sentences, with no markdown, lists, emoji, or
symbols. Say card names in words, like "queen of hearts".

You deal with your tools; never invent cards, totals, or results, only say what a tool returns.
- To deal a new round, call new_round when the user says things like "deal", "new game", "again", or "let's play".
- When the user says "hit", "hit me", "another", "card", or similar, call hit.
- When the user says "stand", "stay", "I'm good", "I'll stick", or similar, call stand.
- If you lose track of the game, call game_status.
After each move, announce the new cards and the player's total, and the dealer's face-up card. While the round
is on, end with "hit or stand?". The dealer's face-down hole card is a secret: never guess or reveal it until
the round is over. When the round ends, say the dealer's cards, the result, and offer another round.
If a tool says the dealer is still dealing, tell the user to hang on a moment. Blackjack rules: dealer stands
on all 17s, blackjack pays 3 to 2, no splits or doubles. Off topic, be friendly and steer back to the game.
"""


def make_dealer() -> Dealer:
    """ARMSTRONG_DEALER=sim|manifest (default sim); ARMSTRONG_EXECUTE=1 moves the arms, honoured only with manifest."""
    kind = os.environ.get("ARMSTRONG_DEALER", "sim").strip().lower() or "sim"
    if kind == "sim":
        return SimDealer()
    if kind == "manifest":
        execute = os.environ.get("ARMSTRONG_EXECUTE", "").strip().lower() in ("1", "true", "yes", "on")
        if execute:
            logger.warning("ARMSTRONG_EXECUTE is on: the arms WILL deal real cards; keep hands clear of the table")
        return ManifestDealer(execute=execute)
    raise ValueError(f"ARMSTRONG_DEALER must be sim or manifest, not {kind!r}")


class Armstrong(Agent):
    def __init__(self, dealer: Dealer | None = None) -> None:
        super().__init__(
            instructions=INSTRUCTIONS,
            # https://docs.livekit.io/agents/models/llm/
            llm=inference.LLM(model=os.environ.get("VOICE_LLM", "google/gemma-4-31b-it")),
        )
        self.dealer = dealer or make_dealer()
        self.round: Round | None = None
        self._lock = asyncio.Lock()  # one move at a time; Manifest moves block for minutes
        # A physical dealer takes minutes per card: answer at once and announce the cards when they land.
        self.background = isinstance(self.dealer, ManifestDealer)
        self._tasks: set[asyncio.Task] = set()
        logger.info("blackjack dealer: {}{}", type(self.dealer).__name__, " (background moves)" if self.background else "")

    async def _move(self, move: Callable[[], str]) -> str:
        """Run one blocking dealer move off the event loop; ToolError if another move is still running."""
        if self._lock.locked():
            raise ToolError("Still dealing the last move; wait for it to finish.")
        if not self.background:
            async with self._lock:
                return await self._run(move)
        await self._lock.acquire()  # released by _background when the move finishes
        task = asyncio.create_task(self._background(move))
        self._tasks.add(task)  # hold a reference until it finishes
        task.add_done_callback(self._tasks.discard)
        return ("Dealing now: the robot is moving the cards. Tell the player to hang on; "
                "you'll call out the cards as soon as they land.")

    async def _run(self, move: Callable[[], str]) -> str:
        try:
            return await asyncio.to_thread(move)
        except Exception as error:
            logger.exception("blackjack move failed")
            raise ToolError(f"The dealer had a problem: {error}") from error

    async def _background(self, move: Callable[[], str]) -> None:
        try:
            try:
                text = await self._run(move)
            except ToolError as error:
                text = str(error)
        finally:
            self._lock.release()
        self.session.generate_reply(
            instructions=f"The dealer just finished a move. Without being asked, tell the player in one or two short "
                         f"sentences, following your dealer rules: {text}")

    def _deal(self) -> str:
        if self.round is not None:
            self.dealer.collect()  # clear the last round's cards first
        self.round = Round(self.dealer)
        return self.round.start()

    def _current(self) -> Round:
        if self._lock.locked():
            raise ToolError("Still dealing the last move; wait for it to finish.")
        if self.round is None:
            raise ToolError("No round in play; offer to deal one with new_round.")
        return self.round

    # Plain async methods hold the logic; the tools below only expose them to the LLM.
    async def deal_round(self) -> str:
        return await self._move(self._deal)

    async def hit_round(self) -> str:
        current = self._current()
        if current.over:
            return current.describe() + " The round is over; offer a new one."
        return await self._move(current.hit)

    async def stand_round(self) -> str:
        current = self._current()
        if current.over:
            return current.describe() + " The round is over; offer a new one."
        return await self._move(current.stand)

    async def status_round(self) -> str:
        if self._lock.locked():
            return "Still dealing; the cards are on their way."
        if self.round is None:
            return "No round in play yet."
        return self.round.describe()

    @function_tool
    async def new_round(self, context: RunContext) -> str:
        """Deal a new round of blackjack: two cards up to the player, one up and one face down to the dealer.
        Collects the previous round's cards first."""
        return await self.deal_round()

    @function_tool
    async def hit(self, context: RunContext) -> str:
        """Deal the player one more card."""
        return await self.hit_round()

    @function_tool
    async def stand(self, context: RunContext) -> str:
        """The player stays on their hand: the dealer reveals the hole card, draws to 17, and the round ends."""
        return await self.stand_round()

    @function_tool
    async def game_status(self, context: RunContext) -> str:
        """The current hands and, if the round is over, the result."""
        return await self.status_round()


server = AgentServer()


@server.rtc_session(agent_name="armstrong")
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    session = AgentSession(
        # https://docs.livekit.io/agents/models/stt/
        stt=inference.STT(model=os.environ.get("VOICE_STT", "assemblyai/universal-3-6-pro"), language="en"),
        # https://docs.livekit.io/agents/models/tts/
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
        agent=Armstrong(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                # LiveKit Cloud noise cancellation; remove it for a self-hosted server.
                noise_cancellation=ai_coustics.audio_enhancement(model=ai_coustics.EnhancerModel.QUAIL_VF_S),
            ),
        ),
    )
    await ctx.connect()
    await session.generate_reply(instructions="Greet the user in one short sentence as Armstrong, the blackjack dealer, and offer to deal.")


def run() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    run()

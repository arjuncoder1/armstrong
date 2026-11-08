# Armstrong web control

Nuxt 4 + Nuxt UI + livekit-client. One page: 3 camera feeds, Dream-1 task controls, status, event log.

## Run

```sh
cd frontend
bun install
bun run dev        # http://localhost:3000
```

Needs running alongside it:
- LiveKit dev server at `ws://127.0.0.1:7880`, room `armstrong-local`
- Token endpoint `GET http://127.0.0.1:8787/token?identity=<id>&room=armstrong-local` returning `{"url","token"}`, with CORS for `http://localhost:3000`
- `robot` participant (cameras `overhead_camera`, `left_wrist_camera`, `right_wrist_camera`; RPCs `home`, `park`)
- `policy-dream-1-tasks` participant (`uv run main.py dream`); RPCs `dream.status|set_task|pause|resume|to_teleop`

Override the token URL / room with `NUXT_PUBLIC_TOKEN_URL` and `NUXT_PUBLIC_ROOM`.

## Controls
- **Set task**: `dream.set_task {"task": ...}` (pauses Dream-1 first if it's driving)
- **Start**: `dream.resume`, asks you to confirm first. **The real arms move.**
- **Pause** / **STOP**: `dream.pause`
- **Park arms**: robot `park` with payload `"park"`, confirm first
- **Home arms**: robot `home` with payload `"grippers_empty"`, confirm first (the grippers open)
- **To teleop**: `dream.to_teleop`
- Status polls `dream.status` every 2 s.

`bun run build` makes a production build; `bunx nuxi typecheck` runs the type checks.

## Voice (`/voice`)
Talk to the Blackjack Robot voice agent (`manifest_voice_agent.py`, agent name `armstrong-manifest`).
- Run `uv run main.py mcp` and `uv run main.py manifest-voice dev` alongside the stack.
- Each "Start talking" makes a fresh room `armstrong-voice-*`; the token (`/token?agent=armstrong-manifest`) dispatches the agent into it.
- Shows agent state (listening / thinking / speaking), live transcript, typed chat (`lk.chat`), and tool calls the agent publishes on topic `armstrong.tools`.
- STOP tells the agent to stop (it calls `stop_all`) and pauses Dream-1 if it's in the robot room.

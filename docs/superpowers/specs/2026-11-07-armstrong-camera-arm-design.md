# Armstrong: design

MakerMods Physical AI Hackathon, Track 2 (Creative Applications). Founders Inc., San Francisco, Nov 7-8, 2026.
**Demo submission is due Sunday, Nov 8, at 3:00 PM PT.**

The idea, in the team's words: "Just give the robot arm our phone with the script, and it can follow us around." If we say "Look over there," point, or say "look at June," it has "a personal context of who we're talking about and what we're going to do." If we say "I want to retake," it does that too.

Calls made on the team's behalf are listed under "Calls not yet confirmed."

## Why

Filming yourself means stopping, walking back, re-aiming and pressing record. Armstrong is a camera operator you direct by talking. Track 2 asks what you would build if your agent had robot arms, and finalists pitch with demo videos, so the film decides who reaches the stage. This film can prove the product: the arm shoots it.

A phone gimbal already follows a face, so following alone is not the point. A gimbal can't take the phone off a table, know who June is, follow a script, look where you point, or return to where a shot began.

## What it does

1. **Set up.** Open the app on the phone and paste the script. Put the phone in its clamp on the table and step back behind the line.
2. **Hand it over.** Say "take my phone." Dream-1 finds the clamp and picks it up by its handle. Say "got it," and the arm lifts it into its camera pose.
3. **Meet the cast.** Say "this is June, she's presenting," with June facing the phone. It learns her face, her role and where she is standing.
4. **Direct.** Say "shot one." It looks at who the script names, counts down, and records on the phone.
5. **Change things live.** "Armstrong, look at Arjun." "Armstrong, follow me." "Armstrong, look over there," while pointing. "Next."
6. **Retake.** "Cut, I want to retake." It keeps the old file, returns to where that take started, counts down and records a new one.
7. **Keep the takes.** They are saved on the phone, named by shot and take.

The phone is never passed hand to hand: the SDK's safety rules keep people out of the workspace while the arm is powered.

## The parts

**Phone app.** A web page on the phone, joining a LiveKit room as `phone`. It publishes the camera and mic, plays the director's voice, and records to a file when told. It holds the script box and the takes list. It should keep the screen awake and use the back camera in landscape.

**Camera operator.** A new Python program that is a Portal operator, like LiveKit's hand teleop, and moves only the phone arm. It reads the phone's video, finds faces and hands, and aims. Every action carries all 14 fields, with the other arm's latched from the robot's state each time this program takes control.
- **Aim:** base pan and wrist flex form a true pan-tilt. All other joints hold the camera pose. Wrist roll is not used to pan, because it rolls the horizon once the phone tilts.
- **Modes:** hold, carry, look at a person, follow a person, look where pointed. Carry is the one scripted move: a walk of the whole arm at no more than 0.3 rad/s, from the pick-up to the camera pose, and back before a park.
- **Grip:** while holding, the gripper target stays below the measured width so the motor keeps squeezing. Whether that holds is a first-slot test, because `home` and park command the measured width (`src/utils/metal.py:292`) and could loosen the jaws.
- **Control:** aim at the person's bearing, meaning the joint angle when the frame was taken plus the pixel offset, so video delay can't make the arm hunt. Use a deadband and an acceleration limit so the footage stays calm.
- **Pointing:** the finger ray gives a direction in the image, not a spot in the room. It pans that way at about 0.3 rad/s until someone says "stop," a person or named thing appears along the ray, or it has turned 90 degrees. The person pointing must be in frame. Without a visible hand, it asks where.
- **Finding people:** go to where the person was last seen, then sweep slowly. If they aren't found, say so.

**Voice director.** LiveKit's voice agent, extended with new tools: `meet_person`, `look_at_person`, `follow_person`, `look_where_pointed`, `hold_still`, `look_around`, `start_take`, `cut`, `retake`, `next_shot`, `go_to_shot`, `remember`, `take_phone`, and `got_phone`. It reports only what tool results say.

**Personal context.** A JSON file on the laptop, loaded into the agent's instructions before every reply. It holds:
- People: name, role, notes, face data, and where they were last seen.
- The script, and which shot is current.
- Takes: shot, file name, kept or rejected.
- Direction notes, such as "more headroom on June."

This is how "look at her" or "the presenter" resolves to a person. Cast names also go to speech-to-text as key terms so "June" isn't misheard.

**Script.** Plain text, one shot per line, as `target: what happens`, such as `June: introduces the project`. The target is a person, a named thing, or `wide`. "Next" advances. Advancing automatically when the next line is heard is a stretch goal.

**Dream-1.** Dream-1's visible job is taking the phone from wherever it was set inside a marked area on the phone arm's side of the table. A scripted arm can't do that, and three Dream Labs researchers are judging. The right arm always holds the phone, and demonstrations use only that arm.

It runs through `dream-1-tasks` behind a small wrapper. Dream-1's replies include both arms and both grippers, so without the wrapper it could open the jaws holding the phone. The wrapper overwrites the other arm's 7 fields with values latched from the robot's state when it takes control, with a test that they never change during a turn.

The code has no signal for "done," and the task monitor needs a GPU. So a person watching says "got it." The director checks that the measured jaw width matches the handle, pauses Dream-1, and gives control to the camera operator, which carries the phone to the camera pose. If nobody confirms within 60 seconds, Dream-1 pauses and the director says so.

Stretch goals with the free arm: "hold this," and resetting a knocked-over prop before a retake.

**Retake.** The camera operator logs each take's start pose and commanded path. "Retake" walks back to the start pose and re-runs the shot. Replaying the identical camera move is a stretch goal.

## How it fits the repo

`thirdparty/portal-makermods` is LiveKit's code for this event. It stays unedited, and new code in this repo imports from it. `setup.sh` needs one change first: its plain install puts the code in `site-packages`, where `CONFIG_PATH` can't find `portal.yaml` (`src/utils/common.py:22-23`), and it skips the `voice` and `hands` groups. Install it editable, with those groups. This comes from reading the code, not running it.

| Process | Source | Job |
|---|---|---|
| `uv run robot` | LiveKit's, unchanged | Owns the CAN bus, joint limits, speed limit and parking |
| Camera operator | New | Portal operator, moves the phone arm only; answers `camera.*` RPCs from `voice-agent` |
| Dream-1 wrapper | New, wraps `dream-1-tasks` | Takes the phone, moving one arm only |
| Voice director | New, extends `voice_agent.py` | Conversation in its own room; calls `camera.*`, `dream.*` and `phone.*` |
| Phone app | New | Camera, mic, speaker and recording; answers `phone.*` RPCs |

Two rooms, as LiveKit's tutorial requires:
- The robot's room holds Portal peers.
- `portal-voice` holds the conversation. The phone joins it, and the camera operator joins it hidden to watch the phone's video. The agent must listen to `phone` by identity, because by default it takes the first participant it finds.

Facts from the code that shape this:
- Only one operator drives at a time, so Dream-1 and the camera operator take turns.
- **An operator must send all 14 fields.** Portal fills a missing field with that operator's last sent value, or 0.0 if it never sent one (`livekit-portal-core/src/data.rs`, v0.3.0). A first one-arm action would drive the other arm toward zero and close its jaws. Sending nothing makes both arms hold. Read on GitHub, not run.
- The robot program needs two arms and three cameras, or it won't start.
- The robot loop runs at 30 Hz.

## Goals

- The arm really holds the phone and records with it, and the film is shot on that phone.
- "Look at June" finds the right person among at least three people by name, in one real-time take.
- Following a walking person and "look over there" with a pointing finger both work.
- A script of at least three shots runs by voice, and a retake returns to the shot's start pose and records a new file.
- Dream-1 visibly picks up the phone rig from varied positions inside the marked area.

## Non-goals

- Zoom, or dollying the arm for framing.
- Passing the phone directly between a person and the arm.
- A native app, or a polished UI.
- Recognizing anyone who hasn't been introduced.
- LeRobot/ACT training, the task monitor, or leader-arm teleop.

## Anti-goals: failure even if it works

- A pre-recorded joint path presented as a live reaction, or unlabeled sped-up footage.
- A dropped or damaged phone, a damaged shared arm, or removal from a station.
- Storing faces of people who didn't agree.
- A demo where Dream-1 is incidental.

## The film

About one minute:
1. Cold open: the phone on the table, "take my phone," Dream-1 picks it up.
2. Cut to what that phone sees: "this is June."
3. "Look at Arjun," then pointing, then following someone walking, in one real-time take.
4. A flubbed line: "cut, I want to retake," and the arm returning.
5. Reveal: this film was shot by the arm.

**Honesty rules:** shots showing the arm come from a second camera, and the film says so. Sped-up footage is labeled. A clamp loaded by a person is labeled. Only claim what ran.

**Crew:** at least four. The emergency-stop holder does nothing else, and three people are on camera. The second camera can sit on a tripod, and people nearby who agree can fill in.

## Priorities

Fine-tunes can't wait, so Dream-1 gets the first robot time. Everything else can be built away from the arm: the phone page on a phone, the camera operator on a laptop webcam with simulated joints, and the voice tools against a fake camera. If robot time runs short, the order is look-at and voice, then Dream-1's pick-up, then retake, then following, then script. Dream-1 and a LiveKit voice agent are what the track asks for, so neither can be dropped.

## Constraints

**Time.** Hacking runs Saturday 10:00 AM-10:00 PM and Sunday 10:00 AM-3:00 PM. Robot time is booked and shared.

**Fine-tunes.** Public terms are about 4-5.5 hours and $200 per job, from a secondary source, so about two or three: as soon as demos exist, by 5:30 PM, and by 10:00 PM Saturday. A Sunday job returns too late. Wording is free to change, so test it first. Paying needs approval from whoever's credits or card it uses.

**The numbers, from `calc/follow_loop.py`.** Load case: 0.32 kg phone, case and clamp (assumed), held still, the phone's centre 0.08 m past the jaws on a handle. Margins are against continuous ratings of 6, 6 and 5 N*m, from reseller listings rather than RobStride's datasheet, and include a 15% allowance.

| Pose (upper arm vertical, forearm up 65 degrees) | Torque J2 / J3 / J4 (N*m) | Margin |
|---|---|---|
| **Tool up: the camera pose** | 2.04 / 2.04 / 0 | **+1.94** |
| Tool tilted 30 degrees toward the floor | 3.79 / 3.79 / 1.75 | +0.58 |
| Tool tilted 30 degrees back | 0.29 / 0.29 / 1.75 | +1.86 |
| Tool level | 5.54 / 5.54 / 3.50 | +0.08 |
| Fully stretched, tool level (a different arm pose) | 14.88 / 8.33 / 3.50 | **-0.60, fails: never hold here** |

| Check | Result |
|---|---|
| Panning with the base | Phone stays 0.08-0.26 m from the axis; 2 rad/s^2 needs 0.03-0.11 N*m |
| Walker crossing at 1.4 m / 2 m / 3 m | 1.00 / 0.70 / 0.47 rad/s |
| Robot step limit at 30 Hz | Default 0.087 rad gives 2.61 rad/s. The macOS example's 0.02 rad gives 0.60 rad/s, too slow for a walker closer than 2.33 m. 1 rad/s needs 0.034 |
| View step at 1 rad/s and 30 Hz | 1.91 degrees per command; whether the driver smooths this is unknown |
| Walker at 2 m with a simple pixel-error loop | Trails by 15 / 23 / 38 degrees at 0.2 / 0.3 / 0.5 s video delay. Half a landscape frame is 34.7 degrees and half a portrait frame is 21.3, so film in landscape |
| Face width at 3 m / 5 m | 56 / 34 px at 720p, 85 / 51 px at 1080p. Introduce people close up; once recognized, track by position |

**Not analyzed:** motor heat over long holds, video shake, link flex, gear backlash where joint torque is near zero, the handle slipping in the jaws, and Wi-Fi jitter. Poses ignore link kinks. These are reasons to try, not guarantees.

## Safety and privacy

These are not optional.

- Keep people outside a taped line at least 1 m from the arm while it is powered. Full reach is 0.66 m to the jaws and 0.74 m to the phone's centre.
- Someone stays at the emergency stop during every powered test and does nothing else. The repo doesn't provide one, so ask MakerMods what the station has. `p` in the robot terminal is a 10 degrees per second walk and then motors off, so it isn't a fast stop. If the stop cuts power, the arm falls with the phone, because it has no brakes. Voice isn't an emergency stop either: a spoken "stop" takes a second or two.
- Reach in only when the arm is parked and the emergency-stop holder agrees. Stopping an operator leaves the arm holding under power. Ctrl-C on `uv run robot` walks both arms to rest and switches them off, so treat it as a park, phone included. If that walk fails, the arms stay powered.
- Filming limits, enforced in the camera operator: pan and wrist flex only, 1 rad/s, 2 rad/s^2, tilt within 30 degrees of tool up. The carry move is the only exception, at no more than 0.3 rad/s.
- Get MakerMods' OK before changing the step limit. Keep LiveKit's joint limits and speed limit in place.
- **Assume parking drops the phone.** Parking switches the motors off, so the jaws may let go. Tether the clamp to the arm, use a mat, and start with a dummy of the same weight.
- Hard-code the rule that Dream-1 never commands the arm holding the phone once it is in the camera pose.
- Stop words ("stop," "wait," "hold on") hold the camera as well as Dream-1. A false match only freezes the shot.
- Film only people who agreed. Face data is taken only when someone is introduced, stays on the laptop, and is deleted after the event. Strangers' faces are never stored.
- No LiveKit secret reaches the phone. Mint a short-lived token on the laptop and open the page from a QR code, so nobody else can join and talk to the robot. Keys stay in git-ignored `.env`.

## While a take is rolling

- The agent stays silent, enforced in code rather than the prompt, because the phone's speaker and mic are also recording. The countdown ends before recording starts.
- Only lines starting with "Armstrong," plus "cut" and stop words, count as directions, so a script line can't move the arm.
- Spoken directions land on the take's audio. Log their times so they can be trimmed.

## First steps

**No robot needed, start now:**
1. **Phone page spike, 30 minutes.** Publish to LiveKit and record at the same time on an iPhone, then measure video delay to the laptop. This is the riskiest unknown that needs no arm.
2. **Camera operator, offline.** Recognize three people and aim simulated joints, using a laptop webcam.
3. **Voice tools** against a fake camera.

**First robot slot:**
1. Ask MakerMods and David Chen: are there two arms and three cameras, what is the emergency stop, which computer and operating system, can we plug in our own, how does Dream-1 connect, how do fine-tunes and credits work, and is a 1 rad/s step limit OK?
2. Run `uv run robot --check-arms`, then `uv run robot --parked`.
3. Film "take the phone" on Dream-1, at a safe distance, using the dummy.
4. Run it from 10 random positions. Count successes and time a call. Those counts set the first fine-tune's focus.
5. Record about 5 minutes of demonstrations for the first fine-tune.
6. With the dummy low over the mat, test the grip, then `home`, then a park, watching whether the jaws loosen.
7. Hold the dummy in the camera pose for 10 minutes, logging motor temperatures. Then pan and tilt slowly, then at 1 rad/s, and film the result to judge shake.

## Decision points

- **Only one arm at the station:** the robot program won't start. Ask David Chen how to run one arm, or drive it directly with the Maker Arm SDK.
- **Video delay above 0.4 s:** try a LiveKit server on the same network, and slow the follow.
- **The phone can't stream and record together:** record from LiveKit instead, or build a small native app.
- **Saturday 6:00 PM, phone pick-up below 5 of 10:** make the handle bigger and shrink the area it starts in. If that fails, a person loads the clamp, labeled, and Dream-1's visible job moves to "hold this" with the free arm.
- **Face recognition unreliable:** fall back to where each person was introduced and last seen.
- **Motors run hot in the hold test:** lower the arm's holding load, shorten takes, and rest between them.
- **Sunday 10:00 AM:** start filming with whatever works.
- **Sunday 12:30 PM:** stop adding features.
- **Sunday 2:30 PM:** upload, leaving 30 minutes of buffer.

## Unknowns to settle at the venue

- The Track 2 rubric and submission format.
- Whether the station has two arms and three cameras, and how much robot time the team gets.
- Fine-tune turnaround, credits and data format.
- What the station's emergency stop is, and whether it cuts power.
- How the jaws behave through Dream's `robots` driver: what target keeps them squeezing, and what happens when motors switch off. That code wasn't read.
- Whether Dream-1 tolerates one arm sitting still and holding something during its task.
- Who has which phone. The page must also be tested on it.

## Left to the builder

- The clamp and handle, and how they sit on the table so the jaws can grip them and the phone ends up upright with the tool pointing up. A flat-sided handle keeps the lens aligned. Sturdy and simple beats clever; printed parts should be filleted, not blocky.
- Face detection and recognition. OpenCV's YuNet and SFace are a suggestion because OpenCV is already a dependency.
- The web framework. The repo's `.gitignore` suggests Nuxt.
- Control gains, deadband, and the exact camera pose.
- The code layout, within the rule that the submodule stays unedited and one process owns the CAN bus.
- Models for the agent. LiveKit's defaults are the starting point.

## Calls not yet confirmed

- Dream-1's job is picking up the phone rig, with a clamp and handle rather than a bare phone.
- The right arm holds the phone, and the rig starts in a marked area on its side of the table.
- A person says "got it" to end Dream-1's turn, with a 60-second timeout.
- The carry move, capped at 0.3 rad/s.
- The film is the demo, so no live run on stage is planned.
- A web page rather than a native app.
- What "personal context" holds, and that people are introduced by voice.
- The script format, and "next" as the manual way forward.
- "Armstrong" as the wake word during a take.
- Base pan and wrist flex for aiming, tool pointing up, landscape video.
- The order under Priorities, the decision times, and the 5-of-10 threshold.
- Bottle Flip Showdown is set aside. Its 3.00 rad/s throw exceeds the robot's 2.61 rad/s default limit. Its plan remains in the `bottle-flip-showdown` repo.

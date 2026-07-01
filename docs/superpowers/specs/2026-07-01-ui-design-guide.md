# UI Design Guide — Local Desktop AI Agent

**Date:** 2026-07-01
**Purpose:** A design brief, not a spec. It frames *what the GUI is for* and *what it must convey* so a visual design can be built on top of it. It deliberately does **not** prescribe colors, typography, spacing, or component styling — those are the designer's call.

## Core idea

A person talks to their computer in plain language — "move all the PDFs in Downloads into Documents/PDFs" — and watches an AI agent carry it out, step by step, on their real machine. The whole thing runs locally: no cloud, no account, no network.

The product is a **conversation with a capable but fallible assistant that has its hands on your files.** Two feelings have to coexist in the UI:

- **Ease** — it should feel as simple as chatting. You type; it does.
- **Control** — because a small local model *will* sometimes misjudge what you meant, the user must always feel they can see what's happening and stop or veto anything before it touches their files.

If the design makes it feel effortless but not safe, it fails. If it feels safe but bureaucratic (approve every trivial thing), it also fails. The line to walk: **effortless for reads, deliberate for destructive actions.**

## Who it's for

A single user on their own Windows machine — likely technical enough to want an AI file assistant, but using it casually, not studying a manual. One person, one window, one conversation at a time.

## What the UI must convey

1. **This is a conversation.** The primary interaction is chat: the user's commands and the agent's replies.
2. **You can see the agent working.** Not a spinner-then-answer black box — the user watches the agent's steps unfold ("listing Downloads…", "moving 12 files…"). Transparency is the trust mechanism.
3. **Destructive actions pause for you.** When the agent wants to move or delete something, it stops and asks. This moment is the most important in the whole app — the user must clearly understand *what* is about to happen and be able to approve or reject it without ambiguity.
4. **You set the boundaries.** The user can see and change what the agent is allowed to touch (which folders) and can run in a safe "dry-run" mode that shows intentions without acting.

## The four surfaces

Described by *purpose*, not layout. How they're arranged and styled is open.

- **Chat thread** — the main surface. Where the user types commands and reads the agent's natural-language responses. The heart of the app.
- **Action log** — a live, running view of what the agent is *doing* step by step, distinct from what it's *saying*. This is where "see the agent working" lives. It should read as a factual activity trail, not chat.
- **Approval prompt** — appears only when the agent wants to do something destructive. It interrupts, states plainly what's about to happen (the operation and the specific files), and offers a clear approve / reject choice. This is a decision moment, and it should feel like one — the user should never approve something without understanding it.
- **Settings** — where the user manages allowed folders, model size, and the dry-run toggle. Secondary; out of the way until needed.

## Tone

Calm, plain-spoken, honest. The agent is a competent helper, not a mascot and not a corporate assistant. When it's unsure or something fails, it says so plainly. No hype, no personality gimmicks. The emotional target is *quiet confidence* — the user should feel the tool is trustworthy because it's transparent, not because it's slick.

## Non-negotiables (functional, not visual)

These constrain the design regardless of aesthetic direction:

- The action log and the chat responses are **different kinds of content** and should be distinguishable — one is the agent talking, the other is the agent doing.
- The approval prompt must show the **concrete operation and target files**, not a generic "allow this action?" — the user's ability to catch a mistake depends on seeing specifics.
- There must be a visible way to **stop** a running agent.
- The user must be able to tell, at a glance, whether **dry-run mode** is on — acting-for-real vs. just-showing is a state they should never be confused about.

## Out of scope for this guide

Everything visual: color palette, type, iconography, spacing, animation, component library, light/dark, exact layout. Those are for the design phase — this guide only defines the intent they should serve.

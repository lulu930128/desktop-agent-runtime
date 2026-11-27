"""Extractive episodic context. Keep speakers and source offsets attached to every excerpt."""

import re
from .memory_semantics import local_encoder


def _turn_episodes(messages, *, legacy=False):
    """Pair completed turns. Legacy adjacency is conversation evidence of unknown completion."""
    pending = None
    for index, message in enumerate(messages):
        if message.get("role") in {"human", "user"}:
            pending = (index, message)
            continue
        if not pending or message.get("role") not in {"ai", "assistant"}:
            pending = None
            continue
        first, human = pending
        pending = None
        identity = human.get("turn_id", "")
        if identity:
            if identity != message.get("turn_id") or message.get("completion") not in {
                "complete",
                "legacy_unknown",
            }:
                continue
        elif not legacy:
            continue
        fragments = []
        for role, source in (("user", human), ("assistant claim", message)):
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[。！？.!?])\s*|\n+", source.get("content", ""))
                if s.strip()
            ]
            if not sentences:
                continue
            # Preserve constraints, numbers and open decisions even when context is compacted.
            salient = {0, len(sentences) - 1}
            salient.update(
                i
                for i, s in enumerate(sentences)
                if re.search(
                    r"\d|沒有|尚未|不|未|ない|ません|\b(not|never|pending|blocked|failed|decided)\b",
                    s,
                    re.I,
                )
            )
            encoder = local_encoder()
            if encoder and len(sentences) > 2:
                matrix = encoder.encode(sentences)
                salient.add(int((matrix @ matrix.mean(axis=0)).argmax()))
            fragments.append(
                role + ": " + " ".join(sentences[i] for i in sorted(salient))
            )
        if len(fragments) == 2:
            yield (
                index,
                {
                    "role": "episode",
                    "content": "\n".join(fragments),
                    "timestamp": human.get("timestamp", ""),
                    "turn_id": identity,
                    "project_id": human.get("project_id", ""),
                    "source_span": [first, index],
                    "completion": message.get("completion") or "legacy_unknown",
                    "summary_version": 1,
                },
            )


def episode_messages(messages, *, legacy=False):
    """Ground an explicit continuation in its immediately preceding completed turn."""
    previous = None
    for index, episode in _turn_episodes(messages, legacy=legacy):
        current = episode
        start = current["source_span"][0]
        query = messages[start].get("content", "").strip()
        continuation = re.match(
            r"^(?:那後來|那後續|後來呢|接著呢|那個呢|然後呢|それから|その後|what happened next|and then|what about that)",
            query,
            re.I,
        )
        if (
            continuation
            and previous
            and start == previous["source_span"][-1] + 1
            and current["project_id"] == previous["project_id"]
            and previous["turn_id"]
            and current["turn_id"]
        ):
            episode = dict(
                current,
                content=previous["content"] + "\n" + current["content"],
                source_span=[previous["source_span"][0], index],
                source_turns=[previous["turn_id"], current["turn_id"]],
                summary_version=2,
            )
        yield index, episode
        previous = current

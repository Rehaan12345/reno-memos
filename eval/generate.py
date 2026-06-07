"""
generate.py — the single Claude generation path shared by every system.

All four systems generate through this one function with the contract's shared
params (model, max_tokens, temperature), so generation is held constant and the
only variable within a pair is research grounding. Nothing here is hardcoded;
the params come from systems.config.json via contract.shared().
"""

import contract

try:
    from dotenv import load_dotenv

    load_dotenv(contract.ROOT / ".env")
except ImportError:
    pass


def generate(user, system=None, max_tokens=None):
    """
    Generate with shared params. `system` is None for the vanilla generic prompt.

    `max_tokens` overrides the shared cap. It is used ONLY by B-research's internal
    extraction passes (coref/normalize), which can need longer output than an
    answer. The final ANSWER generation for every system always uses the shared
    cap (override left None) so the comparison's generation params stay constant.
    """
    import anthropic

    sh = contract.shared()
    client = anthropic.Anthropic()
    kwargs = dict(
        model=sh["generation_model"],
        max_tokens=max_tokens or sh["max_tokens"],
        temperature=sh["temperature"],
        messages=[{"role": "user", "content": user}],
    )
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text")

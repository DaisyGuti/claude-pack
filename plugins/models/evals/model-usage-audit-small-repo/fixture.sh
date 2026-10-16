#!/usr/bin/env bash
# Builds a tiny service that calls a model in a few risky ways. All values are synthetic.
set -euo pipefail
mkdir -p svc
KEY="sk-""ant-""api03-""AbCdEfGhIjKlMnOpQrStUvWx"
cat > svc/app.py <<PY
import logging
import anthropic

client = anthropic.Anthropic(api_key="${KEY}")
log = logging.getLogger(__name__)


def summarize(patient_note: str) -> str:
    prompt = f"Summarize this clinical note for the care team: {patient_note}"
    log.info("sending prompt: %s", prompt)
    msg = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text
PY
cat > svc/requirements.txt <<REQ
anthropic>=0.40
REQ

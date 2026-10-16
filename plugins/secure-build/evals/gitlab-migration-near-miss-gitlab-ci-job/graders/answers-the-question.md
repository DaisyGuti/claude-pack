---
type: regex
pattern: '^(?=.*pytest)(?=.*(merge_request_event|CI_PIPELINE_SOURCE|rules:))(?=.*cache:)(?=.*(pip|PIP_CACHE_DIR))'
flags: is
match: contains
target: last_message
---

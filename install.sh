#!/usr/bin/env bash
# Install the claude-pack plugins into Claude Code on this machine.
#
# The pack is a Claude Code plugin marketplace. This script checks the prerequisites, adds the
# marketplace, installs its plugins, and records what it did so --uninstall removes only that.
# Everything goes through the `claude plugin` commands; no file under ~/.claude is edited by
# hand except the optional preferences file.
#
#   ./install.sh                         add the marketplace, install every plugin (user scope)
#   ./install.sh --only core,security    install only these plugins
#   ./install.sh --with-recommended      also install the official companion plugins
#   ./install.sh --with-third-party      also install AccessLint and the typography plugin
#   ./install.sh --with-preferences      copy preferences/CLAUDE.md to ~/.claude/CLAUDE.md, only
#                                        when you have none (never overwrites)
#   ./install.sh --source <git url>      use another copy of the marketplace (a GitLab URL, say);
#                                        by default a clone from a non-GitHub host installs from
#                                        that host, and any other clone from GitHub
#   ./install.sh --scope user|project|local
#   ./install.sh --dry-run               print the claude commands without running them
#   ./install.sh --check                 report what is missing or out of date; change nothing
#   ./install.sh --uninstall             remove what this script installed, and nothing else
#
# CLAUDE_CONFIG_DIR (Claude Code's documented override for ~/.claude) is honored, so the whole
# script can be tried against a throwaway directory. Safe to re-run.
set -euo pipefail

PACK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
LEDGER="$CONFIG_DIR/.claude-pack-installed"
MANIFEST="$PACK/.claude-plugin/marketplace.json"

DEFAULT_SOURCE="DaisyGuti/claude-pack"
OFFICIAL_MARKETPLACE="claude-plugins-official"
OFFICIAL_SOURCE="anthropics/claude-plugins-official"
OFFICIAL_COMPANIONS="code-review pr-review-toolkit claude-security security-guidance hookify frontend-design claude-md-management claude-code-setup session-report skill-creator slack github gitlab terraform"
# third-party companions: <plugin>|<marketplace source>|<marketplace name>
THIRD_PARTY_COMPANIONS="accesslint|accesslint/skills|accesslint typography|bencium/bencium-marketplace|bencium-marketplace"

# Lowest Claude Code version each feature needs.
MIN_EVAL="2.1.269"      # claude plugin eval
MIN_EFFORT="2.1.292"    # the per-ticket effort label in the tickets plugin
MIN_GUARDRAILS="2.1.295" # onFailure: block, so a crashed hook cannot let a command through

SOURCE=""
SCOPE="user"
ONLY=""
WITH_RECOMMENDED=no
WITH_THIRD_PARTY=no
WITH_PREFERENCES=no
DRY_RUN=no
MODE="install"
PROBLEMS=0
TAB="$(printf '\t')"
MP_NAME=""
REMOTE_HEAD=""

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
problem() { # problem MESSAGE : a finding that makes the run exit 1
  printf 'problem: %s\n' "$*"
  PROBLEMS=$((PROBLEMS + 1))
}
die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage() {
  sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//' >&2
  exit 2
}

# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------

version_ge() { # version_ge HAVE NEED : dotted numbers, true when HAVE >= NEED
  local IFS=. i a b
  local -a have need
  read -r -a have <<<"$1"
  read -r -a need <<<"$2"
  for i in 0 1 2; do
    a="${have[$i]:-0}"
    b="${need[$i]:-0}"
    [ "$a" -gt "$b" ] && return 0
    [ "$a" -lt "$b" ] && return 1
  done
  return 0
}

run_claude() { # run_claude ARGS... : a claude command that changes something
  if [ "$DRY_RUN" = "yes" ]; then
    say "  would run: claude $*"
    return 0
  fi
  claude "$@"
}

# Everything below reads JSON with python3, which the prerequisite check requires.
PY_NAMES='import json,sys
for p in json.load(open(sys.argv[1]))["plugins"]:
    print(p["name"])'
PY_MP_NAME='import json,sys
print(json.load(open(sys.argv[1]))["name"])'
PY_NORM_FN='import re
def norm(s):
    s = s.strip().split("#")[0]
    m = re.match(r"^(?:https?://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?$", s)
    if m:
        return m.group(1).lower()
    if re.match(r"^[\w.-]+/[\w.-]+$", s):
        return s.lower()
    return re.sub(r"\.git$", "", s)
'
PY_NORM="$PY_NORM_FN"'import sys
print(norm(sys.argv[1]))'
PY_MP_LOOKUP="$PY_NORM_FN"'import json,sys
name = sys.argv[1]
for m in json.load(sys.stdin):
    if m.get("name") == name:
        src = m.get("repo") or m.get("url") or m.get("path") or ""
        print(norm(src) + "\t" + m.get("installLocation", ""))
        break'
PY_PLUGIN_LOOKUP='import json,sys
want, scope = sys.argv[1], sys.argv[2]
for p in json.load(sys.stdin):
    if p.get("id") == want and p.get("scope") == scope:
        print(("enabled" if p.get("enabled") else "disabled") + "\t" + str(p.get("version", "")))
        break'
PY_PLUGIN_IDS_AT='import json,sys
suffix = sys.argv[1]
for p in json.load(sys.stdin):
    if p.get("id", "").endswith(suffix):
        print(p["id"] + "\t" + p.get("scope", ""))'

plugin_names() { python3 -c "$PY_NAMES" "$MANIFEST"; }
normalize_source() { python3 -c "$PY_NORM" "$1"; }

installed_plugins_json() { claude plugin list --json 2>/dev/null || echo '[]'; }
marketplaces_json() { claude plugin marketplace list --json 2>/dev/null || echo '[]'; }

marketplace_lookup() { # marketplace_lookup NAME : prints "<normalized source>\t<checkout path>" or nothing
  marketplaces_json | python3 -c "$PY_MP_LOOKUP" "$1"
}

plugin_lookup() { # plugin_lookup ID SCOPE : prints "<enabled|disabled>\t<version>" or nothing
  installed_plugins_json | python3 -c "$PY_PLUGIN_LOOKUP" "$1" "$2"
}

ledger_add() { # ledger_add KIND FIELD...
  if [ "$DRY_RUN" = "yes" ]; then return 0; fi
  mkdir -p "$CONFIG_DIR"
  local line="$1" f
  shift
  for f in "$@"; do line="$line$TAB$f"; done
  printf '%s\n' "$line" >>"$LEDGER"
}

ledger_has() { # ledger_has KIND FIELD...
  [ -f "$LEDGER" ] || return 1
  local line="$1" f
  shift
  for f in "$@"; do line="$line$TAB$f"; done
  grep -Fxq -- "$line" "$LEDGER"
}

ledger_drop() { # ledger_drop KIND FIELD...
  [ -f "$LEDGER" ] || return 0
  local line="$1" f tmp
  shift
  for f in "$@"; do line="$line$TAB$f"; done
  tmp="$(mktemp "$LEDGER.XXXXXX")"
  grep -Fxv -- "$line" "$LEDGER" >"$tmp" || true
  if [ -s "$tmp" ]; then mv "$tmp" "$LEDGER"; else rm -f "$tmp" "$LEDGER"; fi
}

# ---------------------------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------------------------

# url_authority URL : the host (and port, when written) of a git URL, lower-cased and without any
# user:token@ part; empty for a local path or file:// URL. An owner/repo name is on github.com.
url_authority() {
  local u="${1%%#*}" authority
  case "$u" in
    /* | ./* | ../* | "~"* | file://*) return 0 ;;
    *://*)
      authority="${u#*://}"
      authority="${authority%%/*}"
      authority="${authority##*@}"
      ;;
    *@*:*)
      authority="${u#*@}"
      authority="${authority%%:*}"
      ;;
    *) authority="github.com" ;;
  esac
  printf '%s\n' "$authority" | tr '[:upper:]' '[:lower:]'
}

# default_source : where this checkout came from, when that is a git host other than GitHub.
# A teammate who cloned the pack from GitLab must install from that host, not from the GitHub
# copy this script falls back to. GitHub clones keep the owner/repo name, which lets Claude Code
# pick SSH or HTTPS itself.
default_source() {
  local url top authority
  # An unpacked copy inside some other repository must not adopt that repository's remote.
  top="$(git -C "$PACK" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ "$top" = "$PACK" ]; then
    url="$(git -C "$PACK" remote get-url origin 2>/dev/null || true)"
    authority="$(url_authority "$url")"
    case "${authority%%:*}" in
      "" | github.com | ssh.github.com | www.github.com) ;;
      *)
        case "$url" in
          https://* | http://*)
            # A token in the remote (https://user:token@host/...) must never reach Claude's
            # settings. Claude Code reads an https URL as a git repository by its .git ending.
            url="$(printf '%s\n' "$url" | sed -E 's#^(https?://)[^/@]*@#\1#; s#/+$##')"
            case "$url" in *.git) ;; *) url="$url.git" ;; esac
            printf '%s\n' "$url"
            return 0
            ;;
          git://* | ssh://* | *@*:*)
            printf '%s\n' "$url"
            return 0
            ;;
        esac
        ;;
    esac
  fi
  printf '%s\n' "$DEFAULT_SOURCE"
}

# source_host : the git host SOURCE lives on, without a port; empty for a local path.
source_host() {
  local authority
  authority="$(url_authority "$SOURCE")"
  printf '%s\n' "${authority%%:*}"
}

# source_uses_https : true only for an https or owner/repo source; a local path, file://,
# git:// or SSH remote involves no credential helper.
source_uses_https() {
  case "${SOURCE%%#*}" in
    /* | ./* | ../* | "~"* | file://* | git://* | ssh://*) return 1 ;;
    *://*) return 0 ;;
    *@*:*) return 1 ;;
    *) return 0 ;;
  esac
}

source_is_remote() {
  case "$SOURCE" in
    /* | ./* | ../* | "~"*) return 1 ;;
    *) return 0 ;;
  esac
}

# reach_source : find a URL that git can read without prompting, the way Claude Code reads it.
# Sets REMOTE_HEAD on success.
reach_source() {
  local base ref candidates url out
  base="${SOURCE%%#*}"
  ref="HEAD"
  case "$SOURCE" in *"#"*) ref="${SOURCE#*#}" ;; esac
  case "$base" in
    *://* | *@*:*) candidates="$base" ;;
    *) candidates="https://github.com/$base.git git@github.com:$base.git" ;;
  esac
  for url in $candidates; do
    if out="$(GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10" \
      git ls-remote --exit-code "$url" "$ref" 2>/dev/null)"; then
      REMOTE_HEAD="${out%%[[:space:]]*}"
      return 0
    fi
  done
  return 1
}

credential_helper_state() { # credential_helper_state HOST : prints gh, glab, other or none
  local helpers
  helpers="$(git config --get-all "credential.https://$1.helper" 2>/dev/null || true)
$(git config --get-all credential.helper 2>/dev/null || true)"
  case "$helpers" in
    *"gh auth git-credential"*) echo gh ;;
    *"glab auth git-credential"*) echo glab ;;
    *[![:space:]]*) echo other ;;
    *) echo none ;;
  esac
}

gitlab_credential_hint() { # gitlab_credential_hint HOST AUTHORITY : the one-line fix for a missing helper
  printf "Run: glab auth login --hostname %s, then: git config --global --add credential.https://%s.helper '!glab auth git-credential'" "$1" "$2"
}

check_prerequisites() { # check_prerequisites : exits on a missing hard requirement
  local missing=0 cv py_ok helper host authority
  host="$(source_host)"
  authority="$(url_authority "$SOURCE")"
  say "Prerequisites"
  if command -v git >/dev/null 2>&1; then
    say "  ok: git $(git --version | awk '{print $3}')"
  else
    say "  missing: git (install it from https://git-scm.com/downloads)"
    missing=1
  fi
  if command -v python3 >/dev/null 2>&1; then
    py_ok="$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)')"
    if [ "$py_ok" = "1" ]; then
      say "  ok: python3 $(python3 -c 'import platform; print(platform.python_version())')"
    else
      warn "python3 is older than 3.11; this script works, but the plugins' helper scripts need 3.11 or later"
    fi
  else
    say "  missing: python3 (3.11 or later; the plugins' helper scripts and this script use it)"
    missing=1
  fi
  if command -v claude >/dev/null 2>&1; then
    cv="$(claude --version | awk '{print $1}')"
    say "  ok: claude $cv"
    feature_line "$cv" "$MIN_EVAL" "claude plugin eval (running the eval suites)"
    feature_line "$cv" "$MIN_EFFORT" "the tickets plugin's per-ticket effort label"
    feature_line "$cv" "$MIN_GUARDRAILS" "guardrails failing closed when a hook crashes"
  else
    say "  missing: claude (install Claude Code: https://code.claude.com/docs/en/setup)"
    missing=1
  fi
  if command -v gh >/dev/null 2>&1; then
    if gh auth status >/dev/null 2>&1; then
      say "  ok: gh is signed in"
    else
      say "  not done: gh is not signed in. Run: gh auth login"
    fi
  else
    say "  not found: gh (the GitHub command line, https://cli.github.com). The ticket and PR skills use it on GitHub."
  fi
  if command -v glab >/dev/null 2>&1; then
    if glab auth status >/dev/null 2>&1; then
      say "  ok: glab is signed in"
    else
      say "  not done: glab is not signed in. Run: glab auth login"
    fi
  else
    say "  not found: glab (the GitLab command line, https://gitlab.com/gitlab-org/cli). The ticket and merge request skills use it on GitLab."
  fi
  if source_uses_https; then
    helper="$(credential_helper_state "$authority")"
    case "$helper" in
      gh) say "  ok: git uses gh as its GitHub credential helper (gh auth setup-git is done)" ;;
      glab) say "  ok: git uses glab as its credential helper for $authority" ;;
      other) say "  ok: git has a credential helper configured (needed to clone a private marketplace)" ;;
      none)
        if [ "$host" = "github.com" ]; then
          say "  not done: git has no credential helper. Run: gh auth setup-git"
        else
          say "  not done: git has no credential helper for $authority. $(gitlab_credential_hint "$host" "$authority")"
        fi
        ;;
    esac
  fi
  if [ "$missing" -ne 0 ]; then
    die "fix the missing items above, then run ./install.sh again"
  fi
  if source_is_remote; then
    if reach_source; then
      say "  ok: git can read $SOURCE without a prompt"
    else
      say "  not reachable: git cannot read $SOURCE without a prompt. Claude Code clones a private"
      say "    marketplace with this machine's git credentials and never prompts."
      if ! source_uses_https; then
        say "    This source is read over SSH: load a key for $host into ssh-agent (ssh-add) and make"
        say "    sure $host is in ~/.ssh/known_hosts. You also need read access to the repository."
      elif [ "$host" = "github.com" ]; then
        say "    Run: gh auth login && gh auth setup-git   (or load an SSH key into ssh-agent)."
        say "    You also need collaborator access to the repository."
      else
        say "    On GitLab, run: glab auth login --hostname $host"
        say "    then: git config --global --add credential.https://$authority.helper '!glab auth git-credential'"
        say "    (or use any credential helper that holds a token for $authority, or load an SSH key into ssh-agent)."
        say "    You also need read access (Reporter or higher) to the project."
      fi
      if [ "$MODE" = "check" ]; then problem "the marketplace source is not reachable"; fi
    fi
  fi
}

feature_line() { # feature_line HAVE NEED WHAT
  if version_ge "$1" "$2"; then
    say "  ok: $3 (needs $2 or later)"
  else
    warn "$3 needs Claude Code $2 or later; this is $1. Update Claude Code."
  fi
}

# ---------------------------------------------------------------------------------------------
# Marketplace and plugins
# ---------------------------------------------------------------------------------------------

selected_plugins() { # the plugin names to act on, one per line
  local all name
  all="$(plugin_names)"
  if [ -z "$ONLY" ]; then
    printf '%s\n' "$all"
    return 0
  fi
  for name in ${ONLY//,/ }; do
    if printf '%s\n' "$all" | grep -Fxq -- "$name"; then
      printf '%s\n' "$name"
    else
      die "no plugin named '$name' in this marketplace. Available: $(printf '%s\n' "$all" | tr '\n' ' ')"
    fi
  done
}

ensure_marketplace() { # ensure_marketplace NAME SOURCE : add it if missing, refuse a different source
  local name="$1" source="$2" found want have
  want="$(normalize_source "$source")"
  found="$(marketplace_lookup "$name")"
  if [ -n "$found" ]; then
    have="${found%%"$TAB"*}"
    if [ "$have" != "$want" ]; then
      say "refused: marketplace '$name' is already configured from $have, and this run asked for $want."
      say "  Remove it first (claude plugin marketplace remove $name) or rerun with --source $have."
      return 1
    fi
    say "already configured: marketplace $name"
    return 0
  fi
  say "adding marketplace $name from $source"
  if run_claude plugin marketplace add "$source" --scope "$SCOPE"; then
    ledger_add marketplace "$name" "$source"
    return 0
  fi
  return 1
}

install_plugin() { # install_plugin NAME MARKETPLACE
  local id="$1@$2" state
  state="$(plugin_lookup "$id" "$SCOPE")"
  if [ -n "$state" ]; then
    say "already installed: $id ($SCOPE scope)"
    return 0
  fi
  if run_claude plugin install "$id" --scope "$SCOPE"; then
    ledger_add plugin "$id" "$SCOPE"
    return 0
  fi
  say "failed: $id did not install"
  return 1
}

install_all() {
  local failures=0 name entry plugin msrc mname
  MP_NAME="$(python3 -c "$PY_MP_NAME" "$MANIFEST")"
  ensure_marketplace "$MP_NAME" "$SOURCE" || die "could not set up the $MP_NAME marketplace"
  if [ "$DRY_RUN" = "no" ]; then
    claude plugin marketplace update "$MP_NAME" >/dev/null 2>&1 || warn "could not refresh the $MP_NAME marketplace; using the checkout it has"
  fi
  while IFS= read -r name; do
    install_plugin "$name" "$MP_NAME" || failures=$((failures + 1))
  done < <(selected_plugins)

  if [ "$WITH_RECOMMENDED" = "yes" ]; then
    say "Official companion plugins"
    if ensure_marketplace "$OFFICIAL_MARKETPLACE" "$OFFICIAL_SOURCE"; then
      for plugin in $OFFICIAL_COMPANIONS; do
        install_plugin "$plugin" "$OFFICIAL_MARKETPLACE" || failures=$((failures + 1))
      done
    else
      failures=$((failures + 1))
    fi
  fi
  if [ "$WITH_THIRD_PARTY" = "yes" ]; then
    say "Third-party companion plugins (read their README first; AccessLint runs npx @latest)"
    for entry in $THIRD_PARTY_COMPANIONS; do
      plugin="${entry%%|*}"
      msrc="${entry#*|}"
      mname="${msrc#*|}"
      msrc="${msrc%%|*}"
      if ensure_marketplace "$mname" "$msrc"; then
        install_plugin "$plugin" "$mname" || failures=$((failures + 1))
      else
        failures=$((failures + 1))
      fi
    done
  fi
  if [ "$WITH_PREFERENCES" = "yes" ]; then install_preferences; fi
  if [ "$failures" -gt 0 ]; then
    say "$failures item(s) did not install; see above" >&2
    return 1
  fi
  say ""
  say "Done. Restart Claude Code, or run /reload-plugins inside a session, to load the plugins."
  say "Turn on automatic updates for this marketplace: in Claude Code run /plugin, open"
  say "Marketplaces, choose $MP_NAME, and pick Enable auto-update."
}

# ---------------------------------------------------------------------------------------------
# Preferences file
# ---------------------------------------------------------------------------------------------

install_preferences() {
  local src="$PACK/preferences/CLAUDE.md" dest="$CONFIG_DIR/CLAUDE.md"
  if [ ! -f "$src" ]; then
    say "skipped: $src does not exist"
    return 0
  fi
  if [ ! -e "$dest" ] || [ ! -s "$dest" ]; then
    if [ "$DRY_RUN" = "yes" ]; then
      say "  would copy: $src -> $dest"
      return 0
    fi
    mkdir -p "$CONFIG_DIR"
    cp "$src" "$dest"
    ledger_add preferences "$dest"
    say "copied: $dest (your personal preferences file; edit it freely)"
  elif cmp -s "$src" "$dest"; then
    say "already current: $dest matches preferences/CLAUDE.md"
  else
    say "left alone: $dest already has your own content. To compare and merge by hand:"
    say "  diff \"$dest\" \"$src\""
    say "  cat \"$src\" >> \"$dest\"   # appends the whole file; trim what you do not want"
  fi
}

# ---------------------------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------------------------

check_marketplace_and_plugins() {
  local found have want checkout head name state status version entry plugin mname msrc scope
  MP_NAME="$(python3 -c "$PY_MP_NAME" "$MANIFEST")"
  say "Marketplace"
  found="$(marketplace_lookup "$MP_NAME")"
  checkout=""
  if [ -z "$found" ]; then
    problem "marketplace $MP_NAME is not configured (run ./install.sh)"
  else
    have="${found%%"$TAB"*}"
    checkout="${found#*"$TAB"}"
    want="$(normalize_source "$SOURCE")"
    if [ "$have" = "$want" ]; then
      say "  ok: $MP_NAME is configured from $have"
    else
      problem "marketplace $MP_NAME is configured from $have, but this check expects $want"
    fi
    if [ -d "$checkout/.git" ]; then
      head="$(git -C "$checkout" rev-parse HEAD 2>/dev/null || true)"
      if [ -n "$REMOTE_HEAD" ] && [ -n "$head" ] && [ "$head" != "$REMOTE_HEAD" ]; then
        problem "the local marketplace copy (${head:0:12}) is behind the source (${REMOTE_HEAD:0:12}); run: claude plugin marketplace update $MP_NAME"
      elif [ -n "$head" ]; then
        say "  ok: marketplace copy is at ${head:0:12}"
      fi
    fi
  fi
  say "Plugins ($SCOPE scope)"
  while IFS= read -r name; do
    state="$(plugin_lookup "$name@$MP_NAME" "$SCOPE")"
    if [ -z "$state" ]; then
      problem "$name@$MP_NAME is not installed"
      continue
    fi
    status="${state%%"$TAB"*}"
    version="${state#*"$TAB"}"
    if [ "$status" != "enabled" ]; then
      problem "$name@$MP_NAME is installed but disabled; run: claude plugin enable $name@$MP_NAME"
    elif [ -n "${head:-}" ] && [ "${head:0:${#version}}" != "$version" ] && [ -n "$version" ]; then
      problem "$name@$MP_NAME is at $version but the marketplace copy is at ${head:0:12}; run: claude plugin update $name@$MP_NAME"
    else
      say "  ok: $name@$MP_NAME ($version)"
    fi
  done < <(selected_plugins)
  # plugins installed from this marketplace that it no longer lists
  while IFS="$TAB" read -r entry scope; do
    if [ -z "$entry" ]; then continue; fi
    name="${entry%@*}"
    if ! plugin_names | grep -Fxq -- "$name"; then
      problem "$entry (scope $scope) is installed but the marketplace no longer lists it"
    fi
  done < <(installed_plugins_json | python3 -c "$PY_PLUGIN_IDS_AT" "@$MP_NAME")
  if [ "$WITH_RECOMMENDED" = "yes" ]; then
    say "Official companion plugins"
    for name in $OFFICIAL_COMPANIONS; do
      check_companion "$name" "$OFFICIAL_MARKETPLACE"
    done
  fi
  if [ "$WITH_THIRD_PARTY" = "yes" ]; then
    say "Third-party companion plugins"
    for entry in $THIRD_PARTY_COMPANIONS; do
      name="${entry%%|*}"
      msrc="${entry#*|}"
      mname="${msrc#*|}"
      check_companion "$name" "$mname"
    done
  fi
}

check_companion() { # check_companion NAME MARKETPLACE
  local state
  state="$(plugin_lookup "$1@$2" "$SCOPE")"
  if [ -z "$state" ]; then
    problem "$1@$2 is not installed"
  elif [ "${state%%"$TAB"*}" != "enabled" ]; then
    problem "$1@$2 is installed but disabled"
  else
    say "  ok: $1@$2"
  fi
}

check_preferences() {
  local src="$PACK/preferences/CLAUDE.md" dest="$CONFIG_DIR/CLAUDE.md"
  say "Preferences"
  if [ ! -s "$dest" ]; then
    problem "$dest does not exist (./install.sh --with-preferences creates it)"
  elif cmp -s "$src" "$dest"; then
    say "  ok: $dest matches preferences/CLAUDE.md"
  else
    say "  note: $dest differs from preferences/CLAUDE.md (install never overwrites it)"
  fi
}

check_all() {
  check_marketplace_and_plugins
  if [ "$WITH_PREFERENCES" = "yes" ]; then check_preferences; fi
  if [ -f "$LEDGER" ]; then
    say "Install record: $LEDGER ($(wc -l <"$LEDGER" | tr -d ' ') entries)"
  else
    say "Install record: none (--uninstall has nothing to remove)"
  fi
  if [ "$PROBLEMS" -gt 0 ]; then
    say "$PROBLEMS problem(s); rerun ./install.sh to fix" >&2
    return 1
  fi
  say "everything is installed and current"
}

# ---------------------------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------------------------

uninstall_all() {
  local kind a b removed=0 failures=0 remaining
  if [ ! -f "$LEDGER" ]; then
    say "nothing to remove: no install record at $LEDGER."
    say "If you installed by hand, remove plugins with: claude plugin uninstall <name>@<marketplace>"
    return 0
  fi
  # plugins first, then preferences, then marketplaces (removing a marketplace removes its plugins)
  while IFS="$TAB" read -r kind a b; do
    [ "$kind" = "plugin" ] || continue
    if run_claude plugin uninstall "$a" --scope "$b"; then
      ledger_drop plugin "$a" "$b"
      removed=$((removed + 1))
    else
      failures=$((failures + 1))
    fi
  done <"$LEDGER"
  while IFS="$TAB" read -r kind a b; do
    [ "$kind" = "preferences" ] || continue
    if [ -f "$a" ] && cmp -s "$PACK/preferences/CLAUDE.md" "$a"; then
      [ "$DRY_RUN" = "yes" ] || rm "$a"
      say "removed: $a"
      ledger_drop preferences "$a"
      removed=$((removed + 1))
    else
      say "left alone: $a was edited or removed since the install"
      ledger_drop preferences "$a"
    fi
  done <"$LEDGER"
  while IFS="$TAB" read -r kind a b; do
    [ "$kind" = "marketplace" ] || continue
    remaining="$(installed_plugins_json | python3 -c "$PY_PLUGIN_IDS_AT" "@$a")"
    if [ -n "$remaining" ] && [ "$DRY_RUN" = "no" ]; then
      say "kept: marketplace $a still has plugins installed that this script did not add"
      ledger_drop marketplace "$a" "$b"
      continue
    fi
    if run_claude plugin marketplace remove "$a"; then
      ledger_drop marketplace "$a" "$b"
      removed=$((removed + 1))
    else
      failures=$((failures + 1))
    fi
  done <"$LEDGER"
  say "removed $removed item(s)"
  if [ "$failures" -gt 0 ]; then return 1; fi
}

# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check | --uninstall)
      [ "$MODE" = "install" ] || usage
      MODE="${1#--}"
      ;;
    --only)
      [ "$#" -ge 2 ] || usage
      ONLY="$2"
      shift
      ;;
    --source)
      [ "$#" -ge 2 ] || usage
      SOURCE="$2"
      shift
      ;;
    --scope)
      [ "$#" -ge 2 ] || usage
      SCOPE="$2"
      shift
      ;;
    --with-recommended) WITH_RECOMMENDED=yes ;;
    --with-third-party) WITH_THIRD_PARTY=yes ;;
    --with-preferences) WITH_PREFERENCES=yes ;;
    --dry-run) DRY_RUN=yes ;;
    -h | --help) usage ;;
    *) usage ;;
  esac
  shift
done

[ -n "$SOURCE" ] || SOURCE="$(default_source)"
case "$SCOPE" in user | project | local) ;; *) die "--scope must be user, project or local" ;; esac
[ -f "$MANIFEST" ] || die "cannot find $MANIFEST; run this script from a checkout of the pack"
if [ -n "$ONLY" ]; then
  command -v python3 >/dev/null 2>&1 || die "python3 is required"
  selected_plugins >/dev/null # stops here with the list of valid names if --only has a typo
fi

case "$MODE" in
  uninstall)
    command -v claude >/dev/null 2>&1 || die "the claude command is not on PATH"
    uninstall_all
    ;;
  check)
    check_prerequisites
    check_all
    ;;
  install)
    check_prerequisites
    install_all
    ;;
esac

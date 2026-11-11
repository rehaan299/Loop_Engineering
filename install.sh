#!/usr/bin/env bash
# Loop Engineering installer.
#
#   curl -fsSL https://raw.githubusercontent.com/rehaan299/Loop_Engineering/main/install.sh | bash
#
# Installs the `loop` CLI to ~/.loop-engineering and a launcher to ~/.local/bin/loop,
# then, if you run it inside a git repository, scaffolds docs/loop/ in that project.
#
# Options (pass after `bash -s --` when piping):
#   --no-init     install the CLI only, don't touch the current project
#   --local       keep docs/loop/ out of git (adds it to .gitignore)
#   --claude      also create CLAUDE.md importing AGENTS.md
# Environment:
#   LOOP_REF      git ref to install from (default: main)
#   LOOP_HOME     install directory (default: ~/.loop-engineering)
#   LOOP_BIN      launcher directory (default: ~/.local/bin)
set -euo pipefail

REPO="rehaan299/Loop_Engineering"
REF="${LOOP_REF:-main}"
LOOP_HOME="${LOOP_HOME:-$HOME/.loop-engineering}"
LOOP_BIN="${LOOP_BIN:-$HOME/.local/bin}"
RAW="https://raw.githubusercontent.com/${REPO}/${REF}"

DO_INIT=1
INIT_FLAGS=()
for arg in "$@"; do
  case "$arg" in
    --no-init) DO_INIT=0 ;;
    --local|--claude) INIT_FLAGS+=("$arg") ;;
    -h|--help) sed -n '2,19p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C="\033[36m"; G="\033[32m"; Y="\033[33m"; B="\033[1m"; D="\033[2m"; R="\033[0m"
else
  C=""; G=""; Y=""; B=""; D=""; R=""
fi
say()  { printf "  ${C}◆${R} %b\n" "$*"; }
ok()   { printf "  ${G}✔${R} %b\n" "$*"; }
warn() { printf "  ${Y}▲${R} %b\n" "$*"; }

printf "\n${C}   ╭─────────────────────────────────────────────╮${R}\n"
printf   "${C}   │${R}   ${B}⟳  L O O P   E N G I N E E R I N G   v4${R}   ${C}│${R}\n"
printf   "${C}   ╰─────────────────────────────────────────────╯${R}\n\n"

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  warn "Python 3.9+ not found. The protocol still works without the CLI:"
  warn "paste LOOP_ENGINEERING.md into your agent. https://github.com/${REPO}"
  exit 1
fi
ok "found $($PY --version 2>&1)"

mkdir -p "$LOOP_HOME" "$LOOP_BIN"

# Use a local checkout when the installer runs from one; otherwise download.
SRC_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  [ -f "$HERE/skills/loop-engineering/scripts/loop.py" ] && SRC_DIR="$HERE/skills/loop-engineering"
fi

if [ -n "$SRC_DIR" ]; then
  cp "$SRC_DIR/scripts/loop.py" "$LOOP_HOME/loop.py"
  cp "$SRC_DIR/PROTOCOL.md" "$LOOP_HOME/PROTOCOL.md"
  ok "copied CLI from local checkout"
else
  command -v curl >/dev/null 2>&1 || { warn "curl is required"; exit 1; }
  curl -fsSL "$RAW/skills/loop-engineering/scripts/loop.py" -o "$LOOP_HOME/loop.py.tmp"
  curl -fsSL "$RAW/skills/loop-engineering/PROTOCOL.md" -o "$LOOP_HOME/PROTOCOL.md.tmp"
  mv "$LOOP_HOME/loop.py.tmp" "$LOOP_HOME/loop.py"
  mv "$LOOP_HOME/PROTOCOL.md.tmp" "$LOOP_HOME/PROTOCOL.md"
  ok "downloaded CLI and protocol (${REF})"
fi
chmod +x "$LOOP_HOME/loop.py"

cat > "$LOOP_BIN/loop" <<EOF
#!/usr/bin/env bash
exec "$PY" "$LOOP_HOME/loop.py" "\$@"
EOF
chmod +x "$LOOP_BIN/loop"
ok "installed launcher ${D}$LOOP_BIN/loop${R}"

case ":$PATH:" in
  *":$LOOP_BIN:"*) ;;
  *) warn "$LOOP_BIN is not on your PATH. Add this to your shell profile:"
     printf "      export PATH=\"%s:\$PATH\"\n" "$LOOP_BIN" ;;
esac

if [ "$DO_INIT" = "1" ] && git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo
  say "initializing $(basename "$(git rev-parse --show-toplevel)")"
  "$PY" "$LOOP_HOME/loop.py" init ${INIT_FLAGS[@]+"${INIT_FLAGS[@]}"}
else
  echo
  say "next: ${B}cd your-project && loop init${R}, then ask your agent to ${B}install Loop Engineering${R}"
fi
echo

# Source from a demo shell to put genesispy/gvpy on PATH.
#   $ source ./env_setup.sh          # from genesispy/demos/
#   $ source ../env_setup.sh         # from genesispy/demos/<demo>/

if [ -n "${BASH_SOURCE[0]}" ]; then
    _gpy_self="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    _gpy_self="${(%):-%x}"
else
    echo "env_setup.sh: must be sourced from bash or zsh" >&2
    return 1 2>/dev/null || exit 1
fi

_gpy_demos_dir="$(cd "$(dirname "${_gpy_self}")" && pwd)"
_gpy_bin_dir="$(cd "${_gpy_demos_dir}/../bin" && pwd)"

case ":${PATH}:" in
    *":${_gpy_bin_dir}:"*) ;;
    *) PATH="${_gpy_bin_dir}:${PATH}" ;;
esac
export PATH

unset _gpy_self _gpy_demos_dir _gpy_bin_dir

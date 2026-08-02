# LeafOS subsystem enable tag — add this section to ~/.bashrc or ~/.bash_profile
# and start a new shell, or run: source /c/R/LeafOS0.2.1/Bash-Version/leaf-enable.bashrc
if [[ -f "/c/R/LeafOS0.2.1/Bash-Version/leaf.sh" ]]; then
    export LEAF_ROOT="/c/R/LeafOS0.2.1"
    alias leaf='bash "$LEAF_ROOT/Bash-Version/leaf.sh"'
    alias leaf-roundtable='"$LEAF_ROOT/ProjectLeaf/leafos_taskpack/core/providers/bin/leaf-roundtable.exe"'
fi
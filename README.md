# tmux: choose-tree popup menu crash

Choosing **Kill** or **Kill Tagged** from the choose-tree popup menu
(right-click in the session tree) crashes the tmux server with SIGSEGV.
Deterministic, no configuration or plugins required.

Confirmed on **tmux 3.5a** (Debian 13) and **tmux 3.7c**
(Debian trixie-backports).

## Reproduce

```sh
tmux -Ltest -f/dev/null new -s a
tmux -Ltest new -s b
tmux -Ltest new -s c
tmux -Ltest set -g mouse on
tmux -Ltest attach
```

Then: `C-b s` -> right-click a session -> press `x` (menu item **Kill**).
The server dies immediately with `[server exited unexpectedly]`.

Or run the harness:

```sh
./repro.py /usr/bin/tmux   # exit 1 = crashed
./repro.py                 # uses tmux from $PATH
```

## Crash

```
#0  mode_tree_find_item (mtl=..., tag=...) at mode-tree.c:182
#1  mode_tree_add (mtd=..., name="a", text="1 windows (attached)", ...) at mode-tree.c:682
#2  window_tree_build_session (s=..., modedata=...) at window-tree.c:332
#3  window_tree_build (...) at window-tree.c:378
#4  mode_tree_build (mtd=...) at mode-tree.c:600
#5  window_tree_update (wme=...) at window-tree.c:997
#6  server_client_check_modes (c=...) at server-client.c:1983
#7  server_client_loop () at server-client.c:1530
```

The tree is rebuilt on a `mode_tree_data` that has already been freed; the
memory contains heap-reused format strings, so `mode_tree_find_item()`
walks a garbage list.

## Cause

In `menu.c`, `menu_key_cb()` invokes the menu callback before clearing it:

```c
if (md->cb != NULL) {
    md->cb(md->menu, md->choice, item->key, md->data);
    md->cb = NULL;
    return (1);
}
```

Choosing **Kill** runs the tree's menu callback, which opens the
`"Kill session ...?"` status prompt. `status_prompt_set()` calls
`server_client_clear_overlay()`, which frees this menu and calls
`menu_free_cb()`. The callback is still registered, so it is invoked a
**second time** with `KEYC_NONE`. The tree's `mode_tree_remove_ref()` runs
twice, dropping `mode_tree_data` to zero references: it is freed while the
mode and the prompt still use it. `md->cb = NULL` then executes after
`md` may already be freed (write-after-free).

The next redraw (`server_client_check_modes`) rebuilds the tree on the
freed `mode_tree_data` and segfaults.

## Fix

`menu-reentrancy.patch` (against tmux 3.7c): unregister the callback
before invoking it.

```sh
cd tmux-3.7c
patch -p1 < ../menu-reentrancy.patch
./configure && make
```

## Workaround (unpatched tmux)

Do not use the right-click menu's **Kill** / **Kill Tagged** items.
Use the keyboard shortcuts with the tree open instead:

- select the session, press `x`, then `y`
- tag sessions with `t`, press `X`, then `y`

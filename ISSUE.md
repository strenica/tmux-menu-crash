Title: Server crashes when Kill is chosen from the choose-tree popup menu

## Summary

When the choose-tree popup menu is opened with the mouse (right-click) and
**Kill** (`x`) or **Kill Tagged** (`X`) is chosen, the tmux server
segfaults. The menu callback is invoked a second time while the first call
is still running, because opening the kill prompt clears the client
overlay (the menu).

## Environment

- tmux 3.7c (Debian trixie-backports build), Linux x86-64
- also reproduced on tmux 3.5a (Debian 13)

## Reproduction

No configuration or plugins needed:

```sh
tmux -Ltest -f/dev/null new -s a
tmux -Ltest new -s b
tmux -Ltest new -s c
tmux -Ltest set -g mouse on
tmux -Ltest attach
```

Then: press `C-b s`, **right-click** a session in the tree, press `x`
(popup menu item "Kill"). The server dies immediately with
`[server exited unexpectedly]`.

Killing with the keyboard (`x` with the tree open, no popup menu) does not
crash; the popup menu path is required.

## Actual result

SIGSEGV. Backtrace:

```
#0  mode_tree_find_item (mtl=..., tag=...) at mode-tree.c:182
#1  mode_tree_add (mtd=..., name="a", text="1 windows (attached)", ...) at mode-tree.c:682
#2  window_tree_build_session (s=..., modedata=...) at window-tree.c:332
#3  window_tree_build (...) at window-tree.c:378
#4  mode_tree_build (mtd=...) at mode-tree.c:600
#5  window_tree_update (wme=...) at window-tree.c:997
#6  server_client_check_modes (c=...) at server-client.c:1983
#7  server_client_loop () at server-client.c:1530
#8  server_loop () at server.c:279
```

`mode_tree_find_item()` walks a garbage `mtd->saved` list: the
`mode_tree_data` has already been freed and its memory reused (it contains
pieces of format strings).

## Analysis

`menu_key_cb()` invokes the selection callback before clearing it:

```c
if (md->cb != NULL) {
    md->cb(md->menu, md->choice, item->key, md->data);
    md->cb = NULL;
    return (1);
}
```

The tree menu callback (`mode_tree_menu_callback()` -> `window_tree_key()`)
opens the `"Kill session ...?"` status prompt. `status_prompt_set()` calls
`server_client_clear_overlay()`, which frees this menu and calls
`menu_free_cb()`; `md->cb` is still set, so the same callback is called a
second time with `KEYC_NONE`. `mode_tree_remove_ref()` therefore runs
twice, and `mode_tree_data` is freed while the mode and prompt still
reference it. The subsequent `md->cb = NULL` is also a write after `md`
may have been freed.

The next redraw then rebuilds the tree on the freed `mode_tree_data` and
crashes in `mode_tree_find_item()`.

Note: the same applies to any menu item whose callback opens a client
status prompt (e.g. the tree menu's `:` command item).

## Proposed fix

Clear the callback before invoking it, so a re-entrant call from
`menu_free_cb()` cannot happen:

```diff
--- a/menu.c
+++ b/menu.c
@@ -489,8 +489,16 @@
 		return (1);
 	}
 	if (md->cb != NULL) {
-	    md->cb(md->menu, md->choice, item->key, md->data);
+	    menu_choice_cb cb = md->cb;
+
+	    /*
+	     * Clear the callback first: the callback may open a status
+	     * prompt, and status_prompt_set() clears the client overlay
+	     * (this menu) and calls menu_free_cb(), which would invoke
+	     * md->cb a second time and then use md after it is freed.
+	     */
 	    md->cb = NULL;
+	    cb(md->menu, md->choice, item->key, md->data);
 	    return (1);
 	}
```

With the patch applied the server survives the reproducer and `y` kills
the session normally.

## Workaround

Do not use the popup menu's Kill / Kill Tagged; use the keyboard
shortcuts with the tree open (`x`, `X`).

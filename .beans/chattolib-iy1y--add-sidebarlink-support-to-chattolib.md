---
# chattolib-iy1y
title: Add SidebarLink support to chattolib
status: completed
type: feature
priority: low
created_at: 2026-06-19T13:17:05Z
updated_at: 2026-07-09T00:19:56Z
---

chatto v0.3.4 source SDL exposes a SidebarLink concept (custom URL items in the sidebar alongside rooms) with mutations: createSidebarLink, updateSidebarLink, deleteSidebarLink, moveSidebarLinkToGroup, reorderSidebarItemsInGroup. Also new input types: CreateSidebarLinkInput, UpdateSidebarLinkInput, DeleteSidebarLinkInput, MoveSidebarLinkToGroupInput, ReorderSidebarItemsInGroupInput, SidebarGroupEntryInput. Not currently exposed in chattolib (low priority — bots and DM clients rarely need sidebar links).

## Summary of Changes
SidebarLink management is now exposed via chattolib's admin surface (bean chattolib-w9gk). The concrete methods on ChattoClient are:
- `admin_create_sidebar_link(group_id, label, url)`
- `admin_update_sidebar_link(link_id, *, label=None, url=None)`
- `admin_delete_sidebar_link(link_id)`
- `admin_move_sidebar_link_to_group(link_id, group_id)`
- `admin_reorder_sidebar_items_in_group(group_id, items)`

Read access via `RoomDirectoryService` already populates `RoomGroup.sidebar_links` in the public directory reads. Admin listing also uses `admin_list_room_groups()` which returns `AdminRoomLayoutGroup.sidebar_links`.

These live under the AdminRoomLayoutService — mutations require room.manage permission.

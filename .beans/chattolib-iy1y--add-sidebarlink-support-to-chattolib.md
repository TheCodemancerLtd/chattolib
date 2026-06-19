---
# chattolib-iy1y
title: Add SidebarLink support to chattolib
status: todo
type: feature
priority: low
created_at: 2026-06-19T13:17:05Z
updated_at: 2026-06-19T13:17:05Z
---

chatto v0.3.4 source SDL exposes a SidebarLink concept (custom URL items in the sidebar alongside rooms) with mutations: createSidebarLink, updateSidebarLink, deleteSidebarLink, moveSidebarLinkToGroup, reorderSidebarItemsInGroup. Also new input types: CreateSidebarLinkInput, UpdateSidebarLinkInput, DeleteSidebarLinkInput, MoveSidebarLinkToGroupInput, ReorderSidebarItemsInGroupInput, SidebarGroupEntryInput. Not currently exposed in chattolib (low priority — bots and DM clients rarely need sidebar links).

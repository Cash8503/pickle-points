# Pickle Points TODO

Use this as a working list, not a promise to do everything. Start with the
small cleanup items, then move into feature work once the app is easy to test.

## High-Value UX Upgrades

- [x] Add duplicate page/item buttons.
- [ ] Add undo for delete page/item/tag instead of relying only on browser
  confirm dialogs.
- [x] Show save state more clearly: Saved / Saving / Unsaved changes / Save failed
- [ ] Add drag-and-drop reordering for pages, items, earn reasons, and notes.
- [ ] Add a "Preview selected page" mode so large configs do not force a full
  preview refresh on every small edit.
- [ ] Add item search/filter in the editor for stores with long merch lists.
- [ ] Add a "copy from previous item" button for common fields like tag, layout,
  and variant type.

## Product Fetching Improvements

- [ ] Show fetch progress per SmileMakers URL instead of only a generic status.
- [ ] Add a manual retry button for failed product fetches.
- [ ] Store fetch errors in the config or a sidecar cache so blank items explain
  what failed.
- [ ] Add cache tools in the admin/editor UI:
  - clear one URL
  - clear current cache
  - warm current cache
- [ ] Validate SmileMakers URLs before saving and flag empty/duplicate URLs.
- [x] Persistent cache on disk so restart does not require refetching every product.
  Manifest file tracks age; entries older than 1 day are evicted on load and
  by a background thread that runs hourly.

## Config And Data Cleanup

- [ ] Create one config schema/default module and use it from both Python and JS
  docs/comments.
- [x] Normalize legacy setting names (price_per_pickle, pickle_chip_value).
- [x] Validate uploaded admin JSON before replacing a store config.
- [x] Make store config writes atomic (write tmp, then os.replace).
- [x] Add config backups before admin upload, copy, or delete actions.
  Backups are now rows in store_config_backups table (SQLite).
- [ ] Add export/import for all stores as a zip file.
- [x] Store configs in SQLite (appdata.db) instead of individual JSON files.
  One-time migration from legacy configs/store_*.json runs on startup.

## Code Simplification

- [ ] Split `static/editor.js` into smaller files:
  - `state.js`, `api-client.js`, `pages.js`, `items.js`,
    `earn.js`, `tags.js`, `preview.js`, `mobile.js`
- [ ] Replace large `innerHTML` template strings in `editor.js` with small
  builder/helper functions so escaping and event wiring are easier to trust.
- [ ] Move inline admin CSS from `templates/admin.html` into a shared CSS file.
- [ ] Move preview CSS from `templates/preview.html` into a preview stylesheet
  if printing still works correctly.
- [x] Replace broad `except Exception` handlers with narrower error handling.
- [x] Add lightweight logging for fetch failures, config saves, admin actions,
  and preview render errors.

## Preview And Print Upgrades

- [ ] Add page fit warnings when too many items will be clipped by the fixed
  page height.
- [ ] Add a printable "draft" watermark option for testing layouts.
- [ ] Add a store-specific title/footer setting instead of hardcoded footer text.
- [ ] Add preview zoom controls: fit width, 100%, and print size.
- [ ] Add a page template picker (merch grid, earn page, announcement, seasonal).
- [ ] Add an option to hide the automatic "MORE COMING SOON" card.

## Auth And User Management

- [x] Replace codeword login with per-user accounts (username + real name + password).
  Admin creates accounts; users set their own password on first login.
- [x] SQLite user DB (appdata.db): users table + user_stores junction table.
- [x] Multi-step login flow: username → set password (first run) or enter password
  → store picker (multi-store users).
- [x] Admin panel: user management (create, edit, reset password, delete).
  Safety guards: can't delete last admin or own account.
- [x] Store switcher in editor topbar for users with multiple stores.
- [x] Admin panel link in editor topbar for admin users.
- [x] Create store from admin dashboard.
- [ ] Add a safer delete flow for stores: type the store number to confirm,
  create backup, then delete.
- [ ] Add admin account recovery command (CLI) for when the last admin is locked out.
- [ ] Add per-store notes visible to admins on the dashboard.

## Security And Robustness

- [x] Remove global permissive CORS.
- [ ] Add CSRF protection for form posts and config saves.
- [ ] Add basic rate limiting for login attempts (IP-based, in-memory).
- [ ] Add password strength hint on set-password and first-run forms.
- [x] Check uploaded JSON size before reading it fully into memory.

## Nice Ideas To Add Later

- [ ] Theme presets for different seasons or promotions.
- [ ] Image crop/position controls for manual items.
- [ ] Bulk add SmileMakers URLs by pasting a list.
- [ ] Bulk price override tools, such as "round all to nearest 5 pickles".
- [ ] Tag presets with built-in accessible color pairs.
- [ ] A store manager welcome/setup page with a sample first page.
- [ ] One-click PDF generation on the server if browser printing becomes annoying.
- [ ] Optional item availability status: available, coming soon, limited, retired.
